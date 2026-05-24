import logging
from pathlib import Path
import asyncpg

logger = logging.getLogger(__name__)

async def init_database_schema(pool: asyncpg.Pool):
    schema_path = Path(__file__).with_name("schema.sql")
    if not schema_path.exists():
        logger.error("Database initilization failed: can not find the schema file, current path is %s", schema_path)
        return
    
    try:
        with schema_path.open("r", encoding="utf-8") as f:
            schema_sql = f.read()
        async with pool.acquire() as conn:
            await conn.execute(schema_sql)
        logger.info("Database initilization success")
    except Exception as e:
        logger.critical("Unexpected error in DDL execution: %s", str(e))
        raise e
