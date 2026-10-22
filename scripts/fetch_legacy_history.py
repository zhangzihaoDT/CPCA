#!/usr/bin/env python3
"""Fetch Legacy V2 articles (2022-2023) and extract the passenger summary.

Outputs are isolated from the formal pipeline:
    input/legacy/raw/<article_id>.html
    input/legacy/blocks/<period_end>.md
    input/legacy/manifest.json

The parser tolerates missing NEV/YTD fields. It does not write data/*.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from fetch_cpca_history import (  # noqa: E402
    ARTICLE_URL,
    BASE_URL,
    LIST_URL,
    fetch_html,
    parse_article_metadata,
    parse_list_page,
)
from legacy_parse import extract_legacy_overview, parse_legacy_block_multi  # noqa: E402

LEGACY_DIR = Path("input/legacy")
RAW_DIR = LEGACY_DIR / "raw"
BLOCK_DIR = LEGACY_DIR / "blocks"
FAILED_DIR = LEGACY_DIR / "blocks_failed"
MANIFEST_PATH = LEGACY_DIR / "manifest.json"
OFFICIAL_RAW_DIR = Path("input/official/raw")

PERIOD_SOURCE_FIELDS = (
    "article_id",
    "url",
    "title",
    "list_date",
    "week_range",
    "published_at",
    "fetched_at",
    "content_hash",
    "raw_path",
)


def period_record_from_article(record: dict) -> dict | None:
    if not record.get("period_start") or not record.get("period_end"):
        return None
    return {
        **{field: record.get(field) for field in PERIOD_SOURCE_FIELDS},
        "period_start": record["period_start"],
        "period_end": record["period_end"],
        "kind": record.get("kind"),
        "block_path": record.get("block_path"),
        "status": "parsed",
    }


def period_record_from_dataset(record: dict, dataset: dict, block_path: Path) -> dict:
    return {
        **{field: record.get(field) for field in PERIOD_SOURCE_FIELDS},
        "period_start": dataset["period"]["start"],
        "period_end": dataset["period"]["end"],
        "kind": dataset["period"]["kind"],
        "block_path": str(block_path),
        "status": "parsed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch and extract Legacy V2 CPCA articles"
    )
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--max-pages", type=int, default=17)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument(
        "--archive-only",
        action="store_true",
        help="Fetch raw HTML only; do not extract/parse (for 2020-2021)",
    )
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    BLOCK_DIR.mkdir(parents=True, exist_ok=True)
    FAILED_DIR.mkdir(parents=True, exist_ok=True)

    existing_records: list[dict] = []
    existing_period_records: list[dict] = []
    if MANIFEST_PATH.exists() and not args.clean:
        existing_manifest = json.loads(
            MANIFEST_PATH.read_text(encoding="utf-8")
        )
        existing_records = existing_manifest.get("articles", [])
        existing_period_records = existing_manifest.get("periods", [])
        if not existing_period_records:
            existing_period_records = [
                period_record
                for record in existing_records
                if record.get("status") == "parsed"
                for period_record in [period_record_from_article(record)]
                if period_record
            ]

    if args.clean and not args.dry_run:
        for path in BLOCK_DIR.glob("*.md"):
            path.unlink()
        for path in FAILED_DIR.glob("*.md"):
            path.unlink()

    # Reuse the official list-page cache when available; the list is the same.
    all_items: list[dict] = []
    page = 1
    while page <= args.max_pages:
        official_cache = OFFICIAL_RAW_DIR / f"list_page_{page}.html"
        legacy_cache = RAW_DIR / f"list_page_{page}.html"
        if official_cache.exists():
            html = official_cache.read_text(encoding="utf-8", errors="replace")
        elif legacy_cache.exists():
            html = legacy_cache.read_text(encoding="utf-8", errors="replace")
        else:
            data, html = fetch_html(LIST_URL.format(page=page), BASE_URL + "/", args.delay)
            legacy_cache.write_bytes(data)
        items = parse_list_page(html)
        if not items:
            break
        all_items.extend(items)
        week_starts = [
            date.fromisoformat(item["week_start"])
            for item in items
            if item["week_start"]
        ]
        if week_starts and min(week_starts) < start:
            break
        page += 1

    unique: dict[str, dict] = {}
    for item in all_items:
        unique.setdefault(item["article_id"], item)
    items = list(unique.values())

    def in_range(item: dict) -> bool:
        if not item.get("week_start") or not item.get("week_end"):
            return False
        item_start = date.fromisoformat(item["week_start"])
        item_end = date.fromisoformat(item["week_end"])
        return item_end >= start and item_start <= end

    selected = [item for item in items if in_range(item)]
    print(f"Listed articles: {len(items)}")
    print(f"Selected legacy articles ({args.start}..{args.end}): {len(selected)}")
    for item in selected:
        print(
            f"  {item['article_id']}  {item['list_date']}  "
            f"{item['week_range']:<21} {item['title']}"
        )
    if args.dry_run:
        return 0

    fetched_at = datetime.now().isoformat(timespec="seconds")
    records: list[dict] = []
    stats = {
        "selected": len(selected),
        "fetched": 0,
        "extracted": 0,
        "parsed": 0,
        "failed": 0,
        "month": 0,
        "week": 0,
        "has_passenger_retail": 0,
        "has_passenger_wholesale": 0,
        "has_nev": 0,
        "has_ytd": 0,
        "periods": 0,
        "superseded": 0,
        "superseded_periods": 0,
        "archived_only": 0,
    }
    period_records_by_end = {
        record["period_end"]: record
        for record in existing_period_records
        if record.get("period_end")
    }
    parsed_periods: dict[str, dict] = {
        period_end: {
            "article_id": record.get("article_id"),
            "published_at": record.get("published_at", ""),
        }
        for period_end, record in period_records_by_end.items()
    }
    current_periods: set[str] = set()

    for item in selected:
        article_id = item["article_id"]
        raw_path = RAW_DIR / f"{article_id}.html"
        record = {
            **item,
            "raw_path": str(raw_path),
            "fetched_at": fetched_at,
            "status": "pending",
            "error": None,
        }
        try:
            if raw_path.exists() and not args.force:
                data = raw_path.read_bytes()
            elif (OFFICIAL_RAW_DIR / f"{article_id}.html").exists() and not args.force:
                data = (OFFICIAL_RAW_DIR / f"{article_id}.html").read_bytes()
                raw_path.write_bytes(data)
            else:
                data, _ = fetch_html(item["url"], LIST_URL.format(page=1), args.delay)
                raw_path.write_bytes(data)
            stats["fetched"] += 1
            html = data.decode("utf-8", errors="replace")
            record["content_hash"] = hashlib.sha256(data).hexdigest()

            meta = parse_article_metadata(html, item["title"], item["list_date"])
            record.update(meta)
            published_date = date.fromisoformat(meta["published_date"])

            if args.archive_only:
                record["status"] = "archived_only"
                record["error"] = None
                stats["archived_only"] += 1
                records.append(record)
                continue

            try:
                block = extract_legacy_overview(html)
                stats["extracted"] += 1
            except Exception as exc:
                record["status"] = "extract_failed"
                record["error"] = str(exc)
                stats["failed"] += 1
                (FAILED_DIR / f"{article_id}.md").write_text(
                    f"<!-- {item['url']} -->\n{exc}\n", encoding="utf-8"
                )
                records.append(record)
                continue

            try:
                parsed_items = parse_legacy_block_multi(block, published_date)
            except Exception as exc:
                record["status"] = "parse_failed"
                record["error"] = str(exc)
                stats["failed"] += 1
                (FAILED_DIR / f"{article_id}.md").write_text(
                    f"<!-- {item['url']} -->\n{block}\n\n<!-- error: {exc} -->\n",
                    encoding="utf-8",
                )
                records.append(record)
                continue

            record["periods"] = []
            written: list[tuple[dict, Path]] = []
            for dataset, segment in parsed_items:
                period = dataset["period"]
                period_end = period["end"]
                existing_period = parsed_periods.get(period_end)
                if (
                    existing_period
                    and existing_period.get("article_id") != article_id
                    and meta.get("published_at", "")
                    <= existing_period.get("published_at", "")
                ):
                    record["periods"].append(
                        {
                            "start": period["start"],
                            "end": period_end,
                            "kind": period["kind"],
                            "status": "superseded",
                            "superseded_by": existing_period["article_id"],
                        }
                    )
                    stats["superseded_periods"] += 1
                    continue

                parsed_periods[period_end] = {
                    "article_id": article_id,
                    "published_at": meta.get("published_at", ""),
                }
                current_periods.add(period_end)
                block_path = BLOCK_DIR / f"{period_end}.md"
                block_path.write_text(segment + "\n", encoding="utf-8")
                period_records_by_end[period_end] = period_record_from_dataset(
                    record, dataset, block_path
                )
                record["periods"].append(
                    {
                        "start": period["start"],
                        "end": period_end,
                        "kind": period["kind"],
                        "status": "parsed",
                        "block_path": str(block_path),
                    }
                )
                written.append((dataset, block_path))
                if period["kind"] == "month":
                    stats["month"] += 1
                else:
                    stats["week"] += 1
                quality = dataset["quality"]
                stats["has_passenger_retail"] += int(
                    quality["has_passenger_retail"]
                )
                stats["has_passenger_wholesale"] += int(
                    quality["has_passenger_wholesale"]
                )
                stats["has_nev"] += int(quality["has_nev"])
                stats["has_ytd"] += int(quality["has_ytd"])

            if written:
                primary_dataset, primary_block_path = written[0]
                record.update(
                    {
                        "period_start": primary_dataset["period"]["start"],
                        "period_end": primary_dataset["period"]["end"],
                        "kind": primary_dataset["period"]["kind"],
                        "status": "parsed",
                        "error": None,
                        "block_path": str(primary_block_path),
                    }
                )
                (FAILED_DIR / f"{article_id}.md").unlink(missing_ok=True)
                stats["parsed"] += 1
            else:
                record["status"] = "superseded"
                record["error"] = "all periods already parsed from newer articles"
                record["block_path"] = None
                stats["superseded"] += 1
            records.append(record)
        except Exception as exc:
            record["status"] = "fetch_failed"
            record["error"] = str(exc)
            stats["failed"] += 1
            records.append(record)

    merged_by_id = {record["article_id"]: record for record in existing_records}
    for record in records:
        merged_by_id[record["article_id"]] = record
    merged_records = sorted(
        merged_by_id.values(),
        key=lambda record: record.get("list_date", ""),
        reverse=True,
    )
    parsed_records = [
        record for record in merged_records if record.get("status") == "parsed"
    ]
    stats["periods"] = len(current_periods)
    period_records = sorted(
        period_records_by_end.values(), key=lambda record: record.get("period_end", "")
    )
    cumulative = {
        "articles": len(merged_records),
        "parsed": len(parsed_records),
        "periods": len(period_records),
        "month": sum(1 for record in period_records if record.get("kind") == "month"),
        "week": sum(
            1 for record in period_records if record.get("kind") == "month_to_date"
        ),
        "archived_only": sum(
            1 for record in merged_records if record.get("status") == "archived_only"
        ),
        "superseded": sum(
            1 for record in merged_records if record.get("status") == "superseded"
        ),
        "superseded_periods": sum(
            1
            for record in merged_records
            for period in record.get("periods", [])
            if period.get("status") == "superseded"
        ),
    }
    raw_week_starts = [
        record["week_start"] for record in merged_records if record.get("week_start")
    ]
    raw_week_ends = [
        record["week_end"] for record in merged_records if record.get("week_end")
    ]
    parsed_period_starts = [
        record["period_start"] for record in period_records if record.get("period_start")
    ]
    parsed_period_ends = [
        record["period_end"] for record in period_records if record.get("period_end")
    ]
    coverage = {
        "raw_week_start": min(raw_week_starts) if raw_week_starts else None,
        "raw_week_end": max(raw_week_ends) if raw_week_ends else None,
        "parsed_period_start": min(parsed_period_starts)
        if parsed_period_starts
        else None,
        "parsed_period_end": max(parsed_period_ends) if parsed_period_ends else None,
    }
    manifest = {
        "generated_at": fetched_at,
        "source": "https://www.cpcaauto.com/news.php?types=csjd&anid=128&nid=21",
        "start": args.start,
        "end": args.end,
        "coverage": coverage,
        "stats": stats,
        "cumulative": cumulative,
        "periods": period_records,
        "articles": merged_records,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("\nRun stats:")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print("Cumulative manifest:")
    print(json.dumps(cumulative, ensure_ascii=False, indent=2))
    print(f"Manifest: {MANIFEST_PATH}")
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
