#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _fmt_money(v):
    try:
        x = float(v)
    except Exception:
        return "—"
    a = abs(x)
    if a >= 1e12:
        return f"${x/1e12:.2f}T"
    if a >= 1e9:
        return f"${x/1e9:.2f}B"
    if a >= 1e6:
        return f"${x/1e6:.2f}M"
    return f"${x:,.0f}"


def _grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _action_from_rating(rating: str, conviction: float) -> str:
    r = (rating or "").upper().strip()
    if r in {"BUY", "STRONG BUY"} and conviction >= 70:
        return "DEPLOY (Buy Candidate)"
    if r in {"HOLD", "NEUTRAL"} or conviction >= 60:
        return "TRACK (Watchlist)"
    return "HOLD FIRE"


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _safe_float(v):
    try:
        return float(v)
    except Exception:
        return None


def _load_snapshot_row(ticker: str) -> Dict:
    p = ROOT / "data" / "processed" / "comps_snapshot.csv"
    try:
        df = pd.read_csv(p)
    except Exception:
        return {}
    tcol = "ticker" if "ticker" in df.columns else ("symbol" if "symbol" in df.columns else None)
    if not tcol:
        return {}
    df[tcol] = df[tcol].astype(str).str.upper()
    r = df[df[tcol] == ticker.upper()]
    if r.empty:
        return {}
    try:
        return r.iloc[0].to_dict()
    except Exception:
        return {}


def _aha_rows(signals: Dict) -> List[Dict[str, str]]:
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

    rows = [
        {
            "metric": "Sales Growth (YoY)",
            "value": fmt(signals.get("revenue_yoy_pct"), "pct"),
            "zone": zone_high_good(signals.get("revenue_yoy_pct"), 12, 4),
            "rule": "Good >= 12% | Okay 4% to < 12%",
            "meaning": "Shows demand momentum.",
        },
        {
            "metric": "FCF Margin",
            "value": fmt(signals.get("fcf_margin_ttm_pct"), "pct"),
            "zone": zone_high_good(signals.get("fcf_margin_ttm_pct"), 12, 5),
            "rule": "Good >= 12% | Okay 5% to < 12%",
            "meaning": "Shows cash efficiency.",
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
            "meaning": "Counts negative risk-tag headlines.",
        },
        {
            "metric": "Net Debt / FCF",
            "value": fmt(signals.get("net_debt_to_fcf_ttm"), "x"),
            "zone": zone_low_good(signals.get("net_debt_to_fcf_ttm"), 2, 4),
            "rule": "Good <= 2.0x | Okay > 2.0x to 4.0x",
            "meaning": "Debt load relative to cash generation.",
        },
    ]
    return rows


def _load_ticker_payload(ticker: str) -> Dict:
    t = ticker.upper()
    ds = _read_json(OUT / f"decision_summary_{t}.json", {}) or {}
    risk = _read_json(OUT / f"news_risk_summary_{t}.json", {}) or {}
    claim = _read_json(OUT / f"claim_evidence_{t}.json", {}) or {}
    metric_prov = _read_json(OUT / f"metric_provider_used_{t}.json", {}) or {}
    mc = _read_json(ROOT / "export" / f"CANON_{t}" / f"{t}_MONTECARLO.json", {}) or {}
    core = _read_json(ROOT / "export" / f"CANON_{t}" / f"{t}_DECISION_CORE.json", {}) or {}
    snap = _load_snapshot_row(t)
    return {
        "ticker": t,
        "ds": ds,
        "risk": risk,
        "claim": claim,
        "metric_provider": metric_prov.get("metric_provider_used", {}),
        "mc": mc,
        "core": core,
        "snapshot": snap,
    }


