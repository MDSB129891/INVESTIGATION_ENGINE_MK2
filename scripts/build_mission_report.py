#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"


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


def _aha_rows(signals: dict) -> list[dict]:
    def zone_high_good(v, good, ok):
        x = _safe_float(v)
        if x is None:
            return "Unknown"
        if x >= good:
            return "Good"
        if x >= ok:
            return "Okay"
        return "Weak"

    def zone_low_good(v, good, ok):
        x = _safe_float(v)
        if x is None:
            return "Unknown"
        if x <= good:
            return "Good"
        if x <= ok:
            return "Okay"
        return "Weak"

    def fmt(v, mode):
        x = _safe_float(v)
        if x is None:
            return "—"
        if mode == "pct":
            return f"{x:.2f}%"
        if mode == "x":
            return f"{x:.2f}x"
        return f"{x:.2f}"

    return [
        {
            "metric": "Sales Growth (YoY)",
            "value": fmt(signals.get("revenue_yoy_pct"), "pct"),
            "zone": zone_high_good(signals.get("revenue_yoy_pct"), 12, 4),
            "rule": "Good >= 12% | Okay 4% to < 12%",
            "meaning": "Demand momentum.",
        },
        {
            "metric": "FCF Margin",
            "value": fmt(signals.get("fcf_margin_ttm_pct"), "pct"),
            "zone": zone_high_good(signals.get("fcf_margin_ttm_pct"), 12, 5),
            "rule": "Good >= 12% | Okay 5% to < 12%",
            "meaning": "Cash efficiency.",
        },
        {
            "metric": "News Shock (30d)",
            "value": fmt(signals.get("news_shock_30d"), "num"),
            "zone": zone_high_good(signals.get("news_shock_30d"), 20, 0),
            "rule": "Good >= 20 | Okay 0 to < 20",
            "meaning": "Lower values mean headline stress.",
        },
        {
            "metric": "Risk Total (30d)",
            "value": fmt(signals.get("risk_total_30d"), "num"),
            "zone": zone_low_good(signals.get("risk_total_30d"), 2, 5),
            "rule": "Good <= 2 | Okay > 2 to 5",
            "meaning": "Counts risk-tag negatives.",
        },
        {
            "metric": "Net Debt / FCF",
            "value": fmt(signals.get("net_debt_to_fcf_ttm"), "x"),
            "zone": zone_low_good(signals.get("net_debt_to_fcf_ttm"), 2, 4),
            "rule": "Good <= 2.0x | Okay > 2.0x to 4.0x",
            "meaning": "Debt load vs cash generation.",
        },
    ]


