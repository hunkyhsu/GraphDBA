import logging
import re
from datetime import datetime, timezone

from graphdba.agents.get_alert_status import get_alert_status
from graphdba.agents.update_alert import update_alert
from graphdba.agents.state import AgentState, AlertPayload, WorkflowStatus, AgentStateUpdate

logger = logging.getLogger(__name__)

class TriageNode:
    PHYSICAL_KEYWORDS_PATTERN = re.compile(
    r"corruption|bad block|segfault|oom|out of memory|disk full|storage offline|network unreachable|pg_down",
    re.IGNORECASE
    )
    FAST_PATH_SCRIPTS = {
        "PostgreSQLConnectionsExhausted",
    }

    def __init__(self):
        pass
    
    async def __call__(self, state: AgentState) -> AgentStateUpdate:
        alert = AlertPayload.model_validate(state['alert'])
        logger.info("Received the alert: %s-%s", alert.id, alert.name)
        # 0. Crash Recovery
        current_alert_status, fail_reason = await get_alert_status(
            alert_id=alert.id,
        )
        if fail_reason:
            return {
                "workflow_status": WorkflowStatus.FAILED.value,
                "terminal_message": f"Failed to get alert status: {fail_reason}"
            }
        if current_alert_status == "SOLVED":
            return {
                "workflow_status": WorkflowStatus.COMPLETED.value,
                "terminal_message": "Recovery: Executed fast path script successfully"
            }
        if current_alert_status == "ESCALATED":
            return {
                "workflow_status": WorkflowStatus.ESCALATED.value,
                "terminal_message": f"Recovery: Detect physical error for {alert.name}, required human DBA"
            }
        if current_alert_status == "RUNNING":
            return {
                "current_hypotheses": [],
                "rejected_hypotheses": [],
                "final_plan": None,
                "attempt_count": 0,
                "workflow_status": WorkflowStatus.TRIAGED.value,
                "approval_decision": None,
                "human_feedback": None,
                "terminal_message": None
            }

        # 1. Fast-Path A
        if alert.name in self.FAST_PATH_SCRIPTS:
            logger.info("Fast path A triggered for alert %s", alert.name)
            try:
                # ....
                logger.info("Automated self-healing script executing for alert %s ...", alert.name)
                error = await update_alert(
                    alert_id=alert.id,
                    # TODO: AlertStatus.SOLVED
                    status="SOLVED",
                    solved_at=datetime.now(timezone.utc).isoformat(),
                    clear_failure_reason=True,
                )
                if error:
                    return {
                        "workflow_status": WorkflowStatus.FAILED.value,
                        "terminal_message": f"Failed to persist alert SOLVED status: {error} after executing fast path script"
                    }
                return {
                    "workflow_status": WorkflowStatus.COMPLETED.value,
                    "terminal_message": "Executed fast path script successfully"
                }
            except Exception:
                logger.exception("Automated script failed for %s. Falling back to slow path", alert.name)
        # 2. Fast-Path B
        is_physical_error = bool(
            self.PHYSICAL_KEYWORDS_PATTERN.search(alert.description) or 
            self.PHYSICAL_KEYWORDS_PATTERN.search(alert.name)
        )
        if is_physical_error:
            logger.error("Fast path B triggered for alert %s", alert.name)
            reason = f"Detected physical error for {alert.name}, required human DBA"
            error = await update_alert(
                alert_id=alert.id,
                status="ESCALATED",
                escalation_reason=reason,
                clear_failure_reason=True,
            )
            if error:
                return {
                    "workflow_status": WorkflowStatus.FAILED.value,
                    "terminal_message": f"Failed to persist alert ESCALATED status: {error}; original reason: {reason}"
                }
            return {
                "workflow_status": WorkflowStatus.ESCALATED.value,
                "terminal_message": reason
            }
        # 3. State Initialization
        logger.info("Init the state and transfer to diagnostic node.")
        error = await update_alert(
            alert_id=alert.id,
            status="RUNNING",
            clear_failure_reason=True,
        )
        if error:
            return {
                "workflow_status": WorkflowStatus.FAILED.value,
                "terminal_message": f"Failed to persist alert RUNNING status: {error}"
            }
        return {
            "current_hypotheses": [],
            "rejected_hypotheses": [],
            "final_plan": None,
            "attempt_count": 0,
            "workflow_status": WorkflowStatus.TRIAGED.value,
            "approval_decision": None,
            "human_feedback": None,
            "terminal_message": None
        }
