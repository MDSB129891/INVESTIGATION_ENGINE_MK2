#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
OUT = ROOT / "outputs"
EXPORT = ROOT / "export"

OUT.mkdir(parents=True, exist_ok=True)

TOP_TIER_DEFAULT = {
    "reuters", "bloomberg", "wsj", "wall street journal", "financial times", "ft",
    "sec", "edgar", "cnbc", "the information"
}

def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def read_csv(p: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()

def load_whitelist() -> List[str]:
    p = EXPORT / "source_whitelist.csv"
    if not p.exists():
        return sorted(TOP_TIER_DEFAULT)
    out = []
    with p.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            s = (row.get("source") or "").strip()
            if s:
                out.append(s.lower())
    return out or sorted(TOP_TIER_DEFAULT)

def herfindahl(shares: List[float]) -> float:
    # Concentration index: sum(s^2). Higher = more concentrated.
    return sum((s*s) for s in shares)

def score_confidence(source_counts: Dict[str,int], url_cov: float, whitelist_hit_ratio: float, has_sec: bool, n: int) -> Tuple[int, Dict[str, Any]]:
    # Start base
    score = 50

    # URL coverage (0-1)
    if url_cov >= 0.95: score += 10
    elif url_cov >= 0.80: score += 5
    else: score -= 10

    # Source diversification
    total = max(1, sum(source_counts.values()))
    shares = [c/total for c in source_counts.values()]
    hhi = herfindahl(shares)  # 1.0 if 100% one source
    # Penalize high concentration
    if hhi >= 0.85: score -= 18
    elif hhi >= 0.60: score -= 10
    elif hhi >= 0.40: score -= 4
    else: score += 6

    # Whitelist hit ratio
    if whitelist_hit_ratio >= 0.25: score += 10
    elif whitelist_hit_ratio >= 0.10: score += 6
    elif whitelist_hit_ratio >= 0.03: score += 2
    else: score -= 4

    # SEC presence helps veracity even if not “news”
    if has_sec: score += 6

    # Enough data?
    if n >= 300: score += 4
    elif n >= 100: score += 2
    elif n < 20: score -= 8

    score = max(0, min(100, score))
    details = {"hhi": round(hhi, 3)}
    return score, details

def build_clickpack_html(ticker: str, df: pd.DataFrame, out_path: Path) -> None:
    # Simple, readable HTML with a table of top items
    rows = []
    for _, r in df.iterrows():
        title = str(r.get("title","(no title)"))
        url = str(r.get("url",""))
        src = str(r.get("source",""))
        tag = str(r.get("risk_tag",""))
        impact = r.get("impact_score","")
        published = str(r.get("published_at",""))
        link = f'<a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>' if url and url != "nan" else title
        rows.append(f"""
        <tr>
          <td style="white-space:nowrap;">{published[:10]}</td>
          <td>{link}<div style="font-size:12px;opacity:.75">{src} • {tag} • impact {impact}</div></td>
        </tr>
        """)

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>News Clickpack — {ticker}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Arial; padding: 16px; }}
h1 {{ margin: 0 0 8px 0; }}
p {{ margin: 6px 0 12px 0; opacity: .8; }}
table {{ width: 100%; border-collapse: collapse; }}
td {{ border-bottom: 1px solid #eee; padding: 10px 6px; vertical-align: top; }}
a {{ text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.badge {{ display:inline-block; padding:2px 6px; border-radius:10px; font-size:12px; background:#f3f3f3; }}
</style>
</head>
<body>
<h1>News Clickpack — {ticker}</h1>
<p><span class="badge">Click top negatives first</span> • Generated {utc_now()}</p>
<table>
{''.join(rows)}
</table>
</body>
</html>"""
    out_path.write_text(html, encoding="utf-8")

def main(ticker: str):
    ticker = ticker.upper()
    news = read_csv(DATA / "news_unified.csv")
    if news.empty:
        raise FileNotFoundError("Missing data/processed/news_unified.csv — run run_arc_reactor_update.py first")

    # Filter ticker
    if "ticker" in news.columns:
        news = news[news["ticker"].astype(str).str.upper() == ticker].copy()

    if news.empty:
        raise ValueError(f"No news rows found for {ticker} in news_unified.csv")

    # normalize
    for c in ["source","title","url","risk_tag"]:
        if c not in news.columns:
            news[c] = ""

    # URL coverage
    urls = news["url"].astype(str)
    url_cov = float((urls.str.startswith("http")).mean())

    # Source counts
    source_counts = news["source"].astype(str).str.lower().value_counts().to_dict()

    # whitelist hits (based on source field)
    wl = set(load_whitelist())
    src_series = news["source"].astype(str).str.lower()
    whitelist_hits = float(src_series.isin(wl).mean())

    has_sec = ("sec" in source_counts) and (source_counts.get("sec",0) > 0)

    # Build “must click”: take the most negative by impact_score if present
    if "impact_score" in news.columns:
        n2 = news.copy()
        n2["impact_num"] = pd.to_numeric(n2["impact_score"], errors="coerce")
        n2 = n2.sort_values("impact_num", ascending=True)
        must = n2.head(12)
    else:
        must = news.head(12)

    confidence, details = score_confidence(source_counts, url_cov, whitelist_hits, has_sec, len(news))

    payload = {
        "ticker": ticker,
        "generated_utc": utc_now(),
        "rows": int(len(news)),
        "url_coverage": round(url_cov, 3),
        "source_counts": source_counts,
        "whitelist_hit_ratio": round(whitelist_hits, 3),
        "has_sec": bool(has_sec),
        "confidence_score": int(confidence),
        "confidence_details": details,
        "must_click": [
            {
                "published_at": str(r.get("published_at","")),
                "title": str(r.get("title","")),
                "source": str(r.get("source","")),
                "url": str(r.get("url","")),
                "risk_tag": str(r.get("risk_tag","")),
                "impact_score": r.get("impact_score",""),
            }
            for _, r in must.iterrows()
        ],
    }

    (OUT / f"veracity_{ticker}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Clickpack HTML
    clickpack = OUT / f"news_clickpack_{ticker}.html"
    # Show “must click” first + then rest (optional)
    click_df = pd.concat([must, news]).drop_duplicates(subset=["url","title"], keep="first")
    build_clickpack_html(ticker, click_df.head(250), clickpack)

    print("DONE ✅ Veracity pack created:")
    print(f"- {OUT / f'veracity_{ticker}.json'}")
    print(f"- {clickpack}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default=os.getenv("TICKER", "").strip().upper())
    args = ap.parse_args()
    if not args.ticker:
        raise SystemExit("Missing ticker. Pass --ticker TICKER or set TICKER env var.")
    main(args.ticker)
