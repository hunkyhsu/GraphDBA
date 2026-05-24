import sys
import psycopg2
from mcp.server.fastmcp import FastMCP
from config.settings import get_settings

mcp = FastMCP("postgres_mcp_tool")

@mcp.tool()
def read_table() -> str:
    """ONLY use this tool to verify basic database connectivity. 
    It does NOT return performance metrics, locks, or query statuses. 
    It only returns a static success string."""
    try:
        settings = get_settings().database
        connection = psycopg2.connect(
            host=settings.host,
            port=settings.port,
            dbname=settings.db,
            user=settings.user,
            password=settings.password
        )
        cursor = connection.cursor()
        query = f"SELECT * FROM test_connection LIMIT 1;"
        cursor.execute(query)
        results = cursor.fetchone()

        cursor.close()
        connection.close()

        if not results:
            return "Table is empty or missing"
        return str(results)
    except Exception as e:
        return f"Tool execution failed: {str(e)}"

@mcp.tool()
def check_active_locks() -> str:
    """Checking PostgreSQL for active locks and returns the blocking and blocked PIDs and queries """
    try:
        settings = get_settings().database
        connection = psycopg2.connect(
            host=settings.host,
            port=settings.port,
            dbname=settings.db,
            user=settings.user,
            password=settings.password
        )
        cursor = connection.cursor()
        query = """
            SELECT blocked_locks.pid AS blocked_pid,
                   blocking_locks.pid AS blocking_pid,
                   blocked_activity.query AS blocked_query,
                   blocking_activity.query AS blocking_query
            FROM pg_catalog.pg_locks blocked_locks
            JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
            JOIN pg_catalog.pg_locks blocking_locks 
                ON blocking_locks.transactionid = blocked_locks.transactionid
                AND blocking_locks.pid != blocked_locks.pid
            JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
            WHERE NOT blocked_locks.granted;
        """
        cursor.execute(query)
        results = cursor.fetchall()

        cursor.close()
        connection.close()

        if not results:
            return "No active locks found"
        output = "Active locks Detected:\n"
        for result in results:
            output += f"-> PID {result[1]} (Blocking Query: '{result[3]}') is BLOCKING PID {result[0]} (Waiting Query: '{result[2]}')\n"
        return output
    except Exception as e:
        return f"Tool execution failed: {str(e)}"

def main():
    print("Starting MCP server...", file=sys.stderr, flush=True)
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()