#!/usr/bin/env python3
from __future__ import annotations



import sys
from pathlib import Path as _Path
_REPO_ROOT = _Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pandas as pd

from analytics.news.source_weights import weight_for_source
from analytics.news.confirmation import confirmed_risk_tags

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _load_config():
    cfg_path = ROOT / "config" / "run_config.json"
    if cfg_path.exists():
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    return {}

def _read_news_unified() -> pd.DataFrame:
    p = PROCESSED / "news_unified.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p)
    return df

def _tactical_signal(df: pd.DataFrame, ticker: str) -> dict:
    """
    Fast layer: detect abnormal short-term negativity. Lightweight & cheap.
    Uses the existing proxy file if present; otherwise uses simple headline counts.
    """
    proxy_path = PROCESSED / "news_sentiment_proxy.csv"
    tactical = {"ticker": ticker, "shock_7d": None, "neg_7d": None, "articles_7d": None, "tactical_alert": False}

    if proxy_path.exists():
        px = pd.read_csv(proxy_path)
        r = px[px["ticker"].astype(str).str.upper() == ticker.upper()]
        if not r.empty:
            row = r.iloc[0].to_dict()
            tactical["shock_7d"] = row.get("shock_7d")
            tactical["neg_7d"] = row.get("neg_7d")
            tactical["articles_7d"] = row.get("articles_7d")
            try:
                tactical["tactical_alert"] = float(row.get("shock_7d", 0)) <= -20
            except Exception:
                tactical["tactical_alert"] = False
            return tactical

    # fallback: naive last-7d counts
    if df.empty or "published_at" not in df.columns:
        return tactical

    dfx = df[df["ticker"].astype(str).str.upper() == ticker.upper()].copy()
    if dfx.empty:
        return tactical

    dfx["published_at"] = pd.to_datetime(dfx["published_at"], errors="coerce", utc=True)
    since = datetime.now(timezone.utc) - timedelta(days=7)
    d7 = dfx[dfx["published_at"] >= since]
    tactical["articles_7d"] = int(len(d7))
    tactical["neg_7d"] = int((d7.get("impact_score", 0).fillna(0) < 0).sum()) if "impact_score" in d7.columns else None
    # Tactical alert if lots of negatives (fallback rule)
    if tactical["neg_7d"] is not None and tactical["neg_7d"] >= 8:
        tactical["tactical_alert"] = True
    return tactical

def _institutional_confirm(df: pd.DataFrame, ticker: str, min_confirmations: int, cred_th: float) -> dict:
    if df.empty:
        return {"confirmed_tags": {}, "confirmed_any": False}

    dfx = df[df["ticker"].astype(str).str.upper() == ticker.upper()].copy()
    if dfx.empty:
        return {"confirmed_tags": {}, "confirmed_any": False}

    # convert to list of dicts for the confirmation function
    rows = dfx.to_dict(orient="records")
    conf = confirmed_risk_tags(rows, min_confirmations=min_confirmations, credibility_threshold=cred_th)
    return {"confirmed_tags": conf, "confirmed_any": bool(conf)}

def _source_mix(df: pd.DataFrame, ticker: str) -> dict:
    if df.empty:
        return {"top_source": None, "source_share_top": None, "source_diversity": 0, "cred_weighted_avg": None}

    dfx = df[df["ticker"].astype(str).str.upper() == ticker.upper()].copy()
    if dfx.empty or "source" not in dfx.columns:
        return {"top_source": None, "source_share_top": None, "source_diversity": 0, "cred_weighted_avg": None}

    counts = dfx["source"].fillna("unknown").astype(str).str.lower().value_counts()
    top_source = counts.index[0] if len(counts) else None
    total = int(counts.sum()) if len(counts) else 0
    top_share = float(counts.iloc[0] / total) if total else None
    diversity = int(len(counts))

    # credibility weighted average
    w = dfx["source"].fillna("unknown").astype(str).str.lower().map(weight_for_source)
    cred_avg = float(w.mean()) if len(w) else None

    return {"top_source": top_source, "source_share_top": top_share, "source_diversity": diversity, "cred_weighted_avg": cred_avg}

def main(ticker: str, mode: str):
    cfg = _load_config()
    trust = cfg.get("trust") or {}
    min_conf = int(trust.get("min_confirmations", 2))
    cred_th = float(trust.get("credibility_threshold", 1.5))

    df = _read_news_unified()

    tactical = _tactical_signal(df, ticker)
    inst = _institutional_confirm(df, ticker, min_conf, cred_th)
    mix = _source_mix(df, ticker)

    hybrid = {
        "as_of": _utc_now_iso(),
        "mode": mode,
        "ticker": ticker.upper(),
        "tactical": tactical,
        "institutional": inst,
        "source_mix": mix,
        "hybrid_escalate": bool(tactical.get("tactical_alert")) and bool(inst.get("confirmed_any"))
    }

    out = OUTPUTS / f"hybrid_signals_{ticker.upper()}.json"
    out.write_text(json.dumps(hybrid, indent=2), encoding="utf-8")
    print(f"DONE ✅ hybrid signals: {out}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="AAPL")
    ap.add_argument("--mode", default="hybrid")
    args = ap.parse_args()
    main(args.ticker, args.mode)
