#!/usr/bin/env python3
"""Parse input/weekly.md into period JSON datasets.

The weekly text is the single raw source. Each "1.本周车市概述" block becomes
one data/YYYY-MM-DD.json file. Month-end blocks are kept as audit records;
month-to-date blocks feed the weekly standard table.

Usage:
    python3 scripts/ingest_weekly.py [--clean]
"""

from __future__ import annotations

import argparse
import calendar
import json
import re
from datetime import date, timedelta
from pathlib import Path

RAW_PATH = Path("input/weekly.md")
DATA_DIR = Path("data")

CORE_METRICS = (
    "passenger_retail",
    "passenger_wholesale",
    "nev_retail",
    "nev_wholesale",
)

METRIC_LABELS = {
    "passenger_retail": "乘用车零售",
    "passenger_wholesale": "乘用车批发",
    "nev_retail": "新能源零售",
    "nev_wholesale": "新能源批发",
}


def split_blocks(text: str) -> list[str]:
    blocks = [block.strip() for block in re.split(r"1\.本周车市概述", text)]
    return [block for block in blocks if block]


def split_sections(block: str) -> tuple[str, str, str, str | None]:
    """Return passenger, NEV, penetration, production sections."""
    body = block.strip()
    pen_index = body.find("渗透率：")
    prod_index = body.find("生产：")
    nev_end = pen_index if pen_index != -1 else (
        prod_index if prod_index != -1 else len(body)
    )

    nev_label = body.find("新能源：")
    if nev_label != -1:
        passenger_end = nev_label
        nev_start = nev_label + len("新能源：")
    else:
        first_prelim = body.find("初步统计：")
        second_prelim = (
            body.find("初步统计：", first_prelim + 1) if first_prelim != -1 else -1
        )
        if second_prelim != -1:
            passenger_end = second_prelim
            nev_start = second_prelim + len("初步统计：")
        else:
            markers = (
                "乘用车新能源车市场",
                "乘用车新能源市场",
                "新能源车市场",
                "新能源市场",
            )
            positions = [body.find(marker) for marker in markers if body.find(marker) != -1]
            if positions:
                passenger_end = min(positions)
                nev_start = passenger_end
            else:
                passenger_end = nev_end
                nev_start = nev_end

    passenger_start = 0
    if body.startswith("乘用车："):
        passenger_start = len("乘用车：")
    elif body.startswith("初步统计："):
        passenger_start = len("初步统计：")

    passenger = body[passenger_start:passenger_end].strip(" 。；")
    nev = body[nev_start:nev_end].strip(" 。；")
    if pen_index != -1:
        penetration = body[
            pen_index + len("渗透率：") : prod_index if prod_index != -1 else len(body)
        ].strip(" 。；")
    else:
        penetration = ""
    production = (
        body[prod_index + len("生产：") :].strip(" 。；") if prod_index != -1 else None
    )
    return passenger, nev, penetration, production


def parse_metric(sentence: str) -> dict[str, float | None]:
    value_match = re.search(r"([0-9][0-9,]*\.?[0-9]*)\s*万辆", sentence)
    yoy_match = re.search(r"同比[^，。；]*?(下降|增长|降)([0-9.]+)%", sentence)
    vs_match = re.search(r"较上月同期(下降|增长|降)([0-9.]+)%", sentence)
    if not vs_match:
        # Month-end articles often use "环比" for the previous-month comparison.
        vs_match = re.search(r"环比(?!上周)(下降|增长|降)([0-9.]+)%", sentence)
    ytd_value_match = re.search(
        r"今年以来.*?([0-9][0-9,]*\.?[0-9]*)\s*万辆", sentence
    )
    ytd_yoy_match = re.search(
        r"今年以来.*?同比[^，。；]*?(下降|增长|降)([0-9.]+)%", sentence
    )

    def number(match: re.Match[str] | None) -> float | None:
        if not match:
            return None
        return float(match.group(1).replace(",", ""))

    def percent(match: re.Match[str] | None) -> float | None:
        if not match:
            return None
        value = float(match.group(2))
        return -value if match.group(1) in {"下降", "降"} else value

    return {
        "value": number(value_match),
        "yoy_pct": percent(yoy_match),
        "vs_prev_month_same_period_pct": percent(vs_match),
        "ytd_value": number(ytd_value_match),
        "ytd_yoy_pct": percent(ytd_yoy_match),
    }


