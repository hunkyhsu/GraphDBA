from __future__ import annotations
import logging
from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

from graphdba.database.connection_pool import write_lifespan

mcp_write = FastMCP("Write MCP Server", lifespan=write_lifespan)

if __name__ == "__main__":
    mcp_write.run()
