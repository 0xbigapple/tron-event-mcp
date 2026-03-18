"""Distribution tools: histogram bucketing and percentile computation."""

from typing import Literal

from mcp.server.fastmcp import FastMCP

from tron_event_mcp.db.client import get_db
from tron_event_mcp.db.repos.base import run_pipeline
from tron_event_mcp.tools.analytics import (
    CollectionName,
    _build_contract_filter,
    _safe_numeric,
    _validate_field_path,
)

BucketMode = Literal["manual", "auto"]


def register_distribution_tools(mcp: FastMCP) -> None:
    """Register distribution analysis tools on the given MCP server instance."""

    @mcp.tool()
    async def histogram(
        collection: CollectionName,
        field: str,
        bucket_mode: BucketMode = "auto",
        boundaries: list[int] | None = None,
        num_buckets: int = 10,
        filters: dict | None = None,
        contract_address: str | None = None,
        event_name: str | None = None,
        start_timestamp: int | None = None,
        end_timestamp: int | None = None,
    ) -> list[dict]:
        """
        Bucket a numeric field to produce histogram data.
        Supports manual boundary specification or automatic uniform bucketing.

        Args:
          collection: Collection name.
          field: Numeric field path, e.g. "energyUsageTotal", "dataMap.value", "transactionSize".
          bucket_mode: Bucketing mode.
            - "auto" (default): Uniform buckets; count controlled by num_buckets.
            - "manual": Custom bucket boundaries via the boundaries parameter.
          boundaries: Bucket boundary list (ascending integers) for manual mode,
                      e.g. [0, 1000, 10000, 100000, 1000000].
                      Values exceeding the last boundary fall into an overflow bucket.
                      Only used when bucket_mode="manual".
          num_buckets: Number of buckets for auto mode. Default 10, max 50.
                       Only used when bucket_mode="auto".
          filters: Additional filter conditions.
          contract_address: Optional. Restrict to a specific contract address.
          event_name: Optional. Restrict to a specific event name.
          start_timestamp / end_timestamp: Time range in milliseconds.

        Returns (manual mode):
          [
            { "range": "0 ~ 1000", "count": 45000 },
            { "range": "1000 ~ 10000", "count": 23000 },
            { "range": ">= 1000000", "count": 300 }
          ]

        Returns (auto mode):
          [
            { "range": "0 ~ 9800", "count": 45000 },
            { "range": "9800 ~ 19600", "count": 23000 },
            ...
          ]

        Example 1: auto buckets - transaction energy consumption distribution
          histogram(collection="transaction", field="energyUsageTotal")

        Example 2: manual buckets - block transaction count distribution
          histogram(
              collection="block",
              field="transactionSize",
              bucket_mode="manual",
              boundaries=[0, 10, 50, 100, 200, 500],
          )
        """
        db = get_db()
        _validate_field_path(field)
        match_filter = _build_contract_filter(
            filters, contract_address, event_name, collection,
            start_timestamp, end_timestamp,
        )
        field_ref = _safe_numeric(f"${field}")

        if bucket_mode == "manual":
            if not boundaries or len(boundaries) < 2:
                raise ValueError("manual mode requires at least 2 bucket boundaries")
            sorted_bounds = sorted(boundaries)
            pipeline = [
                {"$match": match_filter},
                {"$addFields": {"_val": field_ref}},
                {
                    "$bucket": {
                        "groupBy": "$_val",
                        "boundaries": sorted_bounds,
                        "default": "_overflow",
                        "output": {"count": {"$sum": 1}},
                    }
                },
                {"$project": {"_id": 0, "bucket": "$_id", "count": 1}},
            ]
            raw = await run_pipeline(db, collection, pipeline)

            result = []
            for item in raw:
                b = item["bucket"]
                if b == "_overflow":
                    result.append({
                        "range": f">= {sorted_bounds[-1]}",
                        "count": item["count"],
                    })
                else:
                    idx = sorted_bounds.index(b)
                    upper = sorted_bounds[idx + 1] if idx + 1 < len(sorted_bounds) else None
                    result.append({
                        "range": f"{b} ~ {upper}" if upper is not None else f">= {b}",
                        "count": item["count"],
                    })
            return result

        # auto mode
        safe_num = min(max(2, num_buckets), 50)
        pipeline = [
            {"$match": match_filter},
            {"$addFields": {"_val": field_ref}},
            {
                "$bucketAuto": {
                    "groupBy": "$_val",
                    "buckets": safe_num,
                    "output": {"count": {"$sum": 1}},
                }
            },
            {"$project": {
                "_id": 0,
                "min": "$_id.min",
                "max": "$_id.max",
                "count": 1,
            }},
        ]
        raw = await run_pipeline(db, collection, pipeline)
        return [
            {
                "range": f"{item['min']} ~ {item['max']}",
                "count": item["count"],
            }
            for item in raw
        ]

    @mcp.tool()
    async def percentiles(
        collection: CollectionName,
        field: str,
        pcts: list[float] | None = None,
        filters: dict | None = None,
        contract_address: str | None = None,
        event_name: str | None = None,
        start_timestamp: int | None = None,
        end_timestamp: int | None = None,
    ) -> dict:
        """
        Compute percentiles of a numeric field to understand distribution
        characteristics (median, long tail, etc.).
        Requires MongoDB 5.0 or later.

        Args:
          collection: Collection name.
          field: Numeric field path, e.g. "energyUsageTotal", "dataMap.value".
          pcts: List of percentile values between 0 and 1. Default: [0.5, 0.9, 0.95, 0.99].
                0.5 = median, 0.99 = 99th percentile.
          filters: Additional filter conditions.
          contract_address: Optional. Restrict to a specific contract address.
          event_name: Optional. Restrict to a specific event name.
          start_timestamp / end_timestamp: Time range in milliseconds.

        Returns:
          {
            "count": 77500,
            "p50": 3200,
            "p90": 45000,
            "p95": 120000,
            "p99": 890000
          }

        Example: energy consumption percentiles for transactions
          percentiles(
              collection="transaction",
              field="energyUsageTotal",
              pcts=[0.5, 0.75, 0.9, 0.95, 0.99],
          )
        """
        db = get_db()
        _validate_field_path(field)
        match_filter = _build_contract_filter(
            filters, contract_address, event_name, collection,
            start_timestamp, end_timestamp,
        )
        field_ref = _safe_numeric(f"${field}")

        safe_pcts = [p for p in (pcts or [0.5, 0.9, 0.95, 0.99]) if 0 < p < 1]
        if not safe_pcts:
            raise ValueError("pcts must contain at least one value between 0 and 1")

        pipeline = [
            {"$match": match_filter},
            {"$addFields": {"_val": field_ref}},
            {
                "$group": {
                    "_id": None,
                    "count": {"$sum": 1},
                    "pct_values": {
                        "$percentile": {
                            "input": "$_val",
                            "p": safe_pcts,
                            "method": "approximate",
                        }
                    },
                }
            },
            {"$project": {"_id": 0, "count": 1, "pct_values": 1}},
        ]
        results = await run_pipeline(db, collection, pipeline)

        if not results:
            return {"count": 0, **{f"p{int(p * 100)}": None for p in safe_pcts}}

        row = results[0]
        output: dict = {"count": row["count"]}
        for i, p in enumerate(safe_pcts):
            label = f"p{int(p * 100)}"
            output[label] = row["pct_values"][i] if i < len(row["pct_values"]) else None
        return output
