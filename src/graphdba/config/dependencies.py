from functools import lru_cache
import logging
from contextlib import asynccontextmanager
from langchain_deepseek import ChatDeepSeek
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_huggingface import HuggingFaceEmbeddings

from graphdba.config.settings import get_settings

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def get_embedding():
    embedding_name: str = get_settings().embedding.model_name
    encode_kwargs = {'normalize_embeddings': True}
    model = HuggingFaceEmbeddings(
        model_name=embedding_name,
        encode_kwargs=encode_kwargs
    )
    return model

def get_reasoning_llm() -> ChatDeepSeek:
    llm_settings = get_settings().llm
    return ChatDeepSeek(
        model = llm_settings.deepseek_model,
        api_key = llm_settings.deepseek_key,
        base_url = llm_settings.deepseek_base_url,
        max_tokens = 3000,
        temperature=0.0,
        extra_body={ "thinking": {"type": "enabled"}}
    )

def get_chat_llm() -> ChatDeepSeek:
    llm_settings = get_settings().llm
    return ChatDeepSeek(
        model = llm_settings.deepseek_model,
        api_key = llm_settings.deepseek_key,
        base_url = llm_settings.deepseek_base_url,
        max_tokens = 1000,
        temperature=0.0,
        extra_body={ "thinking": {"type": "disabled"}}
    )

@asynccontextmanager
async def get_mcp_client(is_read: bool):
    server_module = "graphdba.mcp.server_read" if is_read else "graphdba.mcp.server_write"
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "-m", server_module]
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            try:
                await session.initialize()
                logger.info("MCP server connection initialization success.")
                yield session
            except Exception as e:
                logger.exception("MCP server connection failed.")
                raise
            finally:
                logger.info("MCP server closed.")