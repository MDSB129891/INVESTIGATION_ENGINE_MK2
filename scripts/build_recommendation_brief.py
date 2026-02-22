#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
DATA = ROOT / "data" / "processed"


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print("DONE ✅ wrote:", path)


def _safe_float(v):
    try:
        return float(v)
    except Exception:
        return None


def _fmt_usd(v):
    x = _safe_float(v)
    if x is None:
        return "N/A"
    a = abs(x)
    if a >= 1e12:
        return f"${x / 1e12:.2f}T"
    if a >= 1e9:
        return f"${x / 1e9:.2f}B"
    if a >= 1e6:
        return f"${x / 1e6:.2f}M"
    if a >= 1e3:
        return f"${x / 1e3:.2f}K"
    return f"${x:,.2f}"


def _fmt_pct(v):
    x = _safe_float(v)
    if x is None:
        return "N/A"
    return f"{x:.2f}%"


def _load_snapshot_row(ticker: str) -> Dict[str, Any]:
    import csv

    path = DATA / "comps_snapshot.csv"
    if not path.exists():
        return {}
    t = ticker.upper().strip()
    try:
        with path.open("r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return {}
    for row in rows:
        tk = str(row.get("ticker") or row.get("symbol") or "").upper().strip()
        if tk == t:
            return row
    return {}


def _signal_label(value, mode: str) -> str:
    x = _safe_float(value)
    if x is None:
        return "Unknown"
    if mode == "growth":
        if x >= 12:
            return "Strong"
        if x >= 4:
            return "Mixed"
        return "Weak"
    if mode == "fcf_margin":
        if x >= 12:
            return "Strong"
        if x >= 5:
            return "Mixed"
        return "Weak"
    if mode == "risk_shock":
        if x >= 20:
            return "Calm"
        if x >= 0:
            return "Mixed"
        return "Stressed"
    return "Unknown"


def _build_payload(ticker: str, thesis: str) -> dict:
    t = ticker.upper().strip()
    legion = _read_json(OUT / f"iron_legion_command_{t}.json", _read_json(OUT / "iron_legion_command.json", {}))
    focus = (legion or {}).get("focus", {}) if isinstance(legion, dict) else {}
    summary = _read_json(OUT / f"decision_summary_{t}.json", {})

    action = str(focus.get("action") or "UNKNOWN")
    conviction = float(focus.get("conviction_score") or summary.get("score") or 50.0)
    reliability_grade = str(focus.get("reliability_grade") or "—")
    reliability_score = float(focus.get("reliability_score") or 0.0)
    raw_conviction = float(focus.get("conviction_raw_score") or conviction)
    penalty = float(focus.get("conviction_penalty") or 0.0)
    street_simple = str(focus.get("explain_public") or "")
    desk_deep = str(focus.get("explain_pro") or "")
    storm = _read_json(OUT / f"claim_evidence_{t}.json", {})
    storm_results = storm.get("results", []) if isinstance(storm, dict) else []
    storm_pass = sum(1 for r in storm_results if str((r or {}).get("status", "")).upper() == "PASS")
    storm_fail = sum(1 for r in storm_results if str((r or {}).get("status", "")).upper() == "FAIL")
    storm_unknown = sum(1 for r in storm_results if str((r or {}).get("status", "")).upper() == "UNKNOWN")

    summary = _read_json(OUT / f"decision_summary_{t}.json", {})
    news = (summary or {}).get("news_sentiment_proxy", {}) if isinstance(summary, dict) else {}
    news_shock_30d = news.get("shock_30d")
    snapshot = _load_snapshot_row(t)
    price = snapshot.get("price")
    mcap = snapshot.get("market_cap")
    revenue_yoy = snapshot.get("revenue_ttm_yoy_pct")
    fcf_ttm = snapshot.get("fcf_ttm") or snapshot.get("free_cash_flow_ttm")
    fcf_margin = snapshot.get("fcf_margin_ttm_pct")
    net_debt_to_fcf = snapshot.get("net_debt_to_fcf_ttm")

    growth_signal = _signal_label(revenue_yoy, "growth")
    cash_signal = _signal_label(fcf_margin, "fcf_margin")
    risk_signal = _signal_label(news_shock_30d, "risk_shock")

    if action.startswith("DEPLOY"):
        recommendation = "BUY CANDIDATE"
        why = "Model sees favorable conditions, but position sizing rules still apply."
    elif action.startswith("TRACK"):
        recommendation = "WATCHLIST"
        why = "Signal is mixed. Wait for stronger confirmation before deploying capital."
    else:
        recommendation = "DO NOT BUY NOW"
        why = "Signal quality is weak or risk controls are not satisfied yet."

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "ticker": t,
        "thesis": thesis.strip(),
        "recommendation": recommendation,
        "model_action": action,
        "why": why,
        "conviction_score": conviction,
        "conviction_raw_score": raw_conviction,
        "conviction_penalty": penalty,
        "reliability_grade": reliability_grade,
        "reliability_score": reliability_score,
        "street_simple": street_simple,
        "desk_deep": desk_deep,
        "snapshot": {
            "price": price,
            "market_cap": mcap,
            "revenue_ttm_yoy_pct": revenue_yoy,
            "fcf_ttm": fcf_ttm,
            "fcf_margin_ttm_pct": fcf_margin,
            "net_debt_to_fcf_ttm": net_debt_to_fcf,
            "news_shock_30d": news_shock_30d,
        },
        "signals": {
            "growth": growth_signal,
            "cash_quality": cash_signal,
            "risk_temperature": risk_signal,
        },
        "stormbreaker": {
            "pass": storm_pass,
            "fail": storm_fail,
            "unknown": storm_unknown,
        },
    }


