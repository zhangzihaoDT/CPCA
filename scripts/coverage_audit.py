#!/usr/bin/env python3
"""Build a coverage audit for the CPCA historical data asset.

The audit answers three questions:
    - How many weekly and monthly intervals exist per year?
    - How many months have passenger retail / NEV retail data?
    - Where are the calendar, NEV and full-month-close gaps?

It writes:
    data/coverage_audit.csv
    data/coverage_gaps.csv
    reports/coverage_audit.html

The audit does not modify data/*.json, data/legacy/*.json, the standard table
or the weekly brief.
"""

from __future__ import annotations

import calendar
import csv
import html
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from annual_data import (
    METRICS,
    load_monthly_references,
    recover_legacy_months,
    write_annual_exports,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LEGACY_DATA_DIR = DATA_DIR / "legacy"
REPORT_PATH = ROOT / "reports/coverage_audit.html"
SUMMARY_CSV_PATH = DATA_DIR / "coverage_audit.csv"
GAP_CSV_PATH = DATA_DIR / "coverage_gaps.csv"
OFFICIAL_MANIFEST = ROOT / "input/official/manifest.json"
LEGACY_MANIFEST = ROOT / "input/legacy/manifest.json"

KNOWN_PUBLICATION_GAPS = {
    (date(2026, 1, 19), date(2026, 1, 31)): "官网春节前无对应独立周报",
    (date(2026, 2, 9), date(2026, 2, 28)): "官网春节前后无对应独立周报",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_datasets() -> list[tuple[str, dict]]:
    items: list[tuple[str, dict]] = []
    for path in sorted(DATA_DIR.glob("*.json")):
        items.append(("正式数据", load_json(path)))
    for path in sorted(LEGACY_DATA_DIR.glob("*.json")):
        items.append(("Legacy V2", load_json(path)))
    return items


def load_raw_counts() -> Counter[int]:
    counts: Counter[int] = Counter()
    seen: set[tuple[str, str]] = set()
    for path in (OFFICIAL_MANIFEST, LEGACY_MANIFEST):
        if not path.exists():
            continue
        manifest = load_json(path)
        for article in manifest.get("articles", []):
            key = (str(path), str(article.get("article_id")))
            if key in seen:
                continue
            seen.add(key)
            week_end = article.get("week_end")
            if week_end:
                counts[int(week_end[:4])] += 1
    return counts


def metric_value(dataset: dict, key: str) -> float | int | None:
    metric = dataset.get("metrics", {}).get(key)
    if not isinstance(metric, dict):
        return None
    return metric.get("value")


def date_gaps(covered: set[date], start: date, end: date) -> list[tuple[date, date]]:
    gaps: list[tuple[date, date]] = []
    current = start
    while current <= end:
        if current in covered:
            current += timedelta(days=1)
            continue
        gap_start = current
        while current + timedelta(days=1) <= end and (
            current + timedelta(days=1)
        ) not in covered:
            current += timedelta(days=1)
        gaps.append((gap_start, current))
        current += timedelta(days=1)
    return gaps


def group_months(months: list[int]) -> list[list[int]]:
    groups: list[list[int]] = []
    for month in sorted(months):
        if groups and month == groups[-1][-1] + 1:
            groups[-1].append(month)
        else:
            groups.append([month])
    return groups


def format_month_ranges(months: list[int]) -> str:
    groups = group_months(months)
    if not groups:
        return "—"
    parts = []
    for group in groups:
        if len(group) == 1:
            parts.append(str(group[0]))
        else:
            parts.append(f"{group[0]}–{group[-1]}")
    return "、".join(parts)


def missing_close_label(year: dict) -> str:
    return format_month_ranges(year["missing_full_close"])


def build_year(
    year: int,
    items: list[tuple[str, dict]],
    latest: date,
    raw_counts: Counter[int],
    monthly_references: list[dict],
) -> dict:
    layer = "原始归档" if year < 2022 else ("Legacy V2" if year < 2024 else "正式数据")
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    if year == latest.year:
        end = latest

    audit_months = list(range(1, end.month + 1))
    closed_months = [
        month for month in audit_months
        if date(year, month, calendar.monthrange(year, month)[1]) <= end
    ] if year >= 2022 else []
    datasets = [
        dataset
        for _, dataset in items
        if dataset.get("period", {}).get("end", "").startswith(f"{year}-")
    ]
    weekly = [dataset for dataset in datasets if dataset["period"]["kind"] == "month_to_date"]
    monthly = [dataset for dataset in datasets if dataset["period"]["kind"] == "month"]
    reference_months = [
        int(dataset["period"]["end"][5:7]) for dataset in monthly_references
        if dataset["period"]["end"].startswith(f"{year}-")
        and int(dataset["period"]["end"][5:7]) in closed_months
    ]
    complete_months = set(reference_months)
    complete_months.update(
        int(dataset["period"]["end"][5:7]) for dataset in monthly
        if all(metric_value(dataset, key) is not None for key in METRICS)
    )

    any_retail_months: list[int] = []
    any_nev_months: list[int] = []
    full_retail_months: list[int] = []
    full_nev_months: list[int] = []

    for month in audit_months:
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        overlapping = [
            dataset
            for dataset in datasets
            if date.fromisoformat(dataset["period"]["start"]) <= month_end
            and date.fromisoformat(dataset["period"]["end"]) >= month_start
        ]
        if any(metric_value(dataset, "passenger_retail") is not None for dataset in overlapping):
            any_retail_months.append(month)
        if any(metric_value(dataset, "nev_retail") is not None for dataset in overlapping):
            any_nev_months.append(month)
        if any(
            dataset["period"]["kind"] == "month"
            and metric_value(dataset, "passenger_retail") is not None
            for dataset in overlapping
        ):
            full_retail_months.append(month)
        if any(
            dataset["period"]["kind"] == "month"
            and metric_value(dataset, "nev_retail") is not None
            for dataset in overlapping
        ):
            full_nev_months.append(month)

    covered: set[date] = set()
    for dataset in datasets:
        period_start = max(date.fromisoformat(dataset["period"]["start"]), start)
        period_end = min(date.fromisoformat(dataset["period"]["end"]), end)
        current = period_start
        while current <= period_end:
            covered.add(current)
            current += timedelta(days=1)

    total_days = (end - start).days + 1
    covered_days = len(covered)
    missing_full_close = [month for month in closed_months if month not in full_retail_months]
    nev_missing_periods = [
        {
            "start": dataset["period"]["start"],
            "end": dataset["period"]["end"],
            "kind": dataset["period"]["kind"],
        }
        for dataset in datasets
        if metric_value(dataset, "passenger_retail") is not None
        and metric_value(dataset, "nev_retail") is None
    ]

    return {
        "year": year,
        "layer": layer,
        "raw": raw_counts.get(year, 0),
        "parsed": len(datasets),
        "weekly": len(weekly),
        "weekly_complete": sum(
            all(metric_value(dataset, key) is not None for key in METRICS)
            for dataset in weekly
        ),
        "monthly": len(monthly),
        "weekly_retail": sum(
            1 for dataset in weekly if metric_value(dataset, "passenger_retail") is not None
        ),
        "weekly_nev": sum(
            1 for dataset in weekly if metric_value(dataset, "nev_retail") is not None
        ),
        "monthly_retail": sum(
            1 for dataset in monthly if metric_value(dataset, "passenger_retail") is not None
        ),
        "monthly_nev": sum(
            1 for dataset in monthly if metric_value(dataset, "nev_retail") is not None
        ),
        "parsed_retail": sum(
            1 for dataset in datasets if metric_value(dataset, "passenger_retail") is not None
        ),
        "parsed_nev": sum(
            1 for dataset in datasets if metric_value(dataset, "nev_retail") is not None
        ),
        "audit_months": audit_months,
        "closed_months": closed_months,
        "reference_months": reference_months,
        "complete_months": sorted(complete_months.intersection(closed_months)),
        "any_retail_months": any_retail_months,
        "any_nev_months": any_nev_months,
        "full_retail_months": full_retail_months,
        "full_nev_months": full_nev_months,
        "missing_full_close": missing_full_close,
        "nev_missing_periods": nev_missing_periods,
        "covered_days": covered_days,
        "total_days": total_days,
        "calendar_pct": covered_days / total_days * 100 if total_days else 0.0,
        "gaps": date_gaps(covered, start, end),
        "window_start": start,
        "window_end": end,
    }


def build_summary() -> dict:
    items = load_datasets()
    items.extend(recover_legacy_months(items))
    latest = max(date.fromisoformat(dataset["period"]["end"]) for _, dataset in items)
    monthly_references = [
        item for item in load_monthly_references() if item["period"]["end"] <= latest.isoformat()
    ]
    raw_counts = load_raw_counts()
    years = [
        build_year(year, items, latest, raw_counts, monthly_references)
        for year in range(2020, latest.year + 1)
    ]
    parsed_years = [year for year in years if year["year"] >= 2022]

    total_raw = sum(year["raw"] for year in years)
    total_parsed = sum(year["parsed"] for year in years)
    total_weekly = sum(year["weekly"] for year in years)
    total_monthly = sum(year["monthly"] for year in years)
    total_weekly_retail = sum(year["weekly_retail"] for year in years)
    total_weekly_nev = sum(year["weekly_nev"] for year in years)
    total_monthly_retail = sum(year["monthly_retail"] for year in years)
    total_monthly_nev = sum(year["monthly_nev"] for year in years)
    total_retail = sum(year["parsed_retail"] for year in years)
    total_nev = sum(year["parsed_nev"] for year in years)

    month_span = sum(len(year["audit_months"]) for year in parsed_years)
    month_any_retail = sum(len(year["any_retail_months"]) for year in parsed_years)
    month_any_nev = sum(len(year["any_nev_months"]) for year in parsed_years)
    month_full_retail = sum(len(year["full_retail_months"]) for year in parsed_years)
    month_full_nev = sum(len(year["full_nev_months"]) for year in parsed_years)

    calendar_covered = sum(year["covered_days"] for year in parsed_years)
    calendar_total = sum(year["total_days"] for year in parsed_years)
    calendar_pct = calendar_covered / calendar_total * 100 if calendar_total else 0.0
    calendar_gap_days = calendar_total - calendar_covered

    calendar_rows = []
    for year in years:
        if year["year"] < 2022:
            continue
        for gap_start, gap_end in year["gaps"]:
            source_gap = KNOWN_PUBLICATION_GAPS.get((gap_start, gap_end))
            calendar_rows.append(
                {
                    "year": year["year"],
                    "type": "官方未发布" if source_gap else "日历缺口",
                    "start": gap_start.isoformat(),
                    "end": gap_end.isoformat(),
                    "days": (gap_end - gap_start).days + 1,
                    "impact": "乘用车零售/新能源零售",
                    "note": source_gap or "该日期范围缺少已解析区间",
                }
            )
    calendar_rows.insert(0, {
        "year": 2022,
        "type": "官方未发布",
        "start": "2022-10-01",
        "end": "2022-10-07",
        "days": 7,
        "impact": "独立周区间",
        "note": "10 月全月初步统计覆盖这些日期，官网无独立周度值",
    })

    nev_rows = []
    for year in parsed_years:
        if year["parsed"] and not year["any_nev_months"]:
            nev_rows.append(
                {
                    "year": year["year"],
                    "type": "新能源缺口",
                    "start": year["window_start"].isoformat(),
                    "end": year["window_end"].isoformat(),
                    "days": year["total_days"],
                    "impact": "新能源零售",
                    "note": "旧版《车市扫描》摘要无新能源零售；独立月报可提供全月值",
                }
            )
            continue
        for period in year["nev_missing_periods"]:
            nev_rows.append(
                {
                    "year": year["year"],
                    "type": "新能源缺口",
                    "start": period["start"],
                    "end": period["end"],
                    "days": (
                        date.fromisoformat(period["end"])
                        - date.fromisoformat(period["start"])
                    ).days
                    + 1,
                    "impact": "新能源零售",
                    "note": (
                        "《车市扫描》缺全月新能源零售；该月可查独立月报"
                        if period["kind"] == "month" and int(period["end"][5:7]) in year["reference_months"]
                        else "《车市扫描》该区间只有乘用车零售"
                    ),
                }
            )

    month_rows = []
    for year in parsed_years:
        for month in year["missing_full_close"]:
            month_start = date(year["year"], month, 1)
            month_end = date(year["year"], month, calendar.monthrange(year["year"], month)[1])
            has_reference = month in year["reference_months"]
            month_rows.append(
                {
                    "year": year["year"],
                    "type": "车市扫描月度缺口",
                    "start": month_start.isoformat(),
                    "end": month_end.isoformat(),
                    "days": month_end.day,
                    "impact": "全月数据",
                    "note": (
                        "独立《乘用车市场分析》已提供全月值"
                        if has_reference else "当前年度数据无直接全月来源"
                    ),
                }
            )

    return {
        "items": items,
        "monthly_references": monthly_references,
        "latest": latest,
        "years": years,
        "parsed_years": parsed_years,
        "total_raw": total_raw,
        "total_parsed": total_parsed,
        "total_weekly": total_weekly,
        "total_monthly": total_monthly,
        "total_weekly_retail": total_weekly_retail,
        "total_weekly_nev": total_weekly_nev,
        "total_monthly_retail": total_monthly_retail,
        "total_monthly_nev": total_monthly_nev,
        "total_retail": total_retail,
        "total_nev": total_nev,
        "month_span": month_span,
        "month_any_retail": month_any_retail,
        "month_any_nev": month_any_nev,
        "month_full_retail": month_full_retail,
        "month_full_nev": month_full_nev,
        "calendar_covered": calendar_covered,
        "calendar_total": calendar_total,
        "calendar_pct": calendar_pct,
        "calendar_gap_days": calendar_gap_days,
        "calendar_rows": calendar_rows,
        "nev_rows": nev_rows,
        "month_rows": month_rows,
    }


def write_summary_csv(years: list[dict]) -> None:
    fields = [
        "年份",
        "数据层级",
        "原始文章",
        "已解析区间",
        "周度区间",
        "月度收盘",
        "周度乘用车零售",
        "周度新能源零售",
        "月度乘用车零售",
        "月度新能源零售",
        "审计月份",
        "可覆盖月份_乘用车",
        "可覆盖月份_新能源",
        "完整月度收盘_乘用车",
        "完整月度收盘_新能源",
        "完整收盘缺口月份",
        "已结束月份",
        "独立月报数",
        "四项核心指标齐全的全月来源数",
        "日历覆盖天数",
        "日历总天数",
        "日历覆盖率(%)",
    ]
    with SUMMARY_CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for year in years:
            writer.writerow(
                {
                    "年份": year["year"],
                    "数据层级": year["layer"],
                    "原始文章": year["raw"],
                    "已解析区间": year["parsed"],
                    "周度区间": year["weekly"],
                    "月度收盘": year["monthly"],
                    "周度乘用车零售": year["weekly_retail"],
                    "周度新能源零售": year["weekly_nev"],
                    "月度乘用车零售": year["monthly_retail"],
                    "月度新能源零售": year["monthly_nev"],
                    "审计月份": len(year["audit_months"]) if year["year"] >= 2022 else "",
                    "可覆盖月份_乘用车": len(year["any_retail_months"]),
                    "可覆盖月份_新能源": len(year["any_nev_months"]),
                    "完整月度收盘_乘用车": len(year["full_retail_months"]),
                    "完整月度收盘_新能源": len(year["full_nev_months"]),
                    "完整收盘缺口月份": missing_close_label(year),
                    "已结束月份": len(year["closed_months"]),
                    "独立月报数": len(year["reference_months"]),
                    "四项核心指标齐全的全月来源数": len(year["complete_months"]),
                    "日历覆盖天数": year["covered_days"] if year["year"] >= 2022 else "",
                    "日历总天数": year["total_days"] if year["year"] >= 2022 else "",
                    "日历覆盖率(%)": f"{year['calendar_pct']:.1f}" if year["year"] >= 2022 else "",
                }
            )


def write_gap_csv(summary: dict) -> None:
    fields = ["年份", "缺口类型", "开始", "结束", "天数", "影响指标", "说明"]
    rows = (
        summary["calendar_rows"] + summary["nev_rows"] + summary["month_rows"]
    )
    with GAP_CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "年份": row["year"],
                    "缺口类型": row["type"],
                    "开始": row["start"],
                    "结束": row["end"],
                    "天数": row["days"],
                    "影响指标": row["impact"],
                    "说明": row["note"],
                }
            )


