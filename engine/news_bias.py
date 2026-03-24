from __future__ import annotations

import os
import time
from collections import Counter
from typing import Any

import requests

FMP_BASE = "https://financialmodelingprep.com/stable"
GDELT_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
NEWS_TIMEOUT = 12
MAX_HEADLINES = 12

POSITIVE_KEYWORDS = {
    "ceasefire": 18,
    "truce": 16,
    "de-escalation": 18,
    "deal": 10,
    "talks": 8,
    "progress": 8,
    "agreement": 12,
    "approval": 15,
    "inflows": 12,
    "easing": 12,
    "pause": 10,
    "no strike": 18,
    "no attack": 16,
    "open sea lanes": 14,
}
NEGATIVE_KEYWORDS = {
    "attack": 18,
    "strike": 16,
    "retaliation": 18,
    "escalation": 18,
    "war": 14,
    "sanctions": 12,
    "shutdown": 14,
    "blockade": 16,
    "hormuz": 14,
    "outflows": 12,
    "hawkish": 12,
    "missile": 18,
    "drone": 12,
}
SOURCE_WEIGHT = {
    "reuters": 1.25,
    "bloomberg": 1.25,
    "wsj": 1.18,
    "cnbc": 1.12,
    "financial times": 1.12,
    "cointelegraph": 1.0,
    "the block": 1.0,
    "coindesk": 1.0,
    "decrypt": 0.95,
    "gdelt": 0.9,
}

EVENT_TYPE_RULES = [
    ("geopolitical_deescalation", ("ceasefire", "truce", "de-escalation", "deal", "talks progress", "peace")),
    ("geopolitical_escalation", ("attack", "retaliation", "escalation", "strike", "war", "missile", "hormuz")),
    ("macro_easing", ("rate cut", "easing", "liquidity", "stimulus", "dovish")),
    ("macro_hawkish", ("hawkish", "inflation concern", "rate hike", "tightening")),
    ("etf_inflows", ("etf inflow", "inflows", "spot etf")),
    ("etf_outflows", ("etf outflow", "outflows", "redemptions")),
    ("regulatory_relief", ("approval", "dismissed", "settlement", "clarity")),
    ("regulatory_pressure", ("lawsuit", "ban", "probe", "sanctions")),
]

def _now_ts() -> int:
    return int(time.time())

def _source_weight(name: str | None) -> float:
    if not name:
        return 1.0
    low = name.lower()
    for key, val in SOURCE_WEIGHT.items():
        if key in low:
            return val
    return 1.0

def _freshness_weight(ts: int | None) -> float:
    if not ts:
        return 0.65
    age_min = max(0, (_now_ts() - ts) / 60)
    if age_min <= 10:
        return 1.2
    if age_min <= 30:
        return 1.0
    if age_min <= 90:
        return 0.8
    if age_min <= 240:
        return 0.55
    return 0.35

def _parse_ts(text: str | None) -> int | None:
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            import datetime as dt
            return int(dt.datetime.strptime(text, fmt).timestamp())
        except Exception:
            pass
    return None

def _score_text(text: str) -> tuple[int, str | None, list[str]]:
    low = text.lower()
    pos = sum(v for k, v in POSITIVE_KEYWORDS.items() if k in low)
    neg = sum(v for k, v in NEGATIVE_KEYWORDS.items() if k in low)
    tags = [k for k in list(POSITIVE_KEYWORDS) + list(NEGATIVE_KEYWORDS) if k in low][:6]
    bias = None
    if pos > neg and pos >= 8:
        bias = "long"
    elif neg > pos and neg >= 8:
        bias = "short"
    return abs(pos - neg), bias, tags

def _detect_event_type(text: str) -> str:
    low = text.lower()
    for event_type, keys in EVENT_TYPE_RULES:
        if any(k in low for k in keys):
            return event_type
    if "trump" in low or "iran" in low or "israel" in low:
        return "geopolitical_event"
    if "etf" in low:
        return "etf_flow"
    if "fed" in low or "powell" in low or "cpi" in low or "pmi" in low:
        return "macro_event"
    return "general_event"