def _write_html(payload: dict, path: Path):
    snapshot = payload.get("snapshot", {})
    signals = payload.get("signals", {})
    storm = payload.get("stormbreaker", {})
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Recommendation Brief — {payload['ticker']}</title>
<style>
body{{font-family:ui-sans-serif,system-ui;background:#0f1524;color:#ecf3ff;padding:22px}}
.card{{background:#13203a;border:1px solid #264061;border-radius:12px;padding:14px;margin-bottom:12px}}
</style></head><body>
<div class="card">
  <h2 style="margin:0 0 8px 0;">Recommendation Brief — {payload['ticker']}</h2>
  <div>Generated: {payload['generated_utc']}</div>
</div>
<div class="card">
  <h3 style="margin-top:0;">Thesis</h3>
  <div>{payload['thesis']}</div>
</div>
<div class="card">
  <h3 style="margin-top:0;">Model Recommendation</h3>
  <div><b>{payload['recommendation']}</b></div>
  <div>Action: {payload['model_action']}</div>
  <div>Conviction: {payload['conviction_score']:.1f} (raw {payload['conviction_raw_score']:.1f}, penalty {payload['conviction_penalty']:.1f})</div>
  <div>Reliability: {payload['reliability_grade']} ({payload['reliability_score']:.1f})</div>
  <div style="margin-top:8px;">{payload['why']}</div>
</div>
<div class="card">
  <h3 style="margin-top:0;">Plain-English Summary</h3>
  <div><b>Street-Simple:</b> {payload['street_simple']}</div>
  <div style="margin-top:8px;"><b>Desk-Deep:</b> {payload['desk_deep']}</div>
</div>
<div class="card">
  <h3 style="margin-top:0;">Company Snapshot (What Is Happening Now)</h3>
  <div>Price: <b>{_fmt_usd(snapshot.get('price'))}</b></div>
  <div>Market cap: <b>{_fmt_usd(snapshot.get('market_cap'))}</b></div>
  <div>Sales growth (YoY): <b>{_fmt_pct(snapshot.get('revenue_ttm_yoy_pct'))}</b></div>
  <div>Free cash flow (TTM): <b>{_fmt_usd(snapshot.get('fcf_ttm'))}</b></div>
  <div>FCF margin: <b>{_fmt_pct(snapshot.get('fcf_margin_ttm_pct'))}</b></div>
  <div>Net debt / FCF: <b>{snapshot.get('net_debt_to_fcf_ttm') if snapshot.get('net_debt_to_fcf_ttm') is not None else 'N/A'}</b></div>
  <div>News shock (30d): <b>{snapshot.get('news_shock_30d') if snapshot.get('news_shock_30d') is not None else 'N/A'}</b></div>
</div>
<div class="card">
  <h3 style="margin-top:0;">Quick Health Read (Easy Mode)</h3>
  <div>Growth signal: <b>{signals.get('growth', 'Unknown')}</b></div>
  <div>Cash quality signal: <b>{signals.get('cash_quality', 'Unknown')}</b></div>
  <div>Risk temperature: <b>{signals.get('risk_temperature', 'Unknown')}</b></div>
  <div style="margin-top:8px;">Stormbreaker tests: <b>{storm.get('pass', 0)} pass</b>, <b>{storm.get('fail', 0)} fail</b>, <b>{storm.get('unknown', 0)} unknown</b></div>
</div>
<div class="card">
  <h3 style="margin-top:0;">Aha Mode (Apples-to-Apples Rules)</h3>
  <div><b>Sales growth:</b> Good if >= 12%, Mixed if 4% to < 12%, Weak if < 4%</div>
  <div><b>FCF margin:</b> Good if >= 12%, Mixed if 5% to < 12%, Weak if < 5%</div>
  <div><b>News shock:</b> Calm if >= 20, Mixed if 0 to < 20, Stressed if < 0</div>
  <div style="margin-top:8px;"><b>How to read this:</b> We use the same thresholds for every ticker, so comparisons are fair and understandable.</div>
</div>
</body></html>"""
    _write(path, html)


def _write_pdf(payload: dict, path: Path):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception:
        letter = None
        canvas = None

    lines = [
        f"Recommendation Brief — {payload['ticker']}",
        f"Generated: {payload['generated_utc']}",
        "",
        "Thesis:",
        payload["thesis"],
        "",
        f"Model Recommendation: {payload['recommendation']}",
        f"Action: {payload['model_action']}",
        f"Conviction: {payload['conviction_score']:.1f} (raw {payload['conviction_raw_score']:.1f}, penalty {payload['conviction_penalty']:.1f})",
        f"Reliability: {payload['reliability_grade']} ({payload['reliability_score']:.1f})",
        "",
        f"Why: {payload['why']}",
        "",
        f"Street-Simple: {payload['street_simple']}",
        "",
        f"Desk-Deep: {payload['desk_deep']}",
        "",
        "Company Snapshot:",
        f"- Price: {_fmt_usd(payload.get('snapshot', {}).get('price'))}",
        f"- Market cap: {_fmt_usd(payload.get('snapshot', {}).get('market_cap'))}",
        f"- Sales growth (YoY): {_fmt_pct(payload.get('snapshot', {}).get('revenue_ttm_yoy_pct'))}",
        f"- Free cash flow (TTM): {_fmt_usd(payload.get('snapshot', {}).get('fcf_ttm'))}",
        f"- FCF margin: {_fmt_pct(payload.get('snapshot', {}).get('fcf_margin_ttm_pct'))}",
        f"- News shock (30d): {payload.get('snapshot', {}).get('news_shock_30d')}",
        "",
        "Quick Health Read:",
        f"- Growth signal: {payload.get('signals', {}).get('growth', 'Unknown')}",
        f"- Cash quality signal: {payload.get('signals', {}).get('cash_quality', 'Unknown')}",
        f"- Risk temperature: {payload.get('signals', {}).get('risk_temperature', 'Unknown')}",
        f"- Stormbreaker: {payload.get('stormbreaker', {}).get('pass', 0)} pass / {payload.get('stormbreaker', {}).get('fail', 0)} fail / {payload.get('stormbreaker', {}).get('unknown', 0)} unknown",
        "",
        "Aha Mode (Apples-to-Apples Rules):",
        "- Sales growth: Good if >= 12%, Mixed if 4% to < 12%, Weak if < 4%",
        "- FCF margin: Good if >= 12%, Mixed if 5% to < 12%, Weak if < 5%",
        "- News shock: Calm if >= 20, Mixed if 0 to < 20, Stressed if < 0",
        "- Same thresholds are applied to every ticker for fair comparisons.",
    ]

    if canvas is not None and letter is not None:
        c = canvas.Canvas(str(path), pagesize=letter)
        _, h = letter
        y = h - 50
        for line in lines:
            c.drawString(40, y, str(line)[:120])
            y -= 16
            if y < 40:
                c.showPage()
                y = h - 50
        c.save()
        print("DONE ✅ wrote:", path)
        return

    # Fallback: write a minimal valid PDF without external dependencies.
    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    y = 760
    content = ["BT", "/F1 11 Tf"]
    for line in lines:
        content.append(f"1 0 0 1 40 {y} Tm ({_esc(str(line)[:120])}) Tj")
        y -= 14
        if y < 40:
            break
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", errors="replace")

    objs = []
    objs.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objs.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objs.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\nendobj\n"
    )
    objs.append(f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream\nendobj\n")
    objs.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(pdf))
        pdf.extend(obj)
    xref_pos = len(pdf)
    pdf.extend(f"xref\n0 {len(objs)+1}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode("latin-1"))
    pdf.extend(
        f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("latin-1")
    )
    path.write_bytes(bytes(pdf))
    print("DONE ✅ wrote:", path)


def main(ticker: str, thesis: str):
    payload = _build_payload(ticker, thesis)
    t = payload["ticker"]
    json_path = OUT / f"recommendation_brief_{t}.json"
    html_path = OUT / f"recommendation_brief_{t}.html"
    pdf_path = OUT / f"recommendation_brief_{t}.pdf"

    _write(json_path, json.dumps(payload, indent=2))
    _write_html(payload, html_path)
    _write_pdf(payload, pdf_path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build a simple recommendation brief PDF from ticker + thesis.")
    ap.add_argument("--ticker", required=True, help="Ticker symbol, e.g. GM")
    ap.add_argument("--thesis", required=True, help="Plain-English thesis text")
    args = ap.parse_args()
    main(args.ticker, args.thesis)
