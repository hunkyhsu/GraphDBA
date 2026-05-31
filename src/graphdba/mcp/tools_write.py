import uuid
import asyncpg
import json
import time
import logging
from datetime import datetime

from graphdba.mcp.guard_write import WriteSecurityError, validate_sql_syntax, verify_identity
from graphdba.mcp.models import (
    CreateAlertInput, UpdateAlertStatusInput, AlertStatus, AlertResponse,
    ProposeActionInput, ExecuteActionInput, UpdateTicketInput, TicketStatus
)

logger = logging.getLogger(__name__)

class AlertConflictError(Exception): 
    """Alert exist""" 
    pass
class AlertNotFoundError(Exception):
    """Alert id not found"""
    pass
class DBOperationError(Exception):
    """Uniform DB error"""
    pass

async def _insert_alert(input_data: CreateAlertInput, pool: asyncpg.Pool) -> AlertResponse:
    """Insert an alert row and return the stored alert."""
    alert_id = uuid.uuid4()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO alerts (
                    alert_id,fingerprint,alertname,severity,
                    instance,alert_summary,description,raw_payload,started_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, '{}'::jsonb, $8)
                RETURNING *;
                """,
                alert_id,
                input_data.fingerprint,
                input_data.alertname,
                input_data.severity,
                input_data.instance,
                input_data.alert_summary,
                input_data.description,
                # json.dumps(input_data.raw_payload),
                input_data.started_at,
            )
        logger.info("Alert %s created for fingerprint %s", alert_id, input_data.fingerprint)
        return AlertResponse.model_validate(dict(row))
    except asyncpg.UniqueViolationError as e:
        raise AlertConflictError(f"Alert already exists for fingerprint: {input_data.fingerprint}") from e
    except Exception as e:
        raise DBOperationError("Internal database error") from e

async def _update_alert(input_data: UpdateAlertStatusInput, pool: asyncpg.Pool) -> AlertResponse:
    """Update alert workflow status and return the updated alert."""
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE alerts
                SET status = $2,
                    escalation_reason = COALESCE($3, escalation_reason),
                    solved_at = COALESCE($4, solved_at),
                    resolved_at = COALESCE($5, resolved_at),
                    failure_reason = CASE
                        WHEN $6 = TRUE THEN NULL
                        ELSE COALESCE($7, failure_reason)
                    END,
                    updated_at = now()
                WHERE alert_id = $1
                AND status NOT IN ('SOLVED', 'RESOLVED', 'ESCALATED', 'FAILED')
                RETURNING *;
                """,
                input_data.alert_id,
                input_data.status,
                input_data.escalation_reason,
                input_data.solved_at,
                input_data.resolved_at,
                input_data.clear_failure_reason,
                input_data.failure_reason,
            )
        if row is None:
            existing_row = await conn.fetchrow(
                "SELECT * FROM alerts WHERE alert_id = $1;",
                input_data.alert_id
            )
            if existing_row is None:
                raise AlertNotFoundError(f"Alert ID [{input_data.alert_id}] not found")
            logger.info("Alert %s is already in a terminal state %s. Return for idempotency", input_data.alert_id, existing_row["status"])
            return AlertResponse.model_validate(dict(existing_row))
        logger.info("Alert %s updated to status %s", row["alert_id"], input_data.status)
        return AlertResponse.model_validate(dict(row))
    except AlertNotFoundError:
        raise
    except Exception as e:
        raise DBOperationError("Internal database error") from e


