from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import List

from analytics.provider_net import request_with_resilience

from ..schema import NewsItem
from ..utils import parse_iso_datetime


def _key() -> str:
    k = (
        os.getenv("TIINGO_API_KEY")
        or os.getenv("TIINGO_TOKEN")
        or os.getenv("TIINGO_KEY")
        or ""
    ).strip()
    if not k:
        raise RuntimeError("Missing TIINGO_API_KEY")
    return k


def fetch_tiingo_news(ticker: str, days_back: int = 30, max_items: int = 200) -> List[NewsItem]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days_back)
    url = "https://api.tiingo.com/tiingo/news"
    params = {
        "tickers": ticker.upper(),
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "limit": min(max_items, 1000),
        "token": _key(),
    }
    r = request_with_resilience("tiingo", url, params=params)
    data = r.json()
    if not isinstance(data, list):
        return []

    out: List[NewsItem] = []
    for a in data[:max_items]:
        title = a.get("title") or ""
        link = a.get("url") or ""
        dt = a.get("publishedDate") or a.get("crawlDate") or ""
        iso = parse_iso_datetime(dt) or datetime.now(timezone.utc).isoformat()
        summary = a.get("description") or a.get("snippet")
        out.append(
            NewsItem(
                published_at=iso,
                ticker=ticker.upper(),
                title=title,
                source="tiingo",
                url=link,
                summary=summary,
                raw={
                    "source": a.get("source"),
                    "tags": a.get("tags"),
                },
            )
        )
    return out
