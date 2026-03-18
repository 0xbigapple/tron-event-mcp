"""
Shared fixtures and test utilities.

CaptureMCP: lightweight stand-in for FastMCP that intercepts functions
registered via @mcp.tool(), allowing tool functions to be called directly
in tests without depending on FastMCP internals.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class CaptureMCP:
    """Capture tool functions registered via register_*_tools(mcp)."""

    def __init__(self):
        self._tools: dict = {}
        self._resources: dict = {}

    def tool(self):
        def decorator(func):
            self._tools[func.__name__] = func
            return func
        return decorator

    def resource(self, uri: str):
        def decorator(func):
            self._resources[uri] = func
            return func
        return decorator

    def get_tool(self, name: str):
        return self._tools[name]


# ---------------------------------------------------------------------------
# MongoDB mock helpers
# ---------------------------------------------------------------------------

def make_cursor(data: list) -> MagicMock:
    """Create a mock Motor cursor supporting chained calls (sort/skip/limit/to_list)."""
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=data)
    return cursor


def make_mock_db(
    find_data: list | None = None,
    find_one_data: dict | None = None,
    aggregate_data: list | None = None,
    count: int = 0,
) -> tuple[MagicMock, MagicMock]:
    """
    Return (mock_db, mock_collection).
    mock_db[any_collection_name] always returns the same mock_collection.
    """
    col = MagicMock()
    col.find.return_value = make_cursor(find_data or [])
    col.find_one = AsyncMock(return_value=find_one_data)
    col.count_documents = AsyncMock(return_value=count)
    col.estimated_document_count = AsyncMock(return_value=count)
    col.aggregate.return_value = make_cursor(aggregate_data or [])

    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=col)
    return db, col


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

SAMPLE_BLOCK = {
    "triggerName": "blockTrigger",
    "timeStamp": 1705276800000,
    "blockNumber": 64000000,
    "blockHash": "0xabc123",
    "transactionSize": 5,
    "latestSolidifiedBlockNumber": 63999900,
    "transactionList": ["tx1", "tx2"],
}

SAMPLE_TRANSACTION = {
    "triggerName": "transactionTrigger",
    "timeStamp": 1705276801000,
    "transactionId": "abc" * 21 + "a",  # 64 hex chars
    "blockNumber": 64000000,
    "fromAddress": "TFromAddress1234567890123456789012",
    "toAddress": "TToAddress12345678901234567890123",
    "result": "SUCCESS",
    "energyUsageTotal": 10000,
    "netFee": 100,
}

SAMPLE_CONTRACT_EVENT = {
    "triggerName": "contractEventTrigger",
    "timeStamp": 1705276802000,
    "uniqueId": "unique001",
    "contractAddress": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "callerAddress": "TCaller123456789012345678901234567",
    "blockNumber": 64000000,
    "eventName": "Transfer",
    "removed": False,
    "topicMap": {"from": "TFrom...", "to": "TTo...", "value": "1000000"},
    "dataMap": {},
}


@pytest.fixture
def capture_mcp() -> CaptureMCP:
    return CaptureMCP()
