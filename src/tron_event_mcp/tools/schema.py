"""Schema tools: collection field definitions and statistics."""

import asyncio

from mcp.server.fastmcp import FastMCP
from pymongo.errors import PyMongoError

from tron_event_mcp.db.client import get_db
from tron_event_mcp.config import get_settings

# Field descriptions for each collection (derived from Java Trigger class definitions).
SCHEMA_DEFINITIONS: dict = {
    "block": {
        "description": "Block event, triggered once per new block",
        "trigger_name": "blockTrigger",
        "unique_index": "blockNumber",
        "fields": {
            "triggerName": "Trigger type, fixed value: blockTrigger",
            "timeStamp": "Block timestamp in milliseconds",
            "blockNumber": "Block height (unique index)",
            "blockHash": "Block hash",
            "transactionSize": "Number of transactions in the block",
            "latestSolidifiedBlockNumber": "Latest solidified (finalized) block height",
            "transactionList": "List of transaction IDs in the block (string array)",
        },
    },
    "transaction": {
        "description": "Transaction event, triggered once per packaged transaction",
        "trigger_name": "transactionTrigger",
        "unique_index": "transactionId",
        "fields": {
            "triggerName": "Trigger type, fixed value: transactionTrigger",
            "timeStamp": "Transaction timestamp in milliseconds",
            "transactionId": "Transaction hash (unique index)",
            "blockHash": "Hash of the containing block",
            "blockNumber": "Height of the containing block",
            "fromAddress": "Sender address",
            "toAddress": "Receiver address",
            "contractAddress": "Contract address (present for contract calls)",
            "contractType": "Contract type (e.g. TriggerSmartContract)",
            "result": "Transaction result (SUCCESS / FAILED / REVERT)",
            "contractResult": "Contract execution result",
            "feeLimit": "Fee limit in sun",
            "contractCallValue": "TRX amount sent with the call (sun)",
            "energyUsage": "Energy consumed by the caller",
            "energyFee": "Energy fee in sun",
            "originEnergyUsage": "Energy consumed by the contract deployer",
            "energyUsageTotal": "Total energy consumed",
            "netUsage": "Bandwidth consumed",
            "netFee": "Bandwidth fee in sun",
            "assetName": "Transferred asset name (for TRX / TRC10 transfers)",
            "assetAmount": "Transfer amount",
            "internalTransactionList": "List of internal transactions",
        },
    },
    "contractevent": {
        "description": (
            "Contract event, triggered when a smart contract emits an event (ABI-decoded)"
        ),
        "trigger_name": "contractEventTrigger",
        "unique_index": "uniqueId",
        "fields": {
            "triggerName": "Trigger type, fixed value: contractEventTrigger",
            "timeStamp": "Event timestamp in milliseconds",
            "uniqueId": "Unique identifier (used for upsert)",
            "transactionId": "Transaction hash that produced this event",
            "contractAddress": "Contract address",
            "callerAddress": "Caller address",
            "originAddress": "Original contract address",
            "creatorAddress": "Contract creator address",
            "blockNumber": "Block height",
            "removed": "Whether the event was reverted (true = rolled back)",
            "eventName": "Event name (e.g. Transfer, Approval)",
            "eventSignature": "Event signature SHA3 hash",
            "eventSignatureFull": "Full event signature (e.g. Transfer(address,address,uint256))",
            "topicMap": "Decoded indexed parameters as key-value pairs",
            "dataMap": "Decoded non-indexed parameters as key-value pairs",
        },
    },
    "contractlog": {
        "description": (
            "Contract raw log, triggered by smart contract LOG operations (not ABI-decoded)"
        ),
        "trigger_name": "contractLogTrigger",
        "unique_index": "uniqueId",
        "fields": {
            "triggerName": "Trigger type, fixed value: contractLogTrigger",
            "timeStamp": "Log timestamp in milliseconds",
            "uniqueId": "Unique identifier (used for upsert)",
            "transactionId": "Transaction hash that produced this log",
            "contractAddress": "Contract address",
            "callerAddress": "Caller address",
            "originAddress": "Original contract address",
            "creatorAddress": "Contract creator address",
            "blockNumber": "Block height",
            "removed": "Whether the log was reverted",
            "topicList": "Raw topic list (hex string array)",
            "data": "Raw data (hex string)",
        },
    },
    "solidity": {
        "description": "Solidity trigger, fired when a block is finalized (solidified)",
        "trigger_name": "solidityTrigger",
        "unique_index": "latestSolidifiedBlockNumber",
        "fields": {
            "triggerName": "Trigger type, fixed value: solidityTrigger",
            "timeStamp": "Solidification timestamp in milliseconds",
            "latestSolidifiedBlockNumber": "Latest solidified block height (unique index)",
        },
    },
    "solidityevent": {
        "description": "Solidified contract event, same structure as contractevent",
        "trigger_name": "solidityEventTrigger",
        "unique_index": "uniqueId",
        "fields": (
            "Same as contractevent; data has been solidified and will not be rolled back"
        ),
    },
    "soliditylog": {
        "description": "Solidified contract raw log, same structure as contractlog",
        "trigger_name": "solidityLogTrigger",
        "unique_index": "uniqueId",
        "fields": (
            "Same as contractlog; data has been solidified and will not be rolled back"
        ),
    },
}


def register_schema_tools(mcp: FastMCP) -> None:
    """Register schema introspection tools on the given MCP server instance."""

    @mcp.tool()
    async def describe_schema() -> dict:
        """
        Return complete field descriptions, index information, and business meaning
        for all collections.
        [Recommended] Call this tool before your first query to understand the data
        structure and plan your query strategy.

        Returns: { collection_name: { description, trigger_name, unique_index, fields } }
        """
        return SCHEMA_DEFINITIONS

    @mcp.tool()
    async def get_collection_stats() -> dict:
        """
        Return the approximate document count, earliest timestamp, and latest
        timestamp for each collection.
        Useful for evaluating data scale and time coverage before querying.

        Returns: { collection_name: { count, earliest_ts, latest_ts } }
        """
        db = get_db()
        settings = get_settings()

        async def _stat_one(col: str) -> tuple[str, dict]:
            """Fetch stats for a single collection."""
            try:
                count = await db[col].estimated_document_count()
                earliest = await db[col].find_one(
                    {}, {"_id": 0, "timeStamp": 1, "blockNumber": 1},
                    sort=[("timeStamp", 1)]
                )
                latest = await db[col].find_one(
                    {}, {"_id": 0, "timeStamp": 1, "blockNumber": 1},
                    sort=[("timeStamp", -1)]
                )
                return col, {
                    "count": count,
                    "earliest_ts": earliest.get("timeStamp") if earliest else None,
                    "latest_ts": latest.get("timeStamp") if latest else None,
                }
            except PyMongoError as e:
                return col, {"error": str(e)}

        pairs = await asyncio.gather(
            *[_stat_one(col) for col in settings.allowed_collections]
        )
        return dict(pairs)
