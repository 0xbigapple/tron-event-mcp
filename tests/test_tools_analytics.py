"""
Tests for tools/analytics.py: search_contract_activity, get_top_contracts,
aggregate_by_time, get_transaction_stats.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from pymongo import DESCENDING

import pytest

from tests.conftest import (
    CaptureMCP, make_mock_db,
    SAMPLE_CONTRACT_EVENT,
)
from tron_event_mcp.tools.analytics import register_analytics_tools


@pytest.fixture
def tools() -> dict:
    mcp = CaptureMCP()
    register_analytics_tools(mcp)
    return mcp._tools


# ---------------------------------------------------------------------------
# search_contract_activity
# ---------------------------------------------------------------------------

class TestSearchContractActivity:
    async def test_returns_matching_events(self, tools):
        db, _ = make_mock_db(find_data=[SAMPLE_CONTRACT_EVENT])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            result = await tools["search_contract_activity"](
                contract_address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
            )
        assert result == [SAMPLE_CONTRACT_EVENT]

    async def test_filter_includes_contract_address(self, tools):
        db, col = make_mock_db(find_data=[])
        addr = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["search_contract_activity"](contract_address=addr)
        applied_filter = col.find.call_args[0][0]
        assert applied_filter["contractAddress"] == addr

    async def test_event_name_added_for_contractevent(self, tools):
        db, col = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["search_contract_activity"](
                contract_address="Tabc",
                event_name="Transfer",
                collection="contractevent",
            )
        applied_filter = col.find.call_args[0][0]
        assert applied_filter["eventName"] == "Transfer"

    async def test_event_name_added_for_solidityevent(self, tools):
        db, col = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["search_contract_activity"](
                contract_address="Tabc",
                event_name="Approval",
                collection="solidityevent",
            )
        applied_filter = col.find.call_args[0][0]
        assert applied_filter["eventName"] == "Approval"

    async def test_event_name_ignored_for_contractlog(self, tools):
        """contractlog has no eventName field; it should not be added to the filter."""
        db, col = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["search_contract_activity"](
                contract_address="Tabc",
                event_name="Transfer",
                collection="contractlog",
            )
        applied_filter = col.find.call_args[0][0]
        assert "eventName" not in applied_filter

    async def test_time_range_filter_applied(self, tools):
        db, col = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["search_contract_activity"](
                contract_address="Tabc",
                start_timestamp=1_000_000_000_000,
                end_timestamp=2_000_000_000_000,
            )
        applied_filter = col.find.call_args[0][0]
        assert applied_filter["timeStamp"]["$gte"] == 1_000_000_000_000
        assert applied_filter["timeStamp"]["$lte"] == 2_000_000_000_000

    async def test_only_start_timestamp(self, tools):
        db, col = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["search_contract_activity"](
                contract_address="Tabc",
                start_timestamp=1_000_000_000_000,
            )
        applied_filter = col.find.call_args[0][0]
        assert "$gte" in applied_filter["timeStamp"]
        assert "$lte" not in applied_filter["timeStamp"]

    async def test_no_time_range_no_timestamp_filter(self, tools):
        db, col = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["search_contract_activity"](contract_address="Tabc")
        applied_filter = col.find.call_args[0][0]
        assert "timeStamp" not in applied_filter

    async def test_sorts_by_timestamp_descending(self, tools):
        db, col = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["search_contract_activity"](contract_address="Tabc")
        col.find.return_value.sort.assert_called_once_with([("timeStamp", DESCENDING)])

    async def test_default_collection_is_contractevent(self, tools):
        db, _ = make_mock_db(find_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db) as mock_get_db:
            await tools["search_contract_activity"](contract_address="Tabc")
        db.__getitem__.assert_called_with("contractevent")


# ---------------------------------------------------------------------------
# get_top_contracts
# ---------------------------------------------------------------------------

class TestGetTopContracts:
    async def test_returns_ranking(self, tools):
        ranking = [
            {"contractAddress": "T001", "event_count": 1000, "unique_callers": 50},
            {"contractAddress": "T002", "event_count": 500, "unique_callers": 30},
        ]
        db, _ = make_mock_db(aggregate_data=ranking)
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            result = await tools["get_top_contracts"](top_n=2)
        assert result == ranking

    async def test_pipeline_contains_group_and_sort(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["get_top_contracts"]()
        pipeline = col.aggregate.call_args[0][0]
        stages = [list(s.keys())[0] for s in pipeline]
        assert "$group" in stages
        assert "$sort" in stages
        assert "$limit" in stages

    async def test_top_n_capped_at_50(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["get_top_contracts"](top_n=9999)
        pipeline = col.aggregate.call_args[0][0]
        limit_stage = next(s for s in pipeline if "$limit" in s)
        assert limit_stage["$limit"] == 50

    async def test_time_range_in_match_stage(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["get_top_contracts"](
                start_timestamp=1_000_000,
                end_timestamp=2_000_000,
            )
        pipeline = col.aggregate.call_args[0][0]
        match_stage = next(s for s in pipeline if "$match" in s)
        assert match_stage["$match"]["timeStamp"]["$gte"] == 1_000_000
        assert match_stage["$match"]["timeStamp"]["$lte"] == 2_000_000

    async def test_empty_time_range_match_is_empty(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["get_top_contracts"]()
        pipeline = col.aggregate.call_args[0][0]
        match_stage = next(s for s in pipeline if "$match" in s)
        assert match_stage["$match"] == {}


# ---------------------------------------------------------------------------
# aggregate_by_time
# ---------------------------------------------------------------------------

class TestAggregateByTime:
    async def test_returns_time_series(self, tools):
        data = [{"period": "2024-01-15", "count": 1000}]
        db, _ = make_mock_db(aggregate_data=data)
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            result = await tools["aggregate_by_time"](collection="block", granularity="day")
        assert result == data

    @pytest.mark.parametrize("granularity,expected_format", [
        ("hour", "%Y-%m-%dT%H:00"),
        ("day",  "%Y-%m-%d"),
        ("week", "%G-W%V"),
    ])
    async def test_date_format_per_granularity(self, tools, granularity, expected_format):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["aggregate_by_time"](collection="block", granularity=granularity)
        pipeline = col.aggregate.call_args[0][0]
        group_stage = next(s for s in pipeline if "$group" in s)
        date_to_string = group_stage["$group"]["_id"]["$dateToString"]
        assert date_to_string["format"] == expected_format

    async def test_timestamp_converted_from_milliseconds(self, tools):
        """timeStamp is in milliseconds; the pipeline should use $toDate to convert it."""
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["aggregate_by_time"](collection="block", granularity="day")
        pipeline = col.aggregate.call_args[0][0]
        group_stage = next(s for s in pipeline if "$group" in s)
        date_expr = group_stage["$group"]["_id"]["$dateToString"]["date"]
        assert date_expr == {"$toDate": "$timeStamp"}

    async def test_contract_address_filter_in_pipeline(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["aggregate_by_time"](
                collection="contractevent",
                granularity="day",
                contract_address="Tabc",
            )
        pipeline = col.aggregate.call_args[0][0]
        match_stage = next(s for s in pipeline if "$match" in s)
        assert match_stage["$match"]["contractAddress"] == "Tabc"

    async def test_pipeline_sorted_ascending(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["aggregate_by_time"](collection="block", granularity="day")
        pipeline = col.aggregate.call_args[0][0]
        sort_stage = next(s for s in pipeline if "$sort" in s)
        assert sort_stage["$sort"] == {"_id": 1}


# ---------------------------------------------------------------------------
# get_transaction_stats
# ---------------------------------------------------------------------------

class TestGetTransactionStats:
    async def test_returns_three_keys(self, tools):
        db, _ = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            result = await tools["get_transaction_stats"]()
        assert "result_distribution" in result
        assert "avg_energy_usage_total" in result
        assert "contract_type_distribution" in result

    async def test_avg_energy_extracted_from_pipeline(self, tools):
        col = MagicMock()

        call_count = 0

        def make_cursor_for_call(data):
            cur = MagicMock()
            cur.to_list = AsyncMock(return_value=data)
            return cur

        # Three aggregate calls return different results in order
        results = [
            [{"result": "SUCCESS", "count": 100}],      # result_distribution
            [{"contractType": "TriggerSmartContract", "count": 80}],  # contract_type_distribution
            [{"avg_energy": 12345.6}],                  # avg_energy
        ]
        col.aggregate.side_effect = [make_cursor_for_call(r) for r in results]

        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=col)

        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            result = await tools["get_transaction_stats"]()

        assert result["avg_energy_usage_total"] == 12345.6

    async def test_avg_energy_none_when_no_data(self, tools):
        db, _ = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            result = await tools["get_transaction_stats"]()
        assert result["avg_energy_usage_total"] is None

    async def test_time_range_passed_to_pipeline(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["get_transaction_stats"](
                start_timestamp=1_000_000,
                end_timestamp=2_000_000,
            )
        # All aggregate calls should include a time filter in their first $match stage
        for agg_call in col.aggregate.call_args_list:
            pipeline = agg_call[0][0]
            match_stage = next((s for s in pipeline if "$match" in s), None)
            assert match_stage is not None
            assert "timeStamp" in match_stage["$match"]
