import logging
from langgraph.graph.state import CompiledStateGraph
from fastapi import APIRouter, BackgroundTasks, Depends, status

from graphdba.app.core.depends import get_graph
from graphdba.app.schemas.request.alert import AlertRequest
from graphdba.app.schemas.response.alert import AlertsStateResponse

logger = logging.getLogger(__name__)
router = APIRouter()

async def _run_graph(graph: CompiledStateGraph, initial_state: dict, config: dict):
    try:
        if graph.get_state(config=config).values:
            # same request
            logger.info("Duplicate alert ignored for thread %s", config["configurable"]["thread_id"])
            return 
        async for _ in graph.astream(initial_state, config):
            pass
    except Exception:
        logger.exception("Graph run failed for thread %s", config["configurable"]["thread_id"])

@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=AlertsStateResponse)
async def get_alerts(
    body: AlertRequest,
    background_tasks: BackgroundTasks,
    graph: CompiledStateGraph = Depends(get_graph),
):
    # logger.info("Received alert webhook from Alertmanager: %s", body.model_dump_json(indent=2))
    run_ids = []
    for alert in body.alerts:
        if alert.status != "firing":
            continue
        run_id = alert.fingerprint
        config = {"configurable": {"thread_id": run_id}}
        alert_payload = {
            "fingerprint": alert.fingerprint,
            "alertname": alert.labels.get("alertname", ""),
            "instance": alert.labels.get("instance", ""),
            "severity": alert.labels.get("severity", "info"),
            "status": alert.status,
            "summary": alert.annotations.get("summary", ""),
            "description": alert.annotations.get("description", ""),
            "startsAt": alert.startsAt,
            "raw_payload": {},
        }
        background_tasks.add_task(
            _run_graph,
            graph=graph,
            initial_state={"alert": alert_payload},
            config=config,
        )
        run_ids.append(run_id)
    return {"run_id": run_ids[0] if run_ids else "", "status": "accepted"}