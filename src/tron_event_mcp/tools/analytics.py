"""Analytics tools: contract activity search, top contracts, time-series aggregation,
counting, field aggregation, group-by ranking, and transaction statistics.
"""

import asyncio
from typing import Literal

from mcp.server.fastmcp import FastMCP
from pymongo import DESCENDING

from tron_event_mcp.db.client import get_db
from tron_event_mcp.db.repos.base import find_many, run_pipeline, safe_limit, sanitize_filter

ContractCollection = Literal["contractevent", "contractlog", "solidityevent", "soliditylog"]
TimeseriesCollection = Literal["block", "transaction", "contractevent", "contractlog"]
CollectionName = Literal[
    "block", "transaction", "contractevent",
    "contractlog", "solidity", "solidityevent", "soliditylog"
]
Granularity = Literal["hour", "day", "week"]
AggOp = Literal["sum", "avg", "min", "max"]


def _validate_field_path(field: str) -> None:
    """Validate a field path; reject paths containing '$' to prevent injection."""
    if not field or "$" in field:
        raise ValueError(f"invalid field name: {field!r}")


def _safe_numeric(field_ref: str) -> dict:
    """Safely convert a string field to decimal; returns None on conversion failure (ignored by aggregation)."""
    return {"$convert": {"input": field_ref, "to": "decimal", "onError": None, "onNull": None}}


def _build_contract_filter(
    filters: dict | None,
    contract_address: str | None,
    event_name: str | None,
    collection: str,
    start_timestamp: int | None,
    end_timestamp: int | None,
) -> dict:
    """Combine contract address, event name, time range, and user-supplied filters."""
    extra: dict = {**sanitize_filter(filters or {})}
    if contract_address:
        extra["contractAddress"] = contract_address
    if event_name and collection in ("contractevent", "solidityevent"):
        extra["eventName"] = event_name
    return _build_time_filter(start_timestamp, end_timestamp, extra)


def _build_time_filter(
    start_timestamp: int | None,
    end_timestamp: int | None,
    extra: dict | None = None,
) -> dict:
    """Build a time-range filter on the timeStamp field (milliseconds)."""
    f: dict = {}
    if start_timestamp is not None or end_timestamp is not None:
        ts_filter: dict = {}
        if start_timestamp is not None:
            ts_filter["$gte"] = start_timestamp
        if end_timestamp is not None:
            ts_filter["$lte"] = end_timestamp
        f["timeStamp"] = ts_filter
    if extra:
        f.update(extra)
    return f


def _granularity_format(granularity: Granularity) -> str:
    """Return a MongoDB $dateToString format string for the given granularity."""
    return {
        "hour": "%Y-%m-%dT%H:00",
        "day": "%Y-%m-%d",
        "week": "%G-W%V",  # ISO week
    }[granularity]


