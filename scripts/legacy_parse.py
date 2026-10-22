#!/usr/bin/env python3
"""Legacy V2 parser for 2022-2023 CPCA weekly articles.

The early articles do not have the structured "本周车市概述" summary used
from 2024-01-17 onward. They usually contain a one-line passenger summary
(retail and wholesale) but no NEV / YTD / penetration fields.

This parser is deliberately tolerant: missing fields are stored as null.
It never feeds the formal data/*.json or the weekly report.
"""

from __future__ import annotations

import calendar
import re
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from fetch_cpca_history import html_to_text  # noqa: E402


def extract_legacy_overview(html: str) -> str:
    text = html_to_text(html)
    heading = text.find("本周车市概述")
    after = text[heading + len("本周车市概述") :] if heading != -1 else text

    cut = re.search(r"\n\s*1[、.．]\s*", after)
    body = after[: cut.start()] if cut else after
    body = re.sub(r"\s+", " ", body).strip().lstrip("：: ")

    if not body:
        # Some early articles put the summary inside section 1, right after
        # the "1." heading. Take the first two summary sentences there.
        period_re = re.compile(
            r"(\d{1,2}月\s*\d{1,2}\s*日?\s*-\s*\d{1,2}日)"
        )
        for match in period_re.finditer(after):
            segment = after[match.start() : match.start() + 600]
            if "乘用车" in segment and "万辆" in segment:
                rest = after[match.start() :]
                ends = [item.end() for item in re.finditer(r"。", rest)]
                if len(ends) >= 2:
                    body = rest[: ends[1]]
                elif ends:
                    body = rest[: ends[0]]
                else:
                    body = rest[:400]
                break

    body = re.sub(r"\s+", " ", body).strip().lstrip("：: ")
    # Fix malformed thousands separators such as 1.939.5.
    body = re.sub(r"(?<=\d)\.(?=\d{3}\.)", ",", body)
    if not body:
        raise ValueError("legacy overview block is empty")
    return body


def parse_legacy_metric(sentence: str) -> dict[str, float | None]:
    value = re.search(r"([0-9][0-9,]*\.?[0-9]*)\s*万辆", sentence)
    yoy = re.search(r"同比[^，。；]*?(下降|增长|降)([0-9.]+)%", sentence)
    vs_prev = re.search(r"较上月同期(下降|增长|降)([0-9.]+)%", sentence)
    if not vs_prev:
        vs_prev = re.search(r"环比(?!上周)(下降|增长|降)([0-9.]+)%", sentence)
    wow = re.search(r"环比上周(下降|增长|降)([0-9.]+)%", sentence)
    ytd_value = re.search(
        r"今年(?:以来)?累计.*?([0-9][0-9,]*\.?[0-9]*)\s*万辆", sentence
    )
    ytd_yoy = re.search(
        r"今年(?:以来)?累计.*?同比[^，。；]*?(下降|增长|降)([0-9.]+)%", sentence
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
        "value": number(value),
        "yoy_pct": percent(yoy),
        "vs_prev_month_same_period_pct": percent(vs_prev),
        "ytd_value": number(ytd_value),
        "ytd_yoy_pct": percent(ytd_yoy),
        "wow_pct": percent(wow),
    }


def ytd_candidates(block: str, keyword: str) -> list[tuple[float, float | None]]:
    pattern = re.compile(
        rf"今年(?:以来)?累计{keyword}\s*([0-9][0-9,]*\.?[0-9]*)\s*万辆"
        rf"[，,；;]?\s*同比(?:去年)?\s*(下降|增长|降|持平)\s*([0-9.]+)?%?"
    )
    candidates = []
    for match in pattern.finditer(block):
        value = float(match.group(1).replace(",", ""))
        if match.group(2) == "持平" or match.group(3) is None:
            yoy = None
        else:
            number = float(match.group(3))
            yoy = -number if match.group(2) in {"下降", "降"} else number
        candidates.append((value, yoy))
    return candidates


def attach_ytd(metrics: dict, block: str) -> None:
    for keyword, keys in (
        ("零售", ("passenger_retail", "nev_retail")),
        ("批发", ("passenger_wholesale", "nev_wholesale")),
    ):
        candidates = ytd_candidates(block, keyword)
        targets = [key for key in keys if metrics.get(key) is not None]
        for index, key in enumerate(targets):
            metric = metrics[key]
            if metric.get("ytd_value") is not None or index >= len(candidates):
                continue
            metric["ytd_value"], metric["ytd_yoy_pct"] = candidates[index]


def pick_sentence(sentences: list[str], keyword: str, nev: bool | None = None) -> str | None:
    for sentence in sentences:
        if "万辆" not in sentence or keyword not in sentence:
            continue
        has_nev = "新能源" in sentence
        if nev is True and not has_nev:
            continue
        if nev is False and has_nev:
            continue
        return sentence
    return None


