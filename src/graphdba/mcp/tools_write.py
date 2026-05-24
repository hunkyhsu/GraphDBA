import uuid
import asyncpg
import json
import time
import logging
from graphdba.mcp.guard_write import WriteSecurityError, validate_sql_syntax, verify_identity

from graphdba.mcp.models import ProposeActionInput, ExecuteActionInput, UpdateTicketInput, TicketStatus


logger = logging.getLogger(__name__)


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
        logger.exception("Unexpected error in propose_tuning_action")
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

async def _execute_ticket(input_data: ExecuteActionInput, pool: asyncpg.Pool) -> tuple[str | None, str | None]:
    """Executes a previously approved ticket within a safe, rollback-capable transaction."""
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                ticket_row = await conn.fetchrow(
                    "SELECT status, approved_by, execution_steps, rollback_sql FROM change_tickets WHERE ticket_id = $1 FOR UPDATE;",
                    input_data.ticket_id
                )
                if not ticket_row:
                    return None, "Ticket not found"
                if ticket_row["status"] != TicketStatus.APPROVED:
                    return None, f"Excepted ticket status = {TicketStatus.APPROVED}. Current ticket status = {ticket_row['status']}"
                actual_approver_role = ticket_row["approved_by"]
                await conn.execute(
                    "UPDATE change_tickets SET status = 'EXECUTING' WHERE ticket_id = $1;",
                    input_data.ticket_id
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
                    input_data.ticket_id, duration_ms
                )
            logger.info("Ticket %s executed in %d ms", input_data.ticket_id, duration_ms)
            return "SUCCESS", None
        except Exception as exec_err:
            duration_ms = int(time.monotonic() * 1000) - start_ms
            error_msg = str(exec_err)
            async with pool.acquire() as conn:
                await conn.execute(
                    """UPDATE change_tickets
                       SET status = 'FAILED', error_message = $2, execution_duration_ms = $3
                       WHERE ticket_id = $1;""",
                    input_data.ticket_id, error_msg, duration_ms
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
                            input_data.ticket_id
                        )
                except Exception as rb_err:
                    logger.critical("Rollback failed for ticket %s: %s", input_data.ticket_id, str(rb_err))
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE change_tickets SET error_message = $2 WHERE ticket_id = $1;",
                            input_data.ticket_id,
                            f"Exec: {error_msg} | Rollback failed: {str(rb_err)}"
                        )
            logger.error("Ticket %s failed: %s", input_data.ticket_id, error_msg)
            return None, "Execution failed. Auto-rolled back. Details logged."

    except WriteSecurityError as e:
        return None, f"WriteSecurityError in execute ticket: {str(e)}"
    except Exception as e:
        logger.exception("Unexpected error in execute_ticket")
        return None, f"Internal server error: {type(e).__name__}"