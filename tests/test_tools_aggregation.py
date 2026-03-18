"""
Tests for additional aggregation tools: count_events, aggregate_field, group_by_field,
and the sum_field extension for aggregate_by_time.
"""

from unittest.mock import patch

import pytest

from tests.conftest import CaptureMCP, make_mock_db
from tron_event_mcp.tools.analytics import register_analytics_tools


@pytest.fixture
def tools() -> dict:
    mcp = CaptureMCP()
    register_analytics_tools(mcp)
    return mcp._tools


# ---------------------------------------------------------------------------
# count_events
# ---------------------------------------------------------------------------

class TestCountEvents:
    async def test_returns_count(self, tools):
        db, col = make_mock_db(aggregate_data=[{"count": 28798}])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            result = await tools["count_events"](collection="contractevent")
        assert result == {"count": 28798}

    async def test_empty_collection_returns_zero(self, tools):
        db, _ = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            result = await tools["count_events"](collection="contractevent")
        assert result == {"count": 0}

    async def test_pipeline_uses_count_stage(self, tools):
        db, col = make_mock_db(aggregate_data=[{"count": 0}])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["count_events"](collection="contractevent")
        pipeline = col.aggregate.call_args[0][0]
        stages = [list(s.keys())[0] for s in pipeline]
        assert "$match" in stages
        assert "$count" in stages

    async def test_contract_address_filter_applied(self, tools):
        db, col = make_mock_db(aggregate_data=[{"count": 100}])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["count_events"](
                collection="contractevent",
                contract_address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
                event_name="Transfer",
            )
        pipeline = col.aggregate.call_args[0][0]
        match = next(s["$match"] for s in pipeline if "$match" in s)
        assert match["contractAddress"] == "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
        assert match["eventName"] == "Transfer"

    async def test_event_name_ignored_for_non_event_collection(self, tools):
        db, col = make_mock_db(aggregate_data=[{"count": 5}])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["count_events"](
                collection="contractlog",
                event_name="Transfer",
            )
        pipeline = col.aggregate.call_args[0][0]
        match = next(s["$match"] for s in pipeline if "$match" in s)
        assert "eventName" not in match

    async def test_time_range_in_match(self, tools):
        db, col = make_mock_db(aggregate_data=[{"count": 10}])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["count_events"](
                collection="contractevent",
                start_timestamp=1_000_000_000_000,
                end_timestamp=2_000_000_000_000,
            )
        pipeline = col.aggregate.call_args[0][0]
        match = next(s["$match"] for s in pipeline if "$match" in s)
        assert match["timeStamp"]["$gte"] == 1_000_000_000_000
        assert match["timeStamp"]["$lte"] == 2_000_000_000_000

    async def test_extra_filters_merged(self, tools):
        db, col = make_mock_db(aggregate_data=[{"count": 3}])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["count_events"](
                collection="transaction",
                filters={"result": "FAILED"},
            )
        pipeline = col.aggregate.call_args[0][0]
        match = next(s["$match"] for s in pipeline if "$match" in s)
        assert match["result"] == "FAILED"

    async def test_blocked_operator_raises(self, tools):
        db, _ = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            with pytest.raises(ValueError, match="operator not allowed"):
                await tools["count_events"](
                    collection="contractevent",
                    filters={"$where": "1==1"},
                )


# ---------------------------------------------------------------------------
# aggregate_field
# ---------------------------------------------------------------------------