def metric_object(
    sentence: str | None, label: str
) -> dict[str, float | None] | None:
    if sentence is None:
        return None
    parsed = parse_legacy_metric(sentence)
    if parsed["value"] is None:
        return None
    return {
        "label": label,
        "value": parsed["value"],
        "unit": "万辆",
        "yoy_pct": parsed["yoy_pct"],
        "vs_prev_month_same_period_pct": parsed["vs_prev_month_same_period_pct"],
        "ytd_value": parsed["ytd_value"],
        "ytd_yoy_pct": parsed["ytd_yoy_pct"],
        "wow_pct": parsed["wow_pct"],
    }


PERIOD_RE = re.compile(
    r"(\d{1,2})月\s*(\d{1,2})\s*日?\s*-\s*(\d{1,2})日"
)


def is_summary_period_start(block: str, match: re.Match[str]) -> bool:
    """Reject comparison labels such as '较5月1-12日下降21%'."""
    prefix = block[max(0, match.start() - 10) : match.start()]
    if re.search(r"[较比]\s*$", prefix):
        return False
    lookahead = block[match.end() : match.end() + 260]
    return "万辆" in lookahead


def split_legacy_segments(block: str) -> list[str]:
    """Split a summary into independent period segments.

    Most blocks contain one weekly segment plus a cumulative segment that
    starts at the beginning of the same month. A few month-end blocks also
    contain the first days of the next month (e.g. 2022-05-31 + 6/1-5).
    """
    matches = [
        match for match in PERIOD_RE.finditer(block) if is_summary_period_start(block, match)
    ]
    segments = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(block)
        segment = block[match.start() : end].strip()
        if segment:
            segments.append(segment)
    return segments


def parse_legacy_block_multi(
    block: str, published_date: date
) -> list[tuple[dict, str]]:
    """Parse the primary period and any later, non-overlapping period.

    The primary dataset is parsed from the whole block so that a same-period
    NEV paragraph is not lost. Only a genuinely later period (for example the
    〝6月1-5日〞 line in a 5月 month-end article) becomes a second dataset.
    """
    primary = parse_legacy_block(block, published_date)
    result = [(primary, block)]
    for segment in split_legacy_segments(block):
        try:
            dataset = parse_legacy_block(segment, published_date)
        except ValueError:
            continue
        if dataset["period"]["start"] <= primary["period"]["end"]:
            continue
        if all(
            dataset["period"]["start"] > accepted["period"]["end"]
            for accepted, _ in result
        ):
            result.append((dataset, segment))
    return result


def parse_legacy_block(block: str, published_date: date) -> dict:
    period_match = PERIOD_RE.search(block)
    if not period_match:
        raise ValueError(f"Cannot find period in legacy block: {block[:80]}")
    month, start_day, end_day = (int(value) for value in period_match.groups())

    year = published_date.year
    if month > published_date.month:
        year -= 1
    start = date(year, month, start_day)
    end = date(year, month, end_day)
    last_day = calendar.monthrange(year, month)[1]
    kind = "month" if start_day == 1 and end_day == last_day else "month_to_date"
    days = (end - start).days + 1

    sentences = [part.strip() for part in re.split(r"[；。;]", block) if part.strip()]
    passenger_retail = pick_sentence(sentences, "零售", nev=False)
    passenger_wholesale = pick_sentence(sentences, "批发", nev=False)
    nev_retail = pick_sentence(sentences, "零售", nev=True)
    nev_wholesale = pick_sentence(sentences, "批发", nev=True)

    metrics = {
        "passenger_retail": metric_object(passenger_retail, "乘用车零售"),
        "passenger_wholesale": metric_object(passenger_wholesale, "乘用车批发"),
        "nev_retail": metric_object(nev_retail, "新能源零售"),
        "nev_wholesale": metric_object(nev_wholesale, "新能源批发"),
    }
    attach_ytd(metrics, block)
    if metrics["passenger_retail"] is None and metrics["passenger_wholesale"] is None:
        raise ValueError(f"No passenger retail/wholesale found: {block[:80]}")

    return {
        "schema_version": "legacy-v2",
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "label": f"{month}月{start_day}-{end_day}日",
            "kind": kind,
            "days": days,
        },
        "metrics": metrics,
        "quality": {
            "has_passenger_retail": metrics["passenger_retail"] is not None,
            "has_passenger_wholesale": metrics["passenger_wholesale"] is not None,
            "has_nev": metrics["nev_retail"] is not None
            or metrics["nev_wholesale"] is not None,
            "has_ytd": any(
                metric and metric.get("ytd_value") is not None
                for metric in metrics.values()
            ),
        },
        "notes": [],
    }
