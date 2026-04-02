"""
Document loader for PostgreSQL documentation and error code mappings.

Implements Phase 2 Task 3 requirements:
- Parse PostgreSQL documentation (PDF/HTML)
- Extract error code mappings
- Generate embeddings and store in pgvector
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from langchain.text_splitter import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

from rag.pgvector_store import KnowledgeChunk, PGVectorStore


@dataclass(frozen=True)
class DocumentMetadata:
    """Metadata for a loaded document."""

    doc_type: Literal["pdf", "html", "text", "error_code"]
    file_path: str | None = None
    page_number: int | None = None
    error_code: str | None = None
    error_name: str | None = None


class DocumentLoader:
    """Load and process PostgreSQL documentation for RAG retrieval."""

    # PostgreSQL error code pattern (e.g., 42P01, 53300)
    ERROR_CODE_PATTERN = re.compile(
        r"\b([0-9A-Z]{5})\b\s*[-–—:]\s*([a-z_]+(?:\s+[a-z_]+)*)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        embedding_model_name: str = "all-MiniLM-L6-v2",
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> None:
        """
        Initialize document loader.

        Args:
            embedding_model_name: Sentence-transformers model name
            chunk_size: Maximum characters per chunk
            chunk_overlap: Overlap between chunks for context preservation
        """
        self.embedding_model = SentenceTransformer(embedding_model_name)
        self.embedding_dimensions = self.embedding_model.get_sentence_embedding_dimension()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def _generate_chunk_id(self, source: str, content: str, index: int) -> str:
        """Generate deterministic chunk ID from source and content."""
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
        source_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", source)[:50]
        return f"{source_slug}_{index}_{content_hash}"

    def _generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        embeddings = self.embedding_model.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [embedding.tolist() for embedding in embeddings]

    def load_pdf(self, file_path: str | Path) -> list[KnowledgeChunk]:
        """
        Load and chunk a PDF document.

        Args:
            file_path: Path to PDF file

        Returns:
            List of knowledge chunks with embeddings
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        reader = PdfReader(str(file_path))
        all_chunks: list[KnowledgeChunk] = []
        chunk_index = 0

        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text()
            if not text.strip():
                continue

            chunks = self.text_splitter.split_text(text)
            texts = [chunk for chunk in chunks if chunk.strip()]
            if not texts:
                continue

            embeddings = self._generate_embeddings(texts)

            for chunk_text, embedding in zip(texts, embeddings):
                metadata = DocumentMetadata(
                    doc_type="pdf",
                    file_path=str(file_path),
                    page_number=page_num,
                )
                chunk = KnowledgeChunk(
                    chunk_id=self._generate_chunk_id(
                        str(file_path), chunk_text, chunk_index
                    ),
                    source=f"{file_path.name}#page{page_num}",
                    content=chunk_text,
                    embedding=embedding,
                    metadata=metadata.__dict__,
                )
                all_chunks.append(chunk)
                chunk_index += 1

        return all_chunks

    def load_text(self, file_path: str | Path) -> list[KnowledgeChunk]:
        """
        Load and chunk a plain text document.

        Args:
            file_path: Path to text file

        Returns:
            List of knowledge chunks with embeddings
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Text file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()

        chunks = self.text_splitter.split_text(text)
        texts = [chunk for chunk in chunks if chunk.strip()]
        if not texts:
            return []

        embeddings = self._generate_embeddings(texts)
        all_chunks: list[KnowledgeChunk] = []

        for index, (chunk_text, embedding) in enumerate(zip(texts, embeddings)):
            metadata = DocumentMetadata(
                doc_type="text",
                file_path=str(file_path),
            )
            chunk = KnowledgeChunk(
                chunk_id=self._generate_chunk_id(str(file_path), chunk_text, index),
                source=file_path.name,
                content=chunk_text,
                embedding=embedding,
                metadata=metadata.__dict__,
            )
            all_chunks.append(chunk)

        return all_chunks

    def extract_error_codes(self, text: str) -> dict[str, str]:
        """
        Extract PostgreSQL error codes and their names from text.

        Args:
            text: Text containing error code definitions

        Returns:
            Dictionary mapping error codes to error names
        """
        error_codes: dict[str, str] = {}
        matches = self.ERROR_CODE_PATTERN.finditer(text)

        for match in matches:
            code = match.group(1).upper()
            name = match.group(2).strip().lower().replace(" ", "_")
            error_codes[code] = name

        return error_codes

    def load_error_codes(
        self, error_codes: dict[str, str], source: str = "postgresql_error_codes"
    ) -> list[KnowledgeChunk]:
        """
        Create knowledge chunks from error code mappings.

        Args:
            error_codes: Dictionary mapping error codes to names
            source: Source identifier for these error codes

        Returns:
            List of knowledge chunks with embeddings
        """
        if not error_codes:
            return []

        texts = [
            f"PostgreSQL Error Code {code}: {name}\n"
            f"Error {code} is named '{name}' in PostgreSQL."
            for code, name in error_codes.items()
        ]

        embeddings = self._generate_embeddings(texts)
        all_chunks: list[KnowledgeChunk] = []

        for index, ((code, name), text, embedding) in enumerate(
            zip(error_codes.items(), texts, embeddings)
        ):
            metadata = DocumentMetadata(
                doc_type="error_code",
                error_code=code,
                error_name=name,
            )
            chunk = KnowledgeChunk(
                chunk_id=f"error_code_{code}_{index}",
                source=source,
                content=text,
                embedding=embedding,
                metadata=metadata.__dict__,
            )
            all_chunks.append(chunk)

        return all_chunks

    def load_and_store(
        self,
        file_path: str | Path,
        vector_store: PGVectorStore,
        extract_errors: bool = False,
    ) -> int:
        """
        Load a document and store it in the vector database.

        Args:
            file_path: Path to document file
            vector_store: PGVectorStore instance
            extract_errors: Whether to extract and store error codes

        Returns:
            Number of chunks stored
        """
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            chunks = self.load_pdf(file_path)
        elif suffix in [".txt", ".md"]:
            chunks = self.load_text(file_path)
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

        total_stored = vector_store.upsert_chunks(chunks)

        if extract_errors:
            combined_text = "\n".join(chunk.content for chunk in chunks)
            error_codes = self.extract_error_codes(combined_text)
            if error_codes:
                error_chunks = self.load_error_codes(error_codes, str(file_path))
                total_stored += vector_store.upsert_chunks(error_chunks)

        return total_stored
