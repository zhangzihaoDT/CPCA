#!/usr/bin/env python3
"""Validate Legacy V2 datasets in data/legacy/."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

CORE = ("passenger_retail", "passenger_wholesale")
OPTIONAL = ("nev_retail", "nev_wholesale")
NUMERIC_FIELDS = (
    "value",
    "yoy_pct",
    "vs_prev_month_same_period_pct",
    "ytd_value",
    "ytd_yoy_pct",
)


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def main() -> int:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/legacy")
    paths = sorted(data_dir.glob("*.json"))
    if not paths:
        print(f"No legacy JSON files in {data_dir}")
        return 1

    errors: list[str] = []
    stats = {
        "total": 0,
        "month": 0,
        "week": 0,
        "passenger_retail": 0,
        "passenger_wholesale": 0,
        "nev": 0,
        "ytd": 0,
    }
    seen_ends: set[str] = set()

    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}: JSON parse failed: {exc}")
            continue
        stats["total"] += 1

        if data.get("schema_version") != "legacy-v2":
            errors.append(f"{path.name}: schema_version must be legacy-v2")

        period = data.get("period", {})
        try:
            start = date.fromisoformat(period["start"])
            end = date.fromisoformat(period["end"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{path.name}: invalid period")
            continue
        if (end - start).days + 1 != period.get("days"):
            errors.append(f"{path.name}: days mismatch")
        if period["end"] in seen_ends:
            errors.append(f"{path.name}: duplicate period.end")
        seen_ends.add(period["end"])
        if period.get("kind") == "month":
            stats["month"] += 1
        elif period.get("kind") == "month_to_date":
            stats["week"] += 1
        else:
            errors.append(f"{path.name}: invalid period.kind")

        metrics = data.get("metrics", {})
        if not any(isinstance(metrics.get(key), dict) for key in CORE):
            errors.append(f"{path.name}: no passenger retail/wholesale")
        for key in CORE + OPTIONAL:
            metric = metrics.get(key)
            if metric is None:
                continue
            if not isinstance(metric, dict):
                errors.append(f"{path.name}: {key} must be object or null")
                continue
            if not is_number(metric.get("value")):
                errors.append(f"{path.name}: {key}.value missing")
            for field in NUMERIC_FIELDS:
                value = metric.get(field)
                if value is not None and not is_number(value):
                    errors.append(f"{path.name}: {key}.{field} not numeric")
            if key in CORE:
                stats[key] += 1
            if key in OPTIONAL:
                stats["nev"] += 1
            if metric.get("ytd_value") is not None:
                stats["ytd"] += 1

        source = data.get("source", {})
        if source.get("origin") != "official-legacy":
            errors.append(f"{path.name}: source.origin must be official-legacy")
        if not source.get("url"):
            errors.append(f"{path.name}: missing source.url")

    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"Checked {len(paths)} legacy files in {data_dir}")
    if errors:
        print("Errors:")
        for error in errors:
            print(" ", error)
        return 1
    print("OK: no errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
