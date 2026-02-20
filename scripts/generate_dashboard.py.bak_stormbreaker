#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
EXP = ROOT / "export"

def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def main(ticker: str):
    ticker = ticker.upper()
    decision = read_json(OUT / "decision_summary.json")
    ver = read_json(OUT / f"veracity_{ticker}.json")
    alerts = read_json(OUT / f"alerts_{ticker}.json")

    clickpack = f"news_clickpack_{ticker}.html"
    memo_md = f"{ticker}_Full_Investment_Memo.md"
    memo_docx = f"{ticker}_Full_Investment_Memo.docx"
    methodology_md = f"{ticker}_Calculation_Methodology.md"
    methodology_docx = f"{ticker}_Calculation_Methodology.docx"

    rating = decision.get("rating","N/A")
    score = decision.get("score","N/A")
    bucket = decision.get("bucket_scores", {})
    confidence = ver.get("confidence_score","N/A")
    must = ver.get("must_click", [])[:6]
    alert_items = (alerts.get("alerts") or [])[:8]

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"/>
<title>Decision Dashboard — {ticker}</title>
<style>
body {{ font-family: -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Arial; padding:16px; max-width: 980px; margin: 0 auto; }}
h1 {{ margin:0; }}
.small {{ opacity:.75; font-size:13px; }}
.card {{ border:1px solid #eee; border-radius:14px; padding:14px; margin: 14px 0; }}
.grid {{ display:grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
.badge {{ display:inline-block; padding:2px 8px; border-radius:999px; background:#f3f3f3; font-size:12px; }}
a {{ text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
ul {{ margin: 8px 0 0 18px; }}
</style>
</head>
<body>
<h1>Decision Dashboard — {ticker}</h1>
<div class="small">Generated {utc_now()}</div>

<div class="card">
  <div class="badge">TL;DR</div>
  <h2 style="margin:10px 0 6px 0;">Model: {rating} (score {score}/100) • Confidence: {confidence}/100</h2>
  <div class="small">Confidence reflects evidence quality (source diversity + URL coverage + whitelist hits).</div>
</div>

<div class="grid">
  <div class="card">
    <div class="badge">Open</div>
    <ul>
      <li><a href="{clickpack}">News Clickpack (verify sources)</a></li>
      <li><a href="{memo_md}">Full Memo (Markdown)</a></li>
      <li><a href="../export/{memo_docx}">Full Memo (Word)</a></li>
      <li><a href="../export/{ticker}_Full_Investment_Memo.pdf">Full Memo (PDF)</a></li>
      <li><a href="{methodology_md}">Calculation Methodology (Markdown)</a></li>
      <li><a href="../export/{methodology_docx}">Calculation Methodology (Word)</a></li>
    </ul>
  </div>

  <div class="card">
    <div class="badge">Bucket scores</div>
    <ul>
      {''.join([f"<li>{k}: {v}</li>" for k,v in bucket.items()]) if bucket else "<li>N/A</li>"}
    </ul>
  </div>
</div>

<div class="card">
  <div class="badge">ALERTS (thesis breakers)</div>
  <ul>
    {''.join([f"<li><b>{a.get('severity')}</b> — {a.get('message')}</li>" for a in alert_items]) if alert_items else "<li>No alerts triggered ✅</li>"}
  </ul>
</div>

<div class="card">
  <div class="badge">Click first (top negatives)</div>
  <ul>
    {''.join([f"<li><a href='{m.get('url','')}' target='_blank' rel='noopener noreferrer'>{m.get('title','(no title)')}</a> <span class='small'>({m.get('source','')}, {m.get('risk_tag','')}, impact {m.get('impact_score','')})</span></li>" for m in must if m.get("url","").startswith("http")]) or "<li>No must-click items</li>"}
  </ul>
</div>

<div class="card">
  <div class="badge">How to use this (novice)</div>
  <ol>
    <li>Read the Word memo top section (Decision Card).</li>
    <li>Click the “Click first” items above to confirm the biggest risks are real.</li>
    <li>If alerts triggered, treat them as “watchlist” conditions — not automatic sell signals.</li>
    <li>If the same risk theme repeats (insurance/regulatory/labor), escalate caution.</li>
  </ol>
</div>

</body></html>
"""
    out_path = OUT / f"decision_dashboard_{ticker}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"DONE ✅ dashboard created: {out_path}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="UBER")
    args = ap.parse_args()
    main(args.ticker)
