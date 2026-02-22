from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import List

from analytics.provider_net import request_with_resilience

from ..schema import NewsItem
from ..utils import parse_iso_datetime


def _key() -> str:
    k = (
        os.getenv("MARKETAUX_API_KEY")
        or os.getenv("MARKETAUX_TOKEN")
        or os.getenv("MARKETAUX_KEY")
        or ""
    ).strip()
    if not k:
        raise RuntimeError("Missing MARKETAUX_API_KEY")
    return k


def fetch_marketaux_news(ticker: str, days_back: int = 30, max_items: int = 200) -> List[NewsItem]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days_back)
    url = "https://api.marketaux.com/v1/news/all"
    params = {
        "symbols": ticker.upper(),
        "published_after": start.isoformat(),
        "published_before": end.isoformat(),
        "filter_entities": "true",
        "language": "en",
        "limit": min(max_items, 100),
        "api_token": _key(),
    }
    r = request_with_resilience("marketaux", url, params=params)
    data = r.json() or {}
    arts = data.get("data") or []
    if not isinstance(arts, list):
        return []

    out: List[NewsItem] = []
    for a in arts[:max_items]:
        title = a.get("title") or ""
        link = a.get("url") or ""
        dt = a.get("published_at") or ""
        iso = parse_iso_datetime(dt) or datetime.now(timezone.utc).isoformat()
        out.append(
            NewsItem(
                published_at=iso,
                ticker=ticker.upper(),
                title=title,
                source="marketaux",
                url=link,
                summary=a.get("description") or a.get("snippet"),
                raw={
                    "source": (a.get("source") or {}).get("name") if isinstance(a.get("source"), dict) else a.get("source"),
                    "entities": a.get("entities"),
                },
            )
        )
    return out
