#!/usr/bin/env python3
"""Ingest Legacy V2 blocks into a separate historical dataset.

Outputs:
    data/legacy/<period_end>.json
    data/legacy/legacy_dataset.csv

The formal data/*.json, standard_dataset.csv and weekly report are untouched.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from legacy_parse import parse_legacy_block  # noqa: E402

LEGACY_DIR = Path("input/legacy")
BLOCK_DIR = LEGACY_DIR / "blocks"
MANIFEST_PATH = LEGACY_DIR / "manifest.json"
OUTPUT_DIR = Path("data/legacy")
CSV_PATH = OUTPUT_DIR / "legacy_dataset.csv"

FIELDS = [
    "快照日期",
    "时间维度",
    "区间类型",
    "区间开始",
    "区间截止",
    "日历天数",
    "乘用车零售(万辆)",
    "乘用车零售同比(%)",
    "乘用车零售较上月同期(%)",
    "乘用车零售YTD(万辆)",
    "乘用车零售YTD同比(%)",
    "乘用车批发(万辆)",
    "乘用车批发同比(%)",
    "乘用车批发较上月同期(%)",
    "乘用车批发YTD(万辆)",
    "乘用车批发YTD同比(%)",
    "新能源零售(万辆)",
    "新能源零售同比(%)",
    "新能源零售YTD(万辆)",
    "新能源零售YTD同比(%)",
    "新能源批发(万辆)",
    "新能源批发同比(%)",
    "新能源批发YTD(万辆)",
    "新能源批发YTD同比(%)",
    "数据口径",
    "文章ID",
    "发布时间",
    "来源URL",
]


def value_or_blank(value: object) -> str:
    return "" if value is None else str(value)


def metric_fields(metric: dict | None, prefix: str) -> list[str]:
    if metric is None:
        return ["", "", "", "", ""]
    return [
        value_or_blank(metric.get("value")),
        value_or_blank(metric.get("yoy_pct")),
        value_or_blank(metric.get("vs_prev_month_same_period_pct")),
        value_or_blank(metric.get("ytd_value")),
        value_or_blank(metric.get("ytd_yoy_pct")),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Legacy V2 blocks")
    parser.add_argument("--write", action="store_true", help="Write legacy data")
    args = parser.parse_args()

    if not MANIFEST_PATH.exists():
        raise SystemExit(f"Legacy manifest not found: {MANIFEST_PATH}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    period_source = manifest.get("periods", [])
    if not period_source:
        period_source = [
            record
            for record in manifest.get("articles", [])
            if record.get("status") == "parsed"
        ]

    records_by_period: dict[str, dict] = {}
    for record in period_source:
        if record.get("status", "parsed") != "parsed" or not record.get(
            "period_end"
        ):
            continue
        current = records_by_period.get(record["period_end"])
        if current is None or record.get("published_at", "") > current.get(
            "published_at", ""
        ):
            records_by_period[record["period_end"]] = record

    blocks = sorted(BLOCK_DIR.glob("*.md"))
    if not blocks:
        raise SystemExit(f"No legacy blocks found in {BLOCK_DIR}")

    datasets: list[dict] = []
    parse_failed: list[dict] = []
    for block_path in blocks:
        period_end = block_path.stem
        record = records_by_period.get(period_end)
        if record is None:
            parse_failed.append(
                {"period_end": period_end, "error": "manifest record missing"}
            )
            continue
        published_date = date.fromisoformat(
            record.get("published_at", record.get("list_date"))[:10]
        )
        block = block_path.read_text(encoding="utf-8").strip()
        try:
            dataset = parse_legacy_block(block, published_date)
        except Exception as exc:
            parse_failed.append(
                {"period_end": period_end, "article_id": record.get("article_id"),
                 "error": str(exc)}
            )
            continue

        dataset["source"] = {
            "publisher": "CPCA",
            "publisher_full": "乘用车市场信息联席分会（乘联会）",
            "parent_association": "CADA（中国汽车流通协会）",
            "section": "本周车市概述",
            "report_title": "全国乘用车市场零售简报",
            "origin": "official-legacy",
            "format": "legacy-v2",
            "raw_path": record.get("raw_path"),
            "block_path": str(block_path),
            "url": record.get("url"),
            "article_id": record.get("article_id"),
            "title": record.get("title"),
            "week_range": record.get("week_range"),
            "published_at": record.get("published_at"),
            "fetched_at": record.get("fetched_at"),
            "content_hash": record.get("content_hash"),
            "year_inferred": False,
            "year_basis": "年份取自文章标题/发布时间",
            "status": "legacy",
            "report_status": "preliminary",
        }
        dataset["notes"] = [
            {
                "type": "format",
                "text": (
                    "Legacy V2 旧格式：只恢复乘用车零售/批发摘要；"
                    "新能源、YTD、渗透率原文缺失时留空。"
                ),
            },
            {
                "type": "scope",
                "text": "本数据不进入正式周度简报标准表，只作为可追溯历史资产。",
            },
            {
                "type": "source",
                "text": (
                    f"官方来源：{record.get('title')} · {record.get('url')} "
                    f"（文章 id {record.get('article_id')}）。"
                ),
            },
        ]
        datasets.append(dataset)

    datasets.sort(key=lambda item: item["period"]["end"])
    stats = {
        "blocks": len(blocks),
        "parsed": len(datasets),
        "failed": len(parse_failed),
        "month": sum(1 for d in datasets if d["period"]["kind"] == "month"),
        "week": sum(1 for d in datasets if d["period"]["kind"] == "month_to_date"),
        "has_passenger_retail": sum(
            1 for d in datasets if d["metrics"]["passenger_retail"] is not None
        ),
        "has_passenger_wholesale": sum(
            1 for d in datasets if d["metrics"]["passenger_wholesale"] is not None
        ),
        "has_nev": sum(
            1
            for d in datasets
            if d["metrics"]["nev_retail"] is not None
            or d["metrics"]["nev_wholesale"] is not None
        ),
        "has_ytd": sum(
            1
            for d in datasets
            if any(
                metric and metric.get("ytd_value") is not None
                for metric in d["metrics"].values()
            )
        ),
    }

    print("Legacy V2 summary")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if parse_failed:
        print("Parse failures:")
        for failure in parse_failed:
            print(" ", failure)
    print(
        f"Range: {datasets[0]['period']['start']} .. "
        f"{datasets[-1]['period']['end']}"
    )

    if not args.write:
        print("Dry run only. Re-run with --write to write data/legacy/.")
        return 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT_DIR.glob("*.json"):
        path.unlink()

    for dataset in datasets:
        path = OUTPUT_DIR / f"{dataset['period']['end']}.json"
        path.write_text(
            json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for dataset in datasets:
            metrics = dataset["metrics"]
            retail = metric_fields(metrics.get("passenger_retail"), "retail")
            wholesale = metric_fields(
                metrics.get("passenger_wholesale"), "wholesale"
            )
            nev_retail = metrics.get("nev_retail")
            nev_wholesale = metrics.get("nev_wholesale")
            row = {
                "快照日期": dataset["period"]["end"],
                "时间维度": dataset["period"]["label"],
                "区间类型": dataset["period"]["kind"],
                "区间开始": dataset["period"]["start"],
                "区间截止": dataset["period"]["end"],
                "日历天数": dataset["period"]["days"],
                "乘用车零售(万辆)": retail[0],
                "乘用车零售同比(%)": retail[1],
                "乘用车零售较上月同期(%)": retail[2],
                "乘用车零售YTD(万辆)": retail[3],
                "乘用车零售YTD同比(%)": retail[4],
                "乘用车批发(万辆)": wholesale[0],
                "乘用车批发同比(%)": wholesale[1],
                "乘用车批发较上月同期(%)": wholesale[2],
                "乘用车批发YTD(万辆)": wholesale[3],
                "乘用车批发YTD同比(%)": wholesale[4],
                "新能源零售(万辆)": value_or_blank(
                    nev_retail.get("value") if nev_retail else None
                ),
                "新能源零售同比(%)": value_or_blank(
                    nev_retail.get("yoy_pct") if nev_retail else None
                ),
                "新能源零售YTD(万辆)": value_or_blank(
                    nev_retail.get("ytd_value") if nev_retail else None
                ),
                "新能源零售YTD同比(%)": value_or_blank(
                    nev_retail.get("ytd_yoy_pct") if nev_retail else None
                ),
                "新能源批发(万辆)": value_or_blank(
                    nev_wholesale.get("value") if nev_wholesale else None
                ),
                "新能源批发同比(%)": value_or_blank(
                    nev_wholesale.get("yoy_pct") if nev_wholesale else None
                ),
                "新能源批发YTD(万辆)": value_or_blank(
                    nev_wholesale.get("ytd_value") if nev_wholesale else None
                ),
                "新能源批发YTD同比(%)": value_or_blank(
                    nev_wholesale.get("ytd_yoy_pct") if nev_wholesale else None
                ),
                "数据口径": "Legacy V2：原文乘用车摘要；缺失字段留空",
                "文章ID": dataset["source"].get("article_id"),
                "发布时间": dataset["source"].get("published_at"),
                "来源URL": dataset["source"].get("url"),
            }
            writer.writerow(row)

    print(f"Wrote {len(datasets)} JSON files to {OUTPUT_DIR}")
    print(f"Wrote {CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