def _reliability_details(payload: Dict) -> Dict:
    metric_prov = payload.get("metric_provider") or {}
    required = ["price", "market_cap", "revenue_ttm_yoy_pct", "fcf_ttm", "fcf_margin_ttm_pct"]
    missing_metrics = [k for k in required if not isinstance(metric_prov.get(k), dict) or metric_prov.get(k, {}).get("value") is None]

    missing_artifacts = []
    if not payload.get("risk"):
        missing_artifacts.append("risk_out")
    if not payload.get("mc"):
        missing_artifacts.append("mc")
    if not payload.get("core"):
        missing_artifacts.append("core")
    if not payload.get("claim"):
        missing_artifacts.append("claim_out")

    unknown_claims = 0
    for r in (payload.get("claim", {}).get("results", []) or []):
        if str((r or {}).get("status", "")).upper() == "UNKNOWN":
            unknown_claims += 1

    coverage = "present" if not missing_metrics else "missing"
    score = 100.0
    score -= 10.0 * len(missing_metrics)
    score -= 8.0 * len(missing_artifacts)
    score -= min(10.0, float(unknown_claims))
    score = max(0.0, min(100.0, score))
    return {
        "score": round(score, 1),
        "grade": _grade(score),
        "missing_metrics": missing_metrics,
        "stale_artifacts": [],
        "missing_artifacts": missing_artifacts,
        "unknown_claims": unknown_claims,
        "mc_fallback_used": bool((payload.get("mc") or {}).get("results", {}).get("fallback_used", False)),
        "universe_coverage": coverage,
    }


def _entry_band(payload: Dict) -> Tuple[float | None, float | None]:
    mc = payload.get("mc") or {}
    r = mc.get("results", mc if isinstance(mc, dict) else {})
    p10 = _safe_float(r.get("p10") or r.get("P10"))
    p50 = _safe_float(r.get("p50") or r.get("P50"))
    return p10, p50


def _price(payload: Dict) -> float | None:
    p = payload.get("metric_provider", {}).get("price", {})
    return _safe_float(p.get("value"))


