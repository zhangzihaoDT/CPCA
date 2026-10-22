#!/usr/bin/env python3
"""Build the standard CPCA table from period JSON datasets.

The standard table keeps the user-facing shape:

    time dimension | passenger retail | yoy | nev retail | yoy

Rows are grouped by 快照日期. Each weekly snapshot has three rows:
current week, month-to-date, and year-to-date. The first week of a month
has only two rows (current week and year-to-date), because current week is
identical to month-to-date.

Only passenger retail and NEV retail are included; wholesale, penetration
and production stay in the JSON audit layer.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path

FIELDS = [
    "时间维度",
    "乘用车零售(万辆)",
    "乘用车零售同比(%)",
    "新能源零售(万辆)",
    "新能源零售同比(%)",
    "快照日期",
    "区间类型",
    "区间开始",
    "区间截止",
    "日历天数",
    "数据口径",
]

PERIOD_ORDER = {
    "week": 0,
    "month_to_date": 1,
    "year_to_date": 2,
}


def load_periods(data_dir: Path) -> list[dict]:
    items: list[dict] = []
    for path in sorted(data_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_path"] = str(path)
        items.append(data)
    items.sort(key=lambda item: item["period"]["end"])
    return items


def format_range(start: date, end: date, prefix: str) -> str:
    if start.year == end.year and start.month == end.month:
        return f"{prefix}（{start.month}/{start.day}–{end.day}）"
    return f"{prefix}（{start.month}/{start.day}–{end.month}/{end.day}）"


def interval_metrics(previous: dict, current: dict, key: str) -> tuple[float, float] | None:
    prev_metric = previous["metrics"][key]
    curr_metric = current["metrics"][key]
    prev_value = prev_metric.get("value")
    curr_value = curr_metric.get("value")
    prev_yoy = prev_metric.get("yoy_pct")
    curr_yoy = curr_metric.get("yoy_pct")

    if not all(isinstance(value, (int, float)) for value in (prev_value, curr_value, prev_yoy, curr_yoy)):
        return None
    if prev_yoy <= -100 or curr_yoy <= -100:
        return None

    previous_year_prev = prev_value / (1 + prev_yoy / 100)
    previous_year_curr = curr_value / (1 + curr_yoy / 100)
    previous_year_interval = previous_year_curr - previous_year_prev
    if previous_year_interval <= 0:
        return None

    current_interval = curr_value - prev_value
    interval_yoy = (current_interval / previous_year_interval - 1) * 100
    return round(current_interval, 1), round(interval_yoy, 1)


def make_row(
    as_of: str,
    label: str,
    period_type: str,
    start: date,
    end: date,
    retail: float,
    retail_yoy: float,
    nev: float,
    nev_yoy: float,
    basis: str,
) -> dict[str, str]:
    return {
        "快照日期": as_of,
        "时间维度": label,
        "区间类型": period_type,
        "区间开始": start.isoformat(),
        "区间截止": end.isoformat(),
        "日历天数": str((end - start).days + 1),
        "乘用车零售(万辆)": f"{retail:.1f}",
        "乘用车零售同比(%)": f"{retail_yoy:.1f}",
        "新能源零售(万辆)": f"{nev:.1f}",
        "新能源零售同比(%)": f"{nev_yoy:.1f}",
        "数据口径": basis,
    }


def build_rows(items: list[dict]) -> list[dict[str, str]]:
    groups: dict[str, list[dict]] = {}
    for item in items:
        if item["period"].get("kind") != "month_to_date":
            continue
        groups.setdefault(item["period"]["start"], []).append(item)

    rows: list[dict[str, str]] = []
    for group in groups.values():
        group.sort(key=lambda item: item["period"]["end"])
        previous = None
        for index, snapshot in enumerate(group):
            snapshot_date = snapshot["period"]["end"]
            end = date.fromisoformat(snapshot_date)
            metrics = snapshot["metrics"]
            start_mtd = date.fromisoformat(snapshot["period"]["start"])

            if index == 0:
                # 首周：当周 = 当月累计，用原文值；当月行不单列。
                rows.append(
                    make_row(
                        snapshot_date,
                        format_range(start_mtd, end, "当周"),
                        "week",
                        start_mtd,
                        end,
                        metrics["passenger_retail"]["value"],
                        metrics["passenger_retail"]["yoy_pct"],
                        metrics["nev_retail"]["value"],
                        metrics["nev_retail"]["yoy_pct"],
                        "原文发布（首周即当月累计）",
                    )
                )
            else:
                # 非首周：当周 = 相邻两期累计差额。
                start = date.fromisoformat(previous["period"]["end"]) + timedelta(days=1)
                retail = interval_metrics(previous, snapshot, "passenger_retail")
                nev = interval_metrics(previous, snapshot, "nev_retail")
                if retail is None or nev is None:
                    raise ValueError(f"Cannot derive week interval for {snapshot_date}")
                rows.append(
                    make_row(
                        snapshot_date,
                        format_range(start, end, "最新区间"),
                        "week",
                        start,
                        end,
                        retail[0],
                        retail[1],
                        nev[0],
                        nev[1],
                        "由相邻两期累计值及累计同比反推",
                    )
                )
                rows.append(
                    make_row(
                        snapshot_date,
                        format_range(start_mtd, end, "当月累计"),
                        "month_to_date",
                        start_mtd,
                        end,
                        metrics["passenger_retail"]["value"],
                        metrics["passenger_retail"]["yoy_pct"],
                        metrics["nev_retail"]["value"],
                        metrics["nev_retail"]["yoy_pct"],
                        "原文发布",
                    )
                )

            has_ytd = (
                metrics["passenger_retail"].get("ytd_value") is not None
                and metrics["passenger_retail"].get("ytd_yoy_pct") is not None
                and metrics["nev_retail"].get("ytd_value") is not None
                and metrics["nev_retail"].get("ytd_yoy_pct") is not None
            )
            if has_ytd:
                year_start = date(end.year, 1, 1)
                rows.append(
                    make_row(
                        snapshot_date,
                        format_range(year_start, end, "当年累计"),
                        "year_to_date",
                        year_start,
                        end,
                        metrics["passenger_retail"]["ytd_value"],
                        metrics["passenger_retail"]["ytd_yoy_pct"],
                        metrics["nev_retail"]["ytd_value"],
                        metrics["nev_retail"]["ytd_yoy_pct"],
                        "原文发布",
                    )
                )
            previous = snapshot

    return rows


def upsert(path: Path, new_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    existing: list[dict[str, str]] = []
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as handle:
            existing = list(csv.DictReader(handle))

    new_dates = {row["快照日期"] for row in new_rows}
    merged = [row for row in existing if row.get("快照日期") not in new_dates]
    merged.extend(new_rows)
    merged.sort(key=lambda row: (row["快照日期"], PERIOD_ORDER.get(row["区间类型"], 9)))

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(merged)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the standard CPCA CSV table")
    parser.add_argument("--data-dir", default="data", help="Directory containing period JSON files")
    parser.add_argument(
        "--out",
        default="data/standard_dataset.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()

    items = load_periods(Path(args.data_dir))
    new_rows = build_rows(items)
    if not new_rows:
        raise SystemExit(
            "No month-to-date snapshots found; cannot build the standard table."
        )

    output = Path(args.out)
    rows = upsert(output, new_rows)
    dates = sorted({row["快照日期"] for row in rows})
    print(f"Wrote {output}")
    print(f"Snapshots: {', '.join(dates)}")
    print(f"Rows: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
