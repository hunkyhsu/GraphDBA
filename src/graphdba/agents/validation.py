from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from pydantic import BaseModel, Field, field_validator
from langchain_core.prompts import ChatPromptTemplate

from graphdba.agents.state import Hypothesis, HypothesisStatus, ValidationAction, WorkflowStatus
from graphdba.utils.external_call import single_external_call, llm_call_with_retry
from graphdba.database.repositories import hypotheses
from graphdba.database.session import AsyncSessionLocal

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from mcp.client.session import ClientSession
    from langchain_core.runnables.base import RunnableSequence
    from graphdba.agents.state import AgentState, AgentStateUpdate

logger = logging.getLogger(__name__)

class ValidationOutput(BaseModel):
    """Structured output"""
    reasoning: str = Field(description="Detailed explanation of the validation.")
    validation_status: HypothesisStatus = Field(description="Only verified, rejected and inconclusive are allowed.")
    @field_validator("validation_status")
    @classmethod
    def validate_status(cls, v):
        if v == HypothesisStatus.PENDING:
            raise ValueError(f"Status {v} is not allowed.")
        return v

class ValidationNode:
    LLM_TIMEOUT_S = 15.0
    MCP_TIMEOUT_S = 5.0
    MAX_RETRY = 3
    STRING_CUT = 1000

    def __init__(self, llm: BaseChatModel, mcp_client: ClientSession):
        self.mcp_client = mcp_client
        self.llm = llm
        self.structured_llm = self.llm.with_structured_output(ValidationOutput, method="function_calling")
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", 
            """
            You are an elite, objective Database Audit Referee.
            Your primary objective is to review a diagnostic hypothesis, its expected evidence, and the actual aggregated tool outputs, then deliver a definitive validation verdict based on strict database mechanics.

            ### OPERATIONAL DIRECTIVES
            1. **Rigorous Classification**: Evaluate the evidence and classify the hypothesis into exactly one of three states:
               - `verified`: The actual data explicitly and structurally confirms the hypothesis and matches the expected result.
               - `rejected`: The actual data explicitly disproves the hypothesis, contradicts the expected result, or shows the database is operating normally in this metric.
               - `inconclusive`: The data is ambiguous, incomplete, corrupted, empty, or completely unrelated to the metrics needed for validation.
            2. **Factual Deduction Only**: Do not assume, hallucinate, or extrapolate. If a metric is missing from the [ACTUAL TOOL OUTPUT], it does not exist for the sake of this audit.
            3. **Error Handling & Feedback**: 
               - If [ERROR FEEDBACK] indicates a tool execution failure, you must automatically classify the result as `inconclusive` and specify the execution failure in your reasoning.
               - If your own previous output triggered a schema error, use the feedback to self-correct your response formatting immediately.
            4. **Structured JSON Output**: You must enforce strict compliance with the requested output schema, ensuring rationales are concise, technical, and objective.
            
            Rely strictly on empirical data. Do not apply lenient or subjective interpretations to the tool outputs.
            """
            ),
            ("human", 
             """=== AUDIT TARGET ===
            Hypothesis: {root_cause}
            Confidence Score: {confidence_score}
            Expected Result: {expected}

            === ACTUAL TOOL OUTPUT ===
            Treat the following as raw execution telemetry:
            {actual}

            === ERROR FEEDBACK ===
            {error_feedback}

            Based strictly on the telemetry and classification rules above, generate your definitive audit verdict and structured rationale.
            """
            )
        ])

    async def __call__(self, state: AgentState) -> AgentStateUpdate:
        current_hypotheses: list[Hypothesis] = [Hypothesis.model_validate(h) for h in state["current_hypotheses"]]
        logger.info("Starting to validate %d hypotheses", len(current_hypotheses))
        rejected_list: list[Hypothesis] = []
        updated_current: list[Hypothesis] = []
        for hypothesis in current_hypotheses:
            logger.info("Validating the %s hypothesis (%s)", hypothesis.id, hypothesis.root_cause)
            actions: list[ValidationAction] = hypothesis.validation_actions
            aggregate_output = ""
            action_success = False
            for action in actions:
                result, fail_reason = await single_external_call(
                    coro=self.mcp_client.call_tool(
                        name=action.tool_name,
                        arguments=action.tool_payload
                    ),
                    timeout=self.MCP_TIMEOUT_S,
                    label="Read MCP Tool Call",
                    logger=logger
                )
                if fail_reason:
                    aggregate_output += f"\n[Tool: {action.tool_name}] execute failed\n [Error: {fail_reason}]"
                elif result.isError:
                    error_text = result.content[0].text if result.content else "Unknown MCP tool error"
                    aggregate_output += f"\n[Tool: {action.tool_name}] returned error\n [Error: {error_text}]"
                else:
                    aggregate_output += f"\n [Tool: {action.tool_name}]\n [Result: {result.content[0].text if result.content else ''}]"
                    action_success = True
            if not action_success:
                hypothesis.status = HypothesisStatus.INCONCLUSIVE
                hypothesis.feedback = f"Tools call all failed: {aggregate_output[:self.STRING_CUT]}"
                rejected_list.append(hypothesis)
                logger.info("The %s hypothesis is inconclusive", hypothesis.id)
                continue
            chain: RunnableSequence[dict, ValidationOutput] = self.prompt | self.structured_llm
            result, fail_reason = await llm_call_with_retry(
                chain=chain,
                inputs={
                    "root_cause": hypothesis.root_cause,
                    "confidence_score": hypothesis.confidence_score,
                    "expected": hypothesis.expected_result,
                    "actual": aggregate_output[:self.STRING_CUT],
                    "error_feedback": "",
                },
                timeout=self.LLM_TIMEOUT_S,
                max_retry=self.MAX_RETRY,
                logger=logger
            )
            if fail_reason:
                return {
                    "workflow_status": WorkflowStatus.FAILED.value,
                    "terminal_message": fail_reason
                }              
            hypothesis.status = result.validation_status
            hypothesis.feedback = f"[Actual Output]: {aggregate_output[:self.STRING_CUT]}...\n [Feedback]: {result.reasoning}"
            if hypothesis.status in [HypothesisStatus.INCONCLUSIVE, HypothesisStatus.REJECTED]:
                rejected_list.append(hypothesis)
                logger.info("Current hypothesis move to reject_hypotheses list")
            else:
                updated_current.append(hypothesis)
                logger.info("Current hypothesis is verified")                
        validation_status: WorkflowStatus = WorkflowStatus.VALIDATED_SUCCESS if len(updated_current) > 0 else WorkflowStatus.VALIDATED_FAIL
        persisted_hypotheses = [*updated_current, *rejected_list]
        try:
            async with AsyncSessionLocal() as session:
                await hypotheses.upsert_hypotheses(
                    session,
                    alert_id=state["alert"]["id"],
                    attempt_count=state.get("attempt_count", 0),
                    hypotheses=[h.model_dump(mode="json") for h in persisted_hypotheses],
                )
                await session.commit()
        except Exception as exc:
            logger.exception("Failed to persist hypotheses")
            return {
                "workflow_status": WorkflowStatus.FAILED.value,
                "terminal_message": f"Failed to persist hypotheses: {exc}",
            }
        return {
            "workflow_status": validation_status.value,
            "current_hypotheses": [h.model_dump(mode="json") for h in updated_current],
            "rejected_hypotheses": [h.model_dump(mode="json") for h in rejected_list]
        }
