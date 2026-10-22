#!/usr/bin/env python3
"""Render the lean CPCA weekly retail brief from standard_dataset.csv.

The report has three weekly views at most:
- latest interval (or "当周" in the first week of a month)
- month-to-date
- year-to-date

Each view shows passenger retail and NEV retail with year-on-year change.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
from datetime import date
from pathlib import Path

SECTION_ORDER = {"week": 0, "month_to_date": 1, "year_to_date": 2}

CAR_ICON = """
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"
     stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <path d="M4 15.5V12l2-4.5h12L20 12v3.5"/>
  <path d="M4 15.5h16"/>
  <path d="M6.5 7.5h11"/>
  <circle cx="8" cy="16.5" r="1.2"/>
  <circle cx="16" cy="16.5" r="1.2"/>
</svg>
"""

SPARK_ICON = """
<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
  <path d="M12 2.5l2.2 7.3L21.5 12l-7.3 2.2L12 21.5l-2.2-7.3L2.5 12l7.3-2.2L12 2.5z"/>
</svg>
"""


def esc(value: object) -> str:
    return html.escape(str(value))


def fmt_num(value: float | int | None) -> str:
    if value is None:
        return "未发布"
    return f"{float(value):,.1f}"


def fmt_pct(value: float | int | None, digits: int = 1) -> str:
    if value is None:
        return "未发布"
    if value == 0:
        return f"{0:.{digits}f}%"
    return f"{value:+.{digits}f}%"


def fmt_pct_display(value: float | int | None, digits: int = 1) -> str:
    return fmt_pct(value, digits).replace("-", "−")


def pct_class(value: float | int | None) -> str:
    if value is None:
        return "flat"
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "flat"


def fmt_date_cn(value: date) -> str:
    return f"{value.year}年{value.month}月{value.day}日"


def fmt_range_cn(start: date, end: date) -> str:
    if start.year == end.year and start.month == end.month:
        return f"{start.month}月{start.day}–{end.day}日"
    if start.year == end.year:
        return f"{start.month}月{start.day}日–{end.month}月{end.day}日"
    return f"{fmt_date_cn(start)}–{fmt_date_cn(end)}"


def fmt_period_cn(start: date, end: date) -> str:
    if start.year == end.year and start.month == end.month:
        return f"{start.year}年{start.month}月{start.day}–{end.day}日"
    if start.year == end.year:
        return f"{start.year}年{start.month}月{start.day}日–{end.month}月{end.day}日"
    return f"{fmt_date_cn(start)}–{fmt_date_cn(end)}"


def load_latest_period(data_dir: Path) -> dict:
    items: list[dict] = []
    for path in sorted(data_dir.glob("*.json")):
        items.append(json.loads(path.read_text(encoding="utf-8")))
    if not items:
        raise SystemExit(f"No JSON datasets found in {data_dir}")
    return max(items, key=lambda item: item["period"]["end"])


def load_standard_table(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(
            f"Standard dataset not found: {path}. "
            "Run python3 scripts/build_standard_dataset.py first."
        )
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return []

    latest_date = max(row["快照日期"] for row in rows)
    selected = [row for row in rows if row["快照日期"] == latest_date]
    selected.sort(key=lambda row: SECTION_ORDER.get(row.get("区间类型", ""), 9))

    if not any(row.get("区间类型") == "week" for row in selected):
        raise SystemExit(f"No weekly row found in {path} for snapshot {latest_date}")
    return selected


def report_status_label(source: dict) -> str:
    status = source.get("report_status") or source.get("status")
    return "（初步统计）" if status == "preliminary" else ""


def is_estimated(row: dict[str, str]) -> bool:
    return row.get("数据口径", "").startswith("由相邻两期")


def section_title(row: dict[str, str], has_month: bool) -> str:
    kind = row["区间类型"]
    if kind == "week":
        return "最新区间" if has_month else "当周"
    if kind == "month_to_date":
        return "当月累计"
    return "当年累计"


def metric_block(
    label: str,
    value: str,
    yoy: str,
    estimated: bool,
    icon: str,
) -> str:
    yoy_value = float(yoy)
    digits = 1 if estimated else 0
    arrow = "↓" if yoy_value < 0 else ("↑" if yoy_value > 0 else "→")
    icon_svg = CAR_ICON if icon == "car" else SPARK_ICON
    yoy_label = "同比去年同期（估算）" if estimated else "同比去年同期"
    return f"""
      <article class="metric">
        <div class="metric-icon {icon}">{icon_svg}</div>
        <div class="metric-content">
          <div class="metric-label">{esc(label)}</div>
          <div class="metric-value">{fmt_num(float(value))}<span class="unit">万辆</span></div>
          <div class="metric-yoy">
            <span class="yoy-label">{yoy_label}</span>
            <span class="yoy-value {pct_class(yoy_value)}"><span class="arrow">{arrow}</span>{fmt_pct_display(yoy_value, digits)}</span>
          </div>
        </div>
      </article>
    """


def section_block(index: int, row: dict[str, str], has_month: bool) -> str:
    start = date.fromisoformat(row["区间开始"])
    end = date.fromisoformat(row["区间截止"])
    title = section_title(row, has_month)
    estimated = is_estimated(row)
    date_label = fmt_range_cn(start, end)
    latest_class = " is-latest" if index == 0 else ""

    passenger = metric_block(
        "乘用车市场零售",
        row["乘用车零售(万辆)"],
        row["乘用车零售同比(%)"],
        estimated,
        "car",
    )
    nev = metric_block(
        "新能源市场零售",
        row["新能源零售(万辆)"],
        row["新能源零售同比(%)"],
        estimated,
        "spark",
    )

    return f"""
    <section class="section{latest_class}">
      <div class="section-head">
        <div class="section-index">{index + 1:02d}</div>
        <h2>{esc(title)}</h2>
        <div class="section-date">{esc(date_label)}</div>
      </div>
      <div class="metrics">{passenger}{nev}</div>
    </section>
    """


def render_html(latest: dict, rows: list[dict[str, str]]) -> str:
    start = date.fromisoformat(latest["period"]["start"])
    end = date.fromisoformat(latest["period"]["end"])
    period_label = fmt_period_cn(start, end)
    status = report_status_label(latest.get("source", {}))
    has_month = any(row.get("区间类型") == "month_to_date" for row in rows)
    sections = "".join(
        section_block(index, row, has_month) for index, row in enumerate(rows)
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>全国乘用车市场零售简报 · {esc(period_label)}</title>
<style>
:root {{
  --blue: #174A7C;
  --deep: #06213D;
  --cyan: #7ECDEB;
  --light-blue: #DDEFF8;
  --cream: #FFF9EF;
  --gold: #D79A36;
  --text: #1F2D3D;
  --muted: #6B7C8F;
  --line: #E6EDF4;
  --positive: #2F7D6D;
  --negative: #B85C4A;
}}
* {{ box-sizing: border-box; }}
html {{ -webkit-text-size-adjust: 100%; }}
body {{
  margin: 0;
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  background:
    radial-gradient(circle at 12% 8%, rgba(126, 205, 235, 0.18), transparent 30%),
    radial-gradient(circle at 88% 2%, rgba(215, 154, 54, 0.12), transparent 26%),
    var(--cream);
  line-height: 1.6;
}}
.brief {{
  width: calc(100% - 32px);
  max-width: 860px;
  margin: 24px auto;
  padding: 30px 38px 20px;
  border: 1px solid var(--line);
  border-radius: 24px;
  background: #FFFFFF;
  box-shadow: 0 20px 55px rgba(6, 33, 61, 0.06);
}}
.brief-header {{ padding-bottom: 16px; border-bottom: 1px solid var(--line); }}
.header-row {{ display: flex; align-items: center; justify-content: space-between; gap: 20px; }}
.eyebrow {{ color: var(--blue); font-size: 10px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; }}
.brand {{
  padding: 3px 8px;
  border: 1.5px solid var(--blue);
  border-radius: 7px;
  color: var(--blue);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
}}
h1 {{
  margin: 10px 0 4px;
  color: var(--deep);
  font-size: clamp(30px, 4.2vw, 36px);
  font-weight: 750;
  line-height: 1.1;
  letter-spacing: -0.035em;
}}
.subtitle {{ margin: 0; color: var(--muted); font-size: 12px; }}
.section {{
  padding: 14px 0;
  border-top: 1px solid var(--line);
}}
.section:first-of-type {{ border-top: none; }}
.section.is-latest {{
  margin: 10px 0 0;
  padding: 14px 16px;
  border: 1px solid #DDEFF8;
  border-radius: 16px;
  background: #F8FCFF;
}}
.section.is-latest + .section {{ border-top: 1px solid var(--line); }}
.section-head {{ margin-bottom: 7px; }}
.section-index {{ color: var(--blue); font-size: 9px; font-weight: 800; letter-spacing: 0.12em; }}
.section.is-latest .section-index {{ color: var(--gold); }}
.section-head h2 {{ margin: 1px 0; color: var(--deep); font-size: 16px; letter-spacing: -0.01em; }}
.section-date {{ color: var(--muted); font-size: 10px; }}
.metrics {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }}
.metric {{
  display: flex;
  gap: 9px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #FFFFFF;
}}
.metric-icon {{
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: var(--light-blue);
  color: var(--blue);
}}
.metric-icon.spark {{ background: #FFF4E2; color: var(--gold); }}
.metric-icon svg {{ width: 17px; height: 17px; }}
.metric-content {{ min-width: 0; }}
.metric-label {{ color: var(--muted); font-size: 10px; }}
.metric-value {{
  margin: 2px 0 3px;
  color: var(--deep);
  font-size: 24px;
  font-weight: 750;
  line-height: 1.05;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
}}
.unit {{ margin-left: 3px; color: var(--muted); font-size: 9px; font-weight: 500; letter-spacing: 0; }}
.metric-yoy {{ display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }}
.yoy-label {{ color: var(--muted); font-size: 9px; }}
.yoy-value {{ font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums; }}
.yoy-value.negative {{ color: var(--negative); }}
.yoy-value.positive {{ color: var(--positive); }}
.yoy-value.flat {{ color: var(--muted); }}
.arrow {{ margin-right: 2px; }}
.brief-footer {{
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 9px;
  line-height: 1.7;
}}
.sep {{ margin: 0 5px; color: #B9C6D3; }}
@media (max-width: 760px) {{
  .brief {{ width: auto; margin: 12px; padding: 22px 18px 18px; border-radius: 18px; }}
  h1 {{ font-size: 30px; }}
  .section {{ padding: 18px 0; }}
  .section.is-latest {{ padding: 16px 14px; margin-top: 14px; }}
  .section-head {{ margin-bottom: 10px; }}
  .metrics {{ grid-template-columns: 1fr; gap: 9px; }}
  .metric {{ padding: 10px 12px; }}
  .metric-value {{ font-size: 24px; }}
  .brief-footer {{ font-size: 9px; }}
}}
@media (max-height: 820px) and (min-width: 761px) {{
  .brief {{ margin: 10px auto; padding: 20px 30px 14px; }}
  h1 {{ font-size: 30px; }}
  .brief-header {{ padding-bottom: 12px; }}
  .section {{ padding: 10px 0; }}
  .section.is-latest {{ padding: 10px 14px; margin-top: 8px; }}
  .section-head {{ margin-bottom: 5px; }}
  .metric {{ padding: 8px 10px; }}
  .metric-value {{ font-size: 21px; }}
  .metric-icon {{ width: 26px; height: 26px; }}
  .brief-footer {{ margin-top: 8px; padding-top: 8px; }}
}}
@media print {{
  body {{ background: #FFFFFF; }}
  .brief {{ max-width: none; margin: 0; padding: 0; border: none; box-shadow: none; }}
  .section {{ break-inside: avoid; }}
}}
</style>
</head>
<body>
<main class="brief">
  <header class="brief-header">
    <div class="header-row">
      <div class="eyebrow">CPCA WEEKLY · 乘联会周度数据</div>
      <div class="brand">CPCA</div>
    </div>
    <h1>全国乘用车市场<br>零售简报</h1>
    <p class="subtitle">数据统计：{esc(period_label)}{esc(status)}</p>
  </header>
  {sections}
  <footer class="brief-footer">
    <span>数据来源：乘联会（CPCA）</span>
    <span class="sep">｜</span>
    <span>注：本简报为乘用车市场零售销量（含新能源），单位：万辆。</span>
  </footer>
</main>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the CPCA weekly retail brief")
    parser.add_argument("--data-dir", default="data", help="Directory containing period JSON files")
    parser.add_argument(
        "--standard-csv",
        default="data/standard_dataset.csv",
        help="Standard table CSV path",
    )
    parser.add_argument("--out", default=None, help="Output HTML path")
    parser.add_argument("--period", default=None, help="Period end date (YYYY-MM-DD); default latest")
    args = parser.parse_args()

    latest = load_latest_period(Path(args.data_dir))
    if args.period and latest["period"]["end"] != args.period:
        matches = [
            item
            for item in (
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted(Path(args.data_dir).glob("*.json"))
            )
            if item["period"]["end"] == args.period
        ]
        if not matches:
            raise SystemExit(f"No dataset found for period end {args.period}")
        latest = matches[0]

    rows = load_standard_table(Path(args.standard_csv))
    if not rows:
        raise SystemExit("Standard table is empty.")
    if rows[0]["快照日期"] != latest["period"]["end"]:
        raise SystemExit(
            f"Standard table is stale: {rows[0]['快照日期']} != "
            f"{latest['period']['end']}. Run python3 scripts/build_standard_dataset.py first."
        )

    document = render_html(latest, rows)
    out_path = Path(args.out) if args.out else Path("reports") / f"{latest['period']['end']}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(document, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