def register_analytics_tools(mcp: FastMCP) -> None:
    """Register analytics and aggregation tools on the given MCP server instance."""

    @mcp.tool()
    async def search_contract_activity(
        contract_address: str,
        event_name: str | None = None,
        collection: ContractCollection = "contractevent",
        start_timestamp: int | None = None,
        end_timestamp: int | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """
        Query events or logs for a specific contract address, with optional
        event name and time range filters. This is the most commonly used tool
        for analyzing contract activity.

        Args:
          contract_address: TRON contract address (34-char Base58Check string starting with T)
          event_name: Optional event name filter. Only effective for contractevent / solidityevent.
                      Examples: "Transfer", "Approval", "Swap"
          collection: Data source. Default: contractevent (ABI-decoded, human-readable).
                      contractlog = raw logs (hex data, not decoded).
                      solidityevent / soliditylog = finalized (solidified) versions.
          start_timestamp: Start timestamp in milliseconds. Omit for no lower bound.
          end_timestamp: End timestamp in milliseconds. Omit for no upper bound.
          limit: Number of documents to return. Default 20, capped by system config.

        Example 1: latest 50 Transfer events for the USDT contract
          search_contract_activity(
              contract_address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
              event_name="Transfer",
              limit=50
          )

        Example 2: all events for a contract within a time window
          search_contract_activity(
              contract_address="T...",
              start_timestamp=1700000000000,
              end_timestamp=1700086400000
          )
        """
        db = get_db()
        extra: dict = {"contractAddress": contract_address}
        if event_name and collection in ("contractevent", "solidityevent"):
            extra["eventName"] = event_name

        f = _build_time_filter(start_timestamp, end_timestamp, extra)
        return await find_many(
            db, collection, f,
            sort=[("timeStamp", DESCENDING)],
            limit=safe_limit(limit),
        )

    @mcp.tool()
    async def get_top_contracts(
        collection: ContractCollection = "contractevent",
        start_timestamp: int | None = None,
        end_timestamp: int | None = None,
        top_n: int = 10,
    ) -> list[dict]:
        """
        Rank contract addresses by event/log count within a time range.
        Useful for discovering highly active contracts or trending DeFi protocols.

        Args:
          collection: Data source. Default: contractevent.
          start_timestamp: Start timestamp in milliseconds.
          end_timestamp: End timestamp in milliseconds.
          top_n: Number of top entries to return. Default 10, max 50.

        Returns:
          [
            { "contractAddress": "T...", "event_count": 12345, "unique_callers": 890 },
            ...
          ]
        """
        db = get_db()
        match_filter = _build_time_filter(start_timestamp, end_timestamp)
        pipeline = [
            {"$match": match_filter},
            {
                "$group": {
                    "_id": "$contractAddress",
                    "event_count": {"$sum": 1},
                    "unique_callers": {"$addToSet": "$callerAddress"},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "contractAddress": "$_id",
                    "event_count": 1,
                    "unique_callers": {"$size": "$unique_callers"},
                }
            },
            {"$sort": {"event_count": -1}},
            {"$limit": min(top_n, 50)},
        ]
        return await run_pipeline(db, collection, pipeline)

    @mcp.tool()
    async def aggregate_by_time(
        collection: TimeseriesCollection,
        granularity: Granularity = "day",
        start_timestamp: int | None = None,
        end_timestamp: int | None = None,
        contract_address: str | None = None,
        sum_field: str | None = None,
    ) -> list[dict]:
        """
        Aggregate event counts over time buckets to identify activity peaks
        or temporal patterns. Optionally computes a running sum of a numeric field
        (e.g. daily USDT transfer volume).

        Args:
          collection: Data source. One of: block / transaction / contractevent / contractlog.
          granularity: Time bucket size: "hour" / "day" / "week".
          start_timestamp: Start timestamp in milliseconds.
          end_timestamp: End timestamp in milliseconds.
          contract_address: Optional. Restrict to a specific contract
                            (only meaningful for contractevent / contractlog).
          sum_field: Optional. Also compute the sum of this numeric field per bucket.
                     Supports nested paths, e.g. "dataMap.value".
                     Numeric strings are automatically converted.

        Returns (without sum_field):
          [ { "period": "2024-01-15", "count": 45231 }, ... ]

        Returns (with sum_field):
          [ { "period": "2024-01-15", "count": 45231, "sum": 9876543210 }, ... ]

        Example: daily transfer count and total amount for USDT
          aggregate_by_time(
              collection="contractevent",
              granularity="day",
              contract_address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
              sum_field="dataMap.value",
          )
        """
        db = get_db()
        extra = {"contractAddress": contract_address} if contract_address else None
        match_filter = _build_time_filter(start_timestamp, end_timestamp, extra)
        fmt = _granularity_format(granularity)

        group_spec: dict = {
            "_id": {
                "$dateToString": {
                    "format": fmt,
                    "date": {"$toDate": "$timeStamp"},
                }
            },
            "count": {"$sum": 1},
        }
        if sum_field:
            _validate_field_path(sum_field)
            group_spec["sum"] = {"$sum": _safe_numeric(f"${sum_field}")}

        project_spec: dict = {"_id": 0, "period": "$_id", "count": 1}
        if sum_field:
            project_spec["sum"] = 1

        pipeline = [
            {"$match": match_filter},
            {"$group": group_spec},
            {"$sort": {"_id": 1}},
            {"$project": project_spec},
        ]
        return await run_pipeline(db, collection, pipeline)

    @mcp.tool()
    async def count_events(
        collection: CollectionName,
        filters: dict | None = None,
        contract_address: str | None = None,
        event_name: str | None = None,
        start_timestamp: int | None = None,
        end_timestamp: int | None = None,
    ) -> dict:
        """
        Quickly count documents matching the given criteria.
        Much more efficient than paginating through query_events results.

        Args:
          collection: Collection name.
          filters: Filter conditions (same as query_events).
          contract_address: Optional. Restrict to a specific contract address.
          event_name: Optional. Restrict to a specific event name
                      (only effective for contractevent / solidityevent).
          start_timestamp: Start timestamp in milliseconds.
          end_timestamp: End timestamp in milliseconds.

        Returns:
          { "count": 28798 }

        Example: count USDT Transfer events
          count_events(
              collection="contractevent",
              contract_address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
              event_name="Transfer",
          )
        """
        db = get_db()
        match_filter = _build_contract_filter(
            filters, contract_address, event_name, collection,
            start_timestamp, end_timestamp,
        )
        pipeline = [{"$match": match_filter}, {"$count": "count"}]
        results = await run_pipeline(db, collection, pipeline)
        return results[0] if results else {"count": 0}

    @mcp.tool()
    async def aggregate_field(
        collection: CollectionName,
        field: str,
        operations: list[AggOp] | None = None,
        filters: dict | None = None,
        contract_address: str | None = None,
        event_name: str | None = None,
        start_timestamp: int | None = None,
        end_timestamp: int | None = None,
    ) -> dict:
        """
        Perform numeric aggregation (sum / avg / min / max) on a specified field.
        Multiple operations can be computed in a single call.
        Numeric string fields (e.g. dataMap.value) are automatically converted.

        Args:
          collection: Collection name.
          field: Field path to aggregate. Supports nested paths, e.g. "dataMap.value",
                 "energyUsageTotal".
          operations: List of aggregation operations. Options: sum / avg / min / max.
                      Default: ["sum"]. Note: count is always returned automatically,
                      no need to include it.
          filters: Additional filter conditions.
          contract_address: Optional. Restrict to a specific contract address.
          event_name: Optional. Restrict to a specific event name.
          start_timestamp / end_timestamp: Time range in milliseconds.

        Returns:
          { "count": 28798, "sum": 9876543210000, "avg": 342857.3 }

        Example: total and average Transfer amount for USDT
          aggregate_field(
              collection="contractevent",
              field="dataMap.value",
              operations=["sum", "avg"],
              contract_address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
              event_name="Transfer",
          )
        """
        db = get_db()
        _validate_field_path(field)
        match_filter = _build_contract_filter(
            filters, contract_address, event_name, collection,
            start_timestamp, end_timestamp,
        )
        field_ref = f"${field}"
        group_spec: dict = {"_id": None, "count": {"$sum": 1}}
        for op in (operations or ["sum"]):
            if op != "count":
                group_spec[op] = {f"${op}": _safe_numeric(field_ref)}

        all_keys = list(group_spec.keys())
        pipeline = [
            {"$match": match_filter},
            {"$group": group_spec},
            {"$project": {"_id": 0, **{k: 1 for k in all_keys if k != "_id"}}},
        ]
        results = await run_pipeline(db, collection, pipeline)
        return results[0] if results else {k: None for k in all_keys if k != "_id"}

    @mcp.tool()
    async def group_by_field(
        collection: CollectionName,
        group_field: str,
        agg_field: str | None = None,
        agg_op: AggOp = "sum",
        filters: dict | None = None,
        contract_address: str | None = None,
        event_name: str | None = None,
        start_timestamp: int | None = None,
        end_timestamp: int | None = None,
        top_n: int = 20,
        sort_order: Literal["asc", "desc"] = "desc",
    ) -> list[dict]:
        """
        Group by a field and aggregate, useful for address rankings, event
        distribution analysis, etc. When agg_field is omitted, results are
        sorted by occurrence count.

        Args:
          collection: Collection name.
          group_field: Field path to group by, e.g. "contractAddress", "topicMap.to".
          agg_field: Optional. Field path to aggregate, e.g. "dataMap.value".
                     Omit to rank by count only.
          agg_op: Aggregation operation: sum / avg / min / max. Default: sum.
                  Only effective when agg_field is provided.
          filters: Additional filter conditions.
          contract_address: Optional. Restrict to a specific contract address.
          event_name: Optional. Restrict to a specific event name.
          start_timestamp / end_timestamp: Time range in milliseconds.
          top_n: Number of top entries to return. Max 100.
          sort_order: "desc" (default, largest first) or "asc" (smallest first).

        Returns (count mode):
          [ { "group": "TAddress...", "count": 500 }, ... ]

        Returns (agg_field mode):
          [ { "group": "TAddress...", "value": 99999999, "count": 500 }, ... ]

        Example 1: top 20 USDT recipients by cumulative received amount
          group_by_field(
              collection="contractevent",
              group_field="topicMap.to",
              agg_field="dataMap.value",
              agg_op="sum",
              contract_address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
              event_name="Transfer",
          )

        Example 2: rank contracts by event count
          group_by_field(collection="contractevent", group_field="contractAddress")
        """
        db = get_db()
        _validate_field_path(group_field)
        match_filter = _build_contract_filter(
            filters, contract_address, event_name, collection,
            start_timestamp, end_timestamp,
        )
        sort_dir = 1 if sort_order == "asc" else -1
        group_field_ref = f"${group_field}"

        if agg_field is None:
            group_spec = {"_id": group_field_ref, "count": {"$sum": 1}}
            project_spec = {"_id": 0, "group": "$_id", "count": 1}
            sort_key = "count"
        else:
            _validate_field_path(agg_field)
            group_spec = {
                "_id": group_field_ref,
                "value": {f"${agg_op}": _safe_numeric(f"${agg_field}")},
                "count": {"$sum": 1},
            }
            project_spec = {"_id": 0, "group": "$_id", "value": 1, "count": 1}
            sort_key = "value"

        pipeline = [
            {"$match": match_filter},
            {"$group": group_spec},
            {"$project": project_spec},
            {"$sort": {sort_key: sort_dir}},
            {"$limit": min(top_n, 100)},
        ]
        return await run_pipeline(db, collection, pipeline)

    @mcp.tool()
    async def top_events_by_value(
        collection: CollectionName,
        sort_field: str,
        filters: dict | None = None,
        contract_address: str | None = None,
        event_name: str | None = None,
        start_timestamp: int | None = None,
        end_timestamp: int | None = None,
        sort_order: Literal["asc", "desc"] = "desc",
        top_n: int = 10,
        fields: list[str] | None = None,
    ) -> list[dict]:
        """
        Find top N events sorted by the numeric value of a field.
        Unlike query_events which sorts by string order, this tool converts
        the field to a number (via $convert to decimal) before sorting — essential for
        fields like dataMap.value that are stored as numeric strings.

        Use this when you need to find the largest/smallest individual events
        (e.g. "top 3 biggest USDT transfers"). For aggregate statistics
        (total, average), use aggregate_field or group_by_field instead.

        Args:
          collection: Collection name.
          sort_field: Field path to sort by numerically, e.g. "dataMap.value",
                      "energyUsageTotal". The field value must be convertible to a long.
          filters: Additional filter conditions (same as query_events).
          contract_address: Optional. Restrict to a specific contract address.
          event_name: Optional. Restrict to a specific event name
                      (only effective for contractevent / solidityevent).
          start_timestamp: Start timestamp in milliseconds.
          end_timestamp: End timestamp in milliseconds.
          sort_order: "desc" (default, largest first) or "asc" (smallest first).
          top_n: Number of results to return. Default 10, max 100.
          fields: Optional list of fields to return. If omitted, returns all fields.

        Returns:
          List of event documents sorted by the numeric value of sort_field.

        Example: top 3 largest USDT transfers
          top_events_by_value(
              collection="contractevent",
              sort_field="dataMap.value",
              contract_address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
              event_name="Transfer",
              top_n=3,
              fields=["transactionId", "blockNumber", "timeStamp", "topicMap", "dataMap"],
          )
        """
        db = get_db()
        _validate_field_path(sort_field)
        match_filter = _build_contract_filter(
            filters, contract_address, event_name, collection,
            start_timestamp, end_timestamp,
        )
        sort_dir = 1 if sort_order == "asc" else -1
        capped_n = min(top_n, 100)

        pipeline: list[dict] = [
            {"$match": match_filter},
            {"$addFields": {"_sort_val": _safe_numeric(f"${sort_field}")}},
            {"$sort": {"_sort_val": sort_dir}},
            {"$limit": capped_n},
        ]

        if fields:
            for f in fields:
                _validate_field_path(f)
            project: dict = {"_id": 0, "_sort_val": 0}
            for f in fields:
                project[f] = 1
            pipeline.append({"$project": project})
        else:
            pipeline.append({"$project": {"_id": 0, "_sort_val": 0}})

        return await run_pipeline(db, collection, pipeline)

    @mcp.tool()
    async def get_transaction_stats(
        start_timestamp: int | None = None,
        end_timestamp: int | None = None,
    ) -> dict:
        """
        Compute transaction result distribution (SUCCESS / FAILED / REVERT),
        average energy consumption, and contract type distribution.
        Provides a quick overview of on-chain transaction quality and resource usage.

        Args:
          start_timestamp: Start timestamp in milliseconds.
          end_timestamp: End timestamp in milliseconds.

        Returns:
          {
            "result_distribution": [{"result": "SUCCESS", "count": 12000}, ...],
            "avg_energy_usage_total": 12345.6,
            "contract_type_distribution": [
              {"contractType": "TriggerSmartContract", "count": ...}, ...
            ]
          }
        """
        db = get_db()
        match_filter = _build_time_filter(start_timestamp, end_timestamp)

        result_pipeline = [
            {"$match": match_filter},
            {"$group": {"_id": "$result", "count": {"$sum": 1}}},
            {"$project": {"_id": 0, "result": "$_id", "count": 1}},
            {"$sort": {"count": -1}},
        ]
        contract_type_pipeline = [
            {"$match": {**match_filter, "contractType": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": "$contractType", "count": {"$sum": 1}}},
            {"$project": {"_id": 0, "contractType": "$_id", "count": 1}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]
        avg_energy_pipeline = [
            {"$match": match_filter},
            {"$group": {"_id": None, "avg_energy": {"$avg": "$energyUsageTotal"}}},
            {"$project": {"_id": 0, "avg_energy": 1}},
        ]

        result_dist, contract_dist, avg_energy_result = await asyncio.gather(
            run_pipeline(db, "transaction", result_pipeline),
            run_pipeline(db, "transaction", contract_type_pipeline),
            run_pipeline(db, "transaction", avg_energy_pipeline),
        )

        return {
            "result_distribution": result_dist,
            "avg_energy_usage_total": (
                avg_energy_result[0]["avg_energy"] if avg_energy_result else None
            ),
            "contract_type_distribution": contract_dist,
        }
