#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd
from docx import Document

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
EXPORT = ROOT / "export"
PROCESSED = ROOT / "data" / "processed"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, float) and pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None


def _fmt_num(x: Any, digits: int = 2) -> str:
    v = _safe_float(x)
    if v is None:
        return "N/A"
    return f"{v:.{digits}f}"


def _fmt_pct(x: Any, digits: int = 2) -> str:
    v = _safe_float(x)
    if v is None:
        return "N/A"
    return f"{v:.{digits}f}%"


def _fmt_money(x: Any) -> str:
    v = _safe_float(x)
    if v is None:
        return "N/A"
    av = abs(v)
    if av >= 1e12:
        return f"${v / 1e12:.2f}T"
    if av >= 1e9:
        return f"${v / 1e9:.2f}B"
    if av >= 1e6:
        return f"${v / 1e6:.2f}M"
    return f"${v:,.0f}"


def _safe_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _rank_percentile(series: pd.Series, value: Optional[float], higher_is_better: bool = True) -> Optional[float]:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0 or value is None:
        return None
    pct = (s <= value).mean() * 100.0
    return pct if higher_is_better else 100.0 - pct


def _cash_points(fcf_ttm: Optional[float]) -> Tuple[float, str]:
    if fcf_ttm is None:
        return 0.0, "FCF TTM missing"
    if fcf_ttm >= 12e9:
        return 25.0, "FCF TTM >= 12B"
    if fcf_ttm >= 8e9:
        return 21.0, "FCF TTM >= 8B"
    if fcf_ttm >= 4e9:
        return 15.0, "FCF TTM >= 4B"
    if fcf_ttm >= 1e9:
        return 8.0, "FCF TTM >= 1B"
    return 3.0, "FCF TTM < 1B"


def _valuation_points(fcf_yield: Optional[float], rank_fcf_yield: Optional[float]) -> Tuple[float, str]:
    pts = 0.0
    parts = []
    if fcf_yield is None:
        parts.append("absolute leg: missing")
    elif fcf_yield >= 0.08:
        pts += 10
        parts.append("absolute leg: +10 (fcf_yield >= 8%)")
    elif fcf_yield >= 0.06:
        pts += 8
        parts.append("absolute leg: +8 (fcf_yield >= 6%)")
    elif fcf_yield >= 0.04:
        pts += 5
        parts.append("absolute leg: +5 (fcf_yield >= 4%)")
    elif fcf_yield >= 0.025:
        pts += 3
        parts.append("absolute leg: +3 (fcf_yield >= 2.5%)")
    else:
        pts += 1
        parts.append("absolute leg: +1 (fcf_yield < 2.5%)")

    if rank_fcf_yield is not None:
        if rank_fcf_yield >= 75:
            pts += 10
            parts.append("relative leg: +10 (rank >= 75)")
        elif rank_fcf_yield >= 50:
            pts += 7
            parts.append("relative leg: +7 (rank >= 50)")
        elif rank_fcf_yield >= 25:
            pts += 4
            parts.append("relative leg: +4 (rank >= 25)")
        else:
            pts += 2
            parts.append("relative leg: +2 (rank < 25)")
    else:
        parts.append("relative leg: missing")

    pts = max(0.0, min(20.0, pts))
    return pts, "; ".join(parts)


def _growth_points(
    rev_yoy: Optional[float],
    fcf_yoy: Optional[float],
    rank_rev_yoy: Optional[float],
    rank_fcf_yoy: Optional[float],
) -> Tuple[float, str]:
    g = 0.0
    parts = []

    if rev_yoy is not None:
        if rev_yoy >= 20:
            g += 6
            parts.append("rev_yoy: +6")
        elif rev_yoy >= 10:
            g += 4
            parts.append("rev_yoy: +4")
        elif rev_yoy >= 5:
            g += 2
            parts.append("rev_yoy: +2")
        elif rev_yoy < 0:
            g -= 3
            parts.append("rev_yoy: -3")
    else:
        parts.append("rev_yoy: missing")

    if fcf_yoy is not None:
        if fcf_yoy >= 40:
            g += 6
            parts.append("fcf_yoy: +6")
        elif fcf_yoy >= 15:
            g += 4
            parts.append("fcf_yoy: +4")
        elif fcf_yoy >= 5:
            g += 2
            parts.append("fcf_yoy: +2")
        elif fcf_yoy < 0:
            g -= 5
            parts.append("fcf_yoy: -5")
    else:
        parts.append("fcf_yoy: missing")

    if rank_rev_yoy is not None:
        g += 4 if rank_rev_yoy >= 75 else 3 if rank_rev_yoy >= 50 else 2 if rank_rev_yoy >= 25 else 1
        parts.append("rev rank leg applied")
    else:
        parts.append("rev rank leg missing")

    if rank_fcf_yoy is not None:
        g += 4 if rank_fcf_yoy >= 75 else 3 if rank_fcf_yoy >= 50 else 2 if rank_fcf_yoy >= 25 else 1
        parts.append("fcf rank leg applied")
    else:
        parts.append("fcf rank leg missing")

    g = max(0.0, min(20.0, g))
    return g, "; ".join(parts)


