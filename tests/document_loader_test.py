"""
Manual tests for DocumentLoader (Phase 2 Task 3).

Run with: poetry run pytest tests/document_loader_test.py -v
"""

import os
import tempfile
from pathlib import Path

import pytest

from rag.document_loader import DocumentLoader, DocumentMetadata
from rag.pgvector_store import PGVectorStore


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_text_file(temp_dir):
    """Create a sample text file with PostgreSQL content."""
    content = """
PostgreSQL Error Codes

This document describes the error codes used by PostgreSQL.

42P01 - undefined_table
This error occurs when you reference a table that does not exist.

53300 - too_many_connections
This error occurs when the maximum number of connections is reached.

42501 - insufficient_privilege
This error occurs when you don't have permission to perform an operation.
"""
    file_path = temp_dir / "pg_errors.txt"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def sample_pdf_content():
    """Sample content for PDF testing."""
    return """
PostgreSQL Performance Tuning Guide

Chapter 1: Introduction
PostgreSQL is a powerful open-source relational database system.

Chapter 2: Configuration
Key configuration parameters include shared_buffers, work_mem, and maintenance_work_mem.
"""


class TestDocumentLoader:
    """Test suite for DocumentLoader."""

    def test_initialization(self):
        """Test DocumentLoader initialization."""
        loader = DocumentLoader(
            embedding_model_name="all-MiniLM-L6-v2",
            chunk_size=500,
            chunk_overlap=100,
        )
        assert loader.embedding_dimensions == 384
        assert loader.text_splitter.chunk_size == 500
        assert loader.text_splitter.chunk_overlap == 100

    def test_generate_chunk_id(self):
        """Test chunk ID generation is deterministic."""
        loader = DocumentLoader()
        chunk_id1 = loader._generate_chunk_id("test.txt", "content", 0)
        chunk_id2 = loader._generate_chunk_id("test.txt", "content", 0)
        assert chunk_id1 == chunk_id2
        assert "test_txt" in chunk_id1

    def test_generate_embeddings(self):
        """Test embedding generation."""
        loader = DocumentLoader()
        texts = ["PostgreSQL is a database", "Error code 42P01"]
        embeddings = loader._generate_embeddings(texts)
        assert len(embeddings) == 2
        assert len(embeddings[0]) == 384
        assert all(isinstance(val, float) for val in embeddings[0])

    def test_load_text_file(self, sample_text_file):
        """Test loading a plain text file."""
        loader = DocumentLoader(chunk_size=200, chunk_overlap=50)
        chunks = loader.load_text(sample_text_file)

        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.chunk_id
            assert chunk.source == "pg_errors.txt"
            assert chunk.content
            assert len(chunk.embedding) == 384
            assert chunk.metadata["doc_type"] == "text"
            assert chunk.metadata["file_path"] == str(sample_text_file)

    def test_load_nonexistent_file(self):
        """Test loading a file that doesn't exist."""
        loader = DocumentLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_text("/nonexistent/file.txt")

    def test_extract_error_codes(self):
        """Test PostgreSQL error code extraction."""
        loader = DocumentLoader()
        text = """
        42P01 - undefined_table
        53300 - too_many_connections
        42501 - insufficient_privilege
        Some other text without error codes
        """
        error_codes = loader.extract_error_codes(text)

        assert len(error_codes) == 3
        assert error_codes["42P01"] == "undefined_table"
        assert error_codes["53300"] == "too_many_connections"
        assert error_codes["42501"] == "insufficient_privilege"

    def test_extract_error_codes_empty(self):
        """Test error code extraction with no matches."""
        loader = DocumentLoader()
        text = "This text has no error codes"
        error_codes = loader.extract_error_codes(text)
        assert len(error_codes) == 0

    def test_load_error_codes(self):
        """Test creating chunks from error code mappings."""
        loader = DocumentLoader()
        error_codes = {
            "42P01": "undefined_table",
            "53300": "too_many_connections",
        }
        chunks = loader.load_error_codes(error_codes, "test_source")

        assert len(chunks) == 2
        for chunk in chunks:
            assert chunk.source == "test_source"
            assert "PostgreSQL Error Code" in chunk.content
            assert chunk.metadata["doc_type"] == "error_code"
            assert chunk.metadata["error_code"] in ["42P01", "53300"]
            assert len(chunk.embedding) == 384

    def test_load_error_codes_empty(self):
        """Test loading empty error codes."""
        loader = DocumentLoader()
        chunks = loader.load_error_codes({})
        assert len(chunks) == 0

    def test_unsupported_file_type(self, temp_dir):
        """Test loading unsupported file type."""
        loader = DocumentLoader()
        unsupported_file = temp_dir / "test.xlsx"
        unsupported_file.write_text("dummy")

        # Create a mock vector store
        from unittest.mock import Mock
        vector_store = Mock(spec=PGVectorStore)

        with pytest.raises(ValueError, match="Unsupported file type"):
            loader.load_and_store(unsupported_file, vector_store)


class TestDocumentLoaderIntegration:
    """Integration tests requiring database connection."""

    @pytest.fixture
    def vector_store(self):
        """Create a test vector store."""
        # Use test database credentials
        connection_params = {
            "host": os.getenv("VECTOR_DB_HOST", "localhost"),
            "port": int(os.getenv("VECTOR_DB_PORT", "5432")),
            "database": os.getenv("VECTOR_DB_NAME", "agent_vector_db"),
            "user": os.getenv("VECTOR_DB_USER", "rag_agent"),
            "password": os.getenv("VECTOR_DB_PASSWORD", "rag_password_123"),
        }

        store = PGVectorStore(
            embedding_dimensions=384,
            table_name="test_knowledge_chunks",
            connection_params=connection_params,
        )

        try:
            store.ensure_schema()
            yield store
        finally:
            store.drop_table()

    def test_load_and_store_text(self, sample_text_file, vector_store):
        """Test loading and storing a text file."""
        loader = DocumentLoader()
        count = loader.load_and_store(sample_text_file, vector_store)

        assert count > 0
        assert vector_store.count_chunks() == count

    def test_load_and_store_with_error_extraction(self, sample_text_file, vector_store):
        """Test loading with error code extraction."""
        loader = DocumentLoader()
        count = loader.load_and_store(
            sample_text_file, vector_store, extract_errors=True
        )

        # Should have both document chunks and error code chunks
        assert count > 3  # At least 3 error codes extracted
        total_chunks = vector_store.count_chunks()
        assert total_chunks == count

    def test_semantic_search_after_load(self, sample_text_file, vector_store):
        """Test semantic search after loading documents."""
        loader = DocumentLoader()
        loader.load_and_store(sample_text_file, vector_store, extract_errors=True)

        # Search for error-related content
        query_embedding = loader._generate_embeddings(["table not found error"])[0]
        results = vector_store.semantic_search(query_embedding, limit=3)

        assert len(results) > 0
        # Should find content related to undefined_table error
        assert any("42P01" in result.content or "undefined" in result.content.lower()
                   for result in results)

