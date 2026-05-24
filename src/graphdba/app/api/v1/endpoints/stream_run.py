import json
import logging
from typing import AsyncGenerator, Any
from langgraph.graph.state import CompiledStateGraph
from fastapi.responses import StreamingResponse
from fastapi import APIRouter, Depends

from graphdba.app.core.depends import get_graph, get_verified_token

logger = logging.getLogger(__name__)
router = APIRouter()

def _safe_serialize(obj: Any) -> Any:
    """Recursively coerce non-JSON-serializable values to their repr."""
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(v) for v in obj]
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return repr(obj)

@router.get("/{run_id}/stream", response_class=StreamingResponse)
async def stream_run(
    run_id: str,
    graph: CompiledStateGraph = Depends(get_graph),
    _token: dict[str, Any] = Depends(get_verified_token),
):
    """SSE stream of node events for a run."""
    config = {"configurable": {"thread_id": run_id}}

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for event in graph.astream_events(None, config, version="v2"):
                payload = {
                    "event": event["event"],
                    "name": event.get("name"),
                    "data": _safe_serialize(event.get("data", {})),
                }
                yield f"data: {json.dumps(payload)}\n\n"
        except Exception:
            logger.exception("Stream run failed for run_id: %s", run_id)
            yield f"data: {json.dumps({'error': 'Internal server error during streaming'})}\n\n"

    return StreamingResponse(
        event_generator(), 
        media_type="text/event-stream", 
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )