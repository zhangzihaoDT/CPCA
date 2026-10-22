#!/usr/bin/env python3
"""Export passenger-retail values per CPCA statistical interval.

Output columns (exactly two):
    年- XX周, 周销量（万辆）

Rules:
    - 2022-2026: use every official parsed interval, including the monthly
      close records. The requested 2026 row count is 35 official intervals.
    - 2020-2021: the raw articles are archived but not parsed; their official
      weekly intervals are exported with 无数据.
    - Missing weeks listed in MISSING_WEEK_INTERVALS are inserted as 无数据:
      2022-10-01..10-07 and the six 2026 Spring Festival gaps.
    - The week number is the chronological row number within that year,
      including inserted missing weeks. It is not an ISO week.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LEGACY_DATA_DIR = DATA_DIR / "legacy"
LEGACY_MANIFEST = ROOT / "input/legacy/manifest.json"
OUTPUT_PATH = DATA_DIR / "weekly_retail.csv"
NO_DATA = "无数据"

# Gaps documented in docs/findings.md and the coverage audit. These are the
# weeks with no independent official weekly release. The 2026 list is the six
# Spring Festival gaps; 2022 has the 10/1-10/7 gap.
MISSING_WEEK_INTERVALS: dict[int, list[tuple[str, str]]] = {
    2022: [("2022-10-01", "2022-10-07")],
    2026: [
        ("2026-01-19", "2026-01-25"),
        ("2026-01-26", "2026-02-01"),
        ("2026-02-09", "2026-02-15"),
        ("2026-02-16", "2026-02-22"),
        ("2026-02-23", "2026-03-01"),
        ("2026-03-02", "2026-03-08"),
    ],
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_parsed_intervals() -> dict[int, list[dict]]:
    """All official parsed intervals, weekly and monthly close."""
    by_year: dict[int, list[dict]] = defaultdict(list)
    for directory in (DATA_DIR, LEGACY_DATA_DIR):
        for path in sorted(directory.glob("*.json")):
            dataset = load_json(path)
            period = dataset.get("period", {})
            end = period.get("end")
            if not end or not period.get("start"):
                continue
            value = dataset.get("metrics", {}).get("passenger_retail")
            by_year[int(end[:4])].append(
                {
                    "start": period["start"],
                    "end": end,
                    "kind": period.get("kind"),
                    "value": value.get("value") if isinstance(value, dict) else None,
                }
            )
    for rows in by_year.values():
        rows.sort(key=lambda row: (row["end"], row["start"]))
    return by_year


def load_raw_intervals() -> dict[int, list[dict]]:
    """Official intervals for years that only have raw HTML (2020-2021)."""
    by_year: dict[int, list[dict]] = defaultdict(list)
    if not LEGACY_MANIFEST.exists():
        return by_year
    manifest = load_json(LEGACY_MANIFEST)
    seen: set[tuple[str, str]] = set()
    for article in manifest.get("articles", []):
        if article.get("status") != "archived_only":
            continue
        week_start = article.get("week_start")
        week_end = article.get("week_end")
        if not week_start or not week_end:
            continue
        key = (week_start, week_end)
        if key in seen:
            continue
        seen.add(key)
        by_year[int(week_start[:4])].append(
            {"start": week_start, "end": week_end, "kind": "raw", "value": None}
        )
    for rows in by_year.values():
        rows.sort(key=lambda row: (row["start"], row["end"]))
    return by_year


def main() -> int:
    parsed = load_parsed_intervals()
    raw = load_raw_intervals()

    rows: list[tuple[str, str]] = []
    stats: dict[int, dict[str, int]] = {}
    years = sorted(set(parsed) | set(raw))
    for year in years:
        # Prefer parsed intervals. 2020-2021 are raw-only and therefore all
        # 无数据, but their official intervals still get rows.
        source = list(parsed.get(year) or raw.get(year, []))
        for start, end in MISSING_WEEK_INTERVALS.get(year, []):
            source.append(
                {"start": start, "end": end, "kind": "missing", "value": None}
            )
        source.sort(key=lambda row: (row["end"], row["start"]))

        no_data = 0
        data_count = 0
        for index, item in enumerate(source, start=1):
            label = f"{year}-{index:02d}周"
            value = item.get("value")
            if value is None:
                no_data += 1
                rows.append((label, NO_DATA))
            else:
                data_count += 1
                rows.append((label, f"{float(value):.1f}"))
        stats[year] = {
            "rows": len(source),
            "data": data_count,
            "no_data": no_data,
        }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["年- XX周", "周销量（万辆）"])
        writer.writerows(rows)

    print(f"Wrote {OUTPUT_PATH}")
    print(f"Rows: {len(rows)}")
    print("By year:")
    for year in years:
        print(
            f"  {year}: {stats[year]['rows']} rows, "
            f"{stats[year]['data']} data, {stats[year]['no_data']} 无数据"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
