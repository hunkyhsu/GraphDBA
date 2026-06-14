import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.database.models.alert import Alert
from graphdba.database.models.ticket import Ticket, TicketStatus


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


TICKET_SORT_COLUMNS = {
    "created_at": Ticket.created_at,
    "updated_at": Ticket.updated_at,
    "status": Ticket.status,
    "risk_level": Ticket.risk_level,
}


def _apply_ticket_filters(
    stmt: Select,
    *,
    search: str | None = None,
    status: str | None = None,
):
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                Alert.name.ilike(pattern),
                Alert.instance.ilike(pattern),
                Alert.summary.ilike(pattern),
                Ticket.change_reason.ilike(pattern),
            )
        )
    if status and status.lower() != "all":
        stmt = stmt.where(Ticket.status == status.upper())
    return stmt


async def get_ticket_by_id(session: AsyncSession, ticket_id: UUID | str) -> Ticket | None:
    return await session.get(Ticket, UUID(str(ticket_id)))


async def get_ticket_with_alert(
    session: AsyncSession,
    ticket_id: UUID | str,
) -> tuple[Ticket, Alert] | None:
    stmt = (
        select(Ticket, Alert)
        .join(Alert, Alert.id == Ticket.alert_id)
        .where(Ticket.id == UUID(str(ticket_id)))
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.one_or_none()
    return row if row is None else (row[0], row[1])


async def get_pending_ticket_by_alert_id(
    session: AsyncSession,
    alert_id: UUID | str,
) -> Ticket | None:
    stmt = (
        select(Ticket)
        .where(Ticket.alert_id == UUID(str(alert_id)))
        .where(Ticket.status == TicketStatus.PENDING.value)
        .order_by(Ticket.updated_at.desc(), Ticket.id.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_tickets(
    session: AsyncSession,
    *,
    search: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
) -> tuple[list[tuple[Ticket, Alert]], int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    offset = (page - 1) * page_size

    base_count = select(func.count()).select_from(Ticket).join(Alert, Alert.id == Ticket.alert_id)
    count_stmt = _apply_ticket_filters(base_count, search=search, status=status)
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    sort_column = TICKET_SORT_COLUMNS.get(sort_by, Ticket.updated_at)
    order_column = sort_column.asc() if sort_dir.lower() == "asc" else sort_column.desc()
    list_stmt = (
        _apply_ticket_filters(
            select(Ticket, Alert).join(Alert, Alert.id == Ticket.alert_id),
            search=search,
            status=status,
        )
        .order_by(order_column, Ticket.id.desc())
        .limit(page_size)
        .offset(offset)
    )
    result = await session.execute(list_stmt)
    return [(row[0], row[1]) for row in result.all()], total


async def list_recent_pending_tickets(
    session: AsyncSession,
    *,
    limit: int = 3,
) -> list[tuple[Ticket, Alert]]:
    stmt = (
        select(Ticket, Alert)
        .join(Alert, Alert.id == Ticket.alert_id)
        .where(Ticket.status == TicketStatus.PENDING.value)
        .order_by(Ticket.updated_at.desc(), Ticket.id.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


async def count_tickets_by_status(session: AsyncSession, status: str) -> int:
    result = await session.execute(select(func.count()).select_from(Ticket).where(Ticket.status == status))
    return result.scalar_one()


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
) -> Ticket:
    for step in proposed_steps:
        _validate_single_statement(step["action_sql"])
    if rollback_sql:
        _validate_single_statement(rollback_sql)

    ticket = Ticket(
        id=uuid4(),
        alert_id=UUID(str(alert_id)),
        hypothesis_id=target_hypothesis_id,
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
) -> Ticket:
    ticket = await session.get(Ticket, UUID(str(ticket_id)))
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


async def update_ticket_plan(
    session: AsyncSession,
    *,
    ticket_id: UUID | str,
    proposed_steps: list[dict],
    change_reason: str,
    rollback_sql: str | None,
    rollback_note: str | None,
    human_notes: str | None = None,
    pre_execution_notes: list[dict] | None = None,
) -> Ticket:
    ticket = await session.get(Ticket, UUID(str(ticket_id)))
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")
    if ticket.status != TicketStatus.PENDING.value:
        raise TicketStateError(f"Expected ticket status PENDING. Current status is {ticket.status}")

    for step in proposed_steps:
        _validate_single_statement(step["action_sql"])
    if rollback_sql:
        _validate_single_statement(rollback_sql)

    ticket.proposed_steps = proposed_steps
    ticket.change_reason = change_reason
    ticket.rollback_sql = rollback_sql
    ticket.rollback_note = rollback_note
    ticket.metadata_ = {
        **(ticket.metadata_ or {}),
        "draft": {
            "human_notes": human_notes,
            "pre_execution_notes": pre_execution_notes or [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    await session.flush()
    return ticket


async def execute_ticket(session: AsyncSession, ticket_id: UUID | str) -> str:
    ticket = await session.get(Ticket, UUID(str(ticket_id)))
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
        ticket = await session.get(Ticket, UUID(str(ticket_id)))
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
                ticket = await session.get(Ticket, UUID(str(ticket_id)))
                if ticket is not None:
                    ticket.error_message = f"Exec: {exc} | Rollback failed: {rollback_exc}"
                    await session.commit()
        raise TicketExecutionError("Execution failed. Auto-rollback attempted. Details logged.") from exc
