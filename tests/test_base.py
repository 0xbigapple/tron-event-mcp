"""
Tests for db/repos/base.py: security guards and utility functions.
These are pure functions or simple async functions that can be tested
directly without mocking.
"""

import pytest

from tron_event_mcp.db.repos.base import (
    build_projection,
    safe_limit,
    sanitize_filter,
    validate_collection,
    find_many,
    find_one,
    run_pipeline,
)
from tests.conftest import make_mock_db


# ---------------------------------------------------------------------------
# safe_limit
# ---------------------------------------------------------------------------

class TestSafeLimit:
    def test_normal_value(self):
        assert safe_limit(20) == 20

    def test_zero_becomes_one(self):
        assert safe_limit(0) == 1

    def test_negative_becomes_one(self):
        assert safe_limit(-99) == 1

    def test_exceeds_max_is_capped(self):
        # Default max is 500 (from Settings defaults)
        assert safe_limit(10_000) == 500

    def test_exactly_at_max(self):
        assert safe_limit(500) == 500

    def test_one_below_max(self):
        assert safe_limit(499) == 499


# ---------------------------------------------------------------------------
# validate_collection
# ---------------------------------------------------------------------------

class TestValidateCollection:
    @pytest.mark.parametrize("col", [
        "block", "transaction", "contractevent",
        "contractlog", "solidity", "solidityevent", "soliditylog",
    ])
    def test_allowed_collections_pass(self, col):
        validate_collection(col)  # no exception means pass

    @pytest.mark.parametrize("col", [
        "users", "admin", "system.users", "", " ", "block; DROP TABLE",
    ])
    def test_unknown_collection_raises(self, col):
        with pytest.raises(ValueError, match="not in the allowed list"):
            validate_collection(col)


# ---------------------------------------------------------------------------
# sanitize_filter
# ---------------------------------------------------------------------------

class TestSanitizeFilter:
    def test_empty_filter_passes(self):
        assert sanitize_filter({}) == {}

    def test_normal_filter_passes(self):
        f = {"blockNumber": {"$gte": 100}, "result": "SUCCESS"}
        assert sanitize_filter(f) == f

    def test_where_operator_blocked(self):
        with pytest.raises(ValueError, match=r"\$where"):
            sanitize_filter({"$where": "sleep(1000)"})

    def test_function_operator_blocked(self):
        with pytest.raises(ValueError, match=r"\$function"):
            sanitize_filter({"$function": {"body": "...", "args": [], "lang": "js"}})

    def test_accumulator_operator_blocked(self):
        with pytest.raises(ValueError, match=r"\$accumulator"):
            sanitize_filter({"$accumulator": {}})

    def test_nested_blocked_operator_in_and(self):
        with pytest.raises(ValueError, match=r"\$where"):
            sanitize_filter({"$and": [{"$where": "1==1"}]})

    def test_nested_blocked_operator_in_or(self):
        with pytest.raises(ValueError, match=r"\$function"):
            sanitize_filter({"$or": [{"field": {"$function": {}}}]})

    def test_comparison_operators_allowed(self):
        f = {"blockNumber": {"$gte": 100, "$lte": 200}}
        assert sanitize_filter(f) == f

    def test_in_operator_allowed(self):
        f = {"result": {"$in": ["SUCCESS", "FAILED"]}}
        assert sanitize_filter(f) == f


# ---------------------------------------------------------------------------
# build_projection
# ---------------------------------------------------------------------------

class TestBuildProjection:
    def test_no_fields_excludes_id_only(self):
        proj = build_projection(None)
        assert proj == {"_id": 0}

    def test_empty_fields_excludes_id_only(self):
        proj = build_projection([])
        assert proj == {"_id": 0}

    def test_specific_fields_included(self):
        proj = build_projection(["blockNumber", "timeStamp"])
        assert proj == {"_id": 0, "blockNumber": 1, "timeStamp": 1}

    def test_id_always_excluded(self):
        # Even if _id were requested, it should be overridden to excluded
        proj = build_projection(["blockNumber"])
        assert proj.get("_id") == 0


# ---------------------------------------------------------------------------
# find_many (async, requires mock motor)
# ---------------------------------------------------------------------------

class TestFindMany:
    async def test_returns_cursor_data(self):
        data = [{"blockNumber": 1}, {"blockNumber": 2}]
        db, col = make_mock_db(find_data=data)
        result = await find_many(db, "block", {}, [("timeStamp", -1)], limit=10)
        assert result == data

    async def test_limit_is_applied(self):
        db, col = make_mock_db(find_data=[])
        await find_many(db, "block", {}, [("timeStamp", -1)], limit=5)
        col.find.return_value.limit.assert_called_once_with(5)

    async def test_skip_is_applied(self):
        db, col = make_mock_db(find_data=[])
        await find_many(db, "block", {}, [("timeStamp", -1)], limit=10, skip=20)
        col.find.return_value.skip.assert_called_once_with(20)

    async def test_invalid_collection_raises(self):
        db, _ = make_mock_db()
        with pytest.raises(ValueError):
            await find_many(db, "hackers", {}, [("timeStamp", -1)], limit=10)

    async def test_blocked_filter_operator_raises(self):
        db, _ = make_mock_db()
        with pytest.raises(ValueError):
            await find_many(db, "block", {"$where": "1==1"}, [("timeStamp", -1)], limit=10)


# ---------------------------------------------------------------------------
# find_one (async)
# ---------------------------------------------------------------------------

class TestFindOne:
    async def test_returns_document(self):
        doc = {"blockNumber": 100}
        db, _ = make_mock_db(find_one_data=doc)
        result = await find_one(db, "block", {"blockNumber": 100})
        assert result == doc

    async def test_returns_none_when_not_found(self):
        db, _ = make_mock_db(find_one_data=None)
        result = await find_one(db, "block", {"blockNumber": 999})
        assert result is None

    async def test_invalid_collection_raises(self):
        db, _ = make_mock_db()
        with pytest.raises(ValueError):
            await find_one(db, "secret", {"key": "value"})


# ---------------------------------------------------------------------------
# run_pipeline (async)
# ---------------------------------------------------------------------------

class TestRunPipeline:
    async def test_returns_aggregation_result(self):
        data = [{"contractAddress": "Tabc", "count": 100}]
        db, _ = make_mock_db(aggregate_data=data)
        result = await run_pipeline(db, "contractevent", [{"$group": {"_id": "$contractAddress"}}])
        assert result == data

    async def test_invalid_collection_raises(self):
        db, _ = make_mock_db()
        with pytest.raises(ValueError):
            await run_pipeline(db, "unknown", [])