def render_html(summary: dict) -> str:
    years = summary["parsed_years"]
    latest_year = summary["latest"].year
    complete_months = sum(len(year["complete_months"]) for year in years)
    closed_months = sum(len(year["closed_months"]) for year in years)
    complete_weeks = sum(year["weekly_complete"] for year in years)
    total_weeks = sum(year["weekly"] for year in years)
    archive_count = sum(year["raw"] for year in summary["years"] if year["year"] < 2022)

    def card(label: str, value: str, sub: str, accent: bool = False) -> str:
        cls = "card accent" if accent else "card"
        return (
            f'<div class="{cls}"><div class="card-label">{html.escape(label)}</div>'
            f'<div class="card-value">{html.escape(value)}</div>'
            f'<div class="card-sub">{html.escape(sub)}</div></div>'
        )

    def rate(count: int, total: int) -> str:
        return f"{count / total * 100:.1f}".removesuffix(".0") + "%" if total else "—"

    def coverage_cell(count: int, total: int) -> str:
        percent = rate(count, total)
        return (
            f'<td class="coverage-cell"><strong>{percent}</strong>'
            f'<span class="muted">{count} / {total}</span>'
            f'<div class="bar" aria-hidden="true"><span style="width:{percent if total else "0%"}"></span></div></td>'
        )

    cards = "".join(
        [
            card(
                "月度指标覆盖",
                rate(complete_months, closed_months),
                f"{complete_months} / {closed_months} 个已结束月份四项齐全",
                accent=True,
            ),
            card(
                "周度指标覆盖",
                rate(complete_weeks, total_weeks),
                f"{complete_weeks} / {total_weeks} 个已入库周度区间四项齐全",
            ),
            card(
                "《车市扫描》日历覆盖",
                rate(summary["calendar_covered"], summary["calendar_total"]),
                f"{summary['calendar_covered']} / {summary['calendar_total']} 天有统计区间覆盖",
            ),
        ]
    )

    coverage_rows = "".join(
        "<tr>"
        f'<th scope="row">{year["year"]}</th>'
        f'{coverage_cell(len(year["complete_months"]), len(year["closed_months"]))}'
        f'{coverage_cell(year["weekly_complete"], year["weekly"])}'
        f'{coverage_cell(year["covered_days"], year["total_days"])}'
        "</tr>"
        for year in years
    )

    interval_rows = []
    for year in years:
        interval_rows.append(
            "<tr>"
            f"<td><strong>{year['year']}</strong><br><span class=\"muted\">{html.escape(year['layer'])}</span></td>"
            f"<td class=\"num\">{year['raw']}</td>"
            f"<td class=\"num\">{year['parsed']}</td>"
            f"<td class=\"num\">{year['weekly']}</td>"
            f"<td class=\"num\">{year['monthly']}</td>"
            f"<td class=\"num\">{year['weekly_retail']}</td>"
            f"<td class=\"num\">{year['weekly_nev']}</td>"
            f"<td class=\"num\">{year['monthly_retail']}</td>"
            f"<td class=\"num\">{year['monthly_nev']}</td>"
            "</tr>"
        )

    month_rows = []
    for year in years:
        audit_months = len(year["audit_months"])
        year_closed_months = len(year["closed_months"])
        missing = missing_close_label(year)
        month_rows.append(
            "<tr>"
            f"<td><strong>{year['year']}</strong></td>"
            f"<td class=\"num\">{audit_months}</td>"
            f"<td class=\"num\">{len(year['any_retail_months'])} / {audit_months}</td>"
            f"<td class=\"num\">{len(year['any_nev_months'])} / {audit_months}</td>"
            f"<td class=\"num\">{len(year['full_retail_months'])} / {year_closed_months}</td>"
            f"<td class=\"num\">{len(year['full_nev_months'])} / {year_closed_months}</td>"
            f"<td>{html.escape(missing)}</td>"
            f"<td class=\"num\">{len(year['reference_months'])}</td>"
            f"<td class=\"num\">{len(year['complete_months'])} / {year_closed_months}</td>"
            "</tr>"
        )

    calendar_rows_html = "".join(
        "<tr>"
        f"<td>{row['year']}</td>"
        f"<td><span class=\"gap-tag\">{html.escape(row['type'])}</span></td>"
        f"<td>{row['start']} ~ {row['end']}</td>"
        f"<td class=\"num\">{row['days']}</td>"
        f"<td>{html.escape(row['note'])}</td>"
        "</tr>"
        for row in summary["calendar_rows"]
    )

    metric_rows = summary["nev_rows"] + summary["month_rows"]
    metric_rows_html = "".join(
        "<tr>"
        f"<td>{row['year']}</td>"
        f"<td><span class=\"gap-tag\">{html.escape(row['type'])}</span></td>"
        f"<td>{row['start']} ~ {row['end']}</td>"
        f"<td class=\"num\">{row['days']}</td>"
        f"<td>{html.escape(row['impact'])}</td>"
        f"<td>{html.escape(row['note'])}</td>"
        "</tr>"
        for row in metric_rows
    )

    generated = date.today().isoformat()
    latest = summary["latest"].isoformat()

    css = """
    :root {
      --blue: #174A7C;
      --deep-blue: #06213D;
      --cyan: #7ECDEB;
      --light-blue: #DDEFF8;
      --cream: #FFF9EF;
      --gold: #D79A36;
      --brown: #7A4A24;
      --text: #1F2D3D;
      --muted: #6B7C8F;
      --card: #FFFFFF;
      --line: #E6EEF5;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--cream);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
        "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      -webkit-font-smoothing: antialiased;
    }
    .wrap { max-width: 1180px; margin: 0 auto; padding: 34px 24px 46px; }
    header {
      display: flex; justify-content: space-between; align-items: flex-end;
      gap: 24px; padding-bottom: 18px; border-bottom: 2px solid var(--blue);
    }
    h1 { margin: 0; color: var(--blue); font-size: 31px; line-height: 1.2; }
    .subtitle { margin: 8px 0 0; color: var(--muted); font-size: 14px; }
    .meta { color: var(--muted); font-size: 12px; text-align: right; line-height: 1.8; }
    .meta strong { color: var(--deep-blue); }
    .cards {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px;
      margin: 22px 0 0;
    }
    .card {
      background: var(--card); border: 1px solid var(--line); border-radius: 14px;
      padding: 16px 18px 15px; box-shadow: 0 4px 18px rgba(23, 74, 124, .045);
    }
    .card.accent { border-color: rgba(215, 154, 54, .35); }
    .card-label { color: var(--text); font-size: 13px; font-weight: 600; }
    .card-value {
      color: var(--blue); font-size: 38px; font-weight: 700; line-height: 1.2;
      margin-top: 5px; font-variant-numeric: tabular-nums;
    }
    .card.accent .card-value { color: var(--brown); }
    .card-sub { color: var(--muted); font-size: 12px; line-height: 1.5; margin-top: 4px; }
    section { margin-top: 30px; }
    h2 { color: var(--blue); font-size: 20px; margin: 0 0 6px; }
    h3 { color: var(--deep-blue); font-size: 15px; margin: 22px 0 8px; }
    .section-note { color: var(--muted); font-size: 12px; line-height: 1.75; margin: 0 0 11px; }
    .table-wrap {
      overflow-x: auto; background: var(--card); border: 1px solid var(--line);
      border-radius: 12px; box-shadow: 0 3px 14px rgba(23, 74, 124, .035);
    }
    .table-wrap + .section-note { margin-top: 8px; }
    table { width: 100%; border-collapse: collapse; min-width: 780px; }
    .coverage-table { min-width: 0; table-layout: fixed; }
    .coverage-table thead th { white-space: normal; font-size: 12px; }
    .coverage-table thead th:first-child { width: 18%; }
    .coverage-table tbody th {
      background: var(--card); border-top: 1px solid var(--line);
      font-size: 15px; border-right: 1px solid var(--line);
    }
    .coverage-table tbody tr:nth-child(even) th { background: #FBFDFF; }
    .coverage-cell { font-variant-numeric: tabular-nums; }
    .coverage-cell strong {
      color: var(--deep-blue); font-size: 16px; display: inline-block; margin-right: 8px;
    }
    th {
      background: var(--light-blue); color: var(--deep-blue); text-align: left;
      font-size: 11.5px; font-weight: 700; padding: 10px 10px; line-height: 1.35;
      white-space: nowrap;
    }
    td {
      border-top: 1px solid #EEF4F9; padding: 10px 10px; font-size: 12.5px;
      vertical-align: top; line-height: 1.55;
    }
    tr:nth-child(even) td { background: #FBFDFF; }
    .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
    .muted { color: var(--muted); }
    .gap-tag {
      display: inline-block; padding: 2px 7px; border-radius: 6px;
      background: var(--cream); color: var(--brown); border: 1px solid rgba(215, 154, 54, .25);
      font-size: 11.5px; white-space: nowrap;
    }
    .bar {
      height: 5px; width: 100%; background: #EAF2F8; border-radius: 999px;
      overflow: hidden; margin-top: 5px; max-width: 165px;
    }
    .bar span {
      display: block; height: 100%; border-radius: 999px;
      background: linear-gradient(90deg, var(--cyan), var(--blue));
    }
    ul.notes { margin: 6px 0 0; padding-left: 20px; color: var(--muted); font-size: 12.5px; line-height: 1.8; }
    ul.notes strong { color: var(--text); }
    details { margin-top: 30px; padding: 12px 0; border-top: 1px solid var(--line); }
    summary { cursor: pointer; color: var(--blue); font-weight: 700; font-size: 16px; }
    footer {
      margin-top: 34px; padding-top: 15px; border-top: 1px solid var(--line);
      color: var(--muted); font-size: 11.5px; line-height: 1.8;
    }
    @media (max-width: 900px) {
      .wrap { padding: 24px 16px 36px; }
      header { display: block; }
      .meta { text-align: left; margin-top: 12px; }
      h1 { font-size: 25px; }
    }
    @media (max-width: 560px) {
      .cards { gap: 6px; }
      .card { padding: 10px 7px; border-radius: 9px; }
      .card-value { font-size: clamp(21px, 5.8vw, 30px); }
      .card-label, .card-sub { font-size: 11px; }
      .coverage-table td, .coverage-table th { padding: 8px 6px; }
      .coverage-table thead th { font-size: 11px; }
      .coverage-cell strong { display: block; margin-right: 0; }
    }
    """

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>CPCA 2022 年起数据覆盖率审计</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
<header>
  <div>
    <h1>CPCA 2022 年起数据覆盖率</h1>
    <p class="subtitle">2022–{latest_year} 年度审计</p>
  </div>
  <div class="meta">审计截止 <strong>{latest}</strong><br>生成日期 {generated}</div>
