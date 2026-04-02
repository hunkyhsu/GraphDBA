"""
Tests for feedback store (Phase 2 Task 4).

Tests DBA feedback capture, storage, and retrieval with confidence boosting.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from rag.feedback_store import FeedbackAction, FeedbackEntry, FeedbackStore
from rag.pgvector_store import SearchResult


@pytest.fixture
def mock_vector_store():
    """Mock PGVectorStore for testing."""
    store = MagicMock()
    store.upsert_chunks = MagicMock(return_value=1)
    store.semantic_search = MagicMock(return_value=[])
    return store


@pytest.fixture
def mock_embedding_model():
    """Mock SentenceTransformer for testing."""
    with patch("rag.feedback_store.SentenceTransformer") as mock:
        model = MagicMock()
        model.encode = MagicMock(
            return_value=MagicMock(tolist=lambda: [0.1] * 384)
        )
        mock.return_value = model
        yield model


@pytest.fixture
def feedback_store(mock_vector_store, mock_embedding_model):
    """Create FeedbackStore instance with mocked dependencies."""
    return FeedbackStore(
        vector_store=mock_vector_store,
        embedding_model_name="all-MiniLM-L6-v2",
    )


@pytest.fixture
def sample_feedback_entry():
    """Create a sample feedback entry for testing."""
    return FeedbackEntry(
        feedback_id="feedback_test123",
        dba_name="alice",
        action=FeedbackAction.APPROVED,
        timestamp=datetime(2026, 4, 1, 10, 30, 0, tzinfo=timezone.utc),
        symptom="High CPU usage on database server",
        root_cause_hypothesis="Missing index on frequently queried column",
        proposed_solution="CREATE INDEX idx_users_email ON users(email)",
        dba_comment="Approved - index will improve query performance",
        execution_success=True,
        performance_impact="CPU usage reduced by 40%",
        database_instance="prod-db-01",
        error_code=None,
        tags=["performance", "indexing"],
    )


class TestFeedbackEntry:
    """Test FeedbackEntry dataclass."""

    def test_feedback_entry_creation(self, sample_feedback_entry):
        """Test creating a feedback entry."""
        assert sample_feedback_entry.feedback_id == "feedback_test123"
        assert sample_feedback_entry.dba_name == "alice"
        assert sample_feedback_entry.action == FeedbackAction.APPROVED

    def test_feedback_entry_immutable(self, sample_feedback_entry):
        """Test that feedback entries are immutable."""
        with pytest.raises(AttributeError):
            sample_feedback_entry.dba_name = "bob"


class TestFeedbackStore:
    """Test FeedbackStore functionality."""

    def test_initialization(self, feedback_store, mock_vector_store):
        """Test feedback store initialization."""
        assert feedback_store.vector_store == mock_vector_store
        assert feedback_store.FEEDBACK_CONFIDENCE_BOOST == 1.5

    def test_generate_feedback_id(self, feedback_store):
        """Test feedback ID generation."""
        entry = FeedbackEntry(
            feedback_id="temp",
            dba_name="alice",
            action=FeedbackAction.APPROVED,
            timestamp=datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc),
            symptom="Test symptom",
            root_cause_hypothesis="Test hypothesis",
            proposed_solution="Test solution",
        )

        feedback_id = feedback_store._generate_feedback_id(entry)
        assert feedback_id.startswith("feedback_")
        assert len(feedback_id) == 25

    def test_format_feedback_content(self, feedback_store, sample_feedback_entry):
        """Test formatting feedback content."""
        content = feedback_store._format_feedback_content(sample_feedback_entry)

        assert "DBA Feedback: APPROVED" in content
        assert "alice" in content
        assert "High CPU usage" in content
        assert "Missing index" in content
        assert "CREATE INDEX" in content

    def test_create_feedback_metadata(self, feedback_store, sample_feedback_entry):
        """Test metadata creation for feedback entry."""
        metadata = feedback_store._create_feedback_metadata(sample_feedback_entry)

        assert metadata["doc_type"] == "dba_feedback"
        assert metadata["is_high_confidence"] is True
        assert metadata["feedback_id"] == "feedback_test123"
        assert metadata["dba_name"] == "alice"
        assert metadata["action"] == "approved"

    def test_store_feedback(
        self, feedback_store, sample_feedback_entry, mock_vector_store
    ):
        """Test storing feedback in vector store."""
        feedback_id = feedback_store.store_feedback(sample_feedback_entry)

        assert feedback_id == "feedback_test123"
        mock_vector_store.upsert_chunks.assert_called_once()

    def test_retrieve_similar_feedback(
        self, feedback_store, mock_vector_store
    ):
        """Test retrieving similar feedback entries."""
        mock_results = [
            SearchResult(
                chunk_id="feedback_1",
                source="dba_feedback_alice",
                content="Feedback content 1",
                metadata={"doc_type": "dba_feedback", "action": "approved"},
                semantic_score=0.95,
            ),
        ]
        mock_vector_store.semantic_search.return_value = mock_results

        results = feedback_store.retrieve_similar_feedback(
            symptom="High CPU usage", limit=5
        )

        assert len(results) == 1
        assert results[0].metadata["doc_type"] == "dba_feedback"

    def test_boost_feedback_scores(self, feedback_store):
        """Test confidence boosting for feedback entries."""
        results = [
            SearchResult(
                chunk_id="feedback_1",
                source="dba_feedback_alice",
                content="Feedback content",
                metadata={"doc_type": "dba_feedback"},
                semantic_score=0.80,
            ),
        ]

        boosted = feedback_store.boost_feedback_scores(results)
        assert boosted[0].semantic_score == pytest.approx(0.80 * 1.5)


