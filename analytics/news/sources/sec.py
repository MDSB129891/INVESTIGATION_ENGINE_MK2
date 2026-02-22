from __future__ import annotations

import json
import os
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from ..schema import NewsItem
from ..utils import parse_iso_datetime
from analytics.provider_net import request_with_resilience


SEC_TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

# SEC requires a real User-Agent identifying you (email recommended)
DEFAULT_UA = "investment_decision_engine (research) contact: melbello1205@gmail.com "


def _sec_get(url: str, ua: str) -> dict:
    r = request_with_resilience("sec", url, headers={"User-Agent": ua})
    return r.json()


def _load_ticker_cik(cache_path: str, ua: str) -> dict:
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    data = _sec_get(SEC_TICKER_CIK_URL, ua)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def _ticker_to_cik(ticker: str, cache_path: str, ua: str) -> Optional[str]:
    data = _load_ticker_cik(cache_path, ua)
    t = ticker.upper()
    for _, row in data.items():
        if str(row.get("ticker", "")).upper() == t:
            cik_int = int(row.get("cik_str"))
            return f"{cik_int:010d}"
    return None


def fetch_sec_filings(
    ticker: str,
    days_back: int = 30,
    max_items: int = 50,
    cache_dir: str = "data/raw/news_cache",
    user_agent: str = DEFAULT_UA,
) -> List[NewsItem]:
    """
    Pulls recent filings from SEC submissions JSON (high-signal).
    """
    os.makedirs(cache_dir, exist_ok=True)
    cik_cache = os.path.join(cache_dir, "sec_ticker_cik.json")

    cik = _ticker_to_cik(ticker, cik_cache, user_agent)
    if not cik:
        return []

    data = _sec_get(SEC_SUBMISSIONS_URL.format(cik=cik), user_agent)
    recent = (data.get("filings", {}) or {}).get("recent", {}) or {}

    forms = recent.get("form", []) or []
    dates = recent.get("filingDate", []) or []
    accs = recent.get("accessionNumber", []) or []
    primary_docs = recent.get("primaryDocument", []) or []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    out: List[NewsItem] = []

    for form, fdate, acc, doc in zip(forms, dates, accs, primary_docs):
        iso = parse_iso_datetime(fdate) or None
        if not iso:
            continue

        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt < cutoff:
            continue

        acc_no = str(acc).replace("-", "")
        # Filing URL pattern
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}/{doc}"
        title = f"{ticker.upper()} SEC filing: {form} ({fdate})"

        out.append(NewsItem(
            published_at=dt.astimezone(timezone.utc).isoformat(),
            ticker=ticker.upper(),
            title=title,
            source="sec",
            url=url,
            summary=None,
            raw={"form": form, "filingDate": fdate, "accessionNumber": acc},
        ))

        if len(out) >= max_items:
            break

    return out
