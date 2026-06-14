from functools import lru_cache
from urllib.parse import quote

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class DatabaseConfig(BaseModel):
    host: str = Field(default="localhost", description="The host of the database")
    port: int = Field(default=5432, ge=1, le=65535, description="The port of the database")
    db: str = Field(default="agent_metadata", description="The name of the database")
    user: str = Field(default="agent", description="The user of the database")
    password: str = Field(default="password", description="The password of the database")
    pool_size: int = Field(default=5, description="Max connections of connection pool")
    max_overflow: int = Field(default=10, description="")

    @property
    def connection_string(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"

    @property
    def psycopg_connection_string(self) -> str:
        user = quote(self.user, safe="")
        password = quote(self.password, safe="")
        return f"postgresql://{user}:{password}@{self.host}:{self.port}/{self.db}"

class LLMConfig(BaseModel):
    deepseek_key: str = Field(description="DeepSeek API Key")
    deepseek_model: str = Field(default='deepseek-v4-flash', description='DeepSeek API Model')
    deepseek_base_url: str = Field(default='https://api.deepseek.com', description='DeepSeek API URL')

class EmbeddingConfig(BaseModel):
    model_name: str = Field(default="BAAI/bge-small-en-v1.5", description="Embedding model name")

class SecurityConfig(BaseModel):
    max_query_timeout_ms: int = Field(default=15000, description="Max query timeout in ms")
    max_result_rows: int = Field(default=100, description="Max result rows")
    secret_algorithm: str = Field(default="HS256")
    secret_key: str
    access_token_expire_mins: int = Field(default=120)
    

class AgentConfig(BaseModel):
    diagnostic_max_retries: int = Field(default=3)
    node_max_retries: int = Field(default=3)
    startup_recovery_enabled: bool = Field(default=True)
    semantic_similarity_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    diagnostic_llm_timeout_s: float = Field(default=50.0, gt=0)
    diagnostic_embedding_timeout_s: float = Field(default=5.0, gt=0)
    diagnostic_mcp_timeout_s: float = Field(default=5.0, gt=0)
    validation_llm_timeout_s: float = Field(default=15.0, gt=0)
    validation_mcp_timeout_s: float = Field(default=5.0, gt=0)
    planning_llm_timeout_s: float = Field(default=45.0, gt=0)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        env_nested_delimiter='__',
        case_sensitive=False,
        extra='ignore'
    )

    "Sub Configuration"
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)

    def validate_configuration(self) -> list[str]:
        """
        Validate configuration and return list of warnings.

        Returns:
            List of warning messages
        """
        warnings = []
        if not self.llm.deepseek_key:
            warnings.append("No LLM API Keys Configured")
        if not self.database.password:
            warnings.append("No Database Password Configured")
        return warnings

settings = Settings()

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