def _row_for_ticker(payload: Dict, review_date: str) -> Dict:
    ds = payload.get("ds") or {}
    rating = str(ds.get("rating") or "").upper()
    conviction_raw = float(ds.get("score") or 50.0)
    reliability = _reliability_details(payload)
    refresh_warnings = ds.get("refresh_warnings") or []
    claim_rows = (payload.get("claim") or {}).get("results", []) or []
    pass_n = sum(1 for r in claim_rows if str((r or {}).get("status", "")).upper() == "PASS")
    fail_n = sum(1 for r in claim_rows if str((r or {}).get("status", "")).upper() == "FAIL")
    unknown_n = sum(1 for r in claim_rows if str((r or {}).get("status", "")).upper() == "UNKNOWN")
    mc_fallback = bool(reliability.get("mc_fallback_used"))

    # Accuracy-adjusted conviction: penalize for evidence/risk quality, not just raw score.
    penalty = 0.0
    penalty += max(0.0, (100.0 - float(reliability["score"])) * 0.35)
    penalty += min(18.0, 3.0 * len(refresh_warnings))
    penalty += min(20.0, 6.0 * fail_n + 2.0 * unknown_n)
    if mc_fallback:
        penalty += 6.0
    conviction = _clamp(conviction_raw - penalty, 0.0, 100.0)

    action = _action_from_rating(rating, conviction)
    freshness_passed = bool(((ds.get("freshness_sla") or {}).get("passed", False)))
    governor_gates = {
        "reliability_gate": float(reliability["score"]) >= 75.0,
        "conviction_gate": conviction >= 60.0,
        "thesis_fail_gate": fail_n == 0,
        "data_stability_gate": len(refresh_warnings) <= 4,
        "metric_completeness_gate": len(reliability.get("missing_metrics", [])) == 0,
        "freshness_gate": freshness_passed,
        "mc_quality_gate": not mc_fallback,
    }
    governor_override = not all(governor_gates.values())
    if governor_override:
        action = "HOLD FIRE"
    px = _price(payload)
    low, high = _entry_band(payload)
    regime = "Risk-On" if conviction >= 70 else ("Neutral" if conviction >= 55 else "Risk-Off")

    pos = 0.0
    if action.startswith("DEPLOY"):
        pos = round(min(8.0, max(1.5, conviction / 13.0)) * (float(reliability["score"]) / 100.0), 2)
    elif action.startswith("TRACK"):
        pos = round(min(4.0, max(0.75, conviction / 24.0)) * (float(reliability["score"]) / 100.0), 2)

    risk = payload.get("risk") or {}
    snap = payload.get("snapshot") or {}
    core_metrics = ((payload.get("core") or {}).get("metrics") or {})
    revenue_yoy = _safe_float(payload.get("metric_provider", {}).get("revenue_ttm_yoy_pct", {}).get("value"))
    if revenue_yoy is None:
        revenue_yoy = _safe_float(snap.get("revenue_ttm_yoy_pct"))
    fcf_margin = _safe_float(payload.get("metric_provider", {}).get("fcf_margin_ttm_pct", {}).get("value"))
    if fcf_margin is None:
        fcf_margin = _safe_float(snap.get("fcf_margin_ttm_pct"))
    news_shock = _safe_float(risk.get("news_shock_30d"))
    risk_total = _safe_float(risk.get("risk_total_30d"))
    if risk_total is None:
        parts = [
            _safe_float(risk.get("risk_labor_neg_30d")) or 0.0,
            _safe_float(risk.get("risk_regulatory_neg_30d")) or 0.0,
            _safe_float(risk.get("risk_insurance_neg_30d")) or 0.0,
            _safe_float(risk.get("risk_safety_neg_30d")) or 0.0,
            _safe_float(risk.get("risk_competition_neg_30d")) or 0.0,
        ]
        risk_total = sum(parts)
    nd_to_fcf = _safe_float(core_metrics.get("net_debt_to_fcf_ttm"))
    if nd_to_fcf is None:
        nd_to_fcf = _safe_float(snap.get("net_debt_to_fcf_ttm"))

    triggers = [
        "Revenue growth drops below 5% for 2 consecutive quarters.",
        "FCF margin drops below 8%.",
        "News shock falls below -25 or risk_total rises above 8.",
        "Net debt / FCF rises above 4.5x.",
    ]

    public_explain = (
        f"Raw score {conviction_raw:.1f} adjusted to {conviction:.1f} after data-quality checks. "
        f"Thesis tests: {pass_n} pass, {fail_n} fail, {unknown_n} unknown."
    )
    if governor_override:
        public_explain += " Governor overrode action to HOLD FIRE until trust gates pass."
    pro_explain = (
        f"AdjConv={conviction_raw:.1f} - penalties({penalty:.1f}) with components: "
        f"reliability={reliability['score']:.1f}, warnings={len(refresh_warnings)}, "
        f"stormbreaker_fail={fail_n}, stormbreaker_unknown={unknown_n}, mc_fallback={mc_fallback}."
    )
    if governor_override:
        pro_explain += f" Governor gates={governor_gates}."

    return {
        "ticker": payload["ticker"],
        "action": action,
        "governor_override": governor_override,
        "governor_action": action,
        "governor_gates": governor_gates,
        "conviction_score": round(conviction, 1),
        "conviction_raw_score": round(conviction_raw, 1),
        "conviction_penalty": round(penalty, 1),
        "reliability_score": reliability["score"],
        "reliability_grade": reliability["grade"],
        "position_size_pct": pos,
        "regime": regime,
        "price": px,
        "entry_band": {"low": low, "high": high},
        "discipline": {
            "entry_band": {"low": low, "high": high},
            "current_price": px,
            "soft_stop_trigger": (round(px * 1.09, 2) if px else None),
            "next_review_utc": review_date,
            "thesis_break_triggers": triggers,
            "current_signals": {
                "revenue_yoy_pct": revenue_yoy,
                "fcf_margin_ttm_pct": fcf_margin,
                "news_shock_30d": news_shock,
                "risk_total_30d": risk_total,
                "net_debt_to_fcf_ttm": nd_to_fcf,
            },
        },
        "reliability_details": reliability,
        "thesis_test_counts": {"pass": pass_n, "fail": fail_n, "unknown": unknown_n},
        "explain_public": public_explain,
        "explain_pro": pro_explain,
    }