async def _propose_ticket(input_data: ProposeActionInput, pool: asyncpg.Pool) -> tuple[str | None, str | None]:
    """Stages a tuning action for DBA approval. Does NOT execute the SQL.
    Return (ticket id, error message)
    """
    try:
        for step in input_data.agent_steps:
            await validate_sql_syntax(pool, step["action_sql"])
        logger.info("Executing proposal...")
        ticket_id = str(uuid.uuid4())
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO change_tickets
                (ticket_id, alert_fingerprint, alert_payload, hypotheses, hypotheses_id,
                 agent_steps, change_reason, rollback_sql, risk_level, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10);""",
                ticket_id,
                input_data.alert_fingerprint,
                json.dumps(input_data.alert_payload),
                json.dumps(input_data.hypotheses),
                input_data.hypotheses_id,
                json.dumps(input_data.agent_steps),
                input_data.change_reason,
                input_data.rollback_sql,
                input_data.risk_level,
                TicketStatus.PENDING,
            )
        logger.info("Ticket %s staged by agent", ticket_id)
        return ticket_id, None
    except WriteSecurityError as e:
        return None, f"WriteSecurityError when proposing ticket: {str(e)}"
    except Exception as e:
        logger.exception("Unexpected error in propose_ticket")
        return None, f"Internal server error: {type(e).__name__}"

async def _approve_ticket(input_data: UpdateTicketInput, pool: asyncpg.Pool) -> tuple[str | None, str | None]:
    """Records DBA approval for a staged ticket, transitioning it to APPROVED. Return (ticketId, OAuth token, error message)"""
    try:
        identity = verify_identity(input_data.oauth_token)
        logger.info("Updating ticket status...")
        async with pool.acquire() as conn:
            async with conn.transaction():
                ticket_row = await conn.fetchrow(
                    "SELECT status FROM change_tickets WHERE ticket_id = $1 FOR UPDATE;",
                    input_data.ticket_id
                )
                if not ticket_row:
                    return None, "Ticket not found"
                if ticket_row["status"] != TicketStatus.PENDING:
                    return None, f"Excepted ticket status = PENDING. Current ticket status = {ticket_row['status']}"
                
                execution_steps = None if not input_data.modified_sql else input_data.modified_sql
                await conn.execute(
                    """UPDATE change_tickets
                       SET status = $4, approved_by = $2, approved_at = now(), approval_comments = $3, execution_steps = $5
                       WHERE ticket_id = $1;""",
                    input_data.ticket_id,
                    identity["pg_role"],
                    input_data.approval_comments,
                    input_data.ticket_status,
                    execution_steps,
                )
        logger.info("Ticket %s %s by %s", input_data.ticket_id, input_data.ticket_status, identity["pg_role"])
        return input_data.ticket_id, None
    except WriteSecurityError as e:
        return None, f"WriteSecurityError in approve ticket: {str(e)}"
    except Exception as e:
        logger.exception("Unexpected error in approve_ticket")
        return None, f"Internal server error: {type(e).__name__}"

async def _execute_ticket(ticket_id: str, pool: asyncpg.Pool) -> tuple[str | None, str | None]:
    """Executes a previously approved ticket within a safe, rollback-capable transaction."""
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                ticket_row = await conn.fetchrow(
                    "SELECT status, approved_by, execution_steps, rollback_sql FROM change_tickets WHERE ticket_id = $1 FOR UPDATE;",
                    ticket_id
                )
                if not ticket_row:
                    return None, "Ticket not found"
                if ticket_row["status"] != TicketStatus.APPROVED:
                    return None, f"Excepted ticket status = {TicketStatus.APPROVED}. Current ticket status = {ticket_row['status']}"
                actual_approver_role = ticket_row["approved_by"]
                await conn.execute(
                    "UPDATE change_tickets SET status = 'EXECUTING' WHERE ticket_id = $1;",
                    ticket_id
                )

        execution_steps = ticket_row["execution_steps"]
        if isinstance(execution_steps, str):
            execution_steps = json.loads(execution_steps)

        start_ms = int(time.monotonic() * 1000)
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(f"SET LOCAL ROLE {actual_approver_role};")
                    for step in sorted(execution_steps, key=lambda x: x.get("step_order", 0)):
                        await conn.execute(step["action_sql"])

            duration_ms = int(time.monotonic() * 1000) - start_ms
            async with pool.acquire() as conn:
                await conn.execute(
                    """UPDATE change_tickets
                       SET status = 'SUCCESS', executed_at = now(), execution_duration_ms = $2
                       WHERE ticket_id = $1;""",
                    ticket_id, duration_ms
                )
            logger.info("Ticket %s executed in %d ms", ticket_id, duration_ms)
            return "SUCCESS", None
        except Exception as exec_err:
            duration_ms = int(time.monotonic() * 1000) - start_ms
            error_msg = str(exec_err)
            async with pool.acquire() as conn:
                await conn.execute(
                    """UPDATE change_tickets
                       SET status = 'FAILED', error_message = $2, execution_duration_ms = $3
                       WHERE ticket_id = $1;""",
                    ticket_id, error_msg, duration_ms
                )
            rollback_sql = ticket_row["rollback_sql"]
            if rollback_sql:
                try:
                    async with pool.acquire() as conn:
                        async with conn.transaction():
                            await conn.execute(rollback_sql)
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE change_tickets SET status = 'ROLLED_BACK', rollbacked_at = now() WHERE ticket_id = $1;",
                            ticket_id
                        )
                except Exception as rb_err:
                    logger.critical("Rollback failed for ticket %s: %s", ticket_id, str(rb_err))
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE change_tickets SET error_message = $2 WHERE ticket_id = $1;",
                            ticket_id,
                            f"Exec: {error_msg} | Rollback failed: {str(rb_err)}"
                        )
            logger.error("Ticket %s failed: %s", ticket_id, error_msg)
            return None, "Execution failed. Auto-rolled back. Details logged."

    except WriteSecurityError as e:
        return None, f"WriteSecurityError in execute ticket: {str(e)}"
    except Exception as e:
        logger.exception("Unexpected error in execute_ticket")
        return None, f"Internal server error: {type(e).__name__}"
