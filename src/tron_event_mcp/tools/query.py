"""Query tools: basic event retrieval by block, transaction, or arbitrary filters."""

from typing import Literal

from mcp.server.fastmcp import FastMCP
from pymongo import ASCENDING, DESCENDING

from tron_event_mcp.db.client import get_db
from tron_event_mcp.db.repos.base import find_many, find_one, sanitize_filter, safe_limit

CollectionName = Literal[
    "block", "transaction", "contractevent",
    "contractlog", "solidity", "solidityevent", "soliditylog"
]


def register_query_tools(mcp: FastMCP) -> None:
    """Register basic query tools on the given MCP server instance."""

    @mcp.tool()
    async def get_recent_events(
        collection: CollectionName,
        limit: int = 10,
    ) -> list[dict]:
        """
        Fetch the most recent N events from a collection, sorted by timestamp descending.
        Useful for a quick look at the latest on-chain activity.

        Args:
          collection: Collection name. One of: block / transaction / contractevent /
                      contractlog / solidity / solidityevent / soliditylog
          limit: Number of documents to return. Default 10, max 100.

        Example: view the latest 5 blocks
          get_recent_events(collection="block", limit=5)
        """
        db = get_db()
        return await find_many(
            db, collection, {},
            sort=[("timeStamp", DESCENDING)],
            limit=min(limit, 100),
        )

    @mcp.tool()
    async def get_block(block_number: int) -> dict | None:
        """
        Look up a single block by its height.
        Returns block hash, transaction count, transaction ID list,
        solidification progress, etc.

        Args:
          block_number: Block height, e.g. 64000000

        Returns: Block document, or null if not found.
        """
        db = get_db()
        return await find_one(db, "block", {"blockNumber": block_number})

    @mcp.tool()
    async def get_transaction(transaction_id: str) -> dict | None:
        """
        Look up a single transaction by its hash.
        Returns energy consumption, fees, sender/receiver addresses,
        contract call details, etc.

        Args:
          transaction_id: 64-character hex string (transaction hash)

        Example:
          get_transaction("abc123...def456")
        """
        db = get_db()
        return await find_one(db, "transaction", {"transactionId": transaction_id})

    @mcp.tool()
    async def query_events(
        collection: CollectionName,
        filters: dict = {},
        sort_by: str = "timeStamp",
        sort_order: Literal["asc", "desc"] = "desc",
        limit: int = 20,
        skip: int = 0,
        fields: list[str] | None = None,
    ) -> list[dict]:
        """
        General-purpose query interface with arbitrary filters and field projection.
        Use this when specialized tools (get_block, get_transaction,
        search_contract_activity, etc.) cannot satisfy the requirement.

        Args:
          collection: Collection name.
          filters: MongoDB filter dict. Standard comparison operators are supported,
                   e.g. {"result": "FAILED"} or {"blockNumber": {"$gte": 64000000}}.
                   Forbidden operators: $where, $function, $accumulator (security restriction).
          sort_by: Field to sort by. Default: timeStamp.
          sort_order: Sort direction. "asc" for ascending, "desc" for descending.
          limit: Number of documents to return. Default 20, capped by system config.
          skip: Number of documents to skip (for pagination).
          fields: Optional list of fields to include in the response.
                  Omit to return all fields.
                  Example: ["transactionId", "blockNumber", "result"]

        Example 1: query failed transactions
          query_events("transaction", filters={"result": "FAILED"}, limit=50)

        Example 2: query transactions from a specific address, return key fields only
          query_events(
              "transaction",
              filters={"fromAddress": "TXyz..."},
              fields=["transactionId", "blockNumber", "energyUsageTotal", "result"]
          )

        Example 3: paginated query
          query_events("contractevent", limit=20, skip=20)
        """
        db = get_db()
        direction = ASCENDING if sort_order == "asc" else DESCENDING
        return await find_many(
            db, collection,
            filter=sanitize_filter(filters),
            sort=[(sort_by, direction)],
            limit=safe_limit(limit),
            skip=skip,
            fields=fields,
        )
