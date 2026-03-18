"""
Tests for tools/distribution.py: histogram, percentiles.
"""

from unittest.mock import patch

import pytest

from tests.conftest import CaptureMCP, make_mock_db
from tron_event_mcp.tools.distribution import register_distribution_tools


@pytest.fixture
def tools() -> dict:
    mcp = CaptureMCP()
    register_distribution_tools(mcp)
    return mcp._tools


# ---------------------------------------------------------------------------
# histogram
# ---------------------------------------------------------------------------

class TestHistogram:
    # -- auto mode --

    async def test_auto_mode_returns_ranges(self, tools):
        raw = [
            {"min": 0, "max": 5000, "count": 100},
            {"min": 5000, "max": 10000, "count": 50},
        ]
        db, _ = make_mock_db(aggregate_data=raw)
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            result = await tools["histogram"](
                collection="transaction",
                field="energyUsageTotal",
            )
        assert len(result) == 2
        assert result[0]["range"] == "0 ~ 5000"
        assert result[0]["count"] == 100

    async def test_auto_mode_pipeline_uses_bucket_auto(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            await tools["histogram"](
                collection="transaction",
                field="energyUsageTotal",
                bucket_mode="auto",
                num_buckets=5,
            )
        pipeline = col.aggregate.call_args[0][0]
        stages = [list(s.keys())[0] for s in pipeline]
        assert "$bucketAuto" in stages

    async def test_auto_mode_num_buckets_capped_at_50(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            await tools["histogram"](
                collection="transaction",
                field="energyUsageTotal",
                num_buckets=999,
            )
        pipeline = col.aggregate.call_args[0][0]
        bucket_stage = next(s for s in pipeline if "$bucketAuto" in s)
        assert bucket_stage["$bucketAuto"]["buckets"] == 50

    async def test_auto_mode_num_buckets_min_is_2(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            await tools["histogram"](
                collection="transaction",
                field="energyUsageTotal",
                num_buckets=0,
            )
        pipeline = col.aggregate.call_args[0][0]
        bucket_stage = next(s for s in pipeline if "$bucketAuto" in s)
        assert bucket_stage["$bucketAuto"]["buckets"] == 2

    # -- manual mode --

    async def test_manual_mode_returns_ranges_with_overflow(self, tools):
        raw = [
            {"bucket": 0, "count": 100},
            {"bucket": 1000, "count": 50},
            {"bucket": "_overflow", "count": 10},
        ]
        db, _ = make_mock_db(aggregate_data=raw)
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            result = await tools["histogram"](
                collection="transaction",
                field="energyUsageTotal",
                bucket_mode="manual",
                boundaries=[0, 1000, 10000],
            )
        assert result[0]["range"] == "0 ~ 1000"
        assert result[1]["range"] == "1000 ~ 10000"
        assert result[2]["range"] == ">= 10000"
        assert result[2]["count"] == 10

    async def test_manual_mode_pipeline_uses_bucket(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            await tools["histogram"](
                collection="transaction",
                field="energyUsageTotal",
                bucket_mode="manual",
                boundaries=[0, 100, 1000],
            )
        pipeline = col.aggregate.call_args[0][0]
        stages = [list(s.keys())[0] for s in pipeline]
        assert "$bucket" in stages

    async def test_manual_mode_boundaries_sorted(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            await tools["histogram"](
                collection="transaction",
                field="energyUsageTotal",
                bucket_mode="manual",
                boundaries=[1000, 0, 500],  # unsorted input
            )
        pipeline = col.aggregate.call_args[0][0]
        bucket_stage = next(s for s in pipeline if "$bucket" in s)
        assert bucket_stage["$bucket"]["boundaries"] == [0, 500, 1000]

    async def test_manual_mode_too_few_boundaries_raises(self, tools):
        db, _ = make_mock_db()
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            with pytest.raises(ValueError, match="at least 2"):
                await tools["histogram"](
                    collection="transaction",
                    field="energyUsageTotal",
                    bucket_mode="manual",
                    boundaries=[100],
                )

    async def test_manual_mode_no_boundaries_raises(self, tools):
        db, _ = make_mock_db()
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            with pytest.raises(ValueError, match="at least 2"):
                await tools["histogram"](
                    collection="transaction",
                    field="energyUsageTotal",
                    bucket_mode="manual",
                    boundaries=None,
                )

    # -- filters --

    async def test_contract_address_filter_applied(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            await tools["histogram"](
                collection="contractevent",
                field="dataMap.value",
                contract_address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            )
        pipeline = col.aggregate.call_args[0][0]
        match_stage = next(s for s in pipeline if "$match" in s)
        assert match_stage["$match"]["contractAddress"] == "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

    async def test_time_range_filter_applied(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            await tools["histogram"](
                collection="transaction",
                field="energyUsageTotal",
                start_timestamp=1_000_000,
                end_timestamp=2_000_000,
            )
        pipeline = col.aggregate.call_args[0][0]
        match_stage = next(s for s in pipeline if "$match" in s)
        assert match_stage["$match"]["timeStamp"]["$gte"] == 1_000_000

    # -- security --

    async def test_dollar_in_field_name_rejected(self, tools):
        db, _ = make_mock_db()
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            with pytest.raises(ValueError, match="invalid field name"):
                await tools["histogram"](
                    collection="transaction",
                    field="$malicious",
                )


# ---------------------------------------------------------------------------
# percentiles
# ---------------------------------------------------------------------------

class TestPercentiles:
    async def test_returns_percentile_values(self, tools):
        raw = [{"count": 1000, "pct_values": [3200, 45000, 120000, 890000]}]
        db, _ = make_mock_db(aggregate_data=raw)
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            result = await tools["percentiles"](
                collection="transaction",
                field="energyUsageTotal",
                pcts=[0.5, 0.9, 0.95, 0.99],
            )
        assert result["count"] == 1000
        assert result["p50"] == 3200
        assert result["p90"] == 45000
        assert result["p95"] == 120000
        assert result["p99"] == 890000

    async def test_pipeline_uses_percentile_operator(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            await tools["percentiles"](
                collection="transaction",
                field="energyUsageTotal",
            )
        pipeline = col.aggregate.call_args[0][0]
        group_stage = next(s for s in pipeline if "$group" in s)
        assert "$percentile" in group_stage["$group"]["pct_values"]

    async def test_default_pcts(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            await tools["percentiles"](
                collection="transaction",
                field="energyUsageTotal",
            )
        pipeline = col.aggregate.call_args[0][0]
        group_stage = next(s for s in pipeline if "$group" in s)
        pct_config = group_stage["$group"]["pct_values"]["$percentile"]
        assert pct_config["p"] == [0.5, 0.9, 0.95, 0.99]

    async def test_empty_result_returns_none_values(self, tools):
        db, _ = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            result = await tools["percentiles"](
                collection="transaction",
                field="energyUsageTotal",
                pcts=[0.5, 0.99],
            )
        assert result["count"] == 0
        assert result["p50"] is None
        assert result["p99"] is None

    async def test_invalid_pcts_filtered_out(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            await tools["percentiles"](
                collection="transaction",
                field="energyUsageTotal",
                pcts=[0.0, 0.5, 1.0, -0.1, 1.5],  # only 0.5 is valid
            )
        pipeline = col.aggregate.call_args[0][0]
        group_stage = next(s for s in pipeline if "$group" in s)
        assert group_stage["$group"]["pct_values"]["$percentile"]["p"] == [0.5]

    async def test_all_invalid_pcts_raises(self, tools):
        db, _ = make_mock_db()
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            with pytest.raises(ValueError, match="at least one value"):
                await tools["percentiles"](
                    collection="transaction",
                    field="energyUsageTotal",
                    pcts=[0.0, 1.0],
                )

    async def test_contract_address_filter_applied(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            await tools["percentiles"](
                collection="contractevent",
                field="dataMap.value",
                contract_address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
                event_name="Transfer",
            )
        pipeline = col.aggregate.call_args[0][0]
        match_stage = next(s for s in pipeline if "$match" in s)
        assert match_stage["$match"]["contractAddress"] == "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
        assert match_stage["$match"]["eventName"] == "Transfer"

    async def test_dollar_in_field_name_rejected(self, tools):
        db, _ = make_mock_db()
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            with pytest.raises(ValueError, match="invalid field name"):
                await tools["percentiles"](
                    collection="transaction",
                    field="$inject",
                )

    async def test_approximate_method_used(self, tools):
        db, col = make_mock_db(aggregate_data=[])
        with patch("tron_event_mcp.tools.distribution.get_db", return_value=db):
            await tools["percentiles"](
                collection="transaction",
                field="energyUsageTotal",
            )
        pipeline = col.aggregate.call_args[0][0]
        group_stage = next(s for s in pipeline if "$group" in s)
        assert group_stage["$group"]["pct_values"]["$percentile"]["method"] == "approximate"
