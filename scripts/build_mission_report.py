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


def _build_html(payload: dict) -> str:
    ticker = payload["focus_ticker"]
    items = "".join(f"<li>{x}</li>" for x in payload["plain_english_takeaways"])
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Mission Report — {ticker}</title>
<style>body{{font-family:ui-sans-serif,system-ui;background:#0d1320;color:#e6ecfb;padding:24px}}
.card{{background:#121b2b;border:1px solid #243752;border-radius:12px;padding:14px;margin:10px 0}}</style>
</head><body>
<div class="card"><h2>Mission Report — {ticker}</h2>
<div>Generated: {payload["generated_utc"]}</div>
<div>Action: <b>{payload["action"]}</b> · Conviction: <b>{payload["conviction_score"]:.1f}</b> · Reliability: <b>{payload["reliability_grade"]} ({payload["reliability_score"]:.1f})</b></div>
</div>
<div class="card"><h3>Plain-English Takeaways</h3><ul>{items}</ul></div>
<div class="card"><h3>Street-Simple</h3><div>{payload.get("street_simple","")}</div></div>
<div class="card"><h3>Desk-Deep</h3><div>{payload.get("desk_deep","")}</div></div>
<div class="card"><h3>How to interpret this</h3>
<div><b>Action = DEPLOY:</b> model sees a favorable setup, still use position limits.</div>
<div><b>Action = TRACK:</b> setup is mixed; wait for confirmation and monitor triggers.</div>
<div><b>Action = HOLD FIRE:</b> too many weak signals or evidence gaps right now.</div>
</div>
<div class="card"><h3>Files</h3>
<div>HUD: {payload["files"]["hud"]}</div>
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
        "plain_english_takeaways": takeaways,
        "street_simple": focus_block.get("explain_public", ""),
        "desk_deep": focus_block.get("explain_pro", ""),
        "files": {
            "hud": str(ROOT / "export" / f"CANON_{focus}" / f"{focus}_IRONMAN_HUD.html"),
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
            ]
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
