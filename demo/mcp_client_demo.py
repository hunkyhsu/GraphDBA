import asyncio
import json
from openai import AsyncOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from config.settings import get_settings

llm = AsyncOpenAI(
    api_key=get_settings().llm.deepseek_key,
    base_url=get_settings().llm.deepseek_base_url
    )

async def main():
    print("Starting MCP Client and connecting to the Server...")
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "-m", "demo.mcp_server_demo"],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Connected to MCP Server!\n")

            mcp_tools_response = await session.list_tools()

            llm_tools = []
            for tool in mcp_tools_response.tools:
                llm_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema
                    }
                })
            
            messages = [
                {
                    "role": "system",
                    "content": "You are a DBA assistant. Use the available tools to answer the user's question."
                },
                {
                    "role": "user",
                    "content": "Can you check the test_connection table and tell me one of the status?"
                }
            ]
            print("Asking DeepSeek to evaluate the request\n")

            response = await llm.chat.completions.create(
                model = get_settings().llm.deepseek_model,
                messages=messages,
                tools=llm_tools
            )

            message = response.choices[0].message
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    print(f"->DeepSeek decided to execute: {tool_name}()")

                    tool_result = await session.call_tool(tool_name, tool_args)

                    print("\n=== Tool Execution Result ===\n")
                    print(tool_result.content[0].text)
            else:
                print("DeepSeek answered with text:", message.content)

if __name__ == "__main__":
    asyncio.run(main())