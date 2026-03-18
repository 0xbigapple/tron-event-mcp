"""
Tests for tools/cross_collection.py: get_transaction_full, get_address_profile.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import (
    CaptureMCP, make_cursor,
    SAMPLE_TRANSACTION, SAMPLE_CONTRACT_EVENT,
)
from tron_event_mcp.tools.cross_collection import register_cross_collection_tools


@pytest.fixture
def tools() -> dict:
    mcp = CaptureMCP()
    register_cross_collection_tools(mcp)
    return mcp._tools


# ---------------------------------------------------------------------------
# get_transaction_full
# ---------------------------------------------------------------------------

class TestGetTransactionFull:
    def _make_db(self, tx_data=None, events_data=None):
        """Build a mock db that returns different collections by name."""
        tx_col = MagicMock()
        tx_col.find_one = AsyncMock(return_value=tx_data)
        tx_col.find.return_value = make_cursor(events_data or [])

        event_col = MagicMock()
        event_col.find.return_value = make_cursor(events_data or [])
        event_col.find_one = AsyncMock(return_value=None)

        def getitem(name):
            if name == "transaction":
                return tx_col
            if name == "contractevent":
                return event_col
            return MagicMock()

        db = MagicMock()
        db.__getitem__ = MagicMock(side_effect=getitem)
        return db

    async def test_returns_transaction_and_events(self, tools):
        events = [SAMPLE_CONTRACT_EVENT]
        db = self._make_db(tx_data=SAMPLE_TRANSACTION, events_data=events)
        with patch("tron_event_mcp.tools.cross_collection.get_db", return_value=db):
            result = await tools["get_transaction_full"](
                transaction_id=SAMPLE_TRANSACTION["transactionId"]
            )
        assert result["transaction"] == SAMPLE_TRANSACTION
        assert result["events"] == events

    async def test_transaction_not_found_returns_none_tx(self, tools):
        db = self._make_db(tx_data=None, events_data=[])
        with patch("tron_event_mcp.tools.cross_collection.get_db", return_value=db):
            result = await tools["get_transaction_full"](transaction_id="nonexistent")
        assert result["transaction"] is None
        assert result["events"] == []

    async def test_no_events_returns_empty_list(self, tools):
        db = self._make_db(tx_data=SAMPLE_TRANSACTION, events_data=[])
        with patch("tron_event_mcp.tools.cross_collection.get_db", return_value=db):
            result = await tools["get_transaction_full"](
                transaction_id=SAMPLE_TRANSACTION["transactionId"]
            )
        assert result["transaction"] == SAMPLE_TRANSACTION
        assert result["events"] == []


# ---------------------------------------------------------------------------
# get_address_profile
# ---------------------------------------------------------------------------

class TestGetAddressProfile:
    def _make_db(self, find_data=None, aggregate_data=None):
        """
        Build a mock db supporting find (for recent records) and aggregate
        (for count + top_contracts). All aggregate calls return the same result.
        """
        col = MagicMock()
        col.find.return_value = make_cursor(find_data or [])
        col.find_one = AsyncMock(return_value=None)
        col.aggregate.return_value = make_cursor(aggregate_data or [])

        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=col)
        return db, col

    async def test_returns_three_dimensions(self, tools):
        db, _ = self._make_db()
        with patch("tron_event_mcp.tools.cross_collection.get_db", return_value=db):
            result = await tools["get_address_profile"](address="TTestAddr")
        assert "as_sender" in result
        assert "as_receiver" in result
        assert "as_contract_caller" in result

    async def test_each_dimension_has_count_and_recent(self, tools):
        db, _ = self._make_db()
        with patch("tron_event_mcp.tools.cross_collection.get_db", return_value=db):
            result = await tools["get_address_profile"](address="TTestAddr")
        for key in ("as_sender", "as_receiver", "as_contract_caller"):
            assert "count" in result[key]
            assert "recent" in result[key]

    async def test_contract_caller_has_top_contracts(self, tools):
        db, _ = self._make_db()
        with patch("tron_event_mcp.tools.cross_collection.get_db", return_value=db):
            result = await tools["get_address_profile"](address="TTestAddr")
        assert "top_contracts" in result["as_contract_caller"]

    async def test_count_zero_when_no_data(self, tools):
        db, _ = self._make_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.cross_collection.get_db", return_value=db):
            result = await tools["get_address_profile"](address="TEmptyAddr")
        assert result["as_sender"]["count"] == 0
        assert result["as_receiver"]["count"] == 0
        assert result["as_contract_caller"]["count"] == 0

    async def test_recent_limit_capped_at_50(self, tools):
        db, col = self._make_db(find_data=[])
        with patch("tron_event_mcp.tools.cross_collection.get_db", return_value=db):
            await tools["get_address_profile"](address="TTestAddr", recent_limit=999)
        # Verify all find calls have limit <= 50
        for call_args in col.find.return_value.limit.call_args_list:
            assert call_args[0][0] <= 50

    async def test_default_recent_limit_is_10(self, tools):
        db, col = self._make_db(find_data=[])
        with patch("tron_event_mcp.tools.cross_collection.get_db", return_value=db):
            await tools["get_address_profile"](address="TTestAddr")
        for call_args in col.find.return_value.limit.call_args_list:
            assert call_args[0][0] == 10

    async def test_with_count_result(self, tools):
        """When aggregate $count returns data, count should be correctly extracted."""
        col = MagicMock()
        col.find.return_value = make_cursor([])
        col.find_one = AsyncMock(return_value=None)

        # Multiple aggregate calls return different results
        count_results = [
            [{"count": 10}],   # sender count
            [{"count": 5}],    # receiver count
            [{"count": 20}],   # caller count
            [],
            [],
            [],
            [{"contractAddress": "T001", "count": 15}],  # top_contracts
        ]
        col.aggregate.side_effect = [make_cursor(r) for r in count_results]

        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=col)

        with patch("tron_event_mcp.tools.cross_collection.get_db", return_value=db):
            result = await tools["get_address_profile"](address="TTestAddr")
        assert result["as_sender"]["count"] == 10
        assert result["as_receiver"]["count"] == 5
        assert result["as_contract_caller"]["count"] == 20