def _quality_points(margin: Optional[float], rank_margin: Optional[float]) -> Tuple[float, str]:
    q = 0.0
    parts = []
    if margin is not None:
        if margin >= 18:
            q += 9
            parts.append("margin leg: +9")
        elif margin >= 12:
            q += 7
            parts.append("margin leg: +7")
        elif margin >= 8:
            q += 5
            parts.append("margin leg: +5")
        elif margin >= 4:
            q += 3
            parts.append("margin leg: +3")
        else:
            q += 1
            parts.append("margin leg: +1")
    else:
        parts.append("margin leg: missing")

    if rank_margin is not None:
        q += 6 if rank_margin >= 75 else 4 if rank_margin >= 50 else 3 if rank_margin >= 25 else 2
        parts.append("rank leg applied")
    else:
        parts.append("rank leg missing")

    q = max(0.0, min(15.0, q))
    return q, "; ".join(parts)


def _balance_risk_points(
    nd_fcf: Optional[float],
    neg_7d: int,
    shock_7d: int,
    core_hits_30d: int,
    proxy_score_7d: Optional[float],
) -> Tuple[float, str]:
    b = 20.0
    parts = ["start at 20"]

    if nd_fcf is not None:
        if nd_fcf >= 3.0:
            b -= 8
            parts.append("-8 debt penalty (nd_fcf >= 3.0)")
        elif nd_fcf >= 1.5:
            b -= 4
            parts.append("-4 debt penalty (nd_fcf >= 1.5)")
    else:
        b -= 2
        parts.append("-2 debt penalty (missing)")

    if neg_7d >= 6:
        b -= 8
        parts.append("-8 news neg penalty (neg_7d >= 6)")
    elif neg_7d >= 3:
        b -= 5
        parts.append("-5 news neg penalty (neg_7d >= 3)")
    elif neg_7d >= 1:
        b -= 2
        parts.append("-2 news neg penalty (neg_7d >= 1)")

    if shock_7d <= -10:
        b -= 4
        parts.append("-4 shock penalty (shock_7d <= -10)")
    elif shock_7d <= -6:
        b -= 2
        parts.append("-2 shock penalty (shock_7d <= -6)")

    if core_hits_30d >= 6:
        b -= 4
        parts.append("-4 core-risk frequency penalty (>= 6)")
    elif core_hits_30d >= 3:
        b -= 2
        parts.append("-2 core-risk frequency penalty (>= 3)")

    if proxy_score_7d is not None:
        if proxy_score_7d <= 25:
            b -= 4
            parts.append("-4 proxy penalty (proxy_score_7d <= 25)")
        elif proxy_score_7d <= 35:
            b -= 2
            parts.append("-2 proxy penalty (proxy_score_7d <= 35)")
        elif proxy_score_7d >= 70:
            b += 1
            parts.append("+1 proxy bonus (proxy_score_7d >= 70)")

    b = max(0.0, min(20.0, b))
    return b, "; ".join(parts)


def _summary_for_ticker(ticker: str) -> Dict[str, Any]:
    scoped = _safe_json(OUTPUTS / f"decision_summary_{ticker}.json")
    if scoped:
        return scoped
    base = _safe_json(OUTPUTS / "decision_summary.json")
    if str(base.get("ticker", "")).upper() == ticker:
        return base
    return base


def _row_for_ticker(path: Path, ticker_col: str, ticker: str) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        df = pd.read_csv(path)
        if ticker_col not in df.columns:
            return {}
        df[ticker_col] = df[ticker_col].astype(str).str.upper()
        m = df[df[ticker_col] == ticker]
        if m.empty:
            return {}
        return m.iloc[0].to_dict()
    except Exception:
        return {}


