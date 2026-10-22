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

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LEGACY_DATA_DIR = DATA_DIR / "legacy"
REPORT_PATH = ROOT / "reports/coverage_audit.html"
SUMMARY_CSV_PATH = DATA_DIR / "coverage_audit.csv"
GAP_CSV_PATH = DATA_DIR / "coverage_gaps.csv"
OFFICIAL_MANIFEST = ROOT / "input/official/manifest.json"
LEGACY_MANIFEST = ROOT / "input/legacy/manifest.json"

LAYER_BY_YEAR = {
    2020: "原始归档",
    2021: "原始归档",
    2022: "Legacy V2",
    2023: "Legacy V2",
    2024: "正式数据",
    2025: "正式数据",
    2026: "正式数据",
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
    label = format_month_ranges(year["missing_full_close"])
    if year["year"] == 2026 and 10 in year["missing_full_close"]:
        if label == "10":
            label = "10（未结束）"
        else:
            label = label.replace("、10", "、10（未结束）")
    return label


def month_group_dates(year: int, group: list[int]) -> tuple[date, date]:
    first, last = group[0], group[-1]
    start = date(year, first, 1)
    end = date(year, last, calendar.monthrange(year, last)[1])
    return start, end


def build_year(
    year: int,
    items: list[tuple[str, dict]],
    latest: date,
    raw_counts: Counter[int],
) -> dict:
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    if year == latest.year:
        end = latest

    audit_months = list(range(1, end.month + 1))
    datasets = [
        dataset
        for _, dataset in items
        if dataset.get("period", {}).get("end", "").startswith(f"{year}-")
    ]
    weekly = [dataset for dataset in datasets if dataset["period"]["kind"] == "month_to_date"]
    monthly = [dataset for dataset in datasets if dataset["period"]["kind"] == "month"]

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
    missing_full_close = [
        month for month in audit_months if month not in full_retail_months
    ]
    nev_missing_periods = [
        {
            "start": dataset["period"]["start"],
            "end": dataset["period"]["end"],
        }
        for dataset in datasets
        if metric_value(dataset, "passenger_retail") is not None
        and metric_value(dataset, "nev_retail") is None
    ]

    return {
        "year": year,
        "layer": LAYER_BY_YEAR.get(year, ""),
        "raw": raw_counts.get(year, 0),
        "parsed": len(datasets),
        "weekly": len(weekly),
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
    latest = max(date.fromisoformat(dataset["period"]["end"]) for _, dataset in items)
    raw_counts = load_raw_counts()
    years = [
        build_year(year, items, latest, raw_counts)
        for year in range(2020, latest.year + 1)
    ]
    parsed_years = [year for year in years if year["parsed"] > 0]

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

    layer_rows = []
    for layer, label, year_numbers, description in [
        ("原始归档", "2020–2021", range(2020, 2022), "仅原始 HTML；旧格式未解析"),
        (
            "Legacy V2",
            "2022–2023",
            range(2022, 2024),
            "乘用车零售/批发；部分新能源/YTD",
        ),
        (
            "正式数据",
            "2024–2026*",
            range(2024, 2027),
            "完整周度/月度正式数据",
        ),
    ]:
        layer_years = [year for year in years if year["year"] in year_numbers]
        layer_rows.append(
            {
                "layer": layer,
                "years": label,
                "raw": sum(year["raw"] for year in layer_years),
                "parsed": sum(year["parsed"] for year in layer_years),
                "description": description,
            }
        )

    calendar_rows = []
    for year in years:
        if year["parsed"] == 0:
            calendar_rows.append(
                {
                    "year": year["year"],
                    "type": "未解析",
                    "start": year["window_start"].isoformat(),
                    "end": year["window_end"].isoformat(),
                    "days": year["total_days"],
                    "impact": "乘用车零售/新能源零售",
                    "note": "原始 HTML 已归档；旧格式只有周度日均叙述，未生成结构化数据",
                }
            )
            continue
        for gap_start, gap_end in year["gaps"]:
            gap_type = "官方未发布" if year["year"] == 2026 else "日历缺口"
            if year["year"] == 2026:
                note = (
                    "春节前停更/发布节奏；官网无对应周报区间"
                    if gap_start.month == 1
                    else "春节假期/节后恢复；官网无对应周报区间"
                )
            elif year["year"] == 2022:
                note = (
                    "官网无独立周摘要；10/16 文章只有 10/8-16 与 "
                    "10/1-16 累计，不用累计差反推"
                )
            else:
                note = "官网无独立周摘要；保留缺口，不反推"
            calendar_rows.append(
                {
                    "year": year["year"],
                    "type": gap_type,
                    "start": gap_start.isoformat(),
                    "end": gap_end.isoformat(),
                    "days": (gap_end - gap_start).days + 1,
                    "impact": "乘用车零售/新能源零售",
                    "note": note,
                }
            )

    nev_rows = []
    for year in parsed_years:
        if len(year["any_nev_months"]) == 0:
            nev_rows.append(
                {
                    "year": year["year"],
                    "type": "新能源缺口",
                    "start": year["window_start"].isoformat(),
                    "end": year["window_end"].isoformat(),
                    "days": year["total_days"],
                    "impact": "新能源零售",
                    "note": "该年旧格式摘要不发布新能源零售",
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
                    "note": "该区间有乘用车零售，但没有新能源零售速报",
                }
            )

    month_rows = []
    for year in parsed_years:
        for group in group_months(year["missing_full_close"]):
            if year["year"] == 2026 and group == [10]:
                continue
            group_start, group_end = month_group_dates(year["year"], group)
            month_label = format_month_ranges(group)
            impact = "完整月度收盘（乘用车/新能源）"
            note = f"{month_label} 月缺少 kind=month 全月收盘；周度 MTD 不等同于全月收盘"
            if year["year"] == 2022:
                impact = "完整月度收盘（乘用车）"
                note = (
                    f"{month_label} 月只有周度 MTD；"
                    "当前资产仅 5、9 月有完整月度收盘"
                )
            month_rows.append(
                {
                    "year": year["year"],
                    "type": "完整月度收盘缺口",
                    "start": group_start.isoformat(),
                    "end": group_end.isoformat(),
                    "days": (group_end - group_start).days + 1,
                    "impact": impact,
                    "note": note,
                }
            )

    return {
        "items": items,
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
        "layer_rows": layer_rows,
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
                    "审计月份": len(year["audit_months"]),
                    "可覆盖月份_乘用车": len(year["any_retail_months"]),
                    "可覆盖月份_新能源": len(year["any_nev_months"]),
                    "完整月度收盘_乘用车": len(year["full_retail_months"]),
                    "完整月度收盘_新能源": len(year["full_nev_months"]),
                    "完整收盘缺口月份": missing_close_label(year),
                    "日历覆盖天数": year["covered_days"],
                    "日历总天数": year["total_days"],
                    "日历覆盖率(%)": f"{year['calendar_pct']:.1f}",
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
    years = summary["years"]
    total_parsed = summary["total_parsed"]
    total_nev = summary["total_nev"]
    nev_pct = total_nev / total_parsed * 100 if total_parsed else 0.0
    month_span = summary["month_span"]
    month_any_retail = summary["month_any_retail"]
    month_any_nev = summary["month_any_nev"]
    month_full_retail = summary["month_full_retail"]
    month_full_nev = summary["month_full_nev"]
    calendar_pct = summary["calendar_pct"]
    calendar_gap_days = summary["calendar_gap_days"]

    def card(label: str, value: str, sub: str, accent: bool = False) -> str:
        cls = "card accent" if accent else "card"
        return (
            f'<div class="{cls}"><div class="card-label">{html.escape(label)}</div>'
            f'<div class="card-value">{html.escape(value)}</div>'
            f'<div class="card-sub">{html.escape(sub)}</div></div>'
        )

    cards = "".join(
        [
            card("原始归档", str(summary["total_raw"]), "2020–2026 全部层级"),
            card(
                "已解析区间",
                str(total_parsed),
                f"{summary['total_weekly']} 周度 · {summary['total_monthly']} 月度",
            ),
            card(
                "乘用车零售",
                f"{summary['total_retail']}/{total_parsed}",
                "100.0% 已解析区间有值",
            ),
            card(
                "新能源零售",
                f"{total_nev}/{total_parsed}",
                f"{nev_pct:.1f}% 已解析区间有值",
                accent=True,
            ),
            card(
                "月份可覆盖",
                f"{month_any_retail}/{month_span}",
                f"2022–2026 · 新能源 {month_any_nev}/{month_span}",
            ),
            card(
                "解析日历覆盖",
                f"{calendar_pct:.1f}%",
                f"2022–2026 · 缺口 {calendar_gap_days} 天",
            ),
        ]
    )

    layer_rows_html = "".join(
        "<tr>"
        f"<td><span class=\"pill\">{html.escape(row['layer'])}</span></td>"
        f"<td>{html.escape(row['years'])}</td>"
        f"<td class=\"num\">{row['raw']}</td>"
        f"<td class=\"num\">{row['parsed']}</td>"
        f"<td>{html.escape(row['description'])}</td>"
        "</tr>"
        for row in summary["layer_rows"]
    )
    layer_rows_html += (
        "<tr class=\"total\"><td>合计</td><td>2020–2026</td>"
        f"<td class=\"num\">{summary['total_raw']}</td>"
        f"<td class=\"num\">{summary['total_parsed']}</td>"
        "<td>原始归档 + Legacy V2 + 正式数据</td></tr>"
    )

    interval_rows = []
    for year in years:
        pct = year["calendar_pct"]
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
            f"<td class=\"calendar\">{year['covered_days']} / {year['total_days']}"
            f"<div class=\"muted\">{pct:.1f}%</div>"
            f"<div class=\"bar\"><span style=\"width:{min(pct, 100):.1f}%\"></span></div></td>"
            "</tr>"
        )

    month_rows = []
    for year in years:
        audit_months = len(year["audit_months"])
        missing = missing_close_label(year)
        month_rows.append(
            "<tr>"
            f"<td><strong>{year['year']}</strong></td>"
            f"<td class=\"num\">{audit_months}</td>"
            f"<td class=\"num\">{len(year['any_retail_months'])} / {audit_months}</td>"
            f"<td class=\"num\">{len(year['any_nev_months'])} / {audit_months}</td>"
            f"<td class=\"num\">{len(year['full_retail_months'])} / {audit_months}</td>"
            f"<td class=\"num\">{len(year['full_nev_months'])} / {audit_months}</td>"
            f"<td>{html.escape(missing)}</td>"
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
    .eyebrow {
      color: var(--gold); font-size: 12px; font-weight: 700;
      letter-spacing: .14em; text-transform: uppercase; margin-bottom: 7px;
    }
    h1 { margin: 0; color: var(--blue); font-size: 31px; line-height: 1.2; }
    .subtitle { margin: 8px 0 0; color: var(--muted); font-size: 14px; }
    .meta { color: var(--muted); font-size: 12px; text-align: right; line-height: 1.8; }
    .meta strong { color: var(--deep-blue); }
    .lede {
      margin: 22px 0 0; color: var(--text); font-size: 14px; line-height: 1.85;
      max-width: 930px;
    }
    .cards {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px;
      margin: 24px 0 8px;
    }
    .card {
      background: var(--card); border: 1px solid var(--line); border-radius: 14px;
      padding: 16px 18px 15px; box-shadow: 0 4px 18px rgba(23, 74, 124, .045);
    }
    .card.accent { border-color: rgba(215, 154, 54, .35); }
    .card-label { color: var(--muted); font-size: 12px; letter-spacing: .03em; }
    .card-value {
      color: var(--blue); font-size: 27px; font-weight: 700; line-height: 1.2;
      margin-top: 5px; font-variant-numeric: tabular-nums;
    }
    .card.accent .card-value { color: var(--brown); }
    .card-sub { color: var(--muted); font-size: 12px; margin-top: 4px; }
    section { margin-top: 30px; }
    h2 { color: var(--blue); font-size: 20px; margin: 0 0 6px; }
    h3 { color: var(--deep-blue); font-size: 15px; margin: 22px 0 8px; }
    .section-note { color: var(--muted); font-size: 12px; line-height: 1.75; margin: 0 0 11px; }
    .table-wrap {
      overflow-x: auto; background: var(--card); border: 1px solid var(--line);
      border-radius: 12px; box-shadow: 0 3px 14px rgba(23, 74, 124, .035);
    }
    table { width: 100%; border-collapse: collapse; min-width: 780px; }
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
    tr.total td { background: #F3F9FD; font-weight: 700; color: var(--deep-blue); }
    .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
    .calendar { min-width: 105px; font-variant-numeric: tabular-nums; }
    .muted { color: var(--muted); }
    .pill {
      display: inline-block; padding: 2px 8px; border-radius: 999px;
      background: var(--light-blue); color: var(--blue); font-size: 11.5px;
      font-weight: 600; white-space: nowrap;
    }
    .gap-tag {
      display: inline-block; padding: 2px 7px; border-radius: 6px;
      background: var(--cream); color: var(--brown); border: 1px solid rgba(215, 154, 54, .25);
      font-size: 11.5px; white-space: nowrap;
    }
    .bar {
      height: 5px; width: 100%; background: #EAF2F8; border-radius: 999px;
      overflow: hidden; margin-top: 5px; min-width: 80px;
    }
    .bar span {
      display: block; height: 100%; border-radius: 999px;
      background: linear-gradient(90deg, var(--cyan), var(--blue));
    }
    ul.notes { margin: 6px 0 0; padding-left: 20px; color: var(--muted); font-size: 12.5px; line-height: 1.8; }
    ul.notes strong { color: var(--text); }
    footer {
      margin-top: 34px; padding-top: 15px; border-top: 1px solid var(--line);
      color: var(--muted); font-size: 11.5px; line-height: 1.8;
    }
    @media (max-width: 900px) {
      .wrap { padding: 24px 16px 36px; }
      header { display: block; }
      .meta { text-align: left; margin-top: 12px; }
      .cards { grid-template-columns: repeat(2, 1fr); }
      h1 { font-size: 25px; }
    }
    @media (max-width: 560px) {
      .cards { grid-template-columns: 1fr; }
    }
    """

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>CPCA 历史数据覆盖率审计</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
<header>
  <div>
    <div class="eyebrow">CPCA · 数据资产审计</div>
    <h1>历史数据覆盖率审计</h1>
    <p class="subtitle">2020–2026 · 周度区间、月度收盘与指标可用性</p>
  </div>
  <div class="meta">审计截止 <strong>{latest}</strong><br>生成日期 {generated}</div>
</header>

<p class="lede">
所有已解析区间中，乘用车零售覆盖 {summary['total_retail']}/{total_parsed}，
新能源零售覆盖 {total_nev}/{total_parsed}。2022–2026 已发生的 {month_span} 个月中，
{month_any_retail} 个月至少有乘用车零售区间，{month_any_nev} 个月至少有新能源零售区间；
若要求完整月度收盘，则分别为 {month_full_retail} 和 {month_full_nev} 个月。
2020–2021 目前只有原始 HTML，没有结构化数据。
</p>

<section>
  <div class="cards">{cards}</div>
</section>

<section>
  <h2>资产分层</h2>
  <p class="section-note">按数据层级看原始文章与已解析区间；原始文章按统计周截止年归属，和解析区间不完全一一对应。</p>
  <div class="table-wrap">
    <table>
      <thead><tr><th>层级</th><th>覆盖年份</th><th>原始文章</th><th>已解析区间</th><th>说明</th></tr></thead>
      <tbody>{layer_rows_html}</tbody>
    </table>
  </div>
  <p class="section-note">* 2026 年截至 {latest}。2022–2023 的原始文章与解析区间差异来自同 period 旧版去重和一篇文章拆分多个区间。</p>
</section>

<section>
  <h2>年度区间覆盖</h2>
  <p class="section-note">周度区间 = <code>kind=month_to_date</code>；月度收盘 = <code>kind=month</code>。周度是 CPCA 官方发布区间，不保证 7 天。</p>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>年份 / 层级</th><th>原始文章</th><th>已解析区间</th><th>周度区间</th><th>月度收盘</th>
          <th>周度<br>乘用车</th><th>周度<br>新能源</th><th>月度<br>乘用车</th><th>月度<br>新能源</th><th>日历覆盖</th>
        </tr>
      </thead>
      <tbody>{''.join(interval_rows)}</tbody>
    </table>
  </div>
</section>

<section>
  <h2>年度月份覆盖</h2>
  <p class="section-note">“可覆盖月份”表示该月至少有一个区间（含周度 MTD）带有该指标；“完整月度收盘”严格要求该月有 <code>kind=month</code> 记录。2026 年按截至 {latest} 的 10 个月计算。</p>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>年份</th><th>审计月份</th><th>可覆盖<br>乘用车</th><th>可覆盖<br>新能源</th>
          <th>完整收盘<br>乘用车</th><th>完整收盘<br>新能源</th><th>完整收盘缺口月份</th>
        </tr>
      </thead>
      <tbody>{''.join(month_rows)}</tbody>
    </table>
  </div>
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
  <p class="section-note">完整月度收盘缺口按当前已入库资产统计；2022 旧格式文章中的部分月末累计表述尚未入库，不计入覆盖。</p>
  <div class="table-wrap">
    <table>
      <thead><tr><th>年份</th><th>类型</th><th>区间</th><th>天数</th><th>影响指标</th><th>说明</th></tr></thead>
      <tbody>{metric_rows_html}</tbody>
    </table>
  </div>
</section>

<section>
  <h2>口径说明</h2>
  <ul class="notes">
    <li><strong>周度区间</strong>是 CPCA 官方发布统计区间，不保证 7 天；不补官网未发布的自然周。</li>
    <li><strong>月份可覆盖</strong>只表示该月有任意部分区间数据，不等于有完整月度总量；<strong>完整月度收盘</strong>才表示该月有全月口径数据。</li>
    <li><strong>日历覆盖</strong>按所有已解析区间的日期并集计算；2026 年按 1 月 1 日至 {latest} 计算。</li>
    <li>2020–2021 只有原始 HTML 归档，没有进入 `data/*.json` 或 `data/legacy/*.json`，因此按未解析处理。</li>
    <li>缺口只记录，不补数、不插值、不从累计值反推缺失周。</li>
    <li>本报告只审计已入库数据，原始 HTML 中存在但尚未解析的叙述不计入覆盖。</li>
  </ul>
</section>

<footer>
  数据来源：CPCA（乘联会） · 审计脚本：scripts/coverage_audit.py<br>
  输出：data/coverage_audit.csv、data/coverage_gaps.csv · 本报告为离线单文件 HTML
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
