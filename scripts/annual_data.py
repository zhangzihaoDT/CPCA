"""Build annual exports from the CPCA period datasets and monthly references."""

from __future__ import annotations

import calendar
import csv
import json
from datetime import date
from pathlib import Path

from legacy_parse import parse_legacy_month_close

ROOT = Path(__file__).resolve().parent.parent
ANNUAL_DIR = ROOT / "data" / "annual"
MONTHLY_REFERENCE = ROOT / "input" / "monthly" / "reference.csv"
METRICS = {
    "passenger_retail": "乘用车零售",
    "passenger_wholesale": "乘用车批发",
    "nev_retail": "新能源零售",
    "nev_wholesale": "新能源批发",
}


def recover_legacy_months(items: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    existing = {
        item["period"]["end"] for _, item in items if item["period"]["kind"] == "month"
    }
    recovered = []
    for layer, item in items:
        if item["schema_version"] != "legacy-v2" or item["period"]["end"] in existing:
            continue
        end = date.fromisoformat(item["period"]["end"])
        if end.day != calendar.monthrange(end.year, end.month)[1]:
            continue
        source = item["source"]
        block = (ROOT / source["block_path"]).read_text(encoding="utf-8")
        published = date.fromisoformat(source["published_at"][:10])
        dataset = parse_legacy_month_close(block, end, published)
        if dataset:
            dataset["source"] = {**source, "origin": "official-legacy-month-close"}
            recovered.append((layer, dataset))
            existing.add(end.isoformat())
    return recovered


def load_monthly_references() -> list[dict]:
    with MONTHLY_REFERENCE.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    datasets = []
    for row in rows:
        end = date.fromisoformat(row["period_end"])
        if end.day != calendar.monthrange(end.year, end.month)[1]:
            raise ValueError(f"Monthly reference must cover a full month: {end}")
        datasets.append(
            {
                "period": {
                    "start": end.replace(day=1).isoformat(),
                    "end": end.isoformat(),
                    "kind": "month",
                    "days": end.day,
                },
                "metrics": {
                    key: {
                        "label": label,
                        "value": float(row[key]),
                        "yoy_pct": float(row[f"{key}_yoy"]),
                        "unit": "万辆",
                    }
                    for key, label in METRICS.items()
                },
                "source": {
                    "publisher": "CPCA",
                    "section": "乘用车市场分析",
                    "origin": "official-monthly-analysis",
                    "url": row["url"],
                    "article_id": row["article_id"],
                    "published_at": row["published_at"],
                    "content_hash": row["content_hash"],
                    "raw_path": f"input/monthly/raw/{row['article_id']}.html",
                },
            }
        )
    return datasets


def write_annual_exports(summary: dict) -> None:
    ANNUAL_DIR.mkdir(parents=True, exist_ok=True)
    for year in summary["years"]:
        if year["year"] < 2022:
            continue
        prefix = f"{year['year']}-"
        periods = sorted(
            (item for _, item in summary["items"] if item["period"]["end"].startswith(prefix)),
            key=lambda item: (item["period"]["end"], item["period"]["kind"]),
        )
        references = [
            item for item in summary["monthly_references"]
            if item["period"]["end"].startswith(prefix)
        ]
        gaps = [
            row for group in ("calendar_rows", "nev_rows", "month_rows")
            for row in summary[group] if row["year"] == year["year"]
        ]
        dataset = {
            "year": year["year"],
            "through": year["window_end"].isoformat(),
            "periods": periods,
            "monthly_market_analysis": references,
            "coverage_notes": gaps,
        }
        output = ANNUAL_DIR / f"{year['year']}.json"
        output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