def parse_production(section: str | None, month_start: date) -> dict | None:
    if not section:
        return None

    sentences = [part.strip() for part in re.split(r"[；。;]", section) if part.strip()]
    if len(sentences) < 2:
        raise ValueError(f"Cannot parse production section: {section[:80]}")

    period_label_match = re.search(r"(\d{1,2}月[^，。；]*?周)", sentences[0])
    if not period_label_match:
        raise ValueError(f"Cannot parse production period: {sentences[0][:80]}")
    period_label = period_label_match.group(1)

    pure = parse_metric(sentences[0])
    hybrid = parse_metric(sentences[1])
    if pure["value"] is None or hybrid["value"] is None:
        raise ValueError(f"Cannot parse production values: {section[:80]}")

    carried_over = "此部分数据本周暂未更新" in section
    return {
        "period": {
            "start": month_start.isoformat(),
            "end": None,
            "label": period_label,
        },
        "status": "carried_over" if carried_over else "current",
        "note": "原文注明“此部分数据本周暂未更新”。" if carried_over else None,
        "metrics": {
            "pure_fuel_light_vehicle": {
                "label": "纯燃料轻型车生产",
                "value": pure["value"],
                "unit": "万辆",
                "yoy_pct": pure["yoy_pct"],
                "vs_prev_month_same_period_pct": pure[
                    "vs_prev_month_same_period_pct"
                ],
            },
            "hybrid_and_phev": {
                "label": "混合动力与插混生产",
                "value": hybrid["value"],
                "unit": "万辆",
                "yoy_pct": hybrid["yoy_pct"],
                "vs_prev_month_same_period_pct": hybrid[
                    "vs_prev_month_same_period_pct"
                ],
            },
        },
    }


def parse_penetration(section: str) -> dict[str, float] | None:
    if not section:
        return None
    retail = re.search(r"零售渗透率([0-9.]+)%", section)
    wholesale = re.search(r"批发渗透率([0-9.]+)%", section)
    if not retail or not wholesale:
        return None
    return {
        "retail_pct": float(retail.group(1)),
        "wholesale_pct": float(wholesale.group(1)),
    }


def parse_block(block: str, captured_at: date) -> dict:
    period_match = re.search(r"(\d{1,2})月(\d{1,2})-(\d{1,2})日", block)
    if not period_match:
        raise ValueError(f"Cannot find period in block: {block[:80]}")
    month, start_day, end_day = (int(value) for value in period_match.groups())

    year = captured_at.year
    if month > captured_at.month:
        year -= 1
    start = date(year, month, start_day)
    end = date(year, month, end_day)
    last_day = calendar.monthrange(year, month)[1]
    kind = "month" if start_day == 1 and end_day == last_day else "month_to_date"
    days = (end - start).days + 1

    passenger, nev, penetration_section, production_section = split_sections(block)

    passenger_sentences = [
        part.strip() for part in re.split(r"[；。;]", passenger) if part.strip()
    ]
    nev_sentences = [
        part.strip() for part in re.split(r"[；。;]", nev) if part.strip()
    ]

    def pick_sentence(sentences: list[str], kind: str) -> str | None:
        for sentence in sentences:
            if "万辆" not in sentence:
                continue
            has_nev = "新能源" in sentence
            if kind == "passenger_retail" and "零售" in sentence and not has_nev:
                return sentence
            if kind == "passenger_wholesale" and "批发" in sentence and not has_nev:
                return sentence
            if kind == "nev_retail" and "零售" in sentence and has_nev:
                return sentence
            if kind == "nev_wholesale" and "批发" in sentence and has_nev:
                return sentence
        return None

    chosen = {
        "passenger_retail": pick_sentence(passenger_sentences, "passenger_retail"),
        "passenger_wholesale": pick_sentence(
            passenger_sentences, "passenger_wholesale"
        ),
        "nev_retail": pick_sentence(nev_sentences, "nev_retail"),
        "nev_wholesale": pick_sentence(nev_sentences, "nev_wholesale"),
    }
    missing_sentences = [key for key, sentence in chosen.items() if sentence is None]
    if missing_sentences:
        raise ValueError(
            f"Cannot parse metric sections {missing_sentences} in block: {block[:80]}"
        )

    parsed = {key: parse_metric(sentence) for key, sentence in chosen.items()}

    for key, values in parsed.items():
        missing = [
            field
            for field in (
                "value",
                "yoy_pct",
                "vs_prev_month_same_period_pct",
            )
            if values.get(field) is None
        ]
        if missing:
            raise ValueError(f"{key} missing {missing} in block: {block[:80]}")

    metrics = {
        key: {
            "label": METRIC_LABELS[key],
            "value": parsed[key]["value"],
            "unit": "万辆",
            "yoy_pct": parsed[key]["yoy_pct"],
            "vs_prev_month_same_period_pct": parsed[key][
                "vs_prev_month_same_period_pct"
            ],
            "ytd_value": parsed[key]["ytd_value"],
            "ytd_yoy_pct": parsed[key]["ytd_yoy_pct"],
        }
        for key in CORE_METRICS
    }

    penetration = parse_penetration(penetration_section)
    production = parse_production(production_section, start)
    preliminary = block.lstrip().startswith("初步统计")

    return {
        "schema_version": "0.1",
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "label": f"{month}月{start_day}-{end_day}日",
            "kind": kind,
            "days": days,
        },
        "metrics": metrics,
        "penetration": penetration,
        "production": production,
        "derived": {
            "days": days,
            "daily_avg": {
                key: round(metrics[key]["value"] / days, 2) for key in CORE_METRICS
            },
        },
        "validation": {"checks": []},
        "notes": [],
        "_meta": {
            "preliminary": preliminary,
            "block_text": block,
        },
    }


