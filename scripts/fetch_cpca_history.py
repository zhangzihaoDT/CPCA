#!/usr/bin/env python3
"""Fetch CPCA weekly "车市扫描" articles and extract the overview block.

Official archive layout:
    input/official/raw/<article_id>.html      original HTML cache
    input/official/blocks/<period_end>.md     normalized "本周车市概述" block
    input/official/manifest.json              provenance and fetch statistics

The script only extracts the "本周车市概述" block. It does not parse the
detailed article body (weekly daily averages, commentary, etc.).

Usage:
    python3 scripts/fetch_cpca_history.py --start 2026-01-01 --clean
    python3 scripts/fetch_cpca_history.py --start 2026-01-01 --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_module
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from http.cookiejar import CookieJar
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from ingest_weekly import parse_block  # noqa: E402

BASE_URL = "https://www.cpcaauto.com"
LIST_URL = BASE_URL + "/news.php?types=csjd&anid=128&nid=21&page={page}"
ARTICLE_URL = BASE_URL + "/newslist.php?types=csjd&id={article_id}"
OFFICIAL_DIR = Path("input/official")
RAW_DIR = OFFICIAL_DIR / "raw"
BLOCK_DIR = OFFICIAL_DIR / "blocks"
FAILED_DIR = OFFICIAL_DIR / "blocks_failed"
MANIFEST_PATH = OFFICIAL_DIR / "manifest.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": BASE_URL + "/",
    "Upgrade-Insecure-Requests": "1",
}

ITEM_RE = re.compile(
    r'<li class="q">\s*<span>(\d{4}-\d{2}-\d{2})\s*</span>\s*'
    r'<a href="newslist\.php\?types=csjd&id=(\d+)">\s*'
    r'(?:&nbsp;)*\s*(.*?)</a>',
    re.S,
)
TITLE_RE = re.compile(r'<div class="tit">(.*?)</div>', re.S)
PUBLISHED_RE = re.compile(r"发布时间：\s*(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2})?)")
WEEK_RANGE_RE = re.compile(r"\((\d{8,9})-(\d{4,8})\)")

opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(CookieJar())
)


def clean_text(value: str) -> str:
    value = html_module.unescape(value)
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", value).strip()


def fetch_html(url: str, referer: str, delay: float) -> tuple[bytes, str]:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        time.sleep(delay)
        request = urllib.request.Request(
            url, headers={**HEADERS, "Referer": referer}
        )
        try:
            with opener.open(request, timeout=30) as response:
                data = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                text = data.decode(charset, errors="replace")
            if "请使用浏览器访问本站" in text and len(text) < 500:
                raise RuntimeError("site anti-bot challenge returned")
            return data, text
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            last_error = exc
            time.sleep(4 * attempt)
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def parse_week_range(title: str) -> tuple[date, date] | None:
    match = WEEK_RANGE_RE.search(title)
    if not match:
        return None
    start_text, end_text = match.groups()
    if len(start_text) == 9 and start_text[4] == "0":
        start_text = start_text[:4] + start_text[5:]
    if len(end_text) == 4:
        end_text = start_text[:4] + end_text
    try:
        start = date(
            int(start_text[:4]), int(start_text[4:6]), int(start_text[6:8])
        )
        end = date(int(end_text[:4]), int(end_text[4:6]), int(end_text[6:8]))
    except (ValueError, IndexError):
        return None
    return start, end


def parse_list_page(html: str) -> list[dict]:
    items: list[dict] = []
    for match in ITEM_RE.finditer(html):
        published_date, article_id, raw_title = match.groups()
        title = clean_text(raw_title)
        week_range = parse_week_range(title)
        items.append(
            {
                "article_id": article_id,
                "url": ARTICLE_URL.format(article_id=article_id),
                "title": title,
                "list_date": published_date,
                "week_range": (
                    f"{week_range[0].isoformat()}~{week_range[1].isoformat()}"
                    if week_range
                    else None
                ),
                "week_start": week_range[0].isoformat() if week_range else None,
                "week_end": week_range[1].isoformat() if week_range else None,
            }
        )
    return items


def html_to_text(source: str) -> str:
    source = re.sub(
        r"<(script|style)[^>]*>.*?</\1>", "", source, flags=re.S | re.I
    )
    source = re.sub(r"<br\s*/?>", "\n", source, flags=re.I)
    source = re.sub(r"</p\s*>", "\n", source, flags=re.I)
    source = re.sub(r"<[^>]+>", "", source)
    source = html_module.unescape(source)
    source = source.replace("\u00a0", " ").replace("\u3000", " ")
    source = re.sub(r"[ \t\r\f\v]+", " ", source)
    source = re.sub(r"\n\s*\n+", "\n", source)
    return source.strip()


def extract_overview(html: str) -> str:
    text = html_to_text(html)
    heading = text.find("本周车市概述")
    if heading == -1:
        raise ValueError("本周车市概述 heading not found")
    body = text[heading + len("本周车市概述") :]
    cut = re.search(r"\n\s*1[.．]\s*20\d{2}年", body)
    if not cut:
        cut = re.search(r"\n\s*1[.．]", body)
    if cut:
        body = body[: cut.start()]
    body = re.sub(r"\s+", " ", body).strip()
    # Some articles contain malformed thousands separators such as
    # "1.939.5万辆" (should be "1,939.5万辆").
    body = re.sub(r"(?<=\d)\.(?=\d{3}\.)", ",", body)
    if not body:
        raise ValueError("overview block is empty")

    # Some articles embed penetration inside the NEV paragraph; add a
    # separate section so the shared parser can read it.
    if "渗透率：" not in body:
        retail = re.search(r"零售渗透率([0-9.]+)%", body)
        wholesale = re.search(r"批发渗透率([0-9.]+)%", body)
        if retail and wholesale:
            body += (
                f" 渗透率：零售渗透率{retail.group(1)}%；"
                f"批发渗透率{wholesale.group(1)}%。"
            )

    # The parser treats "较上月同期" as the comparison field.
    body = re.sub(r"较上月(?!同期)", "较上月同期", body)
    body = re.sub(r"较上月同期同期", "较上月同期", body)

    # Ensure the block starts at the passenger section.
    start = min(
        [pos for pos in (body.find("乘用车："), body.find("初步统计：")) if pos != -1],
        default=-1,
    )
    if start > 0:
        body = body[start:]
    return body.strip()


def parse_article_metadata(html: str, fallback_title: str, fallback_date: str) -> dict:
    title_match = TITLE_RE.search(html)
    title = clean_text(title_match.group(1)) if title_match else fallback_title
    published_match = PUBLISHED_RE.search(html)
    published_at = (
        published_match.group(1) if published_match else fallback_date
    )
    return {
        "title": title,
        "published_at": published_at,
        "published_date": published_at[:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch CPCA weekly articles and extract their overview blocks"
    )
    parser.add_argument("--start", default="2026-01-01", help="Inclusive start date")
    parser.add_argument("--end", default=None, help="Inclusive end date (default latest)")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between requests")
    parser.add_argument("--max-pages", type=int, default=17, help="Maximum list pages")
    parser.add_argument("--dry-run", action="store_true", help="List articles only")
    parser.add_argument("--force", action="store_true", help="Refetch cached articles")
    parser.add_argument("--clean", action="store_true", help="Remove old blocks before writing")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else None

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    BLOCK_DIR.mkdir(parents=True, exist_ok=True)
    FAILED_DIR.mkdir(parents=True, exist_ok=True)

    existing_records: list[dict] = []
    if MANIFEST_PATH.exists() and not args.clean:
        existing_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        existing_records = existing_manifest.get("articles", [])

    existing_periods = {
        record["period_end"]: record["article_id"]
        for record in existing_records
        if record.get("status") == "parsed" and record.get("period_end")
    }

    if args.clean and not args.dry_run:
        for path in BLOCK_DIR.glob("*.md"):
            path.unlink()
        for path in FAILED_DIR.glob("*.md"):
            path.unlink()

    all_items: list[dict] = []
    page = 1
    while page <= args.max_pages:
        list_url = LIST_URL.format(page=page)
        list_cache = RAW_DIR / f"list_page_{page}.html"
        if list_cache.exists() and not args.force:
            html = list_cache.read_text(encoding="utf-8", errors="replace")
        else:
            data, html = fetch_html(list_url, BASE_URL + "/", args.delay)
            list_cache.write_bytes(data)
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

    # De-duplicate by article id while preserving list order.
    unique: dict[str, dict] = {}
    for item in all_items:
        unique.setdefault(item["article_id"], item)
    items = list(unique.values())

    def in_range(item: dict) -> bool:
        if item["week_start"] and item["week_end"]:
            item_start = date.fromisoformat(item["week_start"])
            item_end = date.fromisoformat(item["week_end"])
            if item_end < start:
                return False
            if end and item_start > end:
                return False
            return True
        published = date.fromisoformat(item["list_date"])
        if published < start:
            return False
        if end and published > end:
            return False
        return True

    selected = [item for item in items if in_range(item)]
    print(f"Listed articles: {len(items)}")
    print(f"Selected articles ({args.start}..{args.end or 'latest'}): {len(selected)}")
    for item in selected:
        print(
            f"  {item['article_id']}  {item['list_date']}  "
            f"{item['week_range'] or '-':<21} {item['title']}"
        )

    if args.dry_run:
        return 0

    fetched_at = datetime.now().isoformat(timespec="seconds")
    records: list[dict] = []
    parsed_periods: dict[str, str] = dict(existing_periods)
    stats = {
        "listed": len(items),
        "selected": len(selected),
        "fetched": 0,
        "extracted": 0,
        "parsed": 0,
        "month": 0,
        "week": 0,
        "failed": 0,
        "duplicate_periods": 0,
    }

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
            else:
                data, _ = fetch_html(item["url"], LIST_URL.format(page=1), args.delay)
                raw_path.write_bytes(data)
            stats["fetched"] += 1
            html = data.decode("utf-8", errors="replace")
            content_hash = hashlib.sha256(data).hexdigest()
            record["content_hash"] = content_hash

            meta = parse_article_metadata(
                html, item["title"], item["list_date"]
            )
            record.update(meta)
            published_date = date.fromisoformat(meta["published_date"])

            try:
                block = extract_overview(html)
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
                parsed = parse_block(block, published_date)
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

            period_end = parsed["period"]["end"]
            period_start = parsed["period"]["start"]
            kind = parsed["period"]["kind"]
            record.update(
                {
                    "period_start": period_start,
                    "period_end": period_end,
                    "kind": kind,
                    "status": "parsed",
                    "error": None,
                }
            )
            existing_article_id = parsed_periods.get(period_end)
            if existing_article_id and existing_article_id != article_id:
                record["status"] = "duplicate_period"
                record["error"] = (
                    f"period {period_end} also produced by article "
                    f"{existing_article_id}"
                )
                stats["duplicate_periods"] += 1
            else:
                parsed_periods[period_end] = article_id
                block_path = BLOCK_DIR / f"{period_end}.md"
                block_path.write_text(block + "\n", encoding="utf-8")
                record["block_path"] = str(block_path)
                stats["parsed"] += 1
                if kind == "month":
                    stats["month"] += 1
                else:
                    stats["week"] += 1
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
    cumulative = {
        "articles": len(merged_records),
        "parsed": len(parsed_records),
        "periods": len(
            {record.get("period_end") for record in parsed_records if record.get("period_end")}
        ),
        "month": sum(1 for record in parsed_records if record.get("kind") == "month"),
        "week": sum(
            1 for record in parsed_records if record.get("kind") == "month_to_date"
        ),
        "extract_failed": sum(
            1 for record in merged_records if record.get("status") == "extract_failed"
        ),
        "parse_failed": sum(
            1 for record in merged_records if record.get("status") == "parse_failed"
        ),
        "fetch_failed": sum(
            1 for record in merged_records if record.get("status") == "fetch_failed"
        ),
        "duplicate_period": sum(
            1 for record in merged_records if record.get("status") == "duplicate_period"
        ),
    }

    manifest = {
        "generated_at": fetched_at,
        "source": "https://www.cpcaauto.com/news.php?types=csjd&anid=128&nid=21",
        "start": args.start,
        "end": args.end,
        "stats": stats,
        "cumulative": cumulative,
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
