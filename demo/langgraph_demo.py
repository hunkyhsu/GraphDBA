from typing import TypedDict, Literal
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config.settings import get_settings

# 1. Define the state
class AgentState(TypedDict):
    alert: str
    diagnosis: str
    validation_status: str
    attempt_count: int

# 2. initial the LLM
llm = ChatOpenAI(
    model = get_settings().llm.deepseek_model,
    api_key = get_settings().llm.deepseek_key,
    base_url = get_settings().llm.deepseek_base_url,
    max_tokens = 500
)

# 3. Define node 1
def diagnostic_node(state: AgentState) -> AgentState:
    attempt = state.get("attempt_count", 0) + 1
    print(f"\n --- [Diagnostic Agent] Analyzing Alert (Attempt {attempt}) ---")

    prompt = f"Database Alert: {state['alert']}\n"

    if state.get("validation_status") and "REJECTED" in state["validation_status"]:
        prompt += f"Previous attempt was rejected: {state["validation_status"]}. Provide a NEW, different diagnosis."

    messages = [
        SystemMessage(content = "You are an expert PostgreSQL DBA. Provide a brief 1-2 sentence diagnosis for the alert."),
        HumanMessage(content = prompt)
    ]

    response = llm.invoke(messages)
    print(f"Proposed Diagnosis: {response.content}")

    return {
        "diagnosis": response.content,
        "attempt_count": attempt
    }

# 4. Define node 2
def validation_node(state: AgentState) -> AgentState:
    print(f"\n --- [Validation Agent] Reviewing Diagnosis ---")

    prompt = f"Database Alert: {state['alert']}\nProposed Diagnosis: {state['diagnosis']}\n"

    messages = [
        SystemMessage(content = "You are a strict Principal PostgreSQL DBA reviewing a junior DBA's work. If the diagnosis lacks detail, just answer REJECTED. If the diagnosis is right, just answer APPROVED"),
        HumanMessage(content = prompt)
    ]

    response = llm.invoke(messages)
    status = response.content.strip()
    print(f"Validation Result: {status}")

    return {
        "validation_status": status
    }

# 5. Define the routing logic (conditional edge)
def route_validation(state: AgentState) -> Literal["diagnostic_node", "__end__"]:
    if "APPROVED" in state.get("validation_status", "").upper():
        return "__end__"
    if state.get("attempt_count", 0) >= 3:
        print("\n --- [System] Max retries reached. Escalating to human DBA. ---")
        return "__end__"
    return "diagnostic_node"

# 6. Build the Graph
builder = StateGraph(AgentState)
builder.add_node("diagnostic_node", diagnostic_node)
builder.add_node("validation_node", validation_node)

builder.add_edge(START, "diagnostic_node")
builder.add_edge("diagnostic_node", "validation_node")
builder.add_conditional_edges(
    "validation_node",
    route_validation
)

graph = builder.compile()

if __name__ == "__main__":
    print("Starting LangGraph Supervisor Demo...")

    initial_state = {
        "alert": "Sudden spike in CPU utilization to 99%. pg_stat_activity shows 50+ sessions waiting on 'transactionid' lock.",
        "diagnosis": "",
        "validation_status": "",
        "attempt_count": 0
    }

    final_state = graph.invoke(initial_state)

    print("\n=== FINAL INCIDENT REPORT ===")
    print(f"Alert: {final_state['alert']}")
    print(f"Final Diagnosis: {final_state['diagnosis']}")
    print(f"Validation Status: {final_state['validation_status']}")