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
    legion = _read(out / f"iron_legion_command_{t}.json")
    focus = legion.get("focus", {})
    public = focus.get("explain_public", "")
    pro = focus.get("explain_pro", "")
    links = [
        ("HUD", f"../export/CANON_{t}/{t}_IRONMAN_HUD.html"),
        ("Iron Legion", f"iron_legion_command_{t}.html"),
        ("Mission Report", f"mission_report_{t}.html"),
        ("Governor", f"confidence_governor_{t}.html"),
        ("Explainability", f"explainability_overlay_{t}.html"),
        ("Stress Suite", f"hulkbuster_stress_{t}.html"),
    ]
    rows = "".join(f"<li><a href='{href}'>{name}</a></li>" for name, href in links)
    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>Legion Commander</title>
<style>
body{{font-family:ui-sans-serif,system-ui;background:#0b1120;color:#ecf2ff;padding:18px}}
.card{{background:#111a2a;border:1px solid #23344e;border-radius:12px;padding:12px;margin:10px 0}}
a{{color:#8fd2ff;text-decoration:none}}
ol{{margin:8px 0 0 18px;padding:0}}
</style>
</head><body>
<div class='card'><h2>Legion Commander — {t}</h2><div>Generated {datetime.now(timezone.utc).isoformat()}</div></div>
<div class='card'><h3 style='margin-top:0'>What this page does</h3>
<div>This is your control room. It links every major armor module for this ticker in one place.</div>
</div>
<div class='card'><h3>Street-Simple</h3><div>{public}</div></div>
<div class='card'><h3>Desk-Deep</h3><div>{pro}</div></div>
<div class='card'><h3>Open Modules</h3><ul>{rows}</ul></div>
<div class='card'><h3 style='margin-top:0'>Suggested Run Order</h3>
<ol>
  <li>Open <b>HUD</b> for the one-screen thesis read.</li>
  <li>Open <b>Iron Legion</b> for action, conviction, and position sizing.</li>
  <li>Open <b>Mission Report</b> to share the rationale with others.</li>
  <li>Open <b>Explainability + Stress Suite</b> before committing capital.</li>
</ol>
</div>
</body></html>"""
    path = out / f"legion_commander_{t}.html"
    path.write_text(html, encoding="utf-8")
    print("DONE ✅ wrote:", path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)
