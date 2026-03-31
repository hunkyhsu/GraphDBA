#!/bin/bash
# Start Read Probe MCP Server

set -e

# Activate virtual environment
source venv/bin/activate

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Start server
echo "Starting Read Probe MCP Server..."
python -m mcp_servers.read_probe_server