def _build_markdown(ticker: str) -> str:
    summary = _summary_for_ticker(ticker)
    comps_path = PROCESSED / "comps_snapshot.csv"
    comps = pd.read_csv(comps_path) if comps_path.exists() else pd.DataFrame()
    if not comps.empty and "ticker" in comps.columns:
        comps["ticker"] = comps["ticker"].astype(str).str.upper()

    row = comps[comps["ticker"] == ticker].iloc[0].to_dict() if (not comps.empty and (comps["ticker"] == ticker).any()) else {}
    news_proxy = _row_for_ticker(PROCESSED / "news_sentiment_proxy.csv", "ticker", ticker)
    risk_df = pd.read_csv(PROCESSED / "news_risk_dashboard.csv") if (PROCESSED / "news_risk_dashboard.csv").exists() else pd.DataFrame()

    fcf_ttm = _safe_float(row.get("fcf_ttm"))
    fcf_yield = _safe_float(row.get("fcf_yield"))
    rev_yoy = _safe_float(row.get("revenue_ttm_yoy_pct"))
    fcf_yoy = _safe_float(row.get("fcf_ttm_yoy_pct"))
    margin = _safe_float(row.get("fcf_margin_ttm_pct"))
    nd_fcf = _safe_float(row.get("net_debt_to_fcf_ttm"))

    rank_fcf_yield = _rank_percentile(comps.get("fcf_yield", pd.Series(dtype=float)), fcf_yield, True) if not comps.empty else None
    rank_rev_yoy = _rank_percentile(comps.get("revenue_ttm_yoy_pct", pd.Series(dtype=float)), rev_yoy, True) if not comps.empty else None
    rank_fcf_yoy = _rank_percentile(comps.get("fcf_ttm_yoy_pct", pd.Series(dtype=float)), fcf_yoy, True) if not comps.empty else None
    rank_margin = _rank_percentile(comps.get("fcf_margin_ttm_pct", pd.Series(dtype=float)), margin, True) if not comps.empty else None

    ns = summary.get("news_summary", {}) or {}
    neg_7d = int(ns.get("neg_7d", news_proxy.get("neg_7d", 0) or 0))
    shock_7d = int(ns.get("shock_7d", news_proxy.get("shock_7d", 0) or 0))

    tag_counts = ns.get("tag_counts_30d") or {}
    if not tag_counts and not risk_df.empty:
        d = risk_df.copy()
        if "ticker" in d.columns:
            d["ticker"] = d["ticker"].astype(str).str.upper()
            d = d[d["ticker"] == ticker]
        if "risk_tag" in d.columns and "neg_count_30d" in d.columns:
            tag_counts = {str(r["risk_tag"]).upper(): int(r["neg_count_30d"]) for _, r in d.iterrows()}

    core_hits = int(tag_counts.get("LABOR", 0)) + int(tag_counts.get("INSURANCE", 0)) + int(tag_counts.get("REGULATORY", 0))
    proxy_score_7d = _safe_float(news_proxy.get("proxy_score_7d"))

    cash_pts, cash_explain = _cash_points(fcf_ttm)
    val_pts, val_explain = _valuation_points(fcf_yield, rank_fcf_yield)
    growth_pts, growth_explain = _growth_points(rev_yoy, fcf_yoy, rank_rev_yoy, rank_fcf_yoy)
    qual_pts, qual_explain = _quality_points(margin, rank_margin)
    br_pts, br_explain = _balance_risk_points(nd_fcf, neg_7d, shock_7d, core_hits, proxy_score_7d)

    reconstructed = int(round(max(0.0, min(100.0, cash_pts + val_pts + growth_pts + qual_pts + br_pts))))
    model_score = summary.get("score")
    model_rating = summary.get("rating")
    bucket_scores = summary.get("bucket_scores") or {}

    lines = []
    lines.append(f"# Calculation Methodology — {ticker}")
    lines.append(f"*Generated: {utc_now()}*")
    lines.append("")
    lines.append("## Purpose")
    lines.append("This document explains how the engine calculates metrics, bucket scores, and the final rating.")
    lines.append("Implementation reference: `scripts/run_arc_reactor_update.py`.")
    lines.append("")
    lines.append("## Data Inputs")
    lines.append("- `data/processed/fundamentals_annual_history.csv`")
    lines.append("- `data/processed/comps_snapshot.csv`")
    lines.append("- `data/processed/news_sentiment_proxy.csv`")
    lines.append("- `data/processed/news_risk_dashboard.csv`")
    lines.append("- `outputs/decision_summary.json` or `outputs/decision_summary_<T>.json`")
    lines.append("")
    lines.append("## Derived Metric Formulas")
    lines.append("- `capex_spend = abs(capitalExpenditure)`")
    lines.append("- `free_cash_flow = operating_cash_flow - capex_spend`")
    lines.append("- `revenue_ttm = rolling_4q_sum(revenue)`")
    lines.append("- `fcf_ttm = rolling_4q_sum(free_cash_flow)`")
    lines.append("- `fcf_margin_ttm_pct = (fcf_ttm / revenue_ttm) * 100`")
    lines.append("- `revenue_ttm_yoy_pct = pct_change_4q(revenue_ttm) * 100`")
    lines.append("- `fcf_ttm_yoy_pct = pct_change_4q(fcf_ttm) * 100`")
    lines.append("- `net_debt = debt - cash`")
    lines.append("- `fcf_yield = fcf_ttm / market_cap`")
    lines.append("- `net_debt_to_fcf_ttm = net_debt / fcf_ttm` (only if `fcf_ttm > 0`)")
    lines.append("- `rank_percentile(metric) = mean(peer_values <= company_value) * 100`")
    lines.append("")
    lines.append("## Score Construction (0-100)")
    lines.append("- `score = clamp(cash_level + valuation + growth + quality + balance_risk, 0, 100)`")
    lines.append("- Rating bands: `BUY` if score >= 80, `HOLD` if score >= 65, else `AVOID`.")
    lines.append("")
    lines.append("### Bucket Rules")
    lines.append("- Cash Level (max 25): thresholded by `fcf_ttm` (>=12B, >=8B, >=4B, >=1B, else low).")
    lines.append("- Valuation (max 20): absolute `fcf_yield` points + relative peer-rank points.")
    lines.append("- Growth (max 20): revenue YoY leg + FCF YoY leg + two peer-rank legs.")
    lines.append("- Quality (max 15): FCF margin leg + peer-rank leg.")
    lines.append("- Balance/Risk (max 20): starts at 20 then subtracts debt/news/shock/core-risk penalties, with proxy-score adjustment.")
    lines.append("")
    lines.append("## Worked Example (Current Run)")
    lines.append(f"- Model score/rating: **{model_score if model_score is not None else 'N/A'} / {model_rating or 'N/A'}**")
    lines.append(f"- Reconstructed score from current inputs: **{reconstructed}**")
    lines.append("")
    lines.append("### Inputs Used")
    lines.append(f"- FCF TTM: { _fmt_money(fcf_ttm) }")
    lines.append(f"- FCF Yield: { _fmt_pct(_safe_float(fcf_yield) * 100 if fcf_yield is not None else None) }")
    lines.append(f"- Revenue YoY: { _fmt_pct(rev_yoy) }")
    lines.append(f"- FCF YoY: { _fmt_pct(fcf_yoy) }")
    lines.append(f"- FCF Margin TTM: { _fmt_pct(margin) }")
    lines.append(f"- Net Debt / FCF: { _fmt_num(nd_fcf) }")
    lines.append(f"- Peer rank (FCF Yield): { _fmt_pct(rank_fcf_yield) }")
    lines.append(f"- Peer rank (Revenue YoY): { _fmt_pct(rank_rev_yoy) }")
    lines.append(f"- Peer rank (FCF YoY): { _fmt_pct(rank_fcf_yoy) }")
    lines.append(f"- Peer rank (FCF Margin): { _fmt_pct(rank_margin) }")
    lines.append(f"- News neg 7d: {neg_7d}")
    lines.append(f"- News shock 7d: {shock_7d}")
    lines.append(f"- Core risk hits 30d (LABOR+INSURANCE+REGULATORY): {core_hits}")
    lines.append(f"- Proxy score 7d: { _fmt_num(proxy_score_7d) }")
    lines.append("")
    lines.append("### Bucket Contributions (Reconstructed)")
    lines.append(f"- Cash Level: **{int(round(cash_pts))}** | {cash_explain}")
    lines.append(f"- Valuation: **{int(round(val_pts))}** | {val_explain}")
    lines.append(f"- Growth: **{int(round(growth_pts))}** | {growth_explain}")
    lines.append(f"- Quality: **{int(round(qual_pts))}** | {qual_explain}")
    lines.append(f"- Balance/Risk: **{int(round(br_pts))}** | {br_explain}")
    lines.append("")
    lines.append("### Bucket Contributions (From Engine Output)")
    if bucket_scores:
        for k, v in bucket_scores.items():
            lines.append(f"- {k}: **{v}**")
    else:
        lines.append("- Not available in current summary payload.")
    lines.append("")
    lines.append("## Notes")
    lines.append("- If reconstructed score and model score differ, the run may have mixed ticker-scoped vs shared summary files.")
    lines.append("- This document is generated from current output files and mirrors current scoring logic.")
    lines.append("")
    return "\n".join(lines) + "\n"


def _write_docx_from_md(md_text: str, out_path: Path) -> None:
    doc = Document()
    for line in md_text.splitlines():
        doc.add_paragraph(line)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))


def main(ticker: str) -> None:
    t = ticker.upper().strip()
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    EXPORT.mkdir(parents=True, exist_ok=True)

    md_text = _build_markdown(t)
    md_path = OUTPUTS / f"{t}_Calculation_Methodology.md"
    docx_path = EXPORT / f"{t}_Calculation_Methodology.docx"

    md_path.write_text(md_text, encoding="utf-8")
    _write_docx_from_md(md_text, docx_path)

    print("DONE ✅ Calculation methodology created:")
    print(f"- {md_path}")
    print(f"- {docx_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)