def _summarize(event_type: str, bias: str, score: int, tags: list[str]) -> str:
    bias_cn = {"long": "偏多", "short": "偏空", "neutral": "中性"}.get(bias, "中性")
    tag_txt = " / ".join(tags[:4]) if tags else "none"
    return f"{event_type}｜{bias_cn}｜强度{score}｜标签: {tag_txt}"

def _safe_get(url: str, params: dict[str, Any]) -> Any:
    try:
        r = requests.get(url, params=params, timeout=NEWS_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def fetch_fmp_news(symbol: str = "BTCUSD") -> list[dict[str, Any]]:
    key = os.getenv("FMP_API_KEY", "").strip()
    if not key:
        return []
    out: list[dict[str, Any]] = []
    endpoints = [
        ("news/crypto-latest", {"apikey": key, "limit": 6}),
        ("news/general-latest", {"apikey": key, "limit": 6}),
        ("news/stock", {"apikey": key, "symbols": symbol, "limit": 6}),
    ]
    for path, params in endpoints:
        data = _safe_get(f"{FMP_BASE}/{path}", params)
        if not isinstance(data, list):
            continue
        for item in data[:6]:
            title = item.get("title") or ""
            text = " ".join([
                title,
                str(item.get("text") or ""),
                str(item.get("publishedDate") or ""),
            ]).strip()
            ts = _parse_ts(item.get("publishedDate"))
            out.append({
                "source": item.get("site") or item.get("publisher") or "fmp",
                "title": title,
                "text": text,
                "url": item.get("url"),
                "ts": ts,
            })
    return out[:MAX_HEADLINES]

def fetch_gdelt_news() -> list[dict[str, Any]]:
    query = '("Trump" OR "Iran" OR "Israel" OR "Hormuz" OR "ceasefire" OR "sanctions" OR "ETF" OR "Fed" OR "Powell" OR "Bitcoin")'
    params = {
        "query": query,
        "mode": "ArtList",
        "maxrecords": 10,
        "sort": "DateDesc",
        "format": "json",
    }
    data = _safe_get(GDELT_BASE, params)
    articles = data.get("articles") if isinstance(data, dict) else None
    if not isinstance(articles, list):
        return []
    out = []
    for item in articles[:10]:
        title = item.get("title") or ""
        text = " ".join([
            title,
            str(item.get("seendate") or ""),
            str(item.get("sourcecountry") or ""),
        ]).strip()
        ts = _parse_ts(item.get("seendate"))
        out.append({
            "source": item.get("sourceCommonName") or "gdelt",
            "title": title,
            "text": text,
            "url": item.get("url"),
            "ts": ts,
        })
    return out

def get_news_bias(symbol: str = "BTCUSD") -> dict[str, Any]:
    raw = []
    raw.extend(fetch_fmp_news(symbol))
    raw.extend(fetch_gdelt_news())

    if not raw:
        return {
            "bias": "neutral",
            "score": 0,
            "event_type": "none",
            "summary": "none｜中性｜强度0｜标签: none",
            "tags": [],
            "headline_count": 0,
        }

    long_score = 0.0
    short_score = 0.0
    tag_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()

    for item in raw:
        text = f"{item.get('title','')} {item.get('text','')}".strip()
        base_score, bias, tags = _score_text(text)
        if base_score <= 0 or not bias:
            continue
        weighted = base_score * _source_weight(item.get("source")) * _freshness_weight(item.get("ts"))
        if bias == "long":
            long_score += weighted
        else:
            short_score += weighted
        for t in tags:
            tag_counter[t] += 1
        type_counter[_detect_event_type(text)] += 1

    if long_score == 0 and short_score == 0:
        return {
            "bias": "neutral",
            "score": 0,
            "event_type": type_counter.most_common(1)[0][0] if type_counter else "none",
            "summary": "none｜中性｜强度0｜标签: none",
            "tags": [],
            "headline_count": len(raw),
        }

    bias = "long" if long_score >= short_score else "short"
    diff = abs(long_score - short_score)
    score = max(0, min(100, int(round(diff))))
    event_type = type_counter.most_common(1)[0][0] if type_counter else "general_event"
    tags = [k for k, _ in tag_counter.most_common(4)]
    return {
        "bias": bias,
        "score": score,
        "event_type": event_type,
        "summary": _summarize(event_type, bias, score, tags),
        "tags": tags,
        "headline_count": len(raw),
    }
