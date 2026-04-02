"""
Feedback store for capturing DBA refinements as high-confidence knowledge.

Implements Phase 2 Task 4 requirements:
- Capture DBA refinements (modifications, approvals, rejections)
- Store as high-confidence knowledge entries in pgvector
- Enable retrieval with confidence boosting for future diagnoses
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from sentence_transformers import SentenceTransformer

from rag.pgvector_store import KnowledgeChunk, PGVectorStore, SearchResult


class FeedbackAction(str, Enum):
    """DBA feedback action types."""

    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    ROLLBACK = "rollback"


@dataclass(frozen=True)
class FeedbackEntry:
    """DBA feedback entry with context."""

    # Core identification
    feedback_id: str
    dba_name: str
    action: FeedbackAction
    timestamp: datetime

    # Diagnosis context
    symptom: str  # Original symptom/alert
    root_cause_hypothesis: str  # Agent's diagnosis
    proposed_solution: str  # Agent's proposed tuning script/action

    # DBA refinement
    dba_comment: str | None = None  # DBA's explanation
    modified_solution: str | None = None  # DBA's modified script (if action=MODIFIED)

    # Outcome tracking
    execution_success: bool | None = None  # Whether execution succeeded
    performance_impact: str | None = None  # Observed impact after execution

    # Additional metadata
    database_instance: str | None = None
    error_code: str | None = None
    tags: list[str] | None = None


class FeedbackStore:
    """Store and retrieve DBA feedback as high-confidence knowledge."""

    # Confidence boost multiplier for feedback entries in retrieval
    FEEDBACK_CONFIDENCE_BOOST = 1.5

    def __init__(
        self,
        vector_store: PGVectorStore,
        embedding_model_name: str = "all-MiniLM-L6-v2",
    ) -> None:
        """
        Initialize feedback store.

        Args:
            vector_store: PGVectorStore instance for storage
            embedding_model_name: Sentence-transformers model name
        """
        self.vector_store = vector_store
        self.embedding_model = SentenceTransformer(embedding_model_name)

    def _generate_feedback_id(self, entry: FeedbackEntry) -> str:
        """Generate deterministic feedback ID."""
        content = f"{entry.dba_name}_{entry.timestamp.isoformat()}_{entry.symptom}"
        return f"feedback_{hashlib.sha256(content.encode()).hexdigest()[:16]}"

    def _format_feedback_content(self, entry: FeedbackEntry) -> str:
        """
        Format feedback entry as semantic text for embedding.

        Creates a rich text representation that captures the full context
        of the DBA's feedback for semantic retrieval.
        """
        lines = [
            f"DBA Feedback: {entry.action.value.upper()}",
            f"Timestamp: {entry.timestamp.isoformat()}",
            f"DBA: {entry.dba_name}",
            "",
            f"Symptom: {entry.symptom}",
            f"Root Cause Hypothesis: {entry.root_cause_hypothesis}",
            f"Proposed Solution: {entry.proposed_solution}",
        ]

        if entry.dba_comment:
            lines.extend(["", f"DBA Comment: {entry.dba_comment}"])

        if entry.modified_solution:
            lines.extend(["", f"Modified Solution: {entry.modified_solution}"])

        if entry.execution_success is not None:
            status = "SUCCESS" if entry.execution_success else "FAILED"
            lines.extend(["", f"Execution Result: {status}"])

        if entry.performance_impact:
            lines.extend(["", f"Performance Impact: {entry.performance_impact}"])

        if entry.database_instance:
            lines.extend(["", f"Database Instance: {entry.database_instance}"])

        if entry.error_code:
            lines.extend(["", f"Error Code: {entry.error_code}"])

        if entry.tags:
            lines.extend(["", f"Tags: {', '.join(entry.tags)}"])

        return "\n".join(lines)

    def _create_feedback_metadata(self, entry: FeedbackEntry) -> dict[str, Any]:
        """Create metadata dict for feedback entry."""
        metadata: dict[str, Any] = {
            "doc_type": "dba_feedback",
            "is_high_confidence": True,
            "feedback_id": entry.feedback_id,
            "dba_name": entry.dba_name,
            "action": entry.action.value,
            "timestamp": entry.timestamp.isoformat(),
            "symptom": entry.symptom,
            "root_cause_hypothesis": entry.root_cause_hypothesis,
        }

        if entry.dba_comment:
            metadata["dba_comment"] = entry.dba_comment

        if entry.execution_success is not None:
            metadata["execution_success"] = entry.execution_success

        if entry.database_instance:
            metadata["database_instance"] = entry.database_instance

        if entry.error_code:
            metadata["error_code"] = entry.error_code

        if entry.tags:
            metadata["tags"] = entry.tags

        return metadata

    def store_feedback(self, entry: FeedbackEntry) -> str:
        """
        Store DBA feedback as high-confidence knowledge.

        Args:
            entry: FeedbackEntry to store

        Returns:
            Feedback ID of stored entry
        """
        content = self._format_feedback_content(entry)
        embedding = self.embedding_model.encode(
            content,
            show_progress_bar=False,
            convert_to_numpy=True,
        ).tolist()

        chunk = KnowledgeChunk(
            chunk_id=entry.feedback_id,
            source=f"dba_feedback_{entry.dba_name}",
            content=content,
            embedding=embedding,
            metadata=self._create_feedback_metadata(entry),
        )

        self.vector_store.upsert_chunks([chunk])
        return entry.feedback_id

    def retrieve_similar_feedback(
        self,
        symptom: str,
        limit: int = 5,
        action_filter: FeedbackAction | None = None,
        success_only: bool = False,
    ) -> list[SearchResult]:
        """
        Retrieve similar DBA feedback for a given symptom.

        Args:
            symptom: Symptom description to search for
            limit: Maximum number of results
            action_filter: Filter by specific feedback action
            success_only: Only return feedback with successful execution

        Returns:
            List of SearchResult with similar feedback entries
        """
        query_embedding = self.embedding_model.encode(
            symptom,
            show_progress_bar=False,
            convert_to_numpy=True,
        ).tolist()

        # Retrieve more results than needed for filtering
        raw_results = self.vector_store.semantic_search(
            query_embedding=query_embedding,
            limit=limit * 3,  # Over-fetch for filtering
        )

        # Filter for feedback entries only
        feedback_results = [
            result
            for result in raw_results
            if result.metadata.get("doc_type") == "dba_feedback"
        ]

        # Apply action filter
        if action_filter:
            feedback_results = [
                result
                for result in feedback_results
                if result.metadata.get("action") == action_filter.value
            ]

        # Apply success filter
        if success_only:
            feedback_results = [
                result
                for result in feedback_results
                if result.metadata.get("execution_success") is True
            ]

        return feedback_results[:limit]

    def boost_feedback_scores(
        self, results: list[SearchResult]
    ) -> list[SearchResult]:
        """
        Apply confidence boost to feedback entries in search results.

        Feedback entries receive a score multiplier to prioritize them
        over regular documentation in hybrid retrieval.

        Args:
            results: List of search results

        Returns:
            Results with boosted scores for feedback entries
        """
        boosted_results = []

        for result in results:
            is_feedback = result.metadata.get("doc_type") == "dba_feedback"

            if is_feedback and result.semantic_score is not None:
                # Boost semantic score
                boosted_score = min(
                    result.semantic_score * self.FEEDBACK_CONFIDENCE_BOOST, 1.0
                )
                boosted_result = SearchResult(
                    chunk_id=result.chunk_id,
                    source=result.source,
                    content=result.content,
                    metadata=result.metadata,
                    semantic_score=boosted_score,
                    lexical_score=result.lexical_score,
                    semantic_rank=result.semantic_rank,
                    lexical_rank=result.lexical_rank,
                    rrf_score=result.rrf_score,
                )
                boosted_results.append(boosted_result)
            else:
                boosted_results.append(result)

        return boosted_results