def _render_html(data: Dict) -> str:
    focus = data["focus"]
    rows = data["legion_table"]
    trust_pass = not bool(focus.get("governor_override"))
    trust_badge = "<span class='tone good'>TRUST PASS</span>" if trust_pass else "<span class='tone bad'>TRUST FAIL</span>"
    signals = focus.get("current_signals", {}) or {}
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
    focus_price = _fmt_money(focus.get("price_text")) if focus.get("price_text") != "—" else "—"
    governor_banner = ""
    if focus.get("governor_override"):
        governor_banner = (
            "<div class='card' style='border-color:#6a2f2f;background:#24171b'>"
            "<div class='k'>Trust Governor Override</div>"
            "<div><b>Action forced to HOLD FIRE</b> until trust gates pass.</div>"
            f"<div style='margin-top:6px'>Gates: {focus.get('governor_gates', {})}</div>"
            "</div>"
        )
    tr_html = []
    for r in rows:
        tr_html.append(
            "<tr>"
            f"<td>{r['ticker']}</td>"
            f"<td>{r['action']}</td>"
            f"<td>{r['conviction_score']:.1f}</td>"
            f"<td>{r['reliability_grade']} ({r['reliability_score']:.1f})</td>"
            f"<td>{r['position_size_pct']:.2f}%</td>"
            f"<td>{r['regime']}</td>"
            "</tr>"
        )
    missing = ", ".join(focus["reliability_details"]["missing_metrics"]) or "None"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Iron Legion Command — {focus['ticker']}</title>
