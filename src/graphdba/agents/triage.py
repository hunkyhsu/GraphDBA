import logging
import re

from graphdba.agents.state import AgentState, AlertPayload, WorkflowStatus, AgentStateUpdate

logger = logging.getLogger(__name__)

PHYSICAL_KEYWORDS_PATTERN = re.compile(
    r"corruption|bad block|segfault|oom|out of memory|disk full|storage offline|network unreachable|pg_down",
    re.IGNORECASE
)

def triage_node(state: AgentState) -> AgentStateUpdate:
    """"""
    alert = AlertPayload.model_validate(state['alert'])
    logger.info("Received the alert: %s-%s-%s", alert.id, alert.severity, alert.name)
    # 1. Deterministic Bypass
    is_critical = alert.severity.upper() in ("CRITICAL", "FATAL")
    is_physical_error = bool(PHYSICAL_KEYWORDS_PATTERN.search(alert.description) or 
                            PHYSICAL_KEYWORDS_PATTERN.search(alert.name))
    if is_critical and is_physical_error:
        logger.error("Triage node escalation required. Reason: physical error detected")
        return {
            "workflow_status": WorkflowStatus.ESCALATED.value,
            "failed_reason": "Detect physical error, require human escalation"
        }
    # 2. Debounce & Maintenance
    is_maintenance_window = False
    if is_maintenance_window:
        logger.info(f"Ignore this alert for {alert.instance} is in maintenance.")
        return {
            "workflow_status": WorkflowStatus.COMPLETED.value,
            "failed_reason": "Maintenance window active. Ignored."
        }
    # 3. State Initialization
    logger.info("Init the state and transfer to diagnostic node.")
    return {
        "current_hypotheses": [],
        "rejected_hypotheses": [],
        "final_plan": None,
        "attempt_count": 0,
        "workflow_status": WorkflowStatus.TRIAGED.value,
        "approval_decision": None,
        "human_feedback": None,
        "failed_reason": None
    }
