from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
EXPORT = ROOT / "export"
DATA = ROOT / "data" / "processed"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _safe_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _exists(rel: str) -> bool:
    return (ROOT / rel).exists()


def _link(label: str, rel: str) -> str:
    ok = _exists(rel)
    badge = "✅" if ok else "⚠️"
    href = "../" + rel
    return f'<li>{badge} <a href="{href}">{label}</a> <code>{rel}</code></li>'


def build_dashboard(ticker: str) -> Path:
    ticker = ticker.upper().strip()

    summary_path = OUTPUTS / "decision_summary.json"
    summary = _safe_json(summary_path)

    # If decision_summary is for a different ticker, still build dashboard,
    # but warn the user loudly.
    summary_ticker = (summary.get("ticker") or "").upper()
    mismatch = summary_ticker and summary_ticker != ticker

    # Canonical artifacts by ticker
    artifacts = [
        ("Full memo (PDF)", f"export/{ticker}_Full_Investment_Memo.pdf"),
        ("Full memo (DOCX)", f"export/{ticker}_Full_Investment_Memo.docx"),
        ("One-page dashboard (this file)", f"outputs/decision_dashboard_{ticker}.html"),
        ("News Sources tab", f"export/CANON_{ticker}/{ticker}_NEWS_SOURCES.html"),
        ("News evidence (raw links)", f"outputs/news_evidence_{ticker}.html"),
        ("Claim evidence (thesis stress test)", f"outputs/claim_evidence_{ticker}.html"),
        ("Veracity / confidence JSON", f"outputs/veracity_{ticker}.json"),
        ("Alerts (red lines)", f"outputs/alerts_{ticker}.json"),
        ("Hybrid signals JSON", f"outputs/hybrid_signals_{ticker}.json"),
        ("Unified news CSV", "data/processed/news_unified.csv"),
        ("Clean news CSV", "data/processed/news_unified_clean.csv"),
        ("News risk dashboard CSV", "data/processed/news_risk_dashboard.csv"),
        ("Fundamentals annual history CSV", "data/processed/fundamentals_annual_history.csv"),
        ("Fundamentals quarterly CSV", "data/processed/fundamentals_quarterly.csv"),
        ("Comps snapshot CSV", "data/processed/comps_snapshot.csv"),
    ]

    # Pull top-line if available
    score = summary.get("score")
    rating = summary.get("rating")
    red_flags = summary.get("red_flags") or []
    bucket = summary.get("bucket_scores") or {}

    html = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'/>",
        f"<title>Decision Dashboard — {ticker}</title>",
        "<style>",
        "body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;max-width:980px;margin:24px auto;padding:0 12px;}",
        "code{background:#f3f3f3;padding:2px 6px;border-radius:6px;}",
        ".card{border:1px solid #ddd;border-radius:16px;padding:14px 16px;margin:12px 0;}",
        "h1{margin:0 0 6px 0;}",
        ".warn{background:#fff3cd;border:1px solid #ffe69c;}",
        "</style></head><body>",
        f"<h1>📊 Decision Dashboard — {ticker}</h1>",
        f"<p><b>Generated:</b> {utc_now()}</p>",
    ]

    if mismatch:
        html += [
            "<div class='card warn'>",
            "<h2>⚠️ Ticker mismatch warning</h2>",
            f"<p>Your <code>outputs/decision_summary.json</code> says ticker <b>{summary_ticker}</b>, but you asked for <b>{ticker}</b>.</p>",
            "<p>This usually means the engine update step didn’t run for the requested ticker (or wrote over the shared summary).</p>",
            "</div>",
        ]

    html += ["<div class='card'>", "<h2>1) Quick summary</h2>"]
    if rating is not None and score is not None:
        html += [f"<p><b>Model rating:</b> {rating} &nbsp; <b>Score:</b> {score}/100</p>"]
    else:
        html += ["<p><b>Model rating:</b> N/A (missing decision_summary.json)</p>"]

    if bucket:
        html += ["<p><b>Bucket scores:</b></p><ul>"]
        for k, v in bucket.items():
            html += [f"<li>{k}: <b>{v}</b></li>"]
        html += ["</ul>"]

    if red_flags:
        html += ["<p><b>Red flags:</b></p><ul>"]
        for rf in red_flags:
            html += [f"<li>{rf}</li>"]
        html += ["</ul>"]
    else:
        html += ["<p><b>Red flags:</b> none listed</p>"]

    html += ["</div>"]

    html += ["<div class='card'>", "<h2>2) What to open (in order)</h2>",
             "<ol>",
             f"<li><b>Full memo PDF</b> — <code>export/{ticker}_Full_Investment_Memo.pdf</code></li>",
             f"<li><b>Claim evidence</b> — <code>outputs/claim_evidence_{ticker}.html</code></li>",
             f"<li><b>News Sources</b> — <code>export/CANON_{ticker}/{ticker}_NEWS_SOURCES.html</code></li>",
             f"<li><b>News evidence</b> — <code>outputs/news_evidence_{ticker}.html</code></li>",
             "</ol>",
             "</div>"]

    html += ["<div class='card'>", "<h2>3) All artifacts</h2>", "<ul>"]
    html += [_link(label, rel) for (label, rel) in artifacts]
    html += ["</ul></div>"]

    html += ["<div class='card'>", "<h2>3) Plain-English cheat sheet</h2>",
             "<ul>",
             "<li><b>Score</b>: 0–100 summary signal from cash/growth/valuation/quality/risk buckets.</li>",
             "<li><b>News Sources</b>: provider checks + source counts + direct links for verification.</li>",
             "<li><b>Claim evidence</b>: maps each thesis claim to supporting/contradicting headlines.</li>",
             "<li><b>Veracity</b>: checks if evidence is diverse and from higher-trust domains.</li>",
             "</ul>",
             "</div>"]

    html += ["</body></html>"]

    out = OUTPUTS / f"decision_dashboard_{ticker}.html"
    out.write_text("\n".join(html), encoding="utf-8")
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    fp = build_dashboard(args.ticker)
    print(f"DONE ✅ dashboard created: {fp}")
