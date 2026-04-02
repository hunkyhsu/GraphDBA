# Manual Testing Guide for Document Loader (Phase 2 Task 3)

This document provides step-by-step manual testing instructions for the DocumentLoader component.

## Prerequisites

1. **PostgreSQL Database Running**
   - PostgreSQL 14+ with pgvector extension
   - Database: `agent_vector_db`
   - User: `rag_agent` with password `rag_password_123`

2. **Environment Setup**
   ```bash
   # Ensure you're in the project root
   cd /Users/hunkyhsu/Claude CodeProjects/GraphDBA
   
   # Install dependencies
   poetry install
   
   # Set up the vector database (run once)
   psql -U postgres -f global_database_setup.sql
   ```

3. **Environment Variables**
   Create a `.env` file or export these variables:
   ```bash
   export VECTOR_DB_HOST=localhost
   export VECTOR_DB_PORT=5432
   export VECTOR_DB_NAME=agent_vector_db
   export VECTOR_DB_USER=rag_agent
   export VECTOR_DB_PASSWORD=rag_password_123
   ```

## Test 1: Run Automated Tests

### Command
```bash
poetry run pytest tests/document_loader_test.py -v
```

### Expected Results
- All tests should pass
- Output should show:
  - `test_initialization PASSED`
  - `test_generate_chunk_id PASSED`
  - `test_generate_embeddings PASSED`
  - `test_load_text_file PASSED`
  - `test_load_nonexistent_file PASSED`
  - `test_extract_error_codes PASSED`
  - `test_extract_error_codes_empty PASSED`
  - `test_load_error_codes PASSED`
  - `test_load_error_codes_empty PASSED`
  - `test_unsupported_file_type PASSED`
  - `test_load_and_store_text PASSED` (requires database)
  - `test_load_and_store_with_error_extraction PASSED` (requires database)
  - `test_semantic_search_after_load PASSED` (requires database)


### Negative Test
If database is not running, integration tests should fail with connection errors:
```
psycopg2.OperationalError: could not connect to server
```

---

## Test 2: Interactive Python Testing

### Command
```bash
poetry run python
```

### Test Script
```python
from pathlib import Path
from rag.document_loader import DocumentLoader
from rag.pgvector_store import PGVectorStore

# Initialize loader
loader = DocumentLoader(
    embedding_model_name="all-MiniLM-L6-v2",
    chunk_size=500,
    chunk_overlap=100
)

# Check embedding dimensions
print(f"Embedding dimensions: {loader.embedding_dimensions}")
# Expected: 384

# Create a test document
test_file = Path("test_pg_doc.txt")
test_file.write_text("""
PostgreSQL Error Codes Reference

42P01 - undefined_table
This error occurs when referencing a non-existent table.

53300 - too_many_connections
Maximum connection limit reached.

42501 - insufficient_privilege
User lacks required permissions.
""")

# Load the document
chunks = loader.load_text(test_file)
print(f"Generated {len(chunks)} chunks")
# Expected: 1-3 chunks depending on content size

# Inspect first chunk
if chunks:
    chunk = chunks[0]
    print(f"Chunk ID: {chunk.chunk_id}")
    print(f"Source: {chunk.source}")
    print(f"Content length: {len(chunk.content)}")
    print(f"Embedding length: {len(chunk.embedding)}")
    print(f"Metadata: {chunk.metadata}")

# Extract error codes
with open(test_file) as f:
    text = f.read()
error_codes = loader.extract_error_codes(text)
print(f"Extracted error codes: {error_codes}")
# Expected: {'42P01': 'undefined_table', '53300': 'too_many_connections', '42501': 'insufficient_privilege'}

# Clean up
test_file.unlink()
```

### Expected Results
- Embedding dimensions: 384
- Generated 1-3 chunks
- Each chunk has valid chunk_id, source, content, embedding
- Error codes extracted: 3 codes (42P01, 53300, 42501)

---

## Test 3: Database Integration Test

### Command
```bash
poetry run python
```

