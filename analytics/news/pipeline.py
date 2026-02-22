from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pandas as pd

from .schema import NewsItem
from .utils import make_dedupe_key
from .scoring import score_and_tag

from .sources.sec import fetch_sec_filings
from .sources.finnhub import fetch_finnhub_company_news
from .sources.tiingo import fetch_tiingo_news
from .sources.marketaux import fetch_marketaux_news
from .sources.alphavantage import fetch_alphavantage_news


def run_news_pipeline(
    tickers: List[str],
    days_back: int = 30,
    enable_sources: Optional[List[str]] = None,
    sec_user_agent: Optional[str] = None,
    debug: bool = True,
) -> pd.DataFrame:
    """
    Stable multi-source news:
      - SEC filings
      - Finnhub company news
      - Tiingo news
      - Marketaux news
      - AlphaVantage news

    Returns a unified per-article DataFrame.
    """
    tickers = [str(t).upper().strip() for t in (tickers or []) if str(t).strip()]
    enable_sources = enable_sources or ["sec", "finnhub"]

    items: List[NewsItem] = []

    for t in tickers:
        # SEC filings
        if "sec" in enable_sources:
            try:
                got = (
                    fetch_sec_filings(t, days_back=days_back, max_items=60, user_agent=sec_user_agent)
                    if sec_user_agent
                    else fetch_sec_filings(t, days_back=days_back, max_items=60)
                )
                if debug:
                    print(f"[news] sec {t}: {len(got)}")
                items.extend(got)
            except Exception as e:
                if debug:
                    print(f"[news] sec {t} ERROR: {e}")

        # Finnhub company news
        if "finnhub" in enable_sources:
            try:
                got = fetch_finnhub_company_news(t, days_back=days_back, max_items=200)
                if debug:
                    print(f"[news] finnhub {t}: {len(got)}")
                items.extend(got)
            except Exception as e:
                if debug:
                    print(f"[news] finnhub {t} ERROR: {e}")

        # Finnhub news-sentiment endpoint is often paywalled (403) — we use our proxy instead.
        if debug and "finnhub" in enable_sources:
            print(f"[news] finnhub_sentiment {t}: SKIPPED (use proxy)")

        if "tiingo" in enable_sources:
            try:
                got = fetch_tiingo_news(t, days_back=days_back, max_items=200)
                if debug:
                    print(f"[news] tiingo {t}: {len(got)}")
                items.extend(got)
            except Exception as e:
                if debug:
                    print(f"[news] tiingo {t} ERROR: {e}")

        if "marketaux" in enable_sources:
            try:
                got = fetch_marketaux_news(t, days_back=days_back, max_items=200)
                if debug:
                    print(f"[news] marketaux {t}: {len(got)}")
                items.extend(got)
            except Exception as e:
                if debug:
                    print(f"[news] marketaux {t} ERROR: {e}")

        if "alphavantage" in enable_sources:
            try:
                got = fetch_alphavantage_news(t, days_back=days_back, max_items=200)
                if debug:
                    print(f"[news] alphavantage {t}: {len(got)}")
                items.extend(got)
            except Exception as e:
                if debug:
                    print(f"[news] alphavantage {t} ERROR: {e}")

    # Tag + score
    items = score_and_tag(items)

    # Dedupe
    seen = set()
    deduped: List[NewsItem] = []
    for it in items:
        it.dedupe_key = make_dedupe_key(it.ticker, it.published_at, it.title)
        if it.dedupe_key in seen:
            continue
        seen.add(it.dedupe_key)
        deduped.append(it)

    df = pd.DataFrame([it.to_dict() for it in deduped])
    if df.empty:
        return df

    # Types
    df["published_at"] = df["published_at"].astype(str)
    df["ticker"] = df["ticker"].astype(str).str.upper()
    df["source"] = df["source"].astype(str)
    df["risk_tag"] = df["risk_tag"].astype(str)
    df["impact_score"] = pd.to_numeric(df["impact_score"], errors="coerce").fillna(0).astype(int)

    # Filter to days_back
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    def _keep(iso: str) -> bool:
        try:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt >= cutoff
        except Exception:
            return True

    df = df[df["published_at"].apply(_keep)].copy()
    df = df.sort_values("published_at", ascending=False).reset_index(drop=True)

    if debug:
        counts = df["source"].value_counts().to_dict()
        print(f"[news] unified rows={len(df)} source_counts={counts}")

    return df


def summarize_news_for_scoring(
    df: pd.DataFrame,
    primary: str,
    days_short: int = 7,
    days_long: int = 30,
) -> dict:
    """
    Compact stats used by Balance/Risk bucket.
    """
    if df is None or df.empty:
        return {
            "neg_7d": 0,
            "neg_30d": 0,
            "shock_7d": 0,
            "tag_counts_30d": {},
            "top_negative_titles_7d": [],
        }

    primary = primary.upper()
    dfp = df[df["ticker"].str.upper() == primary].copy()
    if dfp.empty:
        return {
            "neg_7d": 0,
            "neg_30d": 0,
            "shock_7d": 0,
            "tag_counts_30d": {},
            "top_negative_titles_7d": [],
        }

    now = datetime.now(timezone.utc)

    def _age_days(iso: str) -> float:
        try:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (now - dt).total_seconds() / 86400.0
        except Exception:
            return 9999.0

    dfp["age_days"] = dfp["published_at"].apply(_age_days)

    d7 = dfp[dfp["age_days"] <= days_short]
    d30 = dfp[dfp["age_days"] <= days_long]

    neg_7d = int((d7["impact_score"] < 0).sum())
    neg_30d = int((d30["impact_score"] < 0).sum())
    shock_7d = int(d7.loc[d7["impact_score"] < 0, "impact_score"].sum())

    tag_counts = (
        d30[d30["impact_score"] < 0]
        .groupby("risk_tag")["impact_score"]
        .count()
        .sort_values(ascending=False)
        .to_dict()
    )

    top_neg_titles = (
        d7[d7["impact_score"] < 0]
        .head(8)[["published_at", "risk_tag", "impact_score", "title", "source", "url"]]
        .to_dict(orient="records")
    )

    return {
        "neg_7d": neg_7d,
        "neg_30d": neg_30d,
        "shock_7d": shock_7d,
        "tag_counts_30d": tag_counts,
        "top_negative_titles_7d": top_neg_titles,
    }
