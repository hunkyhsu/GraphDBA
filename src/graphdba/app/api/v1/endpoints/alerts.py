import logging
import json
from langgraph.graph.state import CompiledStateGraph
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from mcp.client.session import ClientSession

from graphdba.app.core.depends import get_graph, get_mcp_read, get_mcp_write
from graphdba.app.schemas.request.alert import AlertItem, AlertRequest
from graphdba.app.schemas.response.alert import AlertsStateResponse
from graphdba.utils.external_call import single_external_call

logger = logging.getLogger(__name__)
router = APIRouter()
MCP_TIMEOUT_S = 10.0

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

async def _get_active_alert_id(mcp_read: ClientSession, fingerprint: str) -> str | None:
    result, fail_reason = await single_external_call(
        coro=mcp_read.call_tool(
            "get_alert_by_fingerprint",
            {"fingerprint": fingerprint},
        ),
        timeout=MCP_TIMEOUT_S,
        label="Get Alert By Fingerprint",
        logger=logger,
    )
    if fail_reason:
        raise RuntimeError(fail_reason)
    if result.isError:
        error_text = result.content[0].text if result.content else "Unknown MCP tool error"
        raise ValueError(error_text)
    payload: dict = json.loads(result.content[0].text)
    return payload.get("alert_id") if payload else None

async def _insert_alert(mcp_write: ClientSession, alert: AlertItem) -> str:
    result, fail_reason = await single_external_call(
        coro=mcp_write.call_tool(
            "insert_alert",
            {
                "input_data": {
                    "fingerprint": alert.fingerprint,
                    "alertname": alert.labels.alertname,
                    "instance": alert.labels.instance,
                    "severity": alert.labels.severity,
                    "alert_summary": alert.annotations.summary,
                    "description": alert.annotations.description,
                    # "raw_payload": alert.model_dump(mode="json"),
                    "started_at": alert.startsAt,
                }
            },
        ),
        timeout=MCP_TIMEOUT_S,
        label="Insert Alert",
        logger=logger,
    )
    if fail_reason:
        raise RuntimeError(fail_reason)
    if result.isError:
        error_text = result.content[0].text if result.content else "Unknown MCP tool error"
        raise ValueError(error_text)
    return result.content[0].text.strip('"')

@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=AlertsStateResponse)
async def get_alerts(
    body: AlertRequest,
    background_tasks: BackgroundTasks,
    graph: CompiledStateGraph = Depends(get_graph),
    mcp_read: ClientSession = Depends(get_mcp_read),
    mcp_write: ClientSession = Depends(get_mcp_write),
):
    run_ids = []
    for alert in body.alerts:
        if alert.status != "firing":
            continue

        try:
            existing_alert_id = await _get_active_alert_id(mcp_read, alert.fingerprint)
        except RuntimeError as e:
            logger.warning("Alert debounce lookup failed for fingerprint %s: %s", alert.fingerprint, str(e))
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
        except ValueError as e:
            logger.warning("Alert debounce tool error for fingerprint %s: %s", alert.fingerprint, str(e))
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

        if existing_alert_id:
            logger.info("Duplicate active alert ignored for fingerprint %s", alert.fingerprint)
            run_ids.append(existing_alert_id)
            continue

        try:
            run_id = await _insert_alert(mcp_write, alert)
        except RuntimeError as e:
            logger.warning("Alert insert failed for fingerprint %s: %s", alert.fingerprint, str(e))
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
        except ValueError as e:
            # A concurrent request may insert the same active fingerprint between
            # the read-side debounce check and the write-side insert attempt.
            try:
                existing_alert_id = await _get_active_alert_id(mcp_read, alert.fingerprint)
            except (RuntimeError, ValueError):
                existing_alert_id = None
            if existing_alert_id:
                logger.info("Concurrent duplicate active alert ignored for fingerprint %s", alert.fingerprint)
                run_ids.append(existing_alert_id)
                continue
            logger.warning("Alert ingestion failed for fingerprint %s: %s", alert.fingerprint, str(e))
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

        config = {"configurable": {"thread_id": run_id}}
        alert_payload = {
            "id": run_id,
            "name": alert.labels.alertname,
            "instance": alert.labels.instance,
            "summary": alert.annotations.summary,
            "description": alert.annotations.description,
            # "raw_payload": {},
        }
        background_tasks.add_task(
            _run_graph,
            graph=graph,
            initial_state={"alert": alert_payload},
            config=config,
        )
        run_ids.append(run_id)
    return {
        "status": "accepted",
        "run_ids": run_ids
    }
