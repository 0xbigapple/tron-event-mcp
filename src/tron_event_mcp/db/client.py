"""MongoDB (Motor) async client management.

Provides a lazy-initialized singleton client and convenience accessors
for the configured database.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from tron_event_mcp.config import get_settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    """Return the Motor client singleton, lazily initialized on first call."""
    global _client  # pylint: disable=global-statement
    if _client is None:
        settings = get_settings()
        _client = AsyncIOMotorClient(
            settings.mongo_uri,
            maxPoolSize=10,
            serverSelectionTimeoutMS=5_000,
            socketTimeoutMS=settings.query_timeout_ms,
        )
    return _client


def get_db() -> AsyncIOMotorDatabase:
    """Return the configured MongoDB database handle."""
    return get_client()[get_settings().mongo_db]


async def close_client() -> None:
    """Close the Motor client and release connection resources."""
    global _client  # pylint: disable=global-statement
    if _client is not None:
        _client.close()
        _client = None
