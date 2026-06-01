import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.database.models.change_ticket import ChangeTicket, TicketStatus


class TicketNotFoundError(Exception):
    """Raised when a change ticket cannot be found."""


class TicketStateError(Exception):
    """Raised when a ticket is not in the required lifecycle state."""


class TicketExecutionError(Exception):
    """Raised when ticket execution fails."""


def _validate_single_statement(sql: str) -> None:
    if not sql or not sql.strip():
        raise TicketExecutionError("SQL cannot be empty")
    if sql.strip().rstrip(";").count(";") > 0:
        raise TicketExecutionError("Multiple SQL statements are not supported")


async def create_ticket_from_plan(
    session: AsyncSession,
    *,
    alert_id: UUID | str,
    target_hypothesis_id: str,
    proposed_steps: list[dict],
    change_reason: str,
    rollback_sql: str | None,
    rollback_note: str | None,
    risk_level: str,
) -> ChangeTicket:
    for step in proposed_steps:
        _validate_single_statement(step["action_sql"])
    if rollback_sql:
        _validate_single_statement(rollback_sql)

    ticket = ChangeTicket(
        ticket_id=uuid4(),
        alert_id=UUID(str(alert_id)),
        target_hypothesis_id=target_hypothesis_id,
        proposed_steps=proposed_steps,
        change_reason=change_reason,
        rollback_sql=rollback_sql,
        rollback_note=rollback_note,
        risk_level=risk_level,
        status=TicketStatus.PENDING.value,
    )
    session.add(ticket)
    await session.flush()
    return ticket


async def approve_ticket(
    session: AsyncSession,
    *,
    ticket_id: UUID | str,
    approved_by: str,
    decision: str,
    modified_sql: str | None = None,
    approval_comments: str | None = None,
) -> ChangeTicket:
    ticket = await session.get(ChangeTicket, UUID(str(ticket_id)))
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")
    if ticket.status != TicketStatus.PENDING.value:
        raise TicketStateError(f"Expected ticket status PENDING. Current status is {ticket.status}")

    if decision == "rejected":
        ticket.status = TicketStatus.REJECTED.value
        ticket.approved_by = approved_by
        ticket.approved_at = datetime.now(timezone.utc)
        ticket.approval_comments = approval_comments
        await session.flush()
        return ticket

    approved_steps = ticket.proposed_steps
    if modified_sql:
        _validate_single_statement(modified_sql)
        approved_steps = [{"step_order": 1, "action_sql": modified_sql}]

    ticket.status = TicketStatus.APPROVED.value
    ticket.approved_by = approved_by
    ticket.approved_at = datetime.now(timezone.utc)
    ticket.approval_comments = approval_comments
    ticket.approved_steps = approved_steps
    await session.flush()
    return ticket


async def execute_ticket(session: AsyncSession, ticket_id: UUID | str) -> str:
    ticket = await session.get(ChangeTicket, UUID(str(ticket_id)))
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")
    if ticket.status != TicketStatus.APPROVED.value:
        raise TicketStateError(f"Expected ticket status APPROVED. Current status is {ticket.status}")

    steps = ticket.approved_steps or ticket.proposed_steps
    for step in steps:
        _validate_single_statement(step["action_sql"])

    ticket.status = TicketStatus.EXECUTING.value
    await session.commit()

    start_ms = int(time.monotonic() * 1000)
    try:
        for step in sorted(steps, key=lambda item: item.get("step_order", 0)):
            await session.execute(text(step["action_sql"]))
        ticket.status = TicketStatus.SUCCESS.value
        ticket.executed_at = datetime.now(timezone.utc)
        ticket.execution_duration_ms = int(time.monotonic() * 1000) - start_ms
        await session.commit()
        return TicketStatus.SUCCESS.value
    except Exception as exc:
        await session.rollback()
        ticket = await session.get(ChangeTicket, UUID(str(ticket_id)))
        if ticket is None:
            raise TicketNotFoundError("Ticket not found") from exc
        ticket.status = TicketStatus.FAILED.value
        ticket.error_message = str(exc)
        ticket.execution_duration_ms = int(time.monotonic() * 1000) - start_ms
        await session.commit()

        if ticket.rollback_sql:
            try:
                _validate_single_statement(ticket.rollback_sql)
                await session.execute(text(ticket.rollback_sql))
                ticket.status = TicketStatus.ROLLED_BACK.value
                ticket.rolled_back_at = datetime.now(timezone.utc)
                await session.commit()
            except Exception as rollback_exc:
                await session.rollback()
                ticket = await session.get(ChangeTicket, UUID(str(ticket_id)))
                if ticket is not None:
                    ticket.error_message = f"Exec: {exc} | Rollback failed: {rollback_exc}"
                    await session.commit()
        raise TicketExecutionError("Execution failed. Auto-rollback attempted. Details logged.") from exc