</header>

<div class="cards">{cards}</div>

<section>
  <h2>各年覆盖率</h2>
  <p class="section-note">四项指标为乘用车和新能源的零售、批发。月度按已结束月份统计，含独立月报。周度按已入库的周度区间统计。</p>
  <div class="table-wrap">
    <table class="coverage-table">
      <thead>
        <tr>
          <th scope="col">年份</th>
          <th scope="col">月度四项齐全</th>
          <th scope="col">周度四项齐全</th>
          <th scope="col">日历覆盖</th>
        </tr>
      </thead>
      <tbody>{coverage_rows}</tbody>
    </table>
  </div>
  <p class="section-note">日历覆盖取《车市扫描》周度和全月区间的日期并集。全月区间可以覆盖缺少独立周报的日期。</p>
</section>

<section>
  <h2>缺口明细</h2>
  <h3>日历与官方发布缺口</h3>
  <div class="table-wrap">
    <table>
      <thead><tr><th>年份</th><th>类型</th><th>区间</th><th>天数</th><th>说明</th></tr></thead>
      <tbody>{calendar_rows_html}</tbody>
    </table>
  </div>

  <h3>指标与月度收盘缺口</h3>
  <p class="section-note">按《车市扫描》列出周度指标和全月缺口。独立月报的数值可以在年度数据中查阅，保留独立来源及发布口径。</p>
  <div class="table-wrap">
    <table>
      <thead><tr><th>年份</th><th>类型</th><th>区间</th><th>天数</th><th>影响指标</th><th>说明</th></tr></thead>
      <tbody>{metric_rows_html}</tbody>
    </table>
  </div>