def _build_html(payload: dict) -> str:
    ticker = payload["focus_ticker"]
    trust_pass = bool(payload.get("trust_pass"))
    trust_badge = "<span class='tone good'>TRUST PASS</span>" if trust_pass else "<span class='tone bad'>TRUST FAIL</span>"
    trust_explain = "All trust gates passed." if trust_pass else "One or more trust gates failed (data quality/conviction/tests/MC)."
    items = "".join(f"<li>{x}</li>" for x in payload["plain_english_takeaways"])
    zone_cls = {"Good": "good", "Okay": "ok", "Weak": "bad", "Unknown": "neutral"}
    aha_html = "".join(
        "<tr>"
        f"<td>{r['metric']}</td>"
        f"<td>{r['value']}</td>"
        f"<td><span class='tone {zone_cls.get(r['zone'], 'neutral')}'>{r['zone']}</span></td>"
        f"<td>{r['rule']}</td>"
        f"<td>{r['meaning']}</td>"
        "</tr>"
        for r in payload.get("aha_mode_rows", [])
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Mission Report — {ticker}</title>
<style>body{{font-family:ui-sans-serif,system-ui;background:#0d1320;color:#e6ecfb;padding:24px}}
.card{{background:#121b2b;border:1px solid #243752;border-radius:12px;padding:14px;margin:10px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #223047;text-align:left;vertical-align:top}}
th{{color:#9db0ce;font-size:12px;text-transform:uppercase}}
.tone{{font-size:11px;border-radius:999px;padding:3px 8px;border:1px solid transparent}}
.tone.good{{color:#23d18b;border-color:rgba(35,209,139,.35);background:rgba(35,209,139,.08)}}
.tone.ok{{color:#f4c267;border-color:rgba(244,194,103,.35);background:rgba(244,194,103,.08)}}
.tone.bad{{color:#ff7b7b;border-color:rgba(255,123,123,.35);background:rgba(255,123,123,.08)}}
.tone.neutral{{color:#9cb1d0;border-color:rgba(156,177,208,.35);background:rgba(156,177,208,.08)}}
</style>
</head><body>
<div class="card"><h2>Mission Report — {ticker}</h2>
<div>Generated: {payload["generated_utc"]}</div>
<div>Action: <b>{payload["action"]}</b> · Conviction: <b>{payload["conviction_score"]:.1f}</b> · Reliability: <b>{payload["reliability_grade"]} ({payload["reliability_score"]:.1f})</b></div>
</div>
<div class="card"><h3>Trust Gate</h3><div>{trust_badge}</div><div style="margin-top:6px">{trust_explain}</div></div>
<div class="card"><h3>Plain-English Takeaways</h3><ul>{items}</ul></div>
<div class="card"><h3>Street-Simple</h3><div>{payload.get("street_simple","")}</div></div>
<div class="card"><h3>Desk-Deep</h3><div>{payload.get("desk_deep","")}</div></div>
<div class="card"><h3>How to interpret this</h3>
<div><b>Action = DEPLOY:</b> model sees a favorable setup, still use position limits.</div>
<div><b>Action = TRACK:</b> setup is mixed; wait for confirmation and monitor triggers.</div>
<div><b>Action = HOLD FIRE:</b> too many weak signals or evidence gaps right now.</div>
</div>
<div class="card"><h3>Aha Mode: Apples-to-Apples Scoreboard</h3>
<div>Same thresholds every run so anyone can compare tickers quickly.</div>
<table><thead><tr><th>Metric</th><th>Your Number</th><th>Zone</th><th>Rule</th><th>What It Means</th></tr></thead>
<tbody>{aha_html}</tbody></table>
</div>
<div class="card"><h3>Files</h3>
<div>HUD: {payload["files"]["hud"]}</div>
<div>News Sources: {payload["files"]["news_sources"]}</div>
<div>Iron Legion: {payload["files"]["iron_legion"]}</div>
<div>Claim Evidence: {payload["files"]["claim_evidence"]}</div>
<div>Receipts: {payload["files"]["receipts"]}</div>
</div>
</body></html>"""


def main(tickers: str):
    tlist = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    focus = tlist[0] if tlist else "UNKNOWN"

    legion = _read_json(OUT / f"iron_legion_command_{focus}.json", _read_json(OUT / "iron_legion_command.json", {}))
    focus_block = (legion or {}).get("focus", {})
    claim = _read_json(OUT / f"claim_evidence_{focus}.json", {})
    results = claim.get("results", []) if isinstance(claim, dict) else []
    fail_n = sum(1 for r in results if str((r or {}).get("status", "")).upper() == "FAIL")
    unk_n = sum(1 for r in results if str((r or {}).get("status", "")).upper() == "UNKNOWN")

    takeaways = [
        f"System action is {focus_block.get('action', 'UNKNOWN')}.",
        f"Conviction is {float(focus_block.get('conviction_score', 50.0)):.1f} out of 100.",
        f"Reliability is {focus_block.get('reliability_grade', '—')} ({float(focus_block.get('reliability_score', 0.0)):.1f}).",
    ]
    if fail_n > 0:
        takeaways.append(f"Stormbreaker has {fail_n} failed thesis checks, so risk controls should stay tighter.")
    if unk_n > 0:
        takeaways.append(f"{unk_n} thesis checks are unknown due to missing evidence; refresh data before aggressive sizing.")
    aha_rows = _aha_rows((focus_block or {}).get("current_signals", {}))

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "focus_ticker": focus,
        "universe": tlist,
        "action": focus_block.get("action", "UNKNOWN"),
        "conviction_score": float(focus_block.get("conviction_score", 50.0)),
        "reliability_score": float(focus_block.get("reliability_score", 0.0)),
        "reliability_grade": focus_block.get("reliability_grade", "—"),
        "conviction_raw_score": float(focus_block.get("conviction_raw_score", focus_block.get("conviction_score", 50.0))),
        "conviction_penalty": float(focus_block.get("conviction_penalty", 0.0)),
        "trust_pass": not bool(focus_block.get("governor_override", False)),
        "plain_english_takeaways": takeaways,
        "aha_mode_rows": aha_rows,
        "street_simple": focus_block.get("explain_public", ""),
        "desk_deep": focus_block.get("explain_pro", ""),
        "files": {
            "hud": str(ROOT / "export" / f"CANON_{focus}" / f"{focus}_IRONMAN_HUD.html"),
            "news_sources": str(ROOT / "export" / f"CANON_{focus}" / f"{focus}_NEWS_SOURCES.html"),
            "iron_legion": str(OUT / f"iron_legion_command_{focus}.html"),
            "claim_evidence": str(OUT / f"claim_evidence_{focus}.html"),
            "receipts": str(OUT / f"receipts_{focus}.html"),
        },
    }

    focus_json = OUT / f"mission_report_{focus}.json"
    focus_html = OUT / f"mission_report_{focus}.html"
    shared_json = OUT / "mission_report.json"
    shared_html = OUT / "mission_report.html"
    focus_pdf = OUT / f"mission_report_{focus}.pdf"
    shared_pdf = OUT / "mission_report.pdf"

    _write(focus_json, json.dumps(payload, indent=2))
    _write(shared_json, json.dumps(payload, indent=2))
    html = _build_html(payload)
    _write(focus_html, html)
    _write(shared_html, html)

    # Try real PDF export via reportlab; fallback to placeholder text if unavailable.
    pdf_ok = False
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        def _render_pdf(path: Path):
            c = canvas.Canvas(str(path), pagesize=letter)
            w, h = letter
            y = h - 50
            lines = [
                f"Mission Report — {focus}",
                f"Generated: {payload['generated_utc']}",
                f"Action: {payload['action']}",
                f"Conviction: {payload['conviction_score']:.1f}",
                f"Reliability: {payload['reliability_grade']} ({payload['reliability_score']:.1f})",
                "",
                "Plain-English Takeaways:",
            ] + [f"- {x}" for x in payload["plain_english_takeaways"]] + [
                "",
                f"Street-Simple: {payload.get('street_simple','')}",
                "",
                f"Desk-Deep: {payload.get('desk_deep','')}",
                "",
                "Aha Mode (same thresholds for every ticker):",
            ]
            for r in payload.get("aha_mode_rows", []):
                lines.append(f"- {r['metric']}: {r['value']} | {r['zone']} | {r['rule']}")
            for line in lines:
                c.drawString(40, y, str(line)[:120])
                y -= 16
                if y < 40:
                    c.showPage()
                    y = h - 50
            c.save()

        _render_pdf(focus_pdf)
        _render_pdf(shared_pdf)
        pdf_ok = True
    except Exception:
        pass

    if not pdf_ok:
        _write(focus_pdf, "Mission Report PDF placeholder. Open the HTML version for full content.")
        _write(shared_pdf, "Mission Report PDF placeholder. Open the HTML version for full content.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True, help="Comma-separated ticker universe; first one is focus")
    args = ap.parse_args()
    main(args.tickers)
