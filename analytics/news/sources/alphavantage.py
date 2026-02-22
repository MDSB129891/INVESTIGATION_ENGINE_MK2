from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import List

from analytics.provider_net import request_with_resilience

from ..schema import NewsItem
from ..utils import parse_iso_datetime


def _key() -> str:
    k = (
        os.getenv("ALPHAVANTAGE_API_KEY")
        or os.getenv("ALPHA_VANTAGE_API_KEY")
        or os.getenv("ALPHAVANTAGE_KEY")
        or os.getenv("ALPHA_VANTAGE_KEY")
        or os.getenv("AV_API_KEY")
        or ""
    ).strip()
    if not k:
        raise RuntimeError("Missing ALPHAVANTAGE_API_KEY")
    return k


def fetch_alphavantage_news(ticker: str, days_back: int = 30, max_items: int = 200) -> List[NewsItem]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": ticker.upper(),
        "time_from": start.strftime("%Y%m%dT%H%M"),
        "time_to": end.strftime("%Y%m%dT%H%M"),
        "limit": min(max_items, 1000),
        "apikey": _key(),
    }
    r = request_with_resilience("alphavantage", url, params=params)
    data = r.json() or {}
    feed = data.get("feed") or []
    if not isinstance(feed, list):
        return []

    out: List[NewsItem] = []
    for a in feed[:max_items]:
        title = a.get("title") or ""
        link = a.get("url") or ""
        dt = a.get("time_published") or ""
        iso = parse_iso_datetime(dt) or datetime.now(timezone.utc).isoformat()
        out.append(
            NewsItem(
                published_at=iso,
                ticker=ticker.upper(),
                title=title,
                source="alphavantage",
                url=link,
                summary=a.get("summary"),
                raw={
                    "source": a.get("source"),
                    "overall_sentiment_score": a.get("overall_sentiment_score"),
                    "overall_sentiment_label": a.get("overall_sentiment_label"),
                },
            )
        )
    return out