</section>

<details>
  <summary>年度区间与月份明细</summary>
  <h3>来源文章与区间数</h3>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>年份 / 层级</th><th>原始文章</th><th>已解析区间</th><th>周度区间</th><th>月度收盘</th>
          <th>周度<br>乘用车</th><th>周度<br>新能源</th><th>月度<br>乘用车</th><th>月度<br>新能源</th>
        </tr>
      </thead>
      <tbody>{''.join(interval_rows)}</tbody>
    </table>
  </div>

  <h3>月份与独立月报</h3>
  <p class="section-note">有数据月份含当月未结束的周度区间。全月统计只计算已结束月份。四项齐全要求同一来源报告同时给出乘用车及新能源零售、批发，包含独立《乘用车市场分析》。</p>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>年份</th><th>审计月份</th><th>可覆盖<br>乘用车</th><th>可覆盖<br>新能源</th>
          <th>车市扫描全月<br>乘用车</th><th>车市扫描全月<br>新能源</th><th>车市扫描全月缺口</th>
          <th>独立月报数</th><th>四项齐全<br>已结束月份</th>
        </tr>
      </thead>
      <tbody>{''.join(month_rows)}</tbody>
    </table>
  </div>
</details>

<section>
  <h2>口径说明</h2>
  <ul class="notes">
    <li><strong>周度区间</strong>是 CPCA 官方发布统计区间，不保证 7 天；不补官网未发布的自然周。</li>
    <li><strong>月份可覆盖</strong>只表示该月有任意部分区间数据，不等于有完整月度总量；<strong>完整月度收盘</strong>才表示该月有全月口径数据。</li>
    <li>缺口只记录，不补数、不插值、不从累计值反推缺失周。</li>
    <li>本报告只审计已入库数据，原始 HTML 中存在但尚未解析的叙述不计入覆盖。</li>
  </ul>