class TestAggregateField:
    async def test_returns_aggregated_values(self, tools):
        data = [{"count": 28798, "sum": 9876543210000, "avg": 342857.3}]
        db, _ = make_mock_db(aggregate_data=data)
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            result = await tools["aggregate_field"](
                collection="contractevent",
                field="dataMap.value",
                operations=["sum", "avg", "count"],
            )
        assert result["sum"] == 9876543210000
        assert result["count"] == 28798

    async def test_empty_result_returns_none_values(self, tools):
        db, _ = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            result = await tools["aggregate_field"](
                collection="contractevent",
                field="dataMap.value",
                operations=["sum", "count"],
            )
        assert result["sum"] is None
        assert result["count"] is None

    async def test_pipeline_has_group_with_tolng(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["aggregate_field"](
                collection="contractevent",
                field="dataMap.value",
                operations=["sum"],
            )
        pipeline = col.aggregate.call_args[0][0]
        group = next(s["$group"] for s in pipeline if "$group" in s)
        assert group["sum"] == {"$sum": {"$toLong": "$dataMap.value"}}

    async def test_count_in_group_does_not_use_field(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["aggregate_field"](
                collection="contractevent",
                field="dataMap.value",
                operations=["sum", "count"],
            )
        pipeline = col.aggregate.call_args[0][0]
        group = next(s["$group"] for s in pipeline if "$group" in s)
        assert group["count"] == {"$sum": 1}

    async def test_contract_filter_applied(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        addr = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["aggregate_field"](
                collection="contractevent",
                field="dataMap.value",
                contract_address=addr,
                event_name="Transfer",
            )
        pipeline = col.aggregate.call_args[0][0]
        match = next(s["$match"] for s in pipeline if "$match" in s)
        assert match["contractAddress"] == addr
        assert match["eventName"] == "Transfer"

    async def test_invalid_field_raises(self, tools):
        db, _ = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            with pytest.raises(ValueError, match="invalid field name"):
                await tools["aggregate_field"](
                    collection="contractevent",
                    field="$injected",
                )

    async def test_all_operations_produce_group_keys(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["aggregate_field"](
                collection="contractevent",
                field="dataMap.value",
                operations=["sum", "avg", "min", "max", "count"],
            )
        pipeline = col.aggregate.call_args[0][0]
        group = next(s["$group"] for s in pipeline if "$group" in s)
        for op in ("sum", "avg", "min", "max", "count"):
            assert op in group


# ---------------------------------------------------------------------------
# group_by_field
# ---------------------------------------------------------------------------

class TestGroupByField:
    async def test_returns_grouped_data(self, tools):
        data = [
            {"group": "TAddr1", "value": 5000000000, "count": 10},
            {"group": "TAddr2", "value": 2000000000, "count": 5},
        ]
        db, _ = make_mock_db(aggregate_data=data)
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            result = await tools["group_by_field"](
                collection="contractevent",
                group_field="topicMap.to",
                agg_field="dataMap.value",
            )
        assert result == data

    async def test_count_only_mode_when_no_agg_field(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["group_by_field"](
                collection="contractevent",
                group_field="contractAddress",
            )
        pipeline = col.aggregate.call_args[0][0]
        group = next(s["$group"] for s in pipeline if "$group" in s)
        assert "value" not in group
        assert group["count"] == {"$sum": 1}

    async def test_agg_field_produces_value_in_group(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["group_by_field"](
                collection="contractevent",
                group_field="topicMap.to",
                agg_field="dataMap.value",
                agg_op="sum",
            )
        pipeline = col.aggregate.call_args[0][0]
        group = next(s["$group"] for s in pipeline if "$group" in s)
        assert group["value"] == {"$sum": {"$toLong": "$dataMap.value"}}

    async def test_sort_descending_by_default(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["group_by_field"](
                collection="contractevent",
                group_field="contractAddress",
            )
        pipeline = col.aggregate.call_args[0][0]
        sort = next(s["$sort"] for s in pipeline if "$sort" in s)
        assert list(sort.values())[0] == -1

    async def test_sort_ascending(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["group_by_field"](
                collection="contractevent",
                group_field="contractAddress",
                sort_order="asc",
            )
        pipeline = col.aggregate.call_args[0][0]
        sort = next(s["$sort"] for s in pipeline if "$sort" in s)
        assert list(sort.values())[0] == 1

    async def test_top_n_capped_at_100(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["group_by_field"](
                collection="contractevent",
                group_field="contractAddress",
                top_n=9999,
            )
        pipeline = col.aggregate.call_args[0][0]
        limit = next(s["$limit"] for s in pipeline if "$limit" in s)
        assert limit == 100

    async def test_contract_filter_applied(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        addr = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["group_by_field"](
                collection="contractevent",
                group_field="topicMap.to",
                contract_address=addr,
                event_name="Transfer",
            )
        pipeline = col.aggregate.call_args[0][0]
        match = next(s["$match"] for s in pipeline if "$match" in s)
        assert match["contractAddress"] == addr
        assert match["eventName"] == "Transfer"

    async def test_invalid_group_field_raises(self, tools):
        db, _ = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            with pytest.raises(ValueError, match="invalid field name"):
                await tools["group_by_field"](
                    collection="contractevent",
                    group_field="$bad",
                )

    async def test_invalid_agg_field_raises(self, tools):
        db, _ = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            with pytest.raises(ValueError, match="invalid field name"):
                await tools["group_by_field"](
                    collection="contractevent",
                    group_field="contractAddress",
                    agg_field="$bad",
                )


# ---------------------------------------------------------------------------
# aggregate_by_time (sum_field extension)
# ---------------------------------------------------------------------------

class TestAggregateByTimeWithSumField:
    async def test_sum_field_added_to_group_spec(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["aggregate_by_time"](
                collection="contractevent",
                granularity="day",
                sum_field="dataMap.value",
            )
        pipeline = col.aggregate.call_args[0][0]
        group = next(s["$group"] for s in pipeline if "$group" in s)
        assert "sum" in group
        assert group["sum"] == {"$sum": {"$toLong": "$dataMap.value"}}

    async def test_sum_field_in_project(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["aggregate_by_time"](
                collection="contractevent",
                granularity="day",
                sum_field="dataMap.value",
            )
        pipeline = col.aggregate.call_args[0][0]
        project = next(s["$project"] for s in pipeline if "$project" in s)
        assert project.get("sum") == 1

    async def test_no_sum_field_omits_sum_key(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["aggregate_by_time"](collection="block", granularity="day")
        pipeline = col.aggregate.call_args[0][0]
        group = next(s["$group"] for s in pipeline if "$group" in s)
        assert "sum" not in group

    async def test_invalid_sum_field_raises(self, tools):
        db, _ = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            with pytest.raises(ValueError, match="invalid field name"):
                await tools["aggregate_by_time"](
                    collection="contractevent",
                    sum_field="$injected",
                )


# ---------------------------------------------------------------------------
# top_events_by_value
# ---------------------------------------------------------------------------

class TestTopEventsByValue:
    async def test_pipeline_uses_addfields_and_tolng(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["top_events_by_value"](
                collection="contractevent",
                sort_field="dataMap.value",
            )
        pipeline = col.aggregate.call_args[0][0]
        add_fields = next(s["$addFields"] for s in pipeline if "$addFields" in s)
        assert add_fields["_sort_val"] == {"$toLong": "$dataMap.value"}

    async def test_sort_descending_by_default(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["top_events_by_value"](
                collection="contractevent",
                sort_field="dataMap.value",
            )
        pipeline = col.aggregate.call_args[0][0]
        sort = next(s["$sort"] for s in pipeline if "$sort" in s)
        assert sort["_sort_val"] == -1

    async def test_sort_ascending(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["top_events_by_value"](
                collection="contractevent",
                sort_field="dataMap.value",
                sort_order="asc",
            )
        pipeline = col.aggregate.call_args[0][0]
        sort = next(s["$sort"] for s in pipeline if "$sort" in s)
        assert sort["_sort_val"] == 1

    async def test_top_n_capped_at_100(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["top_events_by_value"](
                collection="contractevent",
                sort_field="dataMap.value",
                top_n=9999,
            )
        pipeline = col.aggregate.call_args[0][0]
        limit = next(s["$limit"] for s in pipeline if "$limit" in s)
        assert limit == 100

    async def test_contract_filter_applied(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        addr = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["top_events_by_value"](
                collection="contractevent",
                sort_field="dataMap.value",
                contract_address=addr,
                event_name="Transfer",
            )
        pipeline = col.aggregate.call_args[0][0]
        match = next(s["$match"] for s in pipeline if "$match" in s)
        assert match["contractAddress"] == addr
        assert match["eventName"] == "Transfer"

    async def test_fields_projection(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["top_events_by_value"](
                collection="contractevent",
                sort_field="dataMap.value",
                fields=["transactionId", "blockNumber"],
            )
        pipeline = col.aggregate.call_args[0][0]
        project = next(s["$project"] for s in pipeline if "$project" in s)
        assert project["transactionId"] == 1
        assert project["blockNumber"] == 1
        assert project["_id"] == 0
        assert project["_sort_val"] == 0

    async def test_no_fields_still_excludes_sort_val(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["top_events_by_value"](
                collection="contractevent",
                sort_field="dataMap.value",
            )
        pipeline = col.aggregate.call_args[0][0]
        project = next(s["$project"] for s in pipeline if "$project" in s)
        assert project["_sort_val"] == 0
        assert project["_id"] == 0

    async def test_invalid_sort_field_raises(self, tools):
        db, _ = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            with pytest.raises(ValueError, match="invalid field name"):
                await tools["top_events_by_value"](
                    collection="contractevent",
                    sort_field="$injected",
                )

    async def test_invalid_fields_item_raises(self, tools):
        db, _ = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            with pytest.raises(ValueError, match="invalid field name"):
                await tools["top_events_by_value"](
                    collection="contractevent",
                    sort_field="dataMap.value",
                    fields=["$bad"],
                )

    async def test_returns_data(self, tools):
        data = [
            {"transactionId": "abc", "dataMap": {"value": "9999999999"}},
            {"transactionId": "def", "dataMap": {"value": "5000000000"}},
        ]
        db, _ = make_mock_db(aggregate_data=data)
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            result = await tools["top_events_by_value"](
                collection="contractevent",
                sort_field="dataMap.value",
                top_n=2,
            )
        assert result == data

    async def test_time_range_in_match(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.analytics.get_db", return_value=db):
            await tools["top_events_by_value"](
                collection="contractevent",
                sort_field="dataMap.value",
                start_timestamp=1_000_000_000_000,
                end_timestamp=2_000_000_000_000,
            )
        pipeline = col.aggregate.call_args[0][0]
        match = next(s["$match"] for s in pipeline if "$match" in s)
        assert match["timeStamp"]["$gte"] == 1_000_000_000_000
        assert match["timeStamp"]["$lte"] == 2_000_000_000_000