<style>
body{{font-family:ui-sans-serif,system-ui;background:#0a0f18;color:#e9eef9;margin:0;padding:22px}}
.card{{background:#111826;border:1px solid #24324a;border-radius:12px;padding:14px;margin-bottom:12px}}
.k{{color:#99a9c8;font-size:12px;text-transform:uppercase;letter-spacing:.08em}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #223047;text-align:left}}
th{{color:#9db0ce;font-size:12px;text-transform:uppercase}}
.tone{{font-size:11px;border-radius:999px;padding:3px 8px;border:1px solid transparent}}
.tone.good{{color:#23d18b;border-color:rgba(35,209,139,.35);background:rgba(35,209,139,.08)}}
.tone.ok{{color:#f4c267;border-color:rgba(244,194,103,.35);background:rgba(244,194,103,.08)}}
.tone.bad{{color:#ff7b7b;border-color:rgba(255,123,123,.35);background:rgba(255,123,123,.08)}}
.tone.neutral{{color:#9cb1d0;border-color:rgba(156,177,208,.35);background:rgba(156,177,208,.08)}}
</style></head><body>
<div class="card"><div class="k">Iron Legion Command</div>
<h2 style="margin:8px 0 4px 0;">{focus['ticker']} · {focus['action']}</h2>
<div>Conviction: {focus['conviction_score']:.1f} (raw {focus.get('conviction_raw_score', focus['conviction_score']):.1f}, penalty {focus.get('conviction_penalty', 0.0):.1f}) · Reliability: {focus['reliability_grade']} ({focus['reliability_score']:.1f}) · Max position: {focus['position_size_pct']:.2f}%</div>
<div>Entry band: {focus['entry_band_text']} · Current price: {focus_price} · Next review: {focus['next_review']}</div>
<div style="margin-top:6px;"><a href="../export/CANON_{focus['ticker']}/{focus['ticker']}_NEWS_SOURCES.html">Open News Sources tab</a></div>
</div>
<div class='card'><div class='k'>Trust Gate</div><div>{trust_badge}</div></div>
{governor_banner}
<div class="card"><div class="k">Street-Simple (General Audience)</div>
<div>{focus.get('explain_public','')}</div></div>
<div class="card"><div class="k">Desk-Deep (Finance Audience)</div>
<div>{focus.get('explain_pro','')}</div></div>
<div class="card"><div class="k">Comparative Mode (Iron Legion Table)</div>
<table><thead><tr><th>Ticker</th><th>Action</th><th>Conviction</th><th>Reliability</th><th>Max Size</th><th>Regime</th></tr></thead>
<tbody>{''.join(tr_html)}</tbody></table></div>
<div class="card"><div class="k">Data Reliability Score</div>
<div>Missing metrics: {missing}</div>
<div>Universe coverage: {focus['reliability_details']['universe_coverage']}</div></div>
<div class="card"><div class="k">How To Use This Command</div>
<div><b>Conviction</b> tells how strong the signal is after quality penalties.</div>
<div><b>Reliability</b> tells how trustworthy the inputs are in this run.</div>
<div><b>Max position</b> is a risk cap, not a required allocation.</div>
<div><b>HOLD FIRE</b> means wait; <b>TRACK</b> means monitor; <b>DEPLOY</b> means candidate buy setup.</div>
</div>
<div class="card"><div class="k">Aha Mode: Apples-to-Apples Scoreboard</div>
<div style="margin:6px 0 8px 0;color:#b8c8e6;">Same rules every ticker, so non-finance users can compare quickly.</div>
<table><thead><tr><th>Metric</th><th>Your Number</th><th>Zone</th><th>Rule</th><th>What It Means</th></tr></thead>
<tbody>{aha_html}</tbody></table>
</div>
</body></html>"""


def main(focus: str):
    focus = focus.upper()
    focus_ds = _read_json(OUT / f"decision_summary_{focus}.json", {}) or {}
    universe = [focus]
    for t in (focus_ds.get("universe") or []):
        tu = str(t).upper()
        if tu not in universe:
            universe.append(tu)

    now = datetime.now(timezone.utc)
    review_date = (now + timedelta(days=30)).date().isoformat()

    rows = []
    focus_row = None
    for t in universe:
        payload = _load_ticker_payload(t)
        row = _row_for_ticker(payload, review_date)
        rows.append(row)
        if t == focus:
            focus_row = row

    if focus_row is None:
        raise SystemExit(f"Missing focus ticker data: {focus}")

    low = focus_row["entry_band"]["low"]
    high = focus_row["entry_band"]["high"]
    entry_txt = "—"
    if low is not None and high is not None:
        entry_txt = f"{_fmt_money(low)} to {_fmt_money(high)}"
    elif high is not None:
        entry_txt = f"Up to {_fmt_money(high)}"

    focus_block = {
        "ticker": focus,
        "action": focus_row["action"],
        "governor_override": focus_row.get("governor_override", False),
        "governor_action": focus_row.get("governor_action", focus_row["action"]),
        "governor_gates": focus_row.get("governor_gates", {}),
        "conviction_score": focus_row["conviction_score"],
        "conviction_raw_score": focus_row.get("conviction_raw_score", focus_row["conviction_score"]),
        "conviction_penalty": focus_row.get("conviction_penalty", 0.0),
        "reliability_score": focus_row["reliability_score"],
        "reliability_grade": focus_row["reliability_grade"],
        "position_size_pct": focus_row["position_size_pct"],
        "entry_band_text": entry_txt,
        "price_text": _fmt_money(focus_row["price"]) if focus_row.get("price") is not None else "—",
        "stop_text": _fmt_money(focus_row["discipline"]["soft_stop_trigger"]) if focus_row["discipline"]["soft_stop_trigger"] is not None else "—",
        "next_review": review_date,
        "triggers": focus_row["discipline"]["thesis_break_triggers"],
        "current_signals": focus_row["discipline"]["current_signals"],
        "reliability_details": focus_row["reliability_details"],
        "thesis_test_counts": focus_row.get("thesis_test_counts", {}),
        "explain_public": focus_row.get("explain_public", ""),
        "explain_pro": focus_row.get("explain_pro", ""),
    }

    out = {
        "generated_utc": now.isoformat(),
        "focus_ticker": focus,
        "focus": focus_block,
        "legion_table": rows,
        "journal_count": 0,
        "journal_outcome_count": 0,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    shared_json = OUT / "iron_legion_command.json"
    shared_html = OUT / "iron_legion_command.html"
    focus_json = OUT / f"iron_legion_command_{focus}.json"
    focus_html = OUT / f"iron_legion_command_{focus}.html"

    shared_json.write_text(json.dumps(out, indent=2), encoding="utf-8")
    focus_json.write_text(json.dumps(out, indent=2), encoding="utf-8")
    html = _render_html(out)
    shared_html.write_text(html, encoding="utf-8")
    focus_html.write_text(html, encoding="utf-8")

    print("DONE ✅ wrote:", shared_json)
    print("DONE ✅ wrote:", shared_html)
    print("DONE ✅ wrote:", focus_json)
    print("DONE ✅ wrote:", focus_html)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--focus", required=True, help="Focus ticker (e.g., GM)")
    args = ap.parse_args()
    main(args.focus)
