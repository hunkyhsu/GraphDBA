import logging
from typing import Any
from langgraph.graph.state import CompiledStateGraph
from fastapi import APIRouter, Depends, HTTPException
from starlette.status import HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR

from graphdba.app.core.depends import get_graph, get_verified_token
from graphdba.app.schemas.response.runs import RunStateResponse

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/{run_id}", response_model=RunStateResponse)
async def get_run(
    run_id: str,
    graph: CompiledStateGraph = Depends(get_graph),
    _token: dict[str, Any] = Depends(get_verified_token),
):
    config = {"configurable": {"thread_id": run_id}}
    try:
        state = graph.get_state(config)
    except Exception as e:
        logger.warning("Failed to get graph state for run %s: %s", run_id, str(e))
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Graph error: {str(e)}")
    
    if not state.values:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Run failed or state is empty")
    return {
        "run_id": run_id,
        "values": state.values,
        "next": list(state.next)
    }