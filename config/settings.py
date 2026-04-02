"""
Configuration management using Pydantic Settings.

Loads configuration from environment variables with type validation.
"""

from typing import Optional, Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    model_config = SettingsConfigDict(env_prefix='POSTGRES_')

    host: str = Field(default='localhost', description='Database host')
    port: int = Field(default=5432, ge=1, le=65535, description='Database port')
    db: str = Field(default='testdb', description='Database name')
    user: str = Field(default='postgres', description='Database user')
    password: str = Field(default='', description='Database password')

    @property
    def connection_string(self) -> str:
        """Generate PostgreSQL connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"

    @property
    def connection_params(self) -> dict:
        """Get connection parameters as dict."""
        return {
            'host': self.host,
            'port': self.port,
            'database': self.db,
            'user': self.user,
            'password': self.password
        }


class WriteDatabaseSettings(BaseSettings):
    """Write database connection settings (for execution MCP)."""

    model_config = SettingsConfigDict(env_prefix='POSTGRES_WRITE_')

    host: str = Field(default='localhost', description='Write database host')
    port: int = Field(default=5432, ge=1, le=65535, description='Write database port')
    db: str = Field(default='testdb', description='Write database name')
    user: str = Field(default='dba_user', description='Write database user')
    password: str = Field(default='', description='Write database password')

    @property
    def connection_string(self) -> str:
        """Generate PostgreSQL connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"

    @property
    def connection_params(self) -> dict:
        """Get connection parameters as dict."""
        return {
            'host': self.host,
            'port': self.port,
            'database': self.db,
            'user': self.user,
            'password': self.password
        }


class VectorDatabaseSettings(BaseSettings):
    """Vector store database settings."""

    model_config = SettingsConfigDict(env_prefix='VECTOR_DB_')

    host: str = Field(default='localhost', description='Vector DB host')
    port: int = Field(default=5432, ge=1, le=65535, description='Vector DB port')
    name: str = Field(default='knowledge_base', description='Vector DB name')
    user: str = Field(default='vector_user', description='Vector DB user')
    password: str = Field(default='', description='Vector DB password')

    @property
    def connection_string(self) -> str:
        """Generate PostgreSQL connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def connection_params(self) -> dict:
        """Get connection parameters as dict."""
        return {
            'host': self.host,
            'port': self.port,
            'database': self.name,
            'user': self.user,
            'password': self.password
        }


class LLMSettings(BaseSettings):
    """LLM provider settings."""

    model_config = SettingsConfigDict(case_sensitive=False)

    openai_api_key: Optional[str] = Field(default=None, description='OpenAI API key')
    anthropic_api_key: Optional[str] = Field(default=None, description='Anthropic API key')
    dashscope_api_key: Optional[str] = Field(default=None, description='Qwen/DashScope API key')
    deepseek_api_key: Optional[str] = Field(default=None, description='DeepSeek API key')
    deepseek_base_url: str = Field(default='https://api.deepseek.com', description='DeepSeek base URL')
    deepseek_model: str = Field(default='deepseek-chat', description='DeepSeek model name')

    primary_llm_provider: Literal['openai', 'anthropic', 'qwen', 'deepseek'] = Field(
        default='openai',
        description='Primary LLM provider'
    )
    secondary_llm_provider: Optional[Literal['openai', 'anthropic', 'qwen', 'deepseek']] = Field(
        default='deepseek',
        description='Secondary LLM provider for fallback'
    )

    @field_validator('openai_api_key', 'anthropic_api_key', 'dashscope_api_key', 'deepseek_api_key')
    @classmethod
    def validate_api_key(cls, v: Optional[str]) -> Optional[str]:
        """Validate API key format."""
        if v and len(v) < 10:
            raise ValueError('API key too short')
        return v


class MCPServerSettings(BaseSettings):
    """MCP server configuration."""

    model_config = SettingsConfigDict(env_prefix='MCP_')

    read_server_port: int = Field(default=8001, ge=1024, le=65535, description='Read MCP server port')
    write_server_port: int = Field(default=8002, ge=1024, le=65535, description='Write MCP server port')


class APISettings(BaseSettings):
    """FastAPI application settings."""

    model_config = SettingsConfigDict(env_prefix='API_')

    host: str = Field(default='0.0.0.0', description='API host')
    port: int = Field(default=8000, ge=1024, le=65535, description='API port')
    reload: bool = Field(default=False, description='Enable auto-reload')


class SecuritySettings(BaseSettings):
    """Security and authentication settings."""

    jwt_secret_key: str = Field(
        default='change-this-secret-key-in-production',
        min_length=32,
        description='JWT secret key'
    )
    jwt_algorithm: str = Field(default='HS256', description='JWT algorithm')
    jwt_expiration_minutes: int = Field(default=15, ge=1, le=1440, description='JWT expiration in minutes')


class AgentSettings(BaseSettings):
    """Agent workflow configuration."""

    max_workflow_timeout_seconds: int = Field(
        default=1800,
        ge=60,
        le=7200,
        description='Maximum workflow timeout (30 min default)'
    )
    health_check_duration_seconds: int = Field(
        default=300,
        ge=60,
        le=600,
        description='Post-execution health check duration (5 min default)'
    )
    snapshot_retention_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description='Snapshot retention period'
    )


class QuerySafetySettings(BaseSettings):
    """Query safety limits."""

    max_query_timeout_seconds: int = Field(
        default=30,
        ge=5,
        le=300,
        description='Maximum query timeout'
    )
    max_result_rows: int = Field(
        default=100,
        ge=10,
        le=10000,
        description='Maximum result rows'
    )


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    log_level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] = Field(
        default='INFO',
        description='Logging level'
    )
    log_format: Literal['json', 'text'] = Field(
        default='json',
        description='Log output format'
    )


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )

    # Sub-settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    write_database: WriteDatabaseSettings = Field(default_factory=WriteDatabaseSettings)
    vector_database: VectorDatabaseSettings = Field(default_factory=VectorDatabaseSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    mcp: MCPServerSettings = Field(default_factory=MCPServerSettings)
    api: APISettings = Field(default_factory=APISettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    query_safety: QuerySafetySettings = Field(default_factory=QuerySafetySettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    def validate_configuration(self) -> list[str]:
        """
        Validate configuration and return list of warnings.

        Returns:
            List of warning messages
        """
        warnings = []

        # Check if at least one LLM API key is configured
        if not any([
            self.llm.openai_api_key,
            self.llm.anthropic_api_key,
            self.llm.dashscope_api_key,
            self.llm.deepseek_api_key
        ]):
            warnings.append("No LLM API keys configured")

        # Check if primary provider has API key
        provider_key_map = {
            'openai': self.llm.openai_api_key,
            'anthropic': self.llm.anthropic_api_key,
            'qwen': self.llm.dashscope_api_key,
            'deepseek': self.llm.deepseek_api_key
        }

        if not provider_key_map.get(self.llm.primary_llm_provider):
            warnings.append(
                f"Primary LLM provider '{self.llm.primary_llm_provider}' has no API key configured"
            )

        # Check database passwords
        if not self.database.password:
            warnings.append("Read database password not set")

        if not self.write_database.password:
            warnings.append("Write database password not set")

        # Check JWT secret in production
        if self.security.jwt_secret_key == 'change-this-secret-key-in-production':
            warnings.append("JWT secret key is using default value - change in production!")

        return warnings


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings instance."""
    return settings
