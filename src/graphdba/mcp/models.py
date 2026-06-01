from pydantic import BaseModel, Field

# Read Models
class ExplainQueryInput(BaseModel):
    query: str = Field(description="The read-only PostgreSQL query to analyze")
    run_analyze: bool = Field(default=False, description="set True to execute the explain query")

class SlowQueryFilter(BaseModel):
    limit: int = Field(default=100, description="Number of queries to return")
    min_duration_ms: int = Field(default=1000, description="Minimum query duration in ms")

class SafeSelectInput(BaseModel):
    query: str = Field(description="The SELECT query to execute")