### Test Script
```python
from pathlib import Path
from rag.document_loader import DocumentLoader
from rag.pgvector_store import PGVectorStore

# Initialize components
loader = DocumentLoader()
vector_store = PGVectorStore(
    embedding_dimensions=384,
    table_name="manual_test_chunks"
)

# Create schema
vector_store.ensure_schema()
print("Schema created successfully")

# Create test document
test_file = Path("test_manual.txt")
test_file.write_text("""
PostgreSQL Performance Tuning

Shared buffers should be set to 25% of available RAM.
Work memory affects sort and hash operations.

Error 42P01 - undefined_table occurs when table doesn't exist.
Error 53300 - too_many_connections means connection pool is full.
""")

# Load and store with error extraction
count = loader.load_and_store(
    test_file,
    vector_store,
    extract_errors=True
)
print(f"Stored {count} chunks")

# Verify storage
total = vector_store.count_chunks()
print(f"Total chunks in database: {total}")
# Expected: count == total

# Test semantic search
query_embedding = loader._generate_embeddings(["connection limit error"])[0]
results = vector_store.semantic_search(query_embedding, limit=3)
print(f"\nSearch results for 'connection limit error':")
for i, result in enumerate(results, 1):
    print(f"{i}. Score: {result.semantic_score:.4f}")
    print(f"   Content: {result.content[:100]}...")

# Test lexical search
results = vector_store.lexical_search("too_many_connections", limit=3)
print(f"\nLexical search results for 'too_many_connections':")
for i, result in enumerate(results, 1):
    print(f"{i}. Score: {result.lexical_score:.4f}")
    print(f"   Content: {result.content[:100]}...")

# Clean up
vector_store.drop_table()
test_file.unlink()
print("\nCleanup completed")
```

### Expected Results
- Schema created successfully
- Stored 3-5 chunks (document chunks + error code chunks)
- Semantic search returns relevant results with scores > 0.5
- Lexical search finds exact matches for "too_many_connections"
- Cleanup completes without errors

---

## Test 4: Error Code Extraction Accuracy

### Command
```bash
poetry run python
```

### Test Script
```python
from rag.document_loader import DocumentLoader

loader = DocumentLoader()

# Test various error code formats
test_cases = [
    ("42P01 - undefined_table", {"42P01": "undefined_table"}),
    ("53300: too_many_connections", {"53300": "too_many_connections"}),
    ("Error 42501 – insufficient privilege", {"42501": "insufficient_privilege"}),
    ("Multiple: 42P01 - undefined_table and 53300 - too_many_connections",
     {"42P01": "undefined_table", "53300": "too_many_connections"}),
    ("No error codes here", {}),
]

print("Testing error code extraction:")
for text, expected in test_cases:
    result = loader.extract_error_codes(text)
    status = "✓" if result == expected else "✗"
    print(f"{status} Input: {text[:50]}...")
    print(f"  Expected: {expected}")
    print(f"  Got: {result}")
    print()
```

### Expected Results
All test cases should show ✓ (checkmark)

---

## Test 5: Negative Tests

### Test 5.1: Invalid File Path
```python
from rag.document_loader import DocumentLoader

loader = DocumentLoader()

try:
    chunks = loader.load_text("/nonexistent/file.txt")
    print("ERROR: Should have raised FileNotFoundError")
except FileNotFoundError as e:
    print(f"✓ Correctly raised FileNotFoundError: {e}")
```

### Test 5.2: Unsupported File Type
```python
from pathlib import Path
from rag.document_loader import DocumentLoader
from rag.pgvector_store import PGVectorStore
from unittest.mock import Mock

loader = DocumentLoader()
vector_store = Mock(spec=PGVectorStore)

# Create unsupported file
test_file = Path("test.xlsx")
test_file.write_text("dummy")

try:
    loader.load_and_store(test_file, vector_store)
    print("ERROR: Should have raised ValueError")
except ValueError as e:
    print(f"✓ Correctly raised ValueError: {e}")
finally:
    test_file.unlink()
```

