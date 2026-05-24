"""
Configuration management using Pydantic Settings

Loads configuration from environment variables and provides a Pydantic model for easy access.
"""
from functools import lru_cache
from typing import Set
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class DatabaseConfig(BaseModel):
    """Database Configuration"""
    host: str = Field(default="localhost", description="The host of the database")
    port: int = Field(default=5432, ge=1, le=65535, description="The port of the database")
    db: str = Field(default="test_db", description="The name of the database")
    user: str = Field(default="agent_role", description="The user of the database")
    password: str = Field(default="password", description="The password of the database")
    max_connections: int = Field(default=5, description="Max connections of connection pool")
    min_connections: int = Field(default=1, description="Min connections of connection pool")
    connection_timeout: int = Field(default=5, description="Connection timeout of user's role")
    max_inactive_connection_lifetime: int = Field(default=300, description="Max inactive connection lifetime")

    @property
    def connection_string(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"

    @property
    def get_params(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "db": self.db,
            "user": self.user,
            "password": self.password,
            "max_connections": self.max_connections,
            "min_connections": self.min_connections,
            "max_inactive_connection_lifetime": self.max_inactive_connection_lifetime,
        }

class LLMConfig(BaseModel):
    """"LLM Providers Configuration"""
    deepseek_key: str | None = Field(default=None, description="DeepSeek API Key")
    deepseek_model: str = Field(default='deepseek-v4-flash', description='DeepSeek API Model')
    deepseek_base_url: str = Field(default='https://api.deepseek.com', description='DeepSeek API URL')

    @field_validator('deepseek_key')
    @classmethod
    def validate_api_key(cls, v: str | None) -> str | None:
        """Validate the API Key format"""
        if v and len(v) < 10:
            raise ValueError('API Key Invalid')
        return v
    
    @property
    def get_params(self) -> dict:
        return {
            "API Key": self.deepseek_key,
            "API URL": self.deepseek_base_url,
            "API Model": self.deepseek_model
        }

class EmbeddingConfig(BaseModel):
    """Embedding Configuration"""
    model_name: str = Field(default="BAAI/bge-small-en-v1.5", description="Embedding model name")

class SecurityConfig(BaseModel):
    """"Security and authentication Configuration"""
    max_query_timeout_ms: int = Field(default=15000, description="Max query timeout in ms")
    max_result_rows: int = Field(default=100, description="Max result rows")
    oauth_secret: str = Field(default="", description="OAuth key")
    
    @property
    def get_params(self) -> dict:
        return {
            "Max query timeout ms": self.max_query_timeout_ms,
            "Max result rows": self.max_result_rows,
            "OAuth secret key": self.oauth_secret,
        }

class AgentConfig(BaseModel):
    """"Agent Configuration"""
    max_retries: int = Field(default=5, description="Max retries count")
    
    @property
    def get_params(self) -> dict:
        return {
            "Max retries count": self.max_retries,
        }

class Settings(BaseSettings):
    """Main Application Settings"""
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