def penetration_checks(metrics: dict, penetration: dict | None) -> list[dict]:
    checks: list[dict] = []
    if penetration:
        for level, total_key, nev_key in (
            ("retail", "passenger_retail", "nev_retail"),
            ("wholesale", "passenger_wholesale", "nev_wholesale"),
        ):
            total = metrics[total_key]["value"]
            nev = metrics[nev_key]["value"]
            published = penetration.get(f"{level}_pct")
            if published is None:
                continue
            computed = round(nev / total * 100, 2)
            difference = round(computed - published, 2)
            checks.append(
                {
                    "name": f"penetration_{level}",
                    "status": "pass" if abs(difference) <= 0.5 else "flag",
                    "detail": (
                        f"新能源{ '零售' if level == 'retail' else '批发' } {nev:.1f} / "
                        f"乘用车{'零售' if level == 'retail' else '批发'} {total:.1f} = "
                        f"{computed:.2f}%，发布值 {published:.1f}%，差异 {difference:+.2f} 个百分点。"
                    ),
                    "computed_pct": computed,
                    "published_pct": published,
                    "difference_pp": difference,
                }
            )
    else:
        checks.append(
            {
                "name": "penetration",
                "status": "info",
                "detail": "原文未提供渗透率数据。",
            }
        )

    total_retail = metrics["passenger_retail"]["value"]
    total_wholesale = metrics["passenger_wholesale"]["value"]
    nev_retail = metrics["nev_retail"]["value"]
    nev_wholesale = metrics["nev_wholesale"]["value"]
    checks.append(
        {
            "name": "nev_not_above_total",
            "status": "pass"
            if nev_retail <= total_retail and nev_wholesale <= total_wholesale
            else "flag",
            "detail": (
                f"新能源零售 {nev_retail:.1f} ≤ 乘用车零售 {total_retail:.1f}；"
                f"新能源批发 {nev_wholesale:.1f} ≤ 乘用车批发 {total_wholesale:.1f}。"
            ),
        }
    )
    return checks


