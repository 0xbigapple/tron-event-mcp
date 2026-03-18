"""MCP Resources: static documentation exposed as resources for LLM context."""

from mcp.server.fastmcp import FastMCP


def register_resources(mcp: FastMCP) -> None:
    """Register documentation resources on the given MCP server instance."""

    @mcp.resource("tron://event-types")
    def get_event_types() -> str:
        """
        TRON event type quick reference.
        Describes the business meaning, trigger timing, and key fields
        of all 7 event types.
        Loaded as static context automatically; does not consume a tool call.
        """
        return """\
# TRON Event Types

## 7 Event Types Reference

| triggerName | collection | Trigger Timing | Unique Key Field |
|---|---|---|---|
| blockTrigger | block | Every new block produced | blockNumber |
| transactionTrigger | transaction | Transaction packaged into a block | transactionId |
| contractEventTrigger | contractevent | Contract emits an event (ABI-decoded) | uniqueId |
| contractLogTrigger | contractlog | Contract LOG operation (raw hex) | uniqueId |
| solidityTrigger | solidity | Block is finalized (solidified) | latestSolidifiedBlockNumber |
| solidityEventTrigger | solidityevent | Solidified contract event | uniqueId |
| solidityLogTrigger | soliditylog | Solidified contract raw log | uniqueId |

## Important Differences

### contractevent vs contractlog
- **contractevent**: ABI-decoded; topicMap/dataMap contain readable key-value pairs.
  Prefer this collection for event analysis.
- **contractlog**: Raw logs; topicList is a hex string array that requires
  additional decoding to interpret.

### block/transaction vs solidityevent/soliditylog
- **block/transaction/contractevent/contractlog**: Real-time data, written as soon
  as the block is produced. There is a very small chance of chain rollback.
- **solidityevent/soliditylog**: Finalized data, confirmed by enough subsequent
  blocks. Will not be rolled back. Best for deterministic statistics and analysis.

## Timestamp Field
All collections use a `timeStamp` field with **millisecond Unix timestamps** (long type).
Time range query example:
- 2024-01-15 00:00:00 UTC = 1705276800000
- Query a single day: { "timeStamp": { "$gte": 1705276800000, "$lt": 1705363200000 } }

## Address Format
TRON addresses are Base58Check-encoded, starting with **T**, 34 characters long.
Example: TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t (USDT contract address)

## The removed Field
In contractevent, removed=true indicates the event was rolled back; the MongoDB
plugin deletes the corresponding document.
In solidityevent, removed=true never appears (solidified data is never rolled back).
"""

    @mcp.resource("tron://query-guide")
    def get_query_guide() -> str:
        """
        MCP tool usage guide describing recommended scenarios and calling order.
        """
        return """\
# TRON Event MCP Tool Usage Guide

## Recommended Workflow

### Step 1: Understand the Data
1. Call `describe_schema()` to learn the field structure of all collections.
2. Call `get_collection_stats()` to check data scale and time coverage.

### Step 2: Choose the Right Tool

| Scenario | Recommended Tool |
|---|---|
| Quick look at latest events | `get_recent_events` |
| Query by block height | `get_block` |
| Query by transaction hash | `get_transaction` |
| Query a contract's activity | `search_contract_activity` |
| Find most active contracts | `get_top_contracts` |
| Analyze event count trends | `aggregate_by_time` |
| Analyze tx success rate / energy | `get_transaction_stats` |
| Complex custom queries | `query_events` |

## Performance Tips
- Narrow down the time range to avoid full-collection scans.
- Use the `fields` parameter to return only needed fields, reducing data transfer.
- For large-scale analysis, prefer aggregation tools (get_top_contracts,
  aggregate_by_time) over fetching raw data and computing on the LLM side.

## Query Limits
- Maximum 500 documents per request (use skip for pagination).
- Single query timeout: 10 seconds.
- $where, $function and other JavaScript operators are forbidden.
"""
