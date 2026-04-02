# DocumentLoader Quick Reference

## Basic Usage

### 1. Initialize the Loader

```python
from rag.document_loader import DocumentLoader

# Default configuration (all-MiniLM-L6-v2, 1000 char chunks, 200 overlap)
loader = DocumentLoader()

# Custom configuration
loader = DocumentLoader(
    embedding_model_name="all-MiniLM-L6-v2",
    chunk_size=500,
    chunk_overlap=100
)
```

### 2. Load Documents

```python
from pathlib import Path

# Load a text file
chunks = loader.load_text("path/to/document.txt")

# Load a PDF file
chunks = loader.load_pdf("path/to/document.pdf")

# Each chunk contains:
# - chunk_id: Unique identifier
# - source: Source file name
# - content: Text content
# - embedding: 384-dimensional vector
# - metadata: Document metadata
```

### 3. Extract Error Codes

```python
text = """
PostgreSQL Error Codes:
42P01 - undefined_table
53300 - too_many_connections
42501 - insufficient_privilege
"""

error_codes = loader.extract_error_codes(text)
# Returns: {'42P01': 'undefined_table', '53300': 'too_many_connections', ...}

# Create knowledge chunks from error codes
error_chunks = loader.load_error_codes(error_codes, source="pg_manual")
```

### 4. Store in Vector Database

```python
from rag.pgvector_store import PGVectorStore

# Initialize vector store
vector_store = PGVectorStore(
    embedding_dimensions=384,
    table_name="knowledge_chunks"
)
vector_store.ensure_schema()

# Load and store in one step
count = loader.load_and_store(
    file_path="path/to/document.txt",
    vector_store=vector_store,
    extract_errors=True  # Also extract and store error codes
)

print(f"Stored {count} chunks")
```

### 5. Search Stored Documents

```python
# Semantic search
query_embedding = loader._generate_embeddings(["connection error"])[0]
results = vector_store.semantic_search(query_embedding, limit=5)

for result in results:
    print(f"Score: {result.semantic_score:.4f}")
    print(f"Content: {result.content[:100]}...")
    print()

# Lexical search
results = vector_store.lexical_search("too_many_connections", limit=5)

# Hybrid search (best of both)
results = vector_store.hybrid_search(
    query_text="connection error",
    query_embedding=query_embedding,
    limit=5
)
```

## Common Patterns

### Pattern 1: Batch Load Multiple Documents

```python
from pathlib import Path

docs_dir = Path("docs/postgresql")
vector_store = PGVectorStore(embedding_dimensions=384)
vector_store.ensure_schema()

loader = DocumentLoader()
total_chunks = 0

for doc_file in docs_dir.glob("*.txt"):
    count = loader.load_and_store(doc_file, vector_store, extract_errors=True)
    total_chunks += count
    print(f"Loaded {doc_file.name}: {count} chunks")

print(f"Total: {total_chunks} chunks stored")
```

### Pattern 2: Custom Error Code Processing

```python
# Load document
chunks = loader.load_text("pg_manual.txt")

# Extract all error codes from all chunks
all_text = "\n".join(chunk.content for chunk in chunks)
error_codes = loader.extract_error_codes(all_text)

# Create enriched error code chunks
error_chunks = loader.load_error_codes(error_codes, source="pg_manual_v14")

# Store everything
vector_store.upsert_chunks(chunks)
vector_store.upsert_chunks(error_chunks)
```

### Pattern 3: Incremental Updates

```python
# Load new document
new_chunks = loader.load_text("new_doc.txt")

# Upsert (insert or update) - uses chunk_id as key
count = vector_store.upsert_chunks(new_chunks)
print(f"Upserted {count} chunks")

# Same chunk_id will update existing, new IDs will insert
```

## Configuration Options

### Embedding Models

```python
# Fast, lightweight (default)
loader = DocumentLoader(embedding_model_name="all-MiniLM-L6-v2")  # 384 dims

# Better quality, slower
loader = DocumentLoader(embedding_model_name="all-mpnet-base-v2")  # 768 dims

# Multilingual
loader = DocumentLoader(embedding_model_name="paraphrase-multilingual-MiniLM-L12-v2")
```

### Chunking Strategies

```python
# Small chunks for precise retrieval
loader = DocumentLoader(chunk_size=300, chunk_overlap=50)

# Large chunks for more context
loader = DocumentLoader(chunk_size=2000, chunk_overlap=400)

# No overlap (faster, less context preservation)
loader = DocumentLoader(chunk_size=1000, chunk_overlap=0)
```

## Error Handling

```python
from pathlib import Path

try:
    chunks = loader.load_text("nonexistent.txt")
except FileNotFoundError as e:
    print(f"File not found: {e}")

try:
    loader.load_and_store("document.xlsx", vector_store)
except ValueError as e:
    print(f"Unsupported file type: {e}")

try:
    vector_store = PGVectorStore(
        embedding_dimensions=384,
        connection_params={"host": "invalid"}
    )
    loader.load_and_store("doc.txt", vector_store)
except Exception as e:
    print(f"Database error: {e}")
```

## Performance Tips

1. **Batch Processing**: Load multiple documents before storing
2. **Chunk Size**: Larger chunks = fewer embeddings = faster processing
3. **Model Selection**: Smaller models (MiniLM) are 3-5x faster than larger ones
4. **Connection Pooling**: Reuse vector_store instance across multiple loads
5. **Parallel Processing**: Use multiprocessing for large document sets

## Metadata Structure

```python
# Text file metadata
{
    "doc_type": "text",
    "file_path": "/path/to/file.txt"
}

# PDF metadata
{
    "doc_type": "pdf",
    "file_path": "/path/to/file.pdf",
    "page_number": 5
}

# Error code metadata
{
    "doc_type": "error_code",
    "error_code": "42P01",
    "error_name": "undefined_table"
}
```

## Testing

```bash
# Run automated tests
poetry run pytest tests/document_loader_test.py -v

# Run specific test
poetry run pytest tests/document_loader_test.py::TestDocumentLoader::test_extract_error_codes -v

# Run with coverage
poetry run pytest tests/document_loader_test.py --cov=rag.document_loader

# See manual testing guide
cat tests/MANUAL_TEST_DOCUMENT_LOADER.md
```

## Troubleshooting

**Issue**: Model download is slow  
**Solution**: First run downloads ~90MB model, subsequent runs use cache

**Issue**: Out of memory with large PDFs  
**Solution**: Use smaller chunk_size or process page-by-page

**Issue**: Poor search results  
**Solution**: Try hybrid_search() instead of semantic_search() alone

**Issue**: Duplicate chunks  
**Solution**: Chunk IDs are deterministic - same content = same ID = update not duplicate
