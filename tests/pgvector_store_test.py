"""
Integration tests for rag/pgvector_store.py

## Manual Testing

Prerequisites:
1. PostgreSQL is running locally and reachable with `psql`.
2. The target database exists and the user can create tables and extensions.
3. The PostgreSQL server has the `pgvector` extension installed.
4. Poetry dependencies are installed with `poetry install`.

Step-by-step test commands:
1. Export test connection settings:
   `export VECTOR_DB_HOST=localhost`
   `export VECTOR_DB_PORT=5432`
   `export VECTOR_DB_NAME=agent_test_db`
   `export VECTOR_DB_USER=hunkyhsu`
   `export VECTOR_DB_PASSWORD=`
2. Run the test file:
   `poetry run pytest tests/pgvector_store_test.py -v`

Expected results:
1. All tests pass.
2. The fixture creates the `vector` extension if needed.
3. The fixture creates and tears down the `test_knowledge_chunks` table automatically.
4. Semantic, lexical, and hybrid retrieval each return the expected chunk at rank 1.

Negative tests:
1. `test_rejects_wrong_embedding_dimension_on_insert` raises `ValueError`.
2. `test_rejects_wrong_query_embedding_dimension` raises `ValueError`.
3. If `pgvector` is not installed on the PostgreSQL server, schema bootstrap fails with a PostgreSQL extension error.

Cleanup:
1. The session fixture drops `public.test_knowledge_chunks`.
2. No application data is modified outside that test table.
"""

import os

import pytest
import psycopg2

os.environ.setdefault("VECTOR_DB_HOST", "localhost")
os.environ.setdefault("VECTOR_DB_PORT", "5432")
os.environ.setdefault("VECTOR_DB_NAME", "agent_vector_db")
os.environ.setdefault("VECTOR_DB_USER", "rag_agent")
os.environ.setdefault("VECTOR_DB_PASSWORD", "rag_password_123")

from config.settings import VectorDatabaseSettings
from rag.pgvector_store import KnowledgeChunk, PGVectorStore


TEST_TABLE_NAME = "test_knowledge_chunks"
TEST_DIMENSIONS = 3


def _db_params() -> dict:
    """Return vector DB connection parameters for tests."""
    return VectorDatabaseSettings().connection_params


@pytest.fixture(scope="session")
def vector_store() -> PGVectorStore:
    """Provision an isolated pgvector-backed test table."""
    store = PGVectorStore(
        embedding_dimensions=TEST_DIMENSIONS,
        table_name=TEST_TABLE_NAME,
        connection_params=_db_params(),
    )
    store.drop_table()
    store.ensure_schema()
    store.upsert_chunks(
        [
            KnowledgeChunk(
                chunk_id="cpu_spike",
                source="postgres_manual",
                content="High CPU queries often require EXPLAIN ANALYZE and index review.",
                embedding=[0.99, 0.05, 0.0],
                metadata={"topic": "cpu"},
            ),
            KnowledgeChunk(
                chunk_id="deadlock_40p01",
                source="postgres_manual",
                content="Error code 40P01 indicates a deadlock detected condition. "
                "Investigate conflicting transactions and retry the failed statement.",
                embedding=[0.02, 0.98, 0.05],
                metadata={"topic": "locks", "error_code": "40P01"},
            ),
            KnowledgeChunk(
                chunk_id="vacuum_bloat",
                source="operations_runbook",
                content="Table bloat symptoms improve after VACUUM and autovacuum tuning.",
                embedding=[0.05, 0.1, 0.99],
                metadata={"topic": "storage"},
            ),
        ]
    )

    yield store

    store.drop_table()


def _fetch_one(query: str) -> tuple:
    """Execute a direct SQL assertion against the vector DB."""
    with psycopg2.connect(**_db_params()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchone()


class TestSchemaBootstrap:
    """Verify pgvector bootstrap and table creation."""

    def test_enables_pgvector_extension(self, vector_store: PGVectorStore) -> None:
        del vector_store
        result = _fetch_one(
            "SELECT extname FROM pg_extension WHERE extname = 'vector'"
        )
        assert result == ("vector",)

    def test_creates_knowledge_chunks_table(self, vector_store: PGVectorStore) -> None:
        del vector_store
        result = _fetch_one(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'test_knowledge_chunks'
              AND column_name = 'embedding'
            """
        )
        assert result == ("embedding",)

    def test_count_chunks(self, vector_store: PGVectorStore) -> None:
        assert vector_store.count_chunks() == 3


class TestChunkUpsert:
    """Verify chunk storage and updates."""

    def test_upsert_updates_existing_chunk(self, vector_store: PGVectorStore) -> None:
        inserted = vector_store.upsert_chunks(
            [
                KnowledgeChunk(
                    chunk_id="deadlock_40p01",
                    source="postgres_manual",
                    content="Error code 40P01 is deadlock detected. Retry transactions after investigation.",
                    embedding=[0.01, 0.99, 0.05],
                    metadata={"topic": "locks", "error_code": "40P01", "updated": True},
                )
            ]
        )
        assert inserted == 1
        assert vector_store.count_chunks() == 3

        rows = vector_store.lexical_search("40P01 deadlock retry", limit=1)
        assert rows[0].metadata["updated"] is True

    def test_rejects_wrong_embedding_dimension_on_insert(
        self, vector_store: PGVectorStore
    ) -> None:
        with pytest.raises(ValueError):
            vector_store.upsert_chunks(
                [
                    KnowledgeChunk(
                        chunk_id="bad_chunk",
                        source="broken",
                        content="Invalid embedding length.",
                        embedding=[1.0, 2.0],
                    )
                ]
            )


class TestRetrieval:
    """Verify semantic, lexical, and hybrid retrieval behaviour."""

    def test_semantic_search_returns_best_match(
        self, vector_store: PGVectorStore
    ) -> None:
        results = vector_store.semantic_search([1.0, 0.0, 0.0], limit=2)
        assert results[0].chunk_id == "cpu_spike"
        assert results[0].semantic_rank == 1
        assert results[0].semantic_score is not None

    def test_lexical_search_returns_deadlock_chunk(
        self, vector_store: PGVectorStore
    ) -> None:
        results = vector_store.lexical_search("40P01 deadlock transactions", limit=2)
        assert results[0].chunk_id == "deadlock_40p01"
        assert results[0].lexical_rank == 1
        assert results[0].lexical_score is not None

    def test_hybrid_search_uses_rrf(
        self, vector_store: PGVectorStore
    ) -> None:
        results = vector_store.hybrid_search(
            query_text="40P01 deadlock retry transactions",
            query_embedding=[0.0, 1.0, 0.0],
            limit=3,
            semantic_limit=3,
            lexical_limit=3,
        )
        assert results[0].chunk_id == "deadlock_40p01"
        assert results[0].semantic_rank is not None
        assert results[0].lexical_rank is not None
        assert results[0].rrf_score is not None

    def test_rejects_wrong_query_embedding_dimension(
        self, vector_store: PGVectorStore
    ) -> None:
        with pytest.raises(ValueError):
            vector_store.semantic_search([0.1, 0.2], limit=1)
