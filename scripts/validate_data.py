#!/usr/bin/env python3
"""Validate CPCA weekly period datasets.

Usage:
    python3 scripts/validate_data.py [data_dir]

Exit code 0 means no hard errors. Warnings are printed but do not fail the run.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

REQUIRED_METRICS = (
    "passenger_retail",
    "passenger_wholesale",
    "nev_retail",
    "nev_wholesale",
)
REQUIRED_METRIC_FIELDS = (
    "label",
    "value",
    "unit",
    "yoy_pct",
    "vs_prev_month_same_period_pct",
)
TOLERANCE = 0.2  # 万辆；用于同月累计链条检查，容忍发布口径的四舍五入
PENETRATION_TOLERANCE = 0.5  # 百分点；容忍发布值与销量比值的四舍五入


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_period(path: Path, data: dict, errors: list[str], warnings: list[str]) -> None:
    prefix = path.name

    if data.get("schema_version") != "0.1":
        errors.append(f"{prefix}: schema_version 必须为 0.1")

    period = data.get("period")
    if not isinstance(period, dict):
        errors.append(f"{prefix}: 缺少 period")
        return

    try:
        start = date.fromisoformat(period["start"])
        end = date.fromisoformat(period["end"])
    except (KeyError, TypeError, ValueError):
        errors.append(f"{prefix}: period.start/end 不是合法日期")
        return

    if start > end:
        errors.append(f"{prefix}: period.start 晚于 period.end")
    expected_days = (end - start).days + 1
    if period.get("days") != expected_days:
        errors.append(
            f"{prefix}: period.days={period.get('days')}，按日期应为 {expected_days}"
        )

    source = data.get("source", {})
    if source.get("publisher") != "CPCA":
        errors.append(f"{prefix}: source.publisher 必须为 CPCA")
    if not source.get("raw_path"):
        warnings.append(f"{prefix}: 缺少 source.raw_path，无法回溯原文")

    metrics = data.get("metrics")
    if not isinstance(metrics, dict):
        errors.append(f"{prefix}: 缺少 metrics")
        return

    for key in REQUIRED_METRICS:
        metric = metrics.get(key)
        if not isinstance(metric, dict):
            errors.append(f"{prefix}: 缺少指标 {key}")
            continue
        for field in REQUIRED_METRIC_FIELDS:
            if field not in metric:
                errors.append(f"{prefix}: {key} 缺少字段 {field}")
        for field in ("value", "yoy_pct", "vs_prev_month_same_period_pct"):
            if field in metric and not is_number(metric[field]):
                errors.append(f"{prefix}: {key}.{field} 不是数字")
        for field in ("ytd_value", "ytd_yoy_pct"):
            if metric.get(field) is not None and not is_number(metric[field]):
                errors.append(f"{prefix}: {key}.{field} 不是数字")
        if is_number(metric.get("value")) and metric["value"] < 0:
            errors.append(f"{prefix}: {key}.value 不能为负数")
        if is_number(metric.get("ytd_value")) and metric["ytd_value"] < 0:
            errors.append(f"{prefix}: {key}.ytd_value 不能为负数")

    for total_key, nev_key in (
        ("passenger_retail", "nev_retail"),
        ("passenger_wholesale", "nev_wholesale"),
    ):
        total = metrics.get(total_key, {}).get("value")
        nev = metrics.get(nev_key, {}).get("value")
        if is_number(total) and is_number(nev) and nev > total + 1e-9:
            errors.append(
                f"{prefix}: {nev_key} ({nev}) 大于 {total_key} ({total})"
            )

    penetration = data.get("penetration")
    if penetration is not None and not isinstance(penetration, dict):
        errors.append(f"{prefix}: penetration 必须是对象或 null")
    elif isinstance(penetration, dict):
        for level, total_key, nev_key in (
            ("retail", "passenger_retail", "nev_retail"),
            ("wholesale", "passenger_wholesale", "nev_wholesale"),
        ):
            published = penetration.get(f"{level}_pct")
            if published is None:
                continue
            if not is_number(published) or not 0 <= published <= 100:
                errors.append(f"{prefix}: penetration.{level}_pct 非法")
                continue
            total = metrics.get(total_key, {}).get("value")
            nev = metrics.get(nev_key, {}).get("value")
            if is_number(total) and total > 0 and is_number(nev):
                computed = nev / total * 100
                if abs(computed - published) > PENETRATION_TOLERANCE:
                    warnings.append(
                        f"{prefix}: {level} 渗透率不一致：发布 {published}%，计算 {computed:.2f}%"
                    )

    production = data.get("production")
    if production is not None:
        if not isinstance(production, dict):
            errors.append(f"{prefix}: production 必须是对象或 null")
        else:
            if production.get("status") not in {"current", "carried_over"}:
                errors.append(f"{prefix}: production.status 非法")
            if not isinstance(production.get("metrics"), dict):
                errors.append(f"{prefix}: production.metrics 缺失")


def validate_cross_period(
    datasets: list[tuple[Path, dict]], warnings: list[str]
) -> None:
    ordered = sorted(datasets, key=lambda item: item[1]["period"]["end"])
    for (prev_path, prev), (curr_path, curr) in zip(ordered, ordered[1:]):
        prev_period = prev["period"]
        curr_period = curr["period"]
        if prev_period["start"] != curr_period["start"]:
            # 跨月累计基数可能因初步统计修订而变化，不做自动调平。
            continue
        for key in REQUIRED_METRICS:
            prev_metric = prev["metrics"][key]
            curr_metric = curr["metrics"][key]
            if (
                curr_metric.get("ytd_value") is None
                or prev_metric.get("ytd_value") is None
            ):
                continue
            expected_delta = curr_metric["value"] - prev_metric["value"]
            reported_delta = curr_metric["ytd_value"] - prev_metric["ytd_value"]
            diff = reported_delta - expected_delta
            if abs(diff) > TOLERANCE:
                warnings.append(
                    f"{curr_path.name}: {key} 累计差 {reported_delta:.1f} 与本期增量 "
                    f"{expected_delta:.1f} 不一致（差 {diff:+.1f} 万辆）"
                )


def main() -> int:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")
    paths = sorted(data_dir.glob("*.json"))
    if not paths:
        print(f"No JSON files found in {data_dir}")
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    datasets: list[tuple[Path, dict]] = []
    seen_ends: set[str] = set()

    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}: JSON 解析失败：{exc}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{path.name}: 顶层必须是对象")
            continue
        end = data.get("period", {}).get("end")
        if end in seen_ends:
            errors.append(f"{path.name}: period.end={end} 与其他文件重复")
        seen_ends.add(end)
        validate_period(path, data, errors, warnings)
        datasets.append((path, data))

    if datasets:
        validate_cross_period(datasets, warnings)

    print(f"Checked {len(paths)} file(s) in {data_dir}")
    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"  - {warning}")
    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"  - {error}")
        print(f"\nFAILED: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1

    print(f"OK: no hard errors, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
