import asyncio
import logging
from langgraph.graph.state import CompiledStateGraph
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from mcp.client.session import ClientSession
from starlette.status import HTTP_202_ACCEPTED, HTTP_404_NOT_FOUND, HTTP_409_CONFLICT

from graphdba.agents.state import ApprovalDecision
from graphdba.app.core.depends import get_graph, get_mcp_write, get_raw_token
from graphdba.app.schemas.request.approval import ApprovalRequest
from graphdba.app.schemas.response.approval import ApproveResponse

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
    mcp_write: ClientSession = Depends(get_mcp_write),
    token: str = Depends(get_raw_token)  
):
    """Inject human approval and resume the graph past the interrupt."""
    config = {"configurable": {"thread_id": run_id}}
    state = graph.get_state(config)
    if not state.values:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Run not found")
    if not state.next:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail="Run is not waiting for approval")
    await mcp_write.call_tool(
        "approve_ticket",
        {
            "input_data":{
                "oauth_token": token,
                "ticket_id": state.values["ticket_id"],
                "modified_sql": body.modified_sql,
                "ticket_status": body.decision,
                "approval_comments": body.feedback,
            }
        }
    )    
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


