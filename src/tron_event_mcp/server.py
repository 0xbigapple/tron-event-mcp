"""MCP Server entry point: creates the FastMCP instance and registers all tools/resources."""

from mcp.server.fastmcp import FastMCP

from tron_event_mcp.config import get_settings
from tron_event_mcp.db.client import close_client
from tron_event_mcp.resources.docs import register_resources
from tron_event_mcp.tools.analytics import register_analytics_tools
from tron_event_mcp.tools.cross_collection import register_cross_collection_tools
from tron_event_mcp.tools.distribution import register_distribution_tools
from tron_event_mcp.tools.query import register_query_tools
from tron_event_mcp.tools.schema import register_schema_tools

def _create_mcp() -> FastMCP:
    """Create and configure the FastMCP server instance."""
    settings = get_settings()
    return FastMCP(
        "tron-event-mcp",
        host=settings.mcp_host,
        port=settings.mcp_port,
        instructions="""\
TRON blockchain event data query tool.

Data source: real-time TRON on-chain events stored in MongoDB across 7 collections:
block, transaction, contractevent, contractlog, solidity, solidityevent, soliditylog.

Usage recommendations:
1. Call describe_schema() first to understand the data structure
2. Call get_collection_stats() to check data scale and time coverage
3. For contract activity analysis, prefer search_contract_activity (contractevent is ABI-decoded and human-readable)
4. For total counts, use count_events — much more efficient than paginating through query_events
5. For numeric aggregation (sum/avg/min/max), use aggregate_field
6. For group-by rankings (by address, event type, etc.), use group_by_field
7. For trend analysis, use aggregate_by_time (supports sum_field for amount trends); for leaderboards, use get_top_contracts
8. For a transaction's full picture (details + contract events), use get_transaction_full
9. For an address's on-chain activity profile, use get_address_profile
10. For numeric distribution analysis, use histogram (auto/manual buckets); for percentiles, use percentiles
11. Use the general-purpose query_events only when the above tools are insufficient
""",
    )


mcp = _create_mcp()

# Register all tools and resources
register_schema_tools(mcp)
register_query_tools(mcp)
register_analytics_tools(mcp)
register_cross_collection_tools(mcp)
register_distribution_tools(mcp)
register_resources(mcp)


def main() -> None:
    """Start the MCP server using the configured transport."""
    settings = get_settings()
    mcp.run(transport=settings.mcp_transport)


if __name__ == "__main__":
    main()