def build_notes(dataset: dict) -> list[dict]:
    period = dataset["period"]
    production = dataset["production"]
    meta = dataset["_meta"]
    block = meta["block_text"]
    notes: list[dict] = [
        {
            "type": "year",
            "text": (
                "原文未写年份，按采集日期 "
                f"{dataset['source']['captured_at']} 推断为 {period['start'][:4]} 年。"
            ),
        }
    ]

    if not dataset.get("penetration"):
        notes.append({"type": "missing", "text": "原文未提供渗透率数据。"})
    if any(
        dataset["metrics"][key].get("ytd_value") is None
        or dataset["metrics"][key].get("ytd_yoy_pct") is None
        for key in CORE_METRICS
    ):
        notes.append(
            {
                "type": "missing",
                "text": "原文未提供完整的今年以来累计值；缺失字段留空，不补数。",
            }
        )

    if period["kind"] == "month":
        notes.append(
            {
                "type": "status",
                "text": "原文标注“初步统计”，作为月度收盘/审计数据，不进入周快照表。",
            }
        )
    if meta.get("latest"):
        notes.append({"type": "status", "text": "本次录入的最新一期。"})

    if production:
        if production["status"] == "carried_over":
            notes.append(
                {
                    "type": "production",
                    "text": "生产数据原文注明本周暂未更新，按 carried_over 处理。",
                }
            )
        notes.append(
            {
                "type": "period",
                "text": (
                    f"生产周期为“{production['period']['label']}”，"
                    "与零售/批发区间不同，未强行对齐。"
                ),
            }
        )

    if meta.get("first_week"):
        notes.append(
            {
                "type": "period",
                "text": (
                    "本月首个周快照；当周即当月累计，标准表不单列当月。"
                    "首周直接用原文当月累计，不用上月YTD差额，避免把基数修订算进当月。"
                ),
            }
        )
    if "市场市场" in block:
        notes.append(
            {
                "type": "source_text",
                "text": "原文存在“市场市场”重复字，按语义取值，数值未改。",
            }
        )
    return notes


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse input/weekly.md into period JSON files")
    parser.add_argument("--clean", action="store_true", help="Remove existing data/*.json first")
    parser.add_argument("--raw", default=str(RAW_PATH), help="Raw weekly markdown path")
    parser.add_argument("--data-dir", default=str(DATA_DIR), help="Output data directory")
    args = parser.parse_args()

    captured_at = date.today()
    raw_path = Path(args.raw)
    data_dir = Path(args.data_dir)

    text = raw_path.read_text(encoding="utf-8")
    blocks = split_blocks(text)
    if not blocks:
        raise SystemExit(f"No weekly blocks found in {raw_path}")

    datasets = [parse_block(block, captured_at) for block in blocks]
    datasets.sort(key=lambda item: item["period"]["end"])

    ends = [item["period"]["end"] for item in datasets]
    if len(ends) != len(set(ends)):
        raise SystemExit("Duplicate period.end values found in weekly.md")

    latest_end = max(ends)
    latest_date = date.fromisoformat(latest_end)
    iso = latest_date.isocalendar()
    edition_week = f"{iso.year}-W{iso.week:02d}"

    # Mark latest and first-week flags before notes/validation.
    month_groups: dict[str, list[dict]] = {}
    for item in datasets:
        item["_meta"]["latest"] = item["period"]["end"] == latest_end
        if item["period"]["kind"] == "month_to_date":
            month_groups.setdefault(item["period"]["start"], []).append(item)
    for group in month_groups.values():
        group.sort(key=lambda item: item["period"]["end"])
        for index, item in enumerate(group):
            item["_meta"]["first_week"] = index == 0

    # Derived increments for month-to-date snapshots.
    for group in month_groups.values():
        for previous, current in zip(group, group[1:]):
            increment_days = (
                date.fromisoformat(current["period"]["end"])
                - date.fromisoformat(previous["period"]["end"])
            ).days
            current["derived"]["increment_from"] = previous["period"]["end"]
            current["derived"]["increment_days"] = increment_days
            current["derived"]["increment"] = {
                key: round(
                    current["metrics"][key]["value"] - previous["metrics"][key]["value"],
                    1,
                )
                for key in CORE_METRICS
            }
            current["derived"]["increment_daily_avg"] = {
                key: round(
                    current["derived"]["increment"][key] / increment_days,
                    2,
                )
                for key in CORE_METRICS
            }

    for item in datasets:
        item["source"] = {
            "publisher": "CPCA",
            "publisher_full": "乘用车市场信息联席分会（乘联会）",
            "parent_association": "CADA（中国汽车流通协会）",
            "section": "本周车市概述",
            "report_title": "全国乘用车市场零售简报",
            "raw_path": str(raw_path),
            "edition": latest_end,
            "edition_week": edition_week,
            "captured_at": captured_at.isoformat(),
            "year_inferred": True,
            "year_basis": f"原文未写年份，按采集日期 {captured_at.isoformat()} 推断",
            "status": (
                "current"
                if item["_meta"]["latest"]
                else ("preliminary" if item["period"]["kind"] == "month" else "snapshot")
            ),
            "report_status": "preliminary",
        }
        item["validation"]["checks"] = penetration_checks(
            item["metrics"], item["penetration"]
        )
        if item["production"] and item["production"]["status"] == "carried_over":
            item["validation"]["checks"].append(
                {
                    "name": "production_status",
                    "status": "flag",
                    "detail": "生产数据原文注明本周暂未更新，按 carried_over 处理。",
                }
            )
        item["notes"] = build_notes(item)
        del item["_meta"]

    if args.clean:
        for path in data_dir.glob("*.json"):
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                path.unlink()
                continue
            # Official data is canonical; a manual rebuild must not delete it.
            if existing.get("source", {}).get("origin") != "official":
                path.unlink()

    data_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    preserved = 0
    for item in datasets:
        path = data_dir / f"{item['period']['end']}.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("source", {}).get("origin") == "official":
                preserved += 1
                continue
        path.write_text(
            json.dumps(item, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written += 1

    print(f"Parsed {len(datasets)} blocks from {raw_path}")
    print(f"Latest: {latest_end} ({edition_week})")
    print(f"Wrote {written} manual JSON files; preserved {preserved} official files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
