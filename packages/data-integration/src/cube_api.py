"""M6/M7: SSTCube — OLAP operations + H3 GeoCube API.

Supports OLAP four operations (Wu Tingxin §5.3):
- slice: time dimension filtering
- dice: multi-dimensional filtering
- roll_up: aggregation
- to_h3_cube: generate H3 GeoCube
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from src.schema import Record
from src.region_mapping import generate_h3_cube


class SSTCube:
    """Spatio-temporal statistics cube for OLAP operations.

    Wraps a list of seven-tuple records and provides
    OLAP operations (Wu Tingxin §5.3) and H3 GeoCube generation.
    """

    def __init__(self, records: list[Record]):
        self.records = records

    def slice(self, time: str | None = None, space: str | None = None,
              indicator: str | None = None) -> "SSTCube":
        """OLAP slice: filter by one dimension."""
        filtered = self.records
        if time is not None:
            filtered = [r for r in filtered if r.time == time]
        if space is not None:
            filtered = [r for r in filtered if r.space == space]
        if indicator is not None:
            filtered = [r for r in filtered if r.indicator == indicator]
        return SSTCube(filtered)

    def dice(self, times: list[str] | None = None, spaces: list[str] | None = None,
             indicators: list[str] | None = None) -> "SSTCube":
        """OLAP dice: filter by multiple dimensions."""
        filtered = self.records
        if times is not None:
            filtered = [r for r in filtered if r.time in times]
        if spaces is not None:
            filtered = [r for r in filtered if r.space in spaces]
        if indicators is not None:
            filtered = [r for r in filtered if r.indicator in indicators]
        return SSTCube(filtered)

    def roll_up(self, by: str = "space", agg: str = "sum") -> list[dict]:
        """OLAP roll_up: aggregate along a dimension.

        Args:
            by: Dimension to aggregate ("space" or "time" or "indicator").
            agg: Aggregation function ("sum", "mean", "max", "min").

        Returns:
            List of aggregated dicts.
        """
        groups: dict[str, list[float]] = defaultdict(list)
        for rec in self.records:
            dim_val = getattr(rec, by, "") or "unknown"
            groups[dim_val].append(rec.value)

        results: list[dict] = []
        for key, vals in groups.items():
            if agg == "sum":
                v = sum(vals)
            elif agg == "mean":
                v = sum(vals) / len(vals) if vals else 0
            elif agg == "max":
                v = max(vals) if vals else 0
            elif agg == "min":
                v = min(vals) if vals else 0
            else:
                v = sum(vals)
            results.append({by: key, "value": v, "count": len(vals), "agg": agg})

        return results

    def to_h3_cube(self, resolution: int = 5) -> list[dict]:
        """Generate H3 GeoCube from records.

        Returns list of spatial point dicts.
        """
        return generate_h3_cube(self.records, resolution)

    def to_long_table(self) -> list[dict]:
        """Export records as long table dicts."""
        return [r.to_dict() for r in self.records]

    def to_long_table_csv(self) -> str:
        """Export records as CSV string."""
        lines = ["time,space,value,unit,indicator,source,note"]
        for r in self.records:
            note_escaped = r.note.replace('"', '""')
            lines.append(
                f'"{r.time}","{r.space}",{r.value},"{r.unit}",'
                f'"{r.indicator}","{r.source}","{note_escaped}"'
            )
        return "\n".join(lines)

    @property
    def count(self) -> int:
        """Number of records in the cube."""
        return len(self.records)

    def summary(self) -> dict[str, Any]:
        """Get summary statistics of the cube."""
        indicators = set(r.indicator for r in self.records)
        spaces = set(r.space for r in self.records)
        times = set(r.time for r in self.records)
        return {
            "total_records": len(self.records),
            "unique_indicators": len(indicators),
            "unique_spaces": len(spaces),
            "unique_times": len(times),
            "indicators": sorted(indicators),
            "spaces": sorted(spaces),
            "times": sorted(times),
        }
