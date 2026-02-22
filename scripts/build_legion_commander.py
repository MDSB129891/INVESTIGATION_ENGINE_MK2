#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_float(v):
    try:
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
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


def main(ticker: str):
    t = ticker.upper()
    out = ROOT / "outputs"
    legion = _read(out / f"iron_legion_command_{t}.json")
    focus = legion.get("focus", {})
    trust_pass = not bool(focus.get("governor_override", False))
    trust_badge = "<span class='tone good'>TRUST PASS</span>" if trust_pass else "<span class='tone bad'>TRUST FAIL</span>"
    trust_explain = "All trust gates passed." if trust_pass else "One or more trust gates failed (data quality/conviction/tests/MC)."
    public = focus.get("explain_public", "")
    pro = focus.get("explain_pro", "")
    signals = (focus.get("current_signals") or {})
    aha = _aha_rows(signals)
    zone_cls = {"Good": "good", "Okay": "ok", "Weak": "bad", "Unknown": "neutral"}
    aha_html = "".join(
        "<tr>"
        f"<td>{r['metric']}</td>"
        f"<td>{r['value']}</td>"
        f"<td><span class='tone {zone_cls.get(r['zone'], 'neutral')}'>{r['zone']}</span></td>"
        f"<td>{r['rule']}</td>"
        f"<td>{r['meaning']}</td>"
        "</tr>"
        for r in aha
    )
    links = [
        ("HUD", f"../export/CANON_{t}/{t}_IRONMAN_HUD.html"),
        ("News Sources", f"../export/CANON_{t}/{t}_NEWS_SOURCES.html"),
        ("Iron Legion", f"iron_legion_command_{t}.html"),
        ("Stormbreaker", f"../export/CANON_{t}/{t}_STORMBREAKER.html"),
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
table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #223047;text-align:left;vertical-align:top}}
th{{color:#9db0ce;font-size:12px;text-transform:uppercase}}
.tone{{font-size:11px;border-radius:999px;padding:3px 8px;border:1px solid transparent}}
.tone.good{{color:#23d18b;border-color:rgba(35,209,139,.35);background:rgba(35,209,139,.08)}}
.tone.ok{{color:#f4c267;border-color:rgba(244,194,103,.35);background:rgba(244,194,103,.08)}}
.tone.bad{{color:#ff7b7b;border-color:rgba(255,123,123,.35);background:rgba(255,123,123,.08)}}
.tone.neutral{{color:#9cb1d0;border-color:rgba(156,177,208,.35);background:rgba(156,177,208,.08)}}
</style>
</head><body>
<div class='card'><h2>Legion Commander — {t}</h2><div>Generated {datetime.now(timezone.utc).isoformat()}</div></div>
<div class='card'><h3 style='margin-top:0'>Trust Gate</h3><div>{trust_badge}</div><div style='margin-top:6px'>{trust_explain}</div></div>
<div class='card'><h3 style='margin-top:0'>What this page does</h3>
<div>This is your control room. It links every major armor module for this ticker in one place.</div>
</div>
<div class='card'><h3>Street-Simple</h3><div>{public}</div></div>
<div class='card'><h3>Desk-Deep</h3><div>{pro}</div></div>
<div class='card'><h3>Open Modules</h3><ul>{rows}</ul></div>
<div class='card'><h3>Aha Mode: Apples-to-Apples Scoreboard</h3>
<div>Same thresholds every run, so users without finance background can still compare setup quality.</div>
<table><thead><tr><th>Metric</th><th>Your Number</th><th>Zone</th><th>Rule</th><th>What It Means</th></tr></thead>
<tbody>{aha_html}</tbody></table>
</div>
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
