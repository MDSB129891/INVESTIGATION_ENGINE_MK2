#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main(ticker: str):
    t = ticker.upper()
    out = ROOT / "outputs"
    ds = _read(out / f"decision_summary_{t}.json")
    buckets = ds.get("bucket_scores") or {}
    max_map = {"cash_level": 25, "valuation": 20, "growth": 20, "quality": 15, "balance_risk": 20}
    contrib = []
    for k, m in max_map.items():
        v = float(buckets.get(k, 0.0) or 0.0)
        pct = round((v / m) * 100.0, 1) if m else 0.0
        contrib.append({"bucket": k, "score": v, "max": m, "strength_pct": pct})
    contrib.sort(key=lambda x: x["score"], reverse=True)
    payload = {
        "ticker": t,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "top_positive": contrib[:3],
        "top_negative": sorted(contrib, key=lambda x: x["strength_pct"])[:3],
        "plain_english": "This panel shows what pushed the score up and what dragged it down.",
    }
    j = out / f"explainability_overlay_{t}.json"
    h = out / f"explainability_overlay_{t}.html"
    j.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    pos_rows = "".join(
        f"<tr><td>{r['bucket'].replace('_',' ').title()}</td><td>{r['score']:.1f} / {r['max']}</td><td>{r['strength_pct']:.1f}%</td></tr>"
        for r in payload["top_positive"]
    ) or "<tr><td colspan='3'>No positive drivers found.</td></tr>"
    neg_rows = "".join(
        f"<tr><td>{r['bucket'].replace('_',' ').title()}</td><td>{r['score']:.1f} / {r['max']}</td><td>{r['strength_pct']:.1f}%</td></tr>"
        for r in payload["top_negative"]
    ) or "<tr><td colspan='3'>No weak drivers found.</td></tr>"
    html = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>Vision Explainability Overlay — {t}</title>
<style>
body{{font-family:ui-sans-serif,system-ui;background:#0f1525;color:#ecf3ff;padding:20px}}
.card{{background:#131f35;border:1px solid #264061;border-radius:12px;padding:14px;margin:10px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{border-bottom:1px solid #243a59;padding:8px;text-align:left}}
th{{color:#9db6da;font-size:12px;text-transform:uppercase}}
</style></head><body>
<div class='card'><h2 style='margin:0 0 8px 0'>Vision Explainability Overlay — {t}</h2>
<div>Generated: {payload['generated_utc']}</div></div>
<div class='card'><h3 style='margin-top:0'>Why this score happened (plain English)</h3>
<div>{payload['plain_english']}</div>
<div style='margin-top:8px'>Think of the model like five levers. Some levers added points, others removed points.</div></div>
<div class='card'><h3 style='margin-top:0'>Top Score Drivers</h3>
<table><thead><tr><th>Driver</th><th>Points</th><th>Strength</th></tr></thead><tbody>{pos_rows}</tbody></table></div>
<div class='card'><h3 style='margin-top:0'>Top Drags</h3>
<table><thead><tr><th>Drag</th><th>Points</th><th>Strength</th></tr></thead><tbody>{neg_rows}</tbody></table></div>
<div class='card'><h3 style='margin-top:0'>How to use this</h3>
<div>1) If valuation and growth are weak, avoid aggressive entries.</div>
<div>2) If cash quality is strong but risk is high, size smaller and review often.</div>
<div>3) Re-run after new earnings or major news to see which levers changed.</div>
</div>
</body></html>"""
    h.write_text(html, encoding="utf-8")
    print("DONE ✅ wrote:", j)
    print("DONE ✅ wrote:", h)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)
