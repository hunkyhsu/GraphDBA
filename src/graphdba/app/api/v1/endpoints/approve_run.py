import logging
from langgraph.graph.state import CompiledStateGraph
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_202_ACCEPTED, HTTP_404_NOT_FOUND, HTTP_409_CONFLICT

from graphdba.app.core.depends import get_current_user, get_graph
from graphdba.app.schemas.request.approval import ApprovalRequest
from graphdba.app.schemas.response.approval import ApproveResponse
from graphdba.database.models.user import User
from graphdba.database.repositories import tickets
from graphdba.database.session import get_session

logger = logging.getLogger(__name__)
router = APIRouter()

async def _resume_graph(config: dict, graph: CompiledStateGraph):
    try:
        async for _ in graph.astream(None, config):
            pass
    except Exception:
        logger.exception("Graph resume failed for thread %s", config["configurable"]["thread_id"])

@router.post("/{run_id}/approve", status_code=HTTP_202_ACCEPTED, response_model=ApproveResponse)
async def approve_run(
    run_id: str, 
    body: ApprovalRequest,
    background_tasks: BackgroundTasks,
    graph: CompiledStateGraph = Depends(get_graph),  
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Inject human approval and resume the graph past the interrupt."""
    config = {"configurable": {"thread_id": run_id}}
    state = graph.get_state(config)
    if not state.values:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Run not found")
    if not state.next:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail="Run is not waiting for approval")
    try:
        await tickets.approve_ticket(
            session,
            ticket_id=state.values["ticket_id"],
            approved_by=current_user.employee_id,
            decision=body.decision,
            modified_sql=body.modified_sql,
            approval_comments=body.feedback,
        )
        await session.commit()
    except tickets.TicketNotFoundError as exc:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (tickets.TicketExecutionError, tickets.TicketStateError) as exc:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(exc)) from exc
    graph.update_state(config, {
        "approval_decision": body.decision,
        "human_feedback": body.feedback,
    })
    background_tasks.add_task(
        _resume_graph,
        graph=graph,
        config=config
    )
    return {"run_id": run_id, "status": "resuming"}
