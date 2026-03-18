"""
Tests for tools/schema.py: describe_schema and get_collection_stats.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import CaptureMCP, make_mock_db, SAMPLE_BLOCK
from tron_event_mcp.tools.schema import register_schema_tools, SCHEMA_DEFINITIONS


@pytest.fixture
def tools() -> dict:
    mcp = CaptureMCP()
    register_schema_tools(mcp)
    return mcp._tools


# ---------------------------------------------------------------------------
# describe_schema
# ---------------------------------------------------------------------------

class TestDescribeSchema:
    async def test_returns_all_seven_collections(self, tools):
        result = await tools["describe_schema"]()
        expected = {"block", "transaction", "contractevent", "contractlog",
                    "solidity", "solidityevent", "soliditylog"}
        assert set(result.keys()) == expected

    async def test_each_collection_has_required_keys(self, tools):
        result = await tools["describe_schema"]()
        for col, schema in result.items():
            assert "description" in schema, f"{col} missing description"
            assert "trigger_name" in schema, f"{col} missing trigger_name"
            assert "unique_index" in schema, f"{col} missing unique_index"
            assert "fields" in schema, f"{col} missing fields"

    async def test_block_schema_has_correct_unique_index(self, tools):
        result = await tools["describe_schema"]()
        assert result["block"]["unique_index"] == "blockNumber"

    async def test_transaction_schema_has_correct_unique_index(self, tools):
        result = await tools["describe_schema"]()
        assert result["transaction"]["unique_index"] == "transactionId"

    async def test_contract_collections_use_unique_id(self, tools):
        result = await tools["describe_schema"]()
        for col in ("contractevent", "contractlog", "solidityevent", "soliditylog"):
            assert result[col]["unique_index"] == "uniqueId", \
                f"{col}'s unique_index should be uniqueId"

    async def test_returns_same_object_as_module_constant(self, tools):
        result = await tools["describe_schema"]()
        assert result is SCHEMA_DEFINITIONS


# ---------------------------------------------------------------------------
# get_collection_stats
# ---------------------------------------------------------------------------

class TestGetCollectionStats:
    async def test_returns_stats_for_all_collections(self, tools):
        db, col = make_mock_db(count=1000, find_one_data=SAMPLE_BLOCK)
        with patch("tron_event_mcp.tools.schema.get_db", return_value=db):
            result = await tools["get_collection_stats"]()
        assert len(result) == 7
        for col_name in ("block", "transaction", "contractevent", "contractlog",
                          "solidity", "solidityevent", "soliditylog"):
            assert col_name in result

    async def test_count_is_returned(self, tools):
        db, _ = make_mock_db(count=42, find_one_data=SAMPLE_BLOCK)
        with patch("tron_event_mcp.tools.schema.get_db", return_value=db):
            result = await tools["get_collection_stats"]()
        assert result["block"]["count"] == 42

    async def test_timestamp_is_returned(self, tools):
        db, _ = make_mock_db(count=1, find_one_data=SAMPLE_BLOCK)
        with patch("tron_event_mcp.tools.schema.get_db", return_value=db):
            result = await tools["get_collection_stats"]()
        assert result["block"]["earliest_ts"] == SAMPLE_BLOCK["timeStamp"]
        assert result["block"]["latest_ts"] == SAMPLE_BLOCK["timeStamp"]

    async def test_empty_collection_returns_none_timestamps(self, tools):
        db, _ = make_mock_db(count=0, find_one_data=None)
        with patch("tron_event_mcp.tools.schema.get_db", return_value=db):
            result = await tools["get_collection_stats"]()
        assert result["block"]["earliest_ts"] is None
        assert result["block"]["latest_ts"] is None

    async def test_db_error_does_not_crash_other_collections(self, tools):
        """When a single collection errors, the rest should still return normally."""
        call_count = 0
        original_getitem = MagicMock()

        def side_effect_getitem(name):
            nonlocal call_count
            call_count += 1
            col = MagicMock()
            if name == "block":
                col.estimated_document_count = AsyncMock(
                    side_effect=Exception("connection timeout")
                )
            else:
                col.estimated_document_count = AsyncMock(return_value=0)
                col.find_one = AsyncMock(return_value=None)
            return col

        db = MagicMock()
        db.__getitem__ = MagicMock(side_effect=side_effect_getitem)

        with patch("tron_event_mcp.tools.schema.get_db", return_value=db):
            result = await tools["get_collection_stats"]()

        assert "error" in result["block"]
        # Other collections should not have errors
        for col_name in ("transaction", "contractevent"):
            assert "error" not in result[col_name]