### Test 5.3: Database Connection Failure
```python
from rag.document_loader import DocumentLoader
from rag.pgvector_store import PGVectorStore
from pathlib import Path

loader = DocumentLoader()

# Use invalid connection params
vector_store = PGVectorStore(
    embedding_dimensions=384,
    connection_params={
        "host": "invalid_host",
        "port": 5432,
        "database": "invalid_db",
        "user": "invalid_user",
        "password": "invalid_pass",
    }
)

test_file = Path("test.txt")
test_file.write_text("Test content")

try:
    loader.load_and_store(test_file, vector_store)
    print("ERROR: Should have raised connection error")
except Exception as e:
    print(f"✓ Correctly raised connection error: {type(e).__name__}")
finally:
    test_file.unlink()
```

### Expected Results
- All negative tests should raise appropriate exceptions
- Error messages should be clear and informative

---

## Test 6: Performance Test

### Command
```bash
poetry run python
```

### Test Script
```python
import time
from pathlib import Path
from rag.document_loader import DocumentLoader
from rag.pgvector_store import PGVectorStore

# Create large test document
large_content = "\n\n".join([
    f"Section {i}: This is a test section with some PostgreSQL content. "
    f"It discusses database performance and optimization techniques. "
    f"Error codes like 42P01 and 53300 may appear in logs."
    for i in range(100)
])

test_file = Path("large_test.txt")
test_file.write_text(large_content)

# Initialize
loader = DocumentLoader(chunk_size=500, chunk_overlap=100)
vector_store = PGVectorStore(
    embedding_dimensions=384,
    table_name="perf_test_chunks"
)
vector_store.ensure_schema()

# Measure loading time
start = time.time()
chunks = loader.load_text(test_file)
load_time = time.time() - start
print(f"Loading time: {load_time:.2f}s for {len(chunks)} chunks")

# Measure storage time
start = time.time()
count = vector_store.upsert_chunks(chunks)
store_time = time.time() - start
print(f"Storage time: {store_time:.2f}s for {count} chunks")

# Measure search time
query_embedding = loader._generate_embeddings(["database performance"])[0]
start = time.time()
results = vector_store.semantic_search(query_embedding, limit=10)
search_time = time.time() - start
print(f"Search time: {search_time:.2f}s for {len(results)} results")

# Clean up
vector_store.drop_table()
test_file.unlink()

print("\nPerformance benchmarks:")
print(f"- Loading: {len(chunks)/load_time:.1f} chunks/sec")
print(f"- Storage: {count/store_time:.1f} chunks/sec")
print(f"- Search: {search_time*1000:.1f}ms")
```

### Expected Results
- Loading: > 10 chunks/sec
- Storage: > 5 chunks/sec
- Search: < 100ms

---

## Cleanup

After all tests, ensure cleanup:

```bash
# Remove test files
rm -f test_*.txt test_*.pdf

# Drop test tables (if any remain)
psql -U rag_agent -d agent_vector_db -c "DROP TABLE IF EXISTS test_knowledge_chunks CASCADE;"
psql -U rag_agent -d agent_vector_db -c "DROP TABLE IF EXISTS manual_test_chunks CASCADE;"
psql -U rag_agent -d agent_vector_db -c "DROP TABLE IF EXISTS perf_test_chunks CASCADE;"
```

---

## Success Criteria

✓ All automated tests pass  
✓ Interactive tests produce expected outputs  
✓ Database integration works correctly  
✓ Error code extraction is accurate  
✓ Negative tests raise appropriate exceptions  
✓ Performance meets benchmarks  
✓ Cleanup completes without errors

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'sentence_transformers'"
**Solution**: Run `poetry install` to install all dependencies

### Issue: "psycopg2.OperationalError: could not connect to server"
**Solution**: 
1. Ensure PostgreSQL is running: `pg_ctl status`
2. Check connection parameters in `.env`
3. Verify database exists: `psql -U postgres -l | grep agent_vector_db`

### Issue: "pgvector extension not found"
**Solution**: Run the global_database_setup.sql script:
```bash
psql -U postgres -f global_database_setup.sql
```

### Issue: "Embedding model download fails"
**Solution**: 
1. Check internet connection
2. Model will be downloaded on first use (may take 1-2 minutes)
3. Model is cached in `~/.cache/torch/sentence_transformers/`

### Issue: "Tests are slow"
**Solution**: 
- First run downloads the embedding model (~90MB)
- Subsequent runs should be faster
- Use smaller chunk_size for faster testing
