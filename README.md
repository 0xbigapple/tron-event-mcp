# tron-event-mcp

TRON blockchain event data query MCP Server — let AI assistants analyze on-chain data directly.

Works with [event-plugin](https://github.com/317787106/event-plugin): event-plugin writes TRON on-chain events into MongoDB in real time, and this project exposes that data to AI assistants (Claude, Cursor, etc.) via the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/), enabling natural-language-driven on-chain data analysis.

## Data Source

event-plugin listens to a Java-tron node and writes the following 7 event types into MongoDB:

| Collection | Description | Unique Index |
|------------|-------------|--------------|
| `block` | Block event, triggered for every new block | `blockNumber` |
| `transaction` | Transaction event, triggered for every packaged transaction | `transactionId` |
| `contractevent` | Contract event, triggered when a smart contract emits an event (ABI-decoded) | `uniqueId` |
| `contractlog` | Contract raw log, not ABI-decoded (hex data) | `uniqueId` |
| `solidity` | Solidity trigger, fired when a block is finalized | `latestSolidifiedBlockNumber` |
| `solidityevent` | Solidified contract event, same structure as `contractevent` | `uniqueId` |
| `soliditylog` | Solidified contract raw log, same structure as `contractlog` | `uniqueId` |

## Available Tools

### Metadata
| Tool | Description |
|------|-------------|
| `describe_schema` | Return field descriptions, index info, and business meaning for all collections |
| `get_collection_stats` | Return document count and earliest/latest timestamps per collection |

### Query
| Tool | Description |
|------|-------------|
| `search_contract_activity` | Query events/logs for a specific contract, with event name and time range filters |
| `query_events` | General-purpose query with arbitrary filters and field projection |
| `count_events` | Quickly count documents matching given criteria |
| `get_block` | Look up a block by height |
| `get_transaction` | Look up a transaction by hash |

### Aggregation & Analytics
| Tool | Description |
|------|-------------|
| `aggregate_field` | Compute sum / avg / min / max on a specified field |
| `group_by_field` | Group-by aggregation for address rankings, event distribution, etc. |
| `aggregate_by_time` | Time-series aggregation (hour / day / week) with optional sum field |
| `get_top_contracts` | Leaderboard of most active contracts in a time range |

### Cross-Collection
| Tool | Description |
|------|-------------|
| `get_transaction_full` | Full transaction view: details + associated contract events |
| `get_address_profile` | Address activity profile across sender, receiver, and contract caller roles |

### Distribution Analysis
| Tool | Description |
|------|-------------|
| `histogram` | Numeric field bucketing with auto or manual boundaries |
| `percentiles` | Compute percentiles (P50 / P90 / P95 / P99, etc.) |

## Quick Start

### Prerequisites

- Python >= 3.11
- MongoDB >= 7.0 (the `percentiles` tool uses the `$percentile` aggregation operator, which requires 7.0+; all other tools work with 5.0+)

### Installation

```bash
cd tron-event-mcp
make setup
```

### Configuration

Edit the `.env` file (`make setup` copies it from `.env.example` automatically):

```bash
# MongoDB connection (strongly recommended to use a read-only user)
MONGO_URI=mongodb://readonly_user:password@host:27017/dbname?authSource=admin
MONGO_DB=tron

# Maximum documents per query (prevents fetching massive datasets)
MAX_RESULT_LIMIT=500

# Query timeout in milliseconds
QUERY_TIMEOUT_MS=10000
```

### Running

```bash
# stdio mode (for local clients like Claude Code, Cursor, etc.)
make run

# SSE mode (for remote access)
make run-sse
```

### Integration with Claude Code

Add the following to your Claude Code MCP configuration:

```json
{
  "mcpServers": {
    "tron-events": {
      "command": "/path/to/tron-event-mcp/.venv/bin/python",
      "args": ["-m", "tron_event_mcp"]
    }
  }
}
```

### Integration with Cursor

In Cursor Settings > MCP, add the same configuration as above.

## Usage Examples

Once connected, you can ask questions in natural language:

- "What are the most active contracts in the last 24 hours?"
- "Show me the hourly USDT Transfer event volume trend"
- "Analyze the on-chain activity of address TXxx..."
- "What does the energy consumption distribution look like for transactions?"
- "Show me the full details of transaction abc123..."

The AI assistant will automatically select the right combination of tools to answer.

## Project Structure

```
tron-event-mcp/
├── src/tron_event_mcp/
│   ├── server.py            # MCP Server entry point; registers all tools and resources
│   ├── config.py            # Configuration management (env vars / .env)
│   ├── db/                  # MongoDB connection and query layer
│   ├── tools/
│   │   ├── schema.py        # describe_schema, get_collection_stats
│   │   ├── query.py         # get_recent_events, get_block, get_transaction, query_events
│   │   ├── analytics.py     # search_contract_activity, aggregate_field, group_by_field, etc.
│   │   ├── cross_collection.py  # get_transaction_full, get_address_profile
│   │   └── distribution.py  # histogram, percentiles
│   └── resources/           # MCP Resources (documentation resources)
├── tests/
├── pyproject.toml
├── Makefile
└── .env.example
```

## Security Notes

- **Use a read-only MongoDB user** — this tool only performs queries, no write access needed
- Query filters forbid `$where`, `$function`, `$accumulator` and other code-execution operators
- `MAX_RESULT_LIMIT` caps documents per request, protecting database performance
- `QUERY_TIMEOUT_MS` enforces query timeout, preventing slow queries from blocking

## License

MIT
