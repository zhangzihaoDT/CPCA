#!/usr/bin/env python3
"""Merge official CPCA history blocks into the canonical data/ datasets.

Official blocks live in input/official/blocks/ and are described by
input/official/manifest.json. Canonical data lives in data/*.json.

Policy:
- New official periods are written to data/ only with --write.
- Existing periods are compared field by field.
- Matching periods are updated with official provenance.
- Conflicting periods are never overwritten; conflicts are written to
  input/official/conflicts.json for manual review.

Usage:
    python3 scripts/ingest_official.py            # dry run, report only
    python3 scripts/ingest_official.py --write    # apply new/matching data
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from ingest_weekly import (  # noqa: E402
    CORE_METRICS,
    build_notes,
    parse_block,
    penetration_checks,
)

OFFICIAL_DIR = Path("input/official")
MANIFEST_PATH = OFFICIAL_DIR / "manifest.json"
BLOCK_DIR = OFFICIAL_DIR / "blocks"
CONFLICT_PATH = OFFICIAL_DIR / "conflicts.json"
DATA_DIR = Path("data")

COMPARE_FIELDS = (
    "value",
    "yoy_pct",
    "vs_prev_month_same_period_pct",
    "ytd_value",
    "ytd_yoy_pct",
)
TOLERANCE = 0.05


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        raise SystemExit(
            f"Manifest not found: {MANIFEST_PATH}. Run fetch_cpca_history.py first."
        )
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def compare_metrics(official: dict, canonical: dict) -> list[dict]:
    differences: list[dict] = []
    for metric in CORE_METRICS:
        official_metric = official["metrics"][metric]
        canonical_metric = canonical["metrics"][metric]
        for field in COMPARE_FIELDS:
            official_value = official_metric.get(field)
            canonical_value = canonical_metric.get(field)
            if official_value is None or canonical_value is None:
                continue
            if abs(official_value - canonical_value) > TOLERANCE:
                differences.append(
                    {
                        "metric": metric,
                        "field": field,
                        "official": official_value,
                        "canonical": canonical_value,
                    }
                )

    official_pen = official.get("penetration")
    canonical_pen = canonical.get("penetration")
    if official_pen and canonical_pen:
        for key in ("retail_pct", "wholesale_pct"):
            official_value = official_pen.get(key)
            canonical_value = canonical_pen.get(key)
            if official_value is None or canonical_value is None:
                continue
            if abs(official_value - canonical_value) > TOLERANCE:
                differences.append(
                    {
                        "metric": "penetration",
                        "field": key,
                        "official": official_value,
                        "canonical": canonical_value,
                    }
                )
    return differences


def comparison_details(official: dict, canonical: dict) -> dict:
    details: dict = {}
    for metric in CORE_METRICS:
        o = official["metrics"][metric]
        c = canonical["metrics"][metric]
        details[metric] = {
            field: {"official": o.get(field), "canonical": c.get(field)}
            for field in COMPARE_FIELDS
        }
    details["penetration"] = {
        "official": official.get("penetration"),
        "canonical": canonical.get("penetration"),
    }
    return details


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge official CPCA blocks into canonical data"
    )
    parser.add_argument("--write", action="store_true", help="Write new/matching data")
    parser.add_argument(
        "--accept-conflicts",
        default="",
        help="Comma-separated period ends to accept official data for after review",
    )
    args = parser.parse_args()
    accepted_conflicts = {
        value.strip()
        for value in args.accept_conflicts.split(",")
        if value.strip()
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()
    records = [
        record
        for record in manifest.get("articles", [])
        if record.get("status") == "parsed" and record.get("block_path")
    ]
    if not records:
        raise SystemExit("No parsed official blocks found in manifest.")

    datasets = []
    parse_failed: list[dict] = []
    for record in records:
        block_path = Path(record["block_path"])
        if not block_path.exists():
            parse_failed.append(
                {"article_id": record["article_id"], "error": "block file missing"}
            )
            continue
        block = block_path.read_text(encoding="utf-8").strip()
        published_date = date.fromisoformat(
            record.get("published_at", record.get("list_date"))[:10]
        )
        try:
            dataset = parse_block(block, published_date)
        except Exception as exc:
            parse_failed.append(
                {
                    "article_id": record["article_id"],
                    "period_end": record.get("period_end"),
                    "error": str(exc),
                }
            )
            continue
        dataset["_meta"]["official_record"] = record
        datasets.append(dataset)

    datasets.sort(key=lambda item: item["period"]["end"])
    if not datasets:
        raise SystemExit("No official blocks could be parsed.")

    latest_end = datasets[-1]["period"]["end"]
    latest_date = date.fromisoformat(latest_end)
    iso = latest_date.isocalendar()
    edition_week = f"{iso.year}-W{iso.week:02d}"

    month_groups: dict[str, list[dict]] = {}
    for dataset in datasets:
        dataset["_meta"]["latest"] = dataset["period"]["end"] == latest_end
        if dataset["period"]["kind"] == "month_to_date":
            month_groups.setdefault(dataset["period"]["start"], []).append(dataset)
    for group in month_groups.values():
        group.sort(key=lambda item: item["period"]["end"])
        for index, dataset in enumerate(group):
            dataset["_meta"]["first_week"] = index == 0

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
                    current["metrics"][key]["value"]
                    - previous["metrics"][key]["value"],
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

    stats = {
        "official_blocks": len(datasets),
        "month": 0,
        "week": 0,
        "new": 0,
        "matched": 0,
        "conflicts": 0,
        "parse_failed": len(parse_failed),
        "missing_ytd": 0,
        "missing_penetration": 0,
        "written": 0,
        "accepted_conflicts": 0,
    }
    conflicts: list[dict] = []
    new_periods: list[str] = []
    matched_periods: list[str] = []

    for dataset in datasets:
        record = dataset["_meta"]["official_record"]
        period_end = dataset["period"]["end"]
        kind = dataset["period"]["kind"]
        published_at = record.get("published_at") or record.get("list_date")
        fetched_at = record.get("fetched_at") or manifest.get("generated_at")

        dataset["source"] = {
            "publisher": "CPCA",
            "publisher_full": "乘用车市场信息联席分会（乘联会）",
            "parent_association": "CADA（中国汽车流通协会）",
            "section": "本周车市概述",
            "report_title": "全国乘用车市场零售简报",
            "raw_path": record.get("raw_path"),
            "block_path": record.get("block_path"),
            "url": record.get("url"),
            "article_id": record.get("article_id"),
            "title": record.get("title"),
            "week_range": record.get("week_range"),
            "published_at": published_at,
            "fetched_at": fetched_at,
            "content_hash": record.get("content_hash"),
            "origin": "official",
            "edition": latest_end,
            "edition_week": edition_week,
            "captured_at": (fetched_at or published_at or "")[:10],
            "year_inferred": False,
            "year_basis": "年份取自文章标题/发布时间",
            "status": (
                "current"
                if period_end == latest_end
                else ("preliminary" if kind == "month" else "snapshot")
            ),
            "report_status": "preliminary",
        }

        dataset["validation"]["checks"] = penetration_checks(
            dataset["metrics"], dataset.get("penetration")
        )
        if dataset.get("production") and dataset["production"].get("status") == "carried_over":
            dataset["validation"]["checks"].append(
                {
                    "name": "production_status",
                    "status": "flag",
                    "detail": "生产数据原文注明本周暂未更新，按 carried_over 处理。",
                }
            )

        notes = build_notes(dataset)
        notes = [note for note in notes if note.get("type") != "year"]
        notes.insert(
            0,
            {
                "type": "year",
                "text": (
                    f"年份取自文章标题/发布时间（{published_at}）。"
                ),
            },
        )
        notes.insert(
            1,
            {
                "type": "source",
                "text": (
                    f"官方来源：{record.get('title')} · {record.get('url')} "
                    f"（文章 id {record.get('article_id')}）。"
                ),
            },
        )
        dataset["notes"] = notes

        if kind == "month":
            stats["month"] += 1
        else:
            stats["week"] += 1
        if any(
            dataset["metrics"][metric].get("ytd_value") is None
            or dataset["metrics"][metric].get("ytd_yoy_pct") is None
            for metric in CORE_METRICS
        ):
            stats["missing_ytd"] += 1
        if not dataset.get("penetration"):
            stats["missing_penetration"] += 1

        canonical_path = DATA_DIR / f"{period_end}.json"
        if canonical_path.exists():
            canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
            differences = compare_metrics(dataset, canonical)
            if differences:
                stats["conflicts"] += 1
                accepted = period_end in accepted_conflicts
                conflicts.append(
                    {
                        "period_end": period_end,
                        "article_id": record.get("article_id"),
                        "url": record.get("url"),
                        "title": record.get("title"),
                        "canonical_path": str(canonical_path),
                        "block_path": record.get("block_path"),
                        "raw_path": record.get("raw_path"),
                        "differences": differences,
                        "details": comparison_details(dataset, canonical),
                        "accepted": accepted,
                    }
                )
                if accepted:
                    stats["accepted_conflicts"] += 1
                    if args.write:
                        canonical_path.write_text(
                            json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                        )
                        stats["written"] += 1
            else:
                stats["matched"] += 1
                matched_periods.append(period_end)
                if args.write:
                    canonical_path.write_text(
                        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    stats["written"] += 1
        else:
            stats["new"] += 1
            new_periods.append(period_end)
            if args.write:
                canonical_path.write_text(
                    json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                stats["written"] += 1

    conflict_payload = {
        "generated_at": manifest.get("generated_at"),
        "policy": "conflicts are reports only; canonical data is not overwritten",
        "stats": stats,
        "conflicts": conflicts,
    }
    CONFLICT_PATH.write_text(
        json.dumps(conflict_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Official ingest summary")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"New periods: {', '.join(new_periods) if new_periods else '-'}")
    print(f"Matched periods: {', '.join(matched_periods) if matched_periods else '-'}")
    if conflicts:
        print(f"Conflicts: {len(conflicts)} (see {CONFLICT_PATH})")
    if parse_failed:
        print(f"Parse failures: {parse_failed}")
    if not args.write:
        print("Dry run only. Re-run with --write to apply new/matching data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
