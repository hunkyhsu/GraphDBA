"""
PostgreSQL-backed pgvector store for GraphDBA knowledge retrieval.

Implements the Phase 2 Task 1 requirements:
- enable the pgvector extension
- create the knowledge_chunks table with vector and lexical indexes
- store chunk embeddings
- support semantic, lexical, and hybrid retrieval with RRF
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json, RealDictCursor

from config.settings import get_settings


@dataclass(frozen=True)
class KnowledgeChunk:
    """Knowledge chunk with embedding payload."""

    chunk_id: str
    source: str
    content: str
    embedding: list[float]
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class SearchResult:
    """Normalized search result returned by the store."""

    chunk_id: str
    source: str
    content: str
    metadata: dict[str, Any]
    semantic_score: float | None = None
    lexical_score: float | None = None
    semantic_rank: int | None = None
    lexical_rank: int | None = None
    rrf_score: float | None = None


class PGVectorStore:
    """pgvector knowledge store with semantic, lexical, and hybrid retrieval."""

    def __init__(
        self,
        embedding_dimensions: int,
        table_name: str = "knowledge_chunks",
        schema_name: str = "public",
        rrf_k: int = 60,
        connection_params: dict[str, Any] | None = None,
    ) -> None:
        if embedding_dimensions <= 0:
            raise ValueError("embedding_dimensions must be greater than zero")

        self.embedding_dimensions = embedding_dimensions
        self.table_name = table_name
        self.schema_name = schema_name
        self.rrf_k = rrf_k

        if connection_params is None:
            settings = get_settings()
            connection_params = settings.vector_database.connection_params
        self.connection_params = connection_params

        self._sanitized_table_name = re.sub(r"[^a-zA-Z0-9_]", "_", table_name)

    def _connect(self):
        """Open a new psycopg2 connection."""
        return psycopg2.connect(**self.connection_params)

    def _qualified_table(self) -> sql.Composed:
        """Build a safe schema-qualified table identifier."""
        return sql.SQL("{}.{}").format(
            sql.Identifier(self.schema_name),
            sql.Identifier(self.table_name),
        )

    def _embedding_literal(self, embedding: list[float]) -> str:
        """Convert an embedding list into a pgvector literal string."""
        if len(embedding) != self.embedding_dimensions:
            raise ValueError(
                f"Expected embedding with dimension {self.embedding_dimensions}, "
                f"got {len(embedding)}"
            )

        values = ",".join(f"{float(value):.12g}" for value in embedding)
        return f"[{values}]"

    def ensure_schema(self) -> None:
        """Create pgvector extension, storage table, and indexes."""
        vector_index_name = f"{self._sanitized_table_name}_embedding_idx"
        lexical_index_name = f"{self._sanitized_table_name}_content_tsv_idx"
        dimension_sql = sql.SQL(str(self.embedding_dimensions))

        with self._connect() as conn:
            conn.autocommit = True
            with conn.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute(
                    sql.SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {} (
                            chunk_id TEXT PRIMARY KEY,
                            source TEXT NOT NULL,
                            content TEXT NOT NULL,
                            metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            embedding vector({}) NOT NULL,
                            content_tsv tsvector GENERATED ALWAYS AS (
                                to_tsvector('english', coalesce(content, ''))
                            ) STORED,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    ).format(self._qualified_table(), dimension_sql)
                )
                cursor.execute(
                    sql.SQL(
                        "CREATE INDEX IF NOT EXISTS {} ON {} "
                        "USING GIN (content_tsv)"
                    ).format(
                        sql.Identifier(lexical_index_name),
                        self._qualified_table(),
                    )
                )
                cursor.execute(
                    sql.SQL(
                        "CREATE INDEX IF NOT EXISTS {} ON {} "
                        "USING ivfflat (embedding vector_cosine_ops) "
                        "WITH (lists = 100)"
                    ).format(
                        sql.Identifier(vector_index_name),
                        self._qualified_table(),
                    )
                )

    def drop_table(self) -> None:
        """Drop the configured knowledge table."""
        with self._connect() as conn:
            conn.autocommit = True
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP TABLE IF EXISTS {}").format(
                        self._qualified_table()
                    )
                )

    def upsert_chunks(self, chunks: Iterable[KnowledgeChunk]) -> int:
        """Insert or update chunks and their embeddings."""
        chunk_list = list(chunks)
        if not chunk_list:
            return 0

        insert_sql = sql.SQL(
            """
            INSERT INTO {} (
                chunk_id,
                source,
                content,
                metadata,
                embedding,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s::vector, NOW())
            ON CONFLICT (chunk_id) DO UPDATE SET
                source = EXCLUDED.source,
                content = EXCLUDED.content,
                metadata = EXCLUDED.metadata,
                embedding = EXCLUDED.embedding,
                updated_at = NOW()
            """
        ).format(self._qualified_table())

        rows: list[tuple[Any, ...]] = []
        for chunk in chunk_list:
            rows.append(
                (
                    chunk.chunk_id,
                    chunk.source,
                    chunk.content,
                    Json(chunk.metadata or {}),
                    self._embedding_literal(chunk.embedding),
                )
            )

        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(insert_sql, rows)
            conn.commit()

        return len(chunk_list)

    def count_chunks(self) -> int:
        """Return the number of stored chunks."""
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}").format(self._qualified_table())
                )
                return int(cursor.fetchone()[0])

    def semantic_search(
        self,
        query_embedding: list[float],
        limit: int = 5,
    ) -> list[SearchResult]:
        """Search by cosine similarity over pgvector embeddings."""
        vector_literal = self._embedding_literal(query_embedding)

        query_sql = sql.SQL(
            """
            SELECT
                chunk_id,
                source,
                content,
                metadata,
                1 - (embedding <=> %s::vector) AS semantic_score
            FROM {}
            ORDER BY embedding <=> %s::vector, chunk_id ASC
            LIMIT %s
            """
        ).format(self._qualified_table())

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query_sql, (vector_literal, vector_literal, limit))
                rows = cursor.fetchall()

        return [
            SearchResult(
                chunk_id=row["chunk_id"],
                source=row["source"],
                content=row["content"],
                metadata=row["metadata"] or {},
                semantic_score=float(row["semantic_score"]),
                semantic_rank=index,
            )
            for index, row in enumerate(rows, start=1)
        ]

    def lexical_search(
        self,
        query_text: str,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Search by PostgreSQL full-text ranking."""
        if not query_text.strip():
            return []

        query_sql = sql.SQL(
            """
            SELECT
                chunk_id,
                source,
                content,
                metadata,
                ts_rank_cd(
                    content_tsv,
                    websearch_to_tsquery('english', %s)
                ) AS lexical_score
            FROM {}
            WHERE content_tsv @@ websearch_to_tsquery('english', %s)
            ORDER BY lexical_score DESC, chunk_id ASC
            LIMIT %s
            """
        ).format(self._qualified_table())

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query_sql, (query_text, query_text, limit))
                rows = cursor.fetchall()

        return [
            SearchResult(
                chunk_id=row["chunk_id"],
                source=row["source"],
                content=row["content"],
                metadata=row["metadata"] or {},
                lexical_score=float(row["lexical_score"]),
                lexical_rank=index,
            )
            for index, row in enumerate(rows, start=1)
        ]

    def hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        limit: int = 5,
        semantic_limit: int | None = None,
        lexical_limit: int | None = None,
    ) -> list[SearchResult]:
        """Fuse semantic and lexical retrieval with Reciprocal Rank Fusion."""
        semantic_results = self.semantic_search(
            query_embedding=query_embedding,
            limit=semantic_limit or limit,
        )
        lexical_results = self.lexical_search(
            query_text=query_text,
            limit=lexical_limit or limit,
        )
        return self.reciprocal_rank_fusion(
            semantic_results=semantic_results,
            lexical_results=lexical_results,
            limit=limit,
        )

    def reciprocal_rank_fusion(
        self,
        semantic_results: list[SearchResult],
        lexical_results: list[SearchResult],
        limit: int = 5,
    ) -> list[SearchResult]:
        """Merge result lists using Reciprocal Rank Fusion."""
        fused: dict[str, dict[str, Any]] = {}

        for index, result in enumerate(semantic_results, start=1):
            entry = fused.setdefault(
                result.chunk_id,
                {
                    "chunk_id": result.chunk_id,
                    "source": result.source,
                    "content": result.content,
                    "metadata": result.metadata,
                    "semantic_score": None,
                    "lexical_score": None,
                    "semantic_rank": None,
                    "lexical_rank": None,
                    "rrf_score": 0.0,
                },
            )
            entry["semantic_score"] = result.semantic_score
            entry["semantic_rank"] = index
            entry["rrf_score"] += 1.0 / (self.rrf_k + index)

        for index, result in enumerate(lexical_results, start=1):
            entry = fused.setdefault(
                result.chunk_id,
                {
                    "chunk_id": result.chunk_id,
                    "source": result.source,
                    "content": result.content,
                    "metadata": result.metadata,
                    "semantic_score": None,
                    "lexical_score": None,
                    "semantic_rank": None,
                    "lexical_rank": None,
                    "rrf_score": 0.0,
                },
            )
            entry["lexical_score"] = result.lexical_score
            entry["lexical_rank"] = index
            entry["rrf_score"] += 1.0 / (self.rrf_k + index)

        ranked = sorted(
            fused.values(),
            key=lambda item: (
                -item["rrf_score"],
                item["semantic_rank"] or 10**9,
                item["lexical_rank"] or 10**9,
                item["chunk_id"],
            ),
        )

        return [
            SearchResult(
                chunk_id=item["chunk_id"],
                source=item["source"],
                content=item["content"],
                metadata=item["metadata"],
                semantic_score=item["semantic_score"],
                lexical_score=item["lexical_score"],
                semantic_rank=item["semantic_rank"],
                lexical_rank=item["lexical_rank"],
                rrf_score=float(item["rrf_score"]),
            )
            for item in ranked[:limit]
        ]
