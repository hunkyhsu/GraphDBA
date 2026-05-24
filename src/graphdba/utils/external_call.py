import asyncpg
from asyncio import wait_for, TimeoutError
from typing import Any, TypeVar, Coroutine, Callable
from langchain_core.exceptions import OutputParserException
from langchain_core.runnables.base import RunnableSequence
import logging

T = TypeVar("T")

async def db_readonly_fetch(
    pool: asyncpg.Pool,
    query_fn: Callable[[asyncpg.Connection], Coroutine[Any, Any, T]],
    label: str,
    logger: logging.Logger,
) -> tuple[T | None, str | None]:
    """Read-only DB fetch. Returns (result, error). error is None on success."""
    try:
        async with pool.acquire() as conn:
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                return await query_fn(conn), None
    except asyncpg.exceptions.PostgresError as e:
        logger.warning("Database error in %s: %s", label, str(e))
        return None, str(e)
    except Exception:
        logger.exception("Unexpected error in %s", label)
        return None, "Unexpected error: check server logs"

async def single_external_call(coro: Coroutine[Any, Any, T], timeout: float, label: str, logger: logging.Logger = None) -> tuple[T, str | None]:
    """Single-shot external call. Returns (result, error). error is None on success"""
    try:
        return await wait_for(coro, timeout=timeout), None
    except TimeoutError:
        logger.warning("%s timed out after %fs", label, timeout)
        return None, f"{label} timed out after {timeout}s"
    except Exception as e:
        logger.exception("Unexcepted error in %s", label)
        return None, f"{label} failed: {type(e).__name__}: {str(e)}"

async def llm_call_with_retry(
        chain: RunnableSequence[Any, T], 
        inputs: dict, 
        timeout: float, 
        max_retry: int, 
        feedback_key: str = "error_feedback",
        logger: logging.Logger = None,
    ) -> tuple[T | None, str | None]:
    """LLM call with retry + error feedback injection. Return (result, failure_reason)."""
    error_feedback = ""
    for attempt in range(max_retry):
        try:
            result = await wait_for(
                chain.ainvoke({
                    **inputs,
                    feedback_key: error_feedback
                }),
                timeout=timeout,
            )
            return result, None
        except OutputParserException as e:
            if attempt == max_retry - 1:
                return None, f"LLM output parser failed after {max_retry} retries: {str(e)}"
            logger.warning("LLM attempt %d/%d failed. Error: %s", attempt + 1, max_retry, str(e))
            error_feedback = f"Previous LLM output parser attempt failed: {str(e)}"
        except TimeoutError as e:
            if attempt == max_retry - 1:
                return None, f"LLM timed out after {max_retry} retries."
            logger.warning("LLM attempt %d/%d failed. Error: timeout")
            error_feedback = "Previous LLM attempt failed: timeout"
        except Exception as e:
            logger.exception("Unexcepted error in LLM")
            return None, f"Unexcepted LLM error{type(e).__name__}: {str(e)}"
    return None, "LLM retry loop exhausted without result"