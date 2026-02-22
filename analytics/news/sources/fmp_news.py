from __future__ import annotations

import os
from typing import List
from datetime import datetime, timedelta, timezone

from ..schema import NewsItem
from ..utils import parse_iso_datetime
from analytics.provider_net import request_with_resilience


def fetch_fmp_stock_news(
    ticker: str,
    days_back: int = 30,
    max_items: int = 100,
) -> List[NewsItem]:
    """
    Best-effort FMP news fetcher. Endpoint/path can vary by plan.
    We attempt common endpoints and gracefully return [] on failure.

    If it works for your key, it adds good ticker-specific coverage.
    """
    key = os.getenv("FMP_API_KEY")
    if not key:
        return []

    # Candidate endpoints (try in order)
    candidates = [
        # Common legacy:
        ("https://financialmodelingprep.com/api/v3/stock_news", {"tickers": ticker, "limit": max_items, "apikey": key}),
        # Some accounts expose stable news under /stable:
        ("https://financialmodelingprep.com/stable/news", {"symbol": ticker, "limit": max_items, "apikey": key}),
    ]

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    for url, params in candidates:
        try:
            r = request_with_resilience("fmp", url, params=params)
            data = r.json()
            if not isinstance(data, list):
                continue

            out: List[NewsItem] = []
            for a in data:
                title = a.get("title") or ""
                link = a.get("url") or a.get("link") or ""
                dt = a.get("publishedDate") or a.get("date") or a.get("published_at") or ""
                iso = parse_iso_datetime(dt)
                if not iso:
                    iso = datetime.now(timezone.utc).isoformat()

                # filter by days_back
                try:
                    dti = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                    if dti.tzinfo is None:
                        dti = dti.replace(tzinfo=timezone.utc)
                    if dti < cutoff:
                        continue
                except Exception:
                    pass

                out.append(NewsItem(
                    published_at=iso,
                    ticker=ticker.upper(),
                    title=title,
                    source="fmp",
                    url=link,
                    summary=a.get("text") or a.get("summary"),
                    raw={"site": a.get("site"), "publisher": a.get("publisher")},
                ))

            if out:
                return out

        except Exception:
            continue

    return []
