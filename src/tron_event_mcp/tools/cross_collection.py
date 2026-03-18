"""Cross-collection tools: transaction full view and address activity profile."""

import asyncio

from mcp.server.fastmcp import FastMCP
from pymongo import DESCENDING

from tron_event_mcp.db.client import get_db
from tron_event_mcp.db.repos.base import find_one, find_many, run_pipeline, safe_limit
from tron_event_mcp.tools.analytics import _build_time_filter


def register_cross_collection_tools(mcp: FastMCP) -> None:
    """Register cross-collection query tools on the given MCP server instance."""

    @mcp.tool()
    async def get_transaction_full(transaction_id: str) -> dict:
        """
        Full transaction view: returns transaction details along with all
        contract events (contractevent) triggered by that transaction in one call.
        Saves multiple tool calls when analyzing a transaction's complete behavior.

        Args:
          transaction_id: 64-character hex string (transaction hash)

        Returns:
          {
            "transaction": { ...transaction details... },
            "events": [ ...all ABI-decoded contract events for this transaction... ]
          }

        Example:
          get_transaction_full("abc123...def456")
        """
        db = get_db()
        tx, events = await asyncio.gather(
            find_one(db, "transaction", {"transactionId": transaction_id}),
            find_many(
                db, "contractevent",
                {"transactionId": transaction_id},
                sort=[("timeStamp", DESCENDING)],
                limit=100,
            ),
        )
        return {"transaction": tx, "events": events}

    @mcp.tool()
    async def get_address_profile(
        address: str,
        start_timestamp: int | None = None,
        end_timestamp: int | None = None,
        recent_limit: int = 10,
    ) -> dict:
        """
        Address profile: summarize an address's activity as sender, receiver,
        and contract caller within an optional time range.
        Returns multi-dimensional statistics in a single call, replacing
        multiple manual queries.

        Args:
          address: TRON address (34-char Base58Check string starting with T)
          start_timestamp: Start timestamp in milliseconds. Omit for no lower bound.
          end_timestamp: End timestamp in milliseconds. Omit for no upper bound.
          recent_limit: Number of recent records per dimension. Default 10, max 50.

        Returns:
          {
            "as_sender": {
              "count": 120,
              "recent": [ ...latest N outgoing transactions... ]
            },
            "as_receiver": {
              "count": 85,
              "recent": [ ...latest N incoming transactions... ]
            },
            "as_contract_caller": {
              "count": 200,
              "top_contracts": [ { "contractAddress": "T...", "count": 50 }, ... ],
              "recent": [ ...latest N contract call events... ]
            }
          }

        Example:
          get_address_profile("TXyz...abc", recent_limit=5)
        """
        db = get_db()
        limit = min(max(1, recent_limit), 50)
        time_filter = _build_time_filter(start_timestamp, end_timestamp)

        sender_filter = {**time_filter, "fromAddress": address}
        receiver_filter = {**time_filter, "toAddress": address}
        caller_filter = {**time_filter, "callerAddress": address}

        top_contracts_pipeline = [
            {"$match": caller_filter},
            {"$group": {"_id": "$contractAddress", "count": {"$sum": 1}}},
            {"$project": {"_id": 0, "contractAddress": "$_id", "count": 1}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]

        (
            sender_count_result,
            sender_recent,
            receiver_count_result,
            receiver_recent,
            caller_count_result,
            caller_recent,
            top_contracts,
        ) = await asyncio.gather(
            run_pipeline(db, "transaction", [
                {"$match": sender_filter}, {"$count": "count"},
            ]),
            find_many(
                db, "transaction", sender_filter,
                sort=[("timeStamp", DESCENDING)], limit=limit,
            ),
            run_pipeline(db, "transaction", [
                {"$match": receiver_filter}, {"$count": "count"},
            ]),
            find_many(
                db, "transaction", receiver_filter,
                sort=[("timeStamp", DESCENDING)], limit=limit,
            ),
            run_pipeline(db, "contractevent", [
                {"$match": caller_filter}, {"$count": "count"},
            ]),
            find_many(
                db, "contractevent", caller_filter,
                sort=[("timeStamp", DESCENDING)], limit=limit,
            ),
            run_pipeline(db, "contractevent", top_contracts_pipeline),
        )

        return {
            "as_sender": {
                "count": sender_count_result[0]["count"] if sender_count_result else 0,
                "recent": sender_recent,
            },
            "as_receiver": {
                "count": receiver_count_result[0]["count"] if receiver_count_result else 0,
                "recent": receiver_recent,
            },
            "as_contract_caller": {
                "count": caller_count_result[0]["count"] if caller_count_result else 0,
                "top_contracts": top_contracts,
                "recent": caller_recent,
            },
        }
