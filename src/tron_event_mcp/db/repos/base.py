"""Low-level MongoDB query helpers with security guards.

All database access should go through these functions so that collection
whitelisting, operator sanitization, and projection rules are enforced
consistently.
"""

from decimal import Decimal
from typing import Any

from bson import Decimal128
from motor.motor_asyncio import AsyncIOMotorDatabase

from tron_event_mcp.config import get_settings

# Never expose the MongoDB internal _id field to LLM responses.
_BASE_PROJECTION: dict = {"_id": 0}

# Blocked MongoDB operators to prevent JS injection or server-side script execution.
_BLOCKED_OPERATORS: set[str] = {"$where", "$function", "$accumulator", "$expr"}


def safe_limit(requested: int) -> int:
    """Clamp the requested limit to the allowed range [1, max_result_limit]."""
    max_limit = get_settings().max_result_limit
    return min(max(1, requested), max_limit)


def validate_collection(collection: str) -> None:
    """Ensure the collection name is in the whitelist; raise ValueError otherwise."""
    allowed = get_settings().allowed_collections
    if collection not in allowed:
        raise ValueError(f"collection '{collection}' is not in the allowed list: {allowed}")


def sanitize_filter(raw: dict) -> dict:
    """Reject filters containing dangerous MongoDB operators (recursively)."""
    def _check(obj: Any) -> None:
        if isinstance(obj, dict):
            for key in obj:
                if key in _BLOCKED_OPERATORS:
                    raise ValueError(f"operator not allowed: {key}")
                _check(obj[key])
        elif isinstance(obj, list):
            for item in obj:
                _check(item)

    _check(raw)
    return raw


def build_projection(fields: list[str] | None) -> dict:
    """Build a MongoDB projection dict, always excluding _id."""
    if not fields:
        return _BASE_PROJECTION
    return {**_BASE_PROJECTION, **{f: 1 for f in fields}}


async def find_many(
    db: AsyncIOMotorDatabase,
    collection: str,
    query_filter: dict,
    sort: list[tuple[str, int]],
    limit: int,
    skip: int = 0,
    fields: list[str] | None = None,
) -> list[dict]:
    """Query multiple documents with validation, projection, sort, skip, and limit."""
    validate_collection(collection)
    sanitize_filter(query_filter)
    projection = build_projection(fields)
    cursor = (
        db[collection]
        .find(query_filter, projection)
        .sort(sort)
        .skip(skip)
        .limit(safe_limit(limit))
    )
    return await cursor.to_list(None)


async def find_one(
    db: AsyncIOMotorDatabase,
    collection: str,
    query_filter: dict,
    fields: list[str] | None = None,
) -> dict | None:
    """Query a single document with collection and filter validation."""
    validate_collection(collection)
    sanitize_filter(query_filter)
    projection = build_projection(fields)
    return await db[collection].find_one(query_filter, projection)


def _convert_decimal128(obj: Any) -> Any:
    """Recursively convert Decimal128/Decimal to JSON-serializable types, preserving full precision.

    Integer values become int (Python int has arbitrary precision);
    non-integer values become str to avoid float precision loss.
    """
    if isinstance(obj, (Decimal128, Decimal)):
        d = obj.to_decimal() if isinstance(obj, Decimal128) else obj
        if d == d.to_integral_value():
            return int(d)
        return str(d)
    if isinstance(obj, dict):
        return {k: _convert_decimal128(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_decimal128(v) for v in obj]
    return obj


async def run_pipeline(
    db: AsyncIOMotorDatabase,
    collection: str,
    pipeline: list[dict],
) -> list[dict]:
    """Execute a MongoDB aggregation pipeline with collection validation."""
    validate_collection(collection)
    settings = get_settings()
    cursor = db[collection].aggregate(
        pipeline,
        allowDiskUse=True,
        maxTimeMS=settings.query_timeout_ms,
    )
    results = await cursor.to_list(None)
    return _convert_decimal128(results)
