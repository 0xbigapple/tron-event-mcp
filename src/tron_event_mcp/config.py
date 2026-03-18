"""Application settings loaded from environment variables / .env file."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for the TRON Event MCP server.

    Values are read from environment variables or a `.env` file.
    """

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "tron"
    max_result_limit: int = 500
    query_timeout_ms: int = 10_000

    # SSE transport settings
    mcp_transport: Literal["stdio", "sse"] = "stdio"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8080

    allowed_collections: list[str] = [
        "block",
        "transaction",
        "contractevent",
        "contractlog",
        "solidity",
        "solidityevent",
        "soliditylog",
    ]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
