"""
Tests for tools/query.py: get_recent_events, get_block, get_transaction, query_events.
"""

from unittest.mock import patch
from pymongo import ASCENDING, DESCENDING

import pytest

from tests.conftest import (
    CaptureMCP, make_mock_db,
    SAMPLE_BLOCK, SAMPLE_TRANSACTION, SAMPLE_CONTRACT_EVENT,
)
from tron_event_mcp.tools.query import register_query_tools


@pytest.fixture
def tools() -> dict:
    mcp = CaptureMCP()
    register_query_tools(mcp)
    return mcp._tools


# ---------------------------------------------------------------------------
# get_recent_events
# ---------------------------------------------------------------------------

class TestGetRecentEvents:
    async def test_returns_data_from_db(self, tools):
        db, _ = make_mock_db(find_data=[SAMPLE_BLOCK])
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            result = await tools["get_recent_events"](collection="block", limit=5)
        assert result == [SAMPLE_BLOCK]

    async def test_sorts_by_timestamp_descending(self, tools):
        db, col = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            await tools["get_recent_events"](collection="block", limit=5)
        col.find.return_value.sort.assert_called_once_with([("timeStamp", DESCENDING)])

    async def test_default_limit_is_10(self, tools):
        db, col = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            await tools["get_recent_events"](collection="block")
        col.find.return_value.limit.assert_called_once_with(10)

    async def test_limit_capped_at_100(self, tools):
        """get_recent_events caps limit at 100, independent of the global max_result_limit."""
        db, col = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            await tools["get_recent_events"](collection="block", limit=9999)
        col.find.return_value.limit.assert_called_once_with(100)

    async def test_empty_collection_returns_empty_list(self, tools):
        db, _ = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            result = await tools["get_recent_events"](collection="transaction")
        assert result == []

    async def test_all_valid_collections_accepted(self, tools):
        for col_name in ("block", "transaction", "contractevent", "contractlog",
                          "solidity", "solidityevent", "soliditylog"):
            db, _ = make_mock_db(find_data=[])
            with patch("tron_event_mcp.tools.query.get_db", return_value=db):
                result = await tools["get_recent_events"](collection=col_name)
            assert isinstance(result, list)


# ---------------------------------------------------------------------------
# get_block
# ---------------------------------------------------------------------------

class TestGetBlock:
    async def test_returns_block_when_found(self, tools):
        db, _ = make_mock_db(find_one_data=SAMPLE_BLOCK)
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            result = await tools["get_block"](block_number=64000000)
        assert result == SAMPLE_BLOCK

    async def test_returns_none_when_not_found(self, tools):
        db, _ = make_mock_db(find_one_data=None)
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            result = await tools["get_block"](block_number=999999999)
        assert result is None

    async def test_queries_by_block_number(self, tools):
        db, col = make_mock_db(find_one_data=None)
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            await tools["get_block"](block_number=12345)
        col.find_one.assert_called_once()
        call_filter = col.find_one.call_args[0][0]
        assert call_filter == {"blockNumber": 12345}


# ---------------------------------------------------------------------------
# get_transaction
# ---------------------------------------------------------------------------

class TestGetTransaction:
    async def test_returns_transaction_when_found(self, tools):
        db, _ = make_mock_db(find_one_data=SAMPLE_TRANSACTION)
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            result = await tools["get_transaction"](transaction_id="abc123")
        assert result == SAMPLE_TRANSACTION

    async def test_returns_none_when_not_found(self, tools):
        db, _ = make_mock_db(find_one_data=None)
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            result = await tools["get_transaction"](transaction_id="nonexistent")
        assert result is None

    async def test_queries_by_transaction_id(self, tools):
        db, col = make_mock_db(find_one_data=None)
        tx_id = "deadbeef" * 8
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            await tools["get_transaction"](transaction_id=tx_id)
        call_filter = col.find_one.call_args[0][0]
        assert call_filter == {"transactionId": tx_id}


# ---------------------------------------------------------------------------
# query_events
# ---------------------------------------------------------------------------

class TestQueryEvents:
    async def test_returns_matching_documents(self, tools):
        db, _ = make_mock_db(find_data=[SAMPLE_TRANSACTION])
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            result = await tools["query_events"](
                collection="transaction",
                filters={"result": "FAILED"},
            )
        assert result == [SAMPLE_TRANSACTION]

    async def test_default_sort_is_timestamp_desc(self, tools):
        db, col = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            await tools["query_events"](collection="block")
        col.find.return_value.sort.assert_called_once_with([("timeStamp", DESCENDING)])

    async def test_asc_sort_order(self, tools):
        db, col = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            await tools["query_events"](collection="block", sort_order="asc")
        col.find.return_value.sort.assert_called_once_with([("timeStamp", ASCENDING)])

    async def test_custom_sort_field(self, tools):
        db, col = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            await tools["query_events"](collection="block", sort_by="blockNumber")
        col.find.return_value.sort.assert_called_once_with([("blockNumber", DESCENDING)])

    async def test_skip_is_passed_through(self, tools):
        db, col = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            await tools["query_events"](collection="transaction", skip=40)
        col.find.return_value.skip.assert_called_once_with(40)

    async def test_fields_projection_applied(self, tools):
        db, col = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            await tools["query_events"](
                collection="transaction",
                fields=["transactionId", "result"],
            )
        proj = col.find.call_args[0][1]
        assert proj.get("transactionId") == 1
        assert proj.get("result") == 1
        assert proj.get("_id") == 0  # _id always excluded

    async def test_blocked_operator_raises(self, tools):
        db, _ = make_mock_db()
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            with pytest.raises(ValueError, match=r"\$where"):
                await tools["query_events"](
                    collection="block",
                    filters={"$where": "sleep(5000)"},
                )

    async def test_nested_blocked_operator_raises(self, tools):
        db, _ = make_mock_db()
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            with pytest.raises(ValueError):
                await tools["query_events"](
                    collection="transaction",
                    filters={"$or": [{"$where": "1==1"}]},
                )

    async def test_empty_filters_returns_all(self, tools):
        data = [SAMPLE_BLOCK, SAMPLE_BLOCK]
        db, col = make_mock_db(find_data=data)
        with patch("tron_event_mcp.tools.query.get_db", return_value=db):
            result = await tools["query_events"](collection="block", filters={})
        assert len(result) == 2
