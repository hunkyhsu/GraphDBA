import asyncio
from email import message
from typing import Literal
from urllib import response
from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from config.settings import get_settings

class DBAAgent:
    """Encapsulates the LangGraph orchestrator and its MCP dependencies."""
    def __init__(self):
        self.orchestrator_llm = ChatOpenAI(
            model = get_settings().llm.deepseek_model,
            api_key = get_settings().llm.deepseek_key,
            base_url = get_settings().llm.deepseek_base_url,
            max_tokens = 1000,
            extra_body={"thinking": {"type": "disabled"}}
        )
        self.diagnostician_llm = ChatOpenAI(
            model = get_settings().llm.deepseek_model,
            api_key = get_settings().llm.deepseek_key,
            base_url = get_settings().llm.deepseek_base_url,
            max_tokens = 2000
        )
        self.session: ClientSession | None = None
        self.agent_brain = None
        self.graph = self._build_graph()
    
    async def orchestrator_node(self, state: MessagesState):
        """Analyzes the current state and decides the next action."""
        print("-> [Orchestrator Agent] Thinking...")
        response = await self.agent_brain.ainvoke(state["messages"])
        return {"messages": [response]}

    async def execution_node(self, state: MessagesState):
        """Physically executes the tool requested by the reasoning node."""
        last_message = state["messages"][-1]
        tool_results = []

        for tool_call in last_message.tool_calls:
            print(f"-> [Execution Node] Executing Tool: {tool_call['name']}...")
            result = await self.session.call_tool(
                tool_call["name"],
                tool_call.get("args", {})
            )
            tool_results.append(
                ToolMessage(
                    content=result.content[0].text,
                    tool_call_id=tool_call["id"]
                )
            )
        return {"messages": tool_results}
    
    async def diagnostician_node(self, state: MessagesState):
        print(f"-> [Diagnostician Node] Diagnosising...")
        system_instruction = SystemMessage(
            content="""
            You are a Principal PostgreSQL DBA. 
            Review the data gathered by the orchestrator. 
            Provide a deep, multi-paragraph root cause analysis and mitigation plan. 
            Do not guess; 
            Rely purely on the tool outputs in the chat history.
            """
        )
        messages = [system_instruction] + state["messages"]
        response = await self.diagnostician_llm.ainvoke(messages)
        return {"messages": [response]}
    
    def route_orchestrator(self, state: MessagesState) -> Literal["execution_node", "diagnostician_node"]:
        """Determines if the graph should execute a tool or finish."""
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "execution_node"
        print("-> [Routing] Facts gathered. Handing off to diagnostician node...")
        return "diagnostician_node"

    def _build_graph(self):
        """Assembles the LangGraph topology"""
        builder = StateGraph(MessagesState)
        builder.add_node("orchestrator_node", self.orchestrator_node)
        builder.add_node("execution_node", self.execution_node)
        builder.add_node("diagnostician_node", self.diagnostician_node)

        builder.add_edge(START, "orchestrator_node")
        builder.add_conditional_edges("orchestrator_node", self.route_orchestrator)
        builder.add_edge("execution_node", "orchestrator_node")
        builder.add_edge("diagnostician_node", END)

        return builder.compile()
    
    async def  execute_investigation(self, alert_text: str):
        """Manages the lifecycle of the MCP server and runs the graph."""
        print("Booting Integraded DBA Agent...\n")
        server_params = StdioServerParameters(
            command="uv",
            args=["run", "-m", "demo.mcp_server_demo"],
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self.session = session

                mcp_tools = await session.list_tools()
                llm_tools = [{
                    "type":"function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.inputSchema
                    }
                } for t in mcp_tools.tools]

                self.agent_brain = self.orchestrator_llm.bind_tools(llm_tools)

                system_prompt = SystemMessage(
                    content="""
                    You are a fast data-gathering router. 
                    Use tools to find facts about the alert. 
                    CRITICAL: Once you have successfully retrieved the core metrics, 
                    DO NOT call any more tools and DO NOT provide a diagnosis. 
                    Simply output 'I have gathered the facts' and stop.
                    """
                )
                alert_message = HumanMessage(content=f"ALERT: {alert_text}")

                print(f"Incoming Alert: {alert_text}\n")

                final_state = await self.graph.ainvoke(
                    {"messages": [system_prompt, alert_message]},
                    config={"recursion_limit": 10}
                )
                print("\n=== FINAL DIAGNOSTIC REPORT ===")
                print(final_state["messages"][-1].content)

if __name__ == "__main__":
    agent = DBAAgent()
    test_alert = "The application team says queries are freezing and timing out. Please investigate the table test_connection."
    asyncio.run(agent.execute_investigation(test_alert))