</section>

<footer>
  2020–2021 年保留 {archive_count} 篇原始 HTML，仅归档。<br>
  数据来源：CPCA（乘联会） · 审计脚本：scripts/coverage_audit.py<br>
  输出：data/coverage_audit.csv、data/coverage_gaps.csv、data/annual/YYYY.json · 本报告为离线单文件 HTML
</footer>
</div>
</body>
</html>
"""


def main() -> int:
    summary = build_summary()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_summary_csv(summary["years"])
    write_gap_csv(summary)
    write_annual_exports(summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_html(summary), encoding="utf-8")

    print("Coverage audit summary")
    print(
        json.dumps(
            {
                "latest": summary["latest"].isoformat(),
                "raw_articles": summary["total_raw"],
                "parsed_intervals": summary["total_parsed"],
                "weekly": summary["total_weekly"],
                "monthly": summary["total_monthly"],
                "passenger_retail": summary["total_retail"],
                "nev_retail": summary["total_nev"],
                "month_span": summary["month_span"],
                "months_with_passenger_any": summary["month_any_retail"],
                "months_with_nev_any": summary["month_any_nev"],
                "months_with_full_passenger": summary["month_full_retail"],
                "months_with_full_nev": summary["month_full_nev"],
                "calendar_covered_days": summary["calendar_covered"],
                "calendar_total_days": summary["calendar_total"],
                "calendar_pct": round(summary["calendar_pct"], 1),
                "calendar_gap_days": summary["calendar_gap_days"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"Wrote {SUMMARY_CSV_PATH}")
    print(f"Wrote {GAP_CSV_PATH}")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
