#!/usr/bin/env python3
from pathlib import Path
import argparse, json
import pandas as pd
import html

def _missing(x):
    return x is None or x in {"N/A", "—"} or (isinstance(x, float) and x != x)


from pathlib import Path
import html as htmlmod
REPO_ROOT = Path(__file__).resolve().parents[1]



def _load_json(path, default=None):
    try:
        import json
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def _load_montecarlo(ticker: str):
    try:
        import json
        T = ticker.upper()
        canon = REPO_ROOT / "export" / f"CANON_{T}"
        fp = canon / f"{T}_MONTECARLO.json"
        if not fp.exists():
            return {}, None

        j = json.loads(fp.read_text())
        r = j.get("results", j)

        # normalize case
        for a,b in [("P10","p10"),("P50","p50"),("P90","p90")]:
            if b not in r and a in r:
                r[b] = r[a]

        return r, str(fp)
    except Exception:
        return {}, None
# _HUD_HELPERS_BEGIN
def _pill(unit: str) -> str:
    u = (unit or "").lower().strip()
    m = {"usd":"USD", "pct":"pct", "x":"x", "count":"#", "score":"score"}
    return f'<span class="pill" style="margin-left:8px;opacity:.85;">{m.get(u,u)}</span>'

def _fmt_usd(v):
    if v is None:
        return 'N/A'
    try:
        v = float(v)
    except Exception:
        return "N/A"
    a = abs(v)
    if a >= 1e12: return f"${v/1e12:.2f}T"
    if a >= 1e9:  return f"${v/1e9:.2f}B"
    if a >= 1e6:  return f"${v/1e6:.2f}M"
    if a >= 1e3:  return f"${v/1e3:.2f}K"
    return f"${v:,.0f}"

def _fmt_pct(v):
    try:
        return f"{float(v):.2f}%"
    except Exception:
        return "N/A"

def _fmt_x(v):
    try:
        return f"{float(v):.2f}x"
    except Exception:
        return "N/A"

def _fmt_num(v):
    try:
        x = float(v)
        if abs(x - round(x)) < 1e-9:
            return str(int(round(x)))
        return f"{x:.2f}"
    except Exception:
        return str(v) if v is not None else "N/A"

def _interp_fcf_yield(v_pct):
    # simple, intuitive bands (not gospel—just usability)
    try:
        v = float(v_pct)
    except Exception:
        return "N/A"
    if v >= 8:  return "High cash return for the price (good)"
    if v >= 4:  return "Decent cash return (okay)"
    if v >= 0:  return "Low cash return (meh)"
    return "Negative cash return (bad)"

def _interp_news_shock(score):
    # you described: “Lower (more negative) = worse headlines”
    try:
        s = float(score)
    except Exception:
        return "N/A"
    if s >= 60: return "Very stable headlines (quiet)"
    if s >= 30: return "Mostly stable (some noise)"
    if s >= 10: return "Choppy headlines (pay attention)"
    return "Headline risk elevated (watch closely)"
# _HUD_HELPERS_END

def _fallback_fcf_yield_from_dcf(ticker: str):
    """
    Returns FCF yield as a float fraction (e.g., 0.064 for 6.4%), or None.
    Looks at export/CANON_{T}/{T}_DCF.json with inputs.fcf and inputs.market_cap_used.
    """
    try:
        from pathlib import Path
        import json
        T = str(ticker).upper()
        dcf_path = Path(f"export/CANON_{T}/{T}_DCF.json")
        if not dcf_path.exists():
            return None
        d = json.loads(dcf_path.read_text(encoding="utf-8"))
        fcf = float(d.get("inputs", {}).get("fcf") or 0.0)
        mc  = float(d.get("inputs", {}).get("market_cap_used") or 0.0)
        if fcf > 0 and mc > 0:
            return fcf / mc
        return None
    except Exception:
        return None


ROOT = Path(__file__).resolve().parents[1]

def _read_json(p: Path):
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))

def _load_snapshot_row(ticker: str):
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
    return r.iloc[0]  # <-- Series

def fmt_money(x):
    try:
        x = float(x)
    except:
        return "N/A"
    s = abs(x)
    if s >= 1e12: return f"${x/1e12:.2f}T"
    if s >= 1e9:  return f"${x/1e9:.2f}B"
    if s >= 1e6:  return f"${x/1e6:.2f}M"
    return f"${x:,.0f}"

def fmt_pct(x):
    try:
        return f"{float(x):.2f}%"
    except:
        return "N/A"

def main(ticker: str):
    T = ticker.upper()
    canon = ROOT / "export" / f"CANON_{T}"
    canon.mkdir(parents=True, exist_ok=True)

    row = _load_snapshot_row(T)

    # --- normalize snapshot row to dict (so patches always work) ---
    try:
        if not isinstance(row, dict):
            row = row.to_dict()
    except Exception:
        row = {}

    # ---- Fallback normalization (snapshot schema differences)
    # Some pipelines use fcf_ttm + fcf_yield (fraction) instead of free_cash_flow_ttm + fcf_yield_pct.
    try:
        _row = row if isinstance(row, dict) else (row.to_dict() if hasattr(row, "to_dict") else {})
    except Exception:
        _row = {}

    # Normalize: Free cash flow (TTM)
    if _row.get("free_cash_flow_ttm") is None and _row.get("free_cash_flow") is None:
        if _row.get("fcf_ttm") is not None:
            _row["free_cash_flow_ttm"] = _row.get("fcf_ttm")

    # Normalize: FCF yield pct (prefer explicit pct, else fraction*100)
    if _row.get("fcf_yield_pct") is None:
        if _row.get("fcf_yield") is not None:
            try:
                _row["fcf_yield_pct"] = float(_row["fcf_yield"]) * 100.0
            except Exception:
                pass

    row = _row

    # --- Risk summary (30d) from outputs/news_risk_summary_{T}.json ---
    risk_labor = risk_reg = risk_ins = risk_safe = risk_comp = risk_total = "N/A"
    risk_shock = "N/A"
    risk_generated = "N/A"

    # --- Receipts (audit trail) pulled into HUD ---
    receipts_payload = _load_json(Path("outputs") / f"receipts_{T}.json", {})
    receipt_map = {}
    try:
        for r in receipts_payload.get("receipts", []) or []:
            if isinstance(r, dict) and r.get("metric"):
                receipt_map[str(r["metric"])] = r
    except Exception:
        receipt_map = {}


    # --- Receipts-based numeric fallbacks (if snapshot is missing) ---

    def _r_actual(metric: str):

        try:

            v = (receipt_map.get(metric) or {}).get("actual")

            return v

        except Exception:

            return None


    try:

        # Free cash flow (TTM): prefer snapshot free_cash_flow_ttm, else receipts latest_free_cash_flow, else snapshot fcf_ttm

        if isinstance(row, dict):

            if row.get("free_cash_flow_ttm") in (None, "N/A"):

                row["free_cash_flow_ttm"] = _r_actual("latest_free_cash_flow") or row.get("fcf_ttm") or row.get("free_cash_flow")

    

            # FCF yield pct: prefer snapshot fcf_yield_pct, else receipts fcf_yield_pct, else snapshot fcf_yield * 100

            if row.get("fcf_yield_pct") in (None, "N/A"):

                v = _r_actual("fcf_yield_pct")

                if v is not None:

                    row["fcf_yield_pct"] = v

                elif row.get("fcf_yield") is not None:

                    try:

                        row["fcf_yield_pct"] = float(row.get("fcf_yield")) * 100.0

                    except Exception:

                        pass

    except Exception:

        pass


    def _receipt_line(metric: str, fallback_label: str) -> str:

        r = receipt_map.get(metric) or {}

        what = r.get("what_it_is") or fallback_label

        why  = r.get("why_it_matters") or ""

        if not why:

            return (

                f"<li class=\"rct\">"

                f"<div class=\"rct_title\">{htmlmod.escape(str(fallback_label))}</div>"

                f"</li>"

            )

        return (

            f"<li class=\"rct\">"

            f"<div class=\"rct_title\">{htmlmod.escape(str(fallback_label))}</div>"

            f"<div class=\"rct_body\">"

            f"<div><span class=\"rct_k\">what it is:</span> <b>{htmlmod.escape(str(what))}</b></div>"

            f"<div><span class=\"rct_k\">why it matters:</span> {htmlmod.escape(str(why))}</div>"

            f"</div>"

            f"</li>"

        )


    receipts_html = "<ul class=\"receipts\">"
    receipts_html += _receipt_line("latest_free_cash_flow", "Free cash flow (TTM)")
    receipts_html += _receipt_line("latest_fcf_margin_pct", "FCF margin")
    receipts_html += _receipt_line("fcf_yield_pct", "FCF yield")
    receipts_html += _receipt_line("news_shock_30d", "News shock (30d)")
    receipts_html += _receipt_line("latest_revenue_yoy_pct", "Sales growth (YoY)")
    receipts_html += _receipt_line("mc_p10", "Monte Carlo DCF P10")
    receipts_html += _receipt_line("mc_p50", "Monte Carlo DCF P50")
    receipts_html += _receipt_line("mc_p90", "Monte Carlo DCF P90")
    receipts_html += "</ul>"
    try:
        import json
        from pathlib import Path as _P
        _t = T
        _p = _P(f"outputs/news_risk_summary_{_t}.json")
        if not _p.exists():
            _p = _P(f"export/CANON_{_t}/news_risk_summary_{_t}.json")
        if _p.exists():
            _r = json.loads(_p.read_text(encoding="utf-8"))
            risk_labor = _r.get("risk_labor_neg_30d", 0)
            risk_reg   = _r.get("risk_regulatory_neg_30d", 0)
            risk_ins   = _r.get("risk_insurance_neg_30d", 0)
            risk_safe  = _r.get("risk_safety_neg_30d", 0)
            risk_comp  = _r.get("risk_competition_neg_30d", 0)
            risk_total = _r.get("risk_total_30d", risk_labor + risk_reg + risk_ins + risk_safe + risk_comp)
            risk_shock = _r.get("news_shock_30d", _r.get("news_shock", "N/A"))
            risk_generated = _r.get("generated_at") or _r.get("generated_utc") or "N/A"
            if risk_generated == "N/A":
                try:
                    from datetime import datetime, timezone
                    risk_generated = datetime.fromtimestamp(
                        _p.stat().st_mtime, tz=timezone.utc
                    ).isoformat()
                except Exception:
                    pass
    except Exception:
        pass

    # --- Macro context (free rates/inflation proxies) ---
    macro_regime = "Macro Unknown"
    macro_source = "outputs/macro_context.json"
    macro_generated = "N/A"
    macro_used_cache = False
    macro_dgs10 = macro_cpi = macro_ff = None
    macro_explain = (
        "Macro data is unavailable right now. Treat confidence as neutral and focus on company-specific signals."
    )
    try:
        macro = _read_json(ROOT / "outputs" / "macro_context.json") or {}
        macro_regime = str(macro.get("macro_regime") or macro_regime)
        macro_source = str(macro.get("source") or macro_source)
        macro_generated = str(macro.get("generated_utc") or macro_generated)
        macro_used_cache = bool(macro.get("used_cache"))
        series = macro.get("series") or {}
        macro_dgs10 = series.get("DGS10")
        macro_cpi = series.get("CPIAUCSL")
        macro_ff = series.get("FEDFUNDS")
        if "Tight Policy" in macro_regime:
            macro_explain = "Rates are relatively tight. Future cash flows are discounted harder, so valuation upside usually needs stronger proof."
        elif "Higher Yield Regime" in macro_regime:
            macro_explain = "Bond yields are elevated. Growth stocks can face pressure unless fundamentals are clearly improving."
        elif "Lower Yield Regime" in macro_regime:
            macro_explain = "Rate pressure is lighter. Valuation multiples usually get more support."
        elif "Neutral Macro" in macro_regime:
            macro_explain = "Macro is mixed/normal. Company execution matters more than macro tailwinds or headwinds."
    except Exception:
        pass


    # --- Canon artifacts ---
    decision_core = _read_json(canon / f"{T}_DECISION_CORE.json") or {}
    mc = _read_json(canon / f"{T}_MONTECARLO.json") or {}

    # Prefer decision_core.metrics for cone + news shock; fall back to MC inputs when needed
    _m = (decision_core.get("metrics") or {}) if isinstance(decision_core, dict) else {}

    # News shock fallback
    if _missing(risk_shock) and not _missing(_m.get("news_shock_30d")):
        risk_shock = _m.get("news_shock_30d")

    # Cone prices (per share)
    bear = _m.get("bear_price") or ((mc.get("inputs") or {}).get("bear") if isinstance(mc, dict) else None)
    base = _m.get("base_price") or ((mc.get("inputs") or {}).get("base") if isinstance(mc, dict) else None)
    bull = _m.get("bull_price") or ((mc.get("inputs") or {}).get("bull") if isinstance(mc, dict) else None)

    # MC percentiles + probs
    mc_p10 = mc.get("p10") if isinstance(mc, dict) else None
    mc_p50 = mc.get("p50") if isinstance(mc, dict) else None
    mc_p90 = mc.get("p90") if isinstance(mc, dict) else None
    prob_down_20 = mc.get("prob_down_20pct") if isinstance(mc, dict) else None
    prob_up_20   = mc.get("prob_up_20pct") if isinstance(mc, dict) else None
    mc_src = (mc.get("source") or {}) if isinstance(mc, dict) else {}
    mc_src_str = mc_src.get("decision_core") or mc_src.get("dcf") or "N/A"

    # Price used for % deltas (try decision core price_used, else row price)
    price_used = _m.get("price_used") or row.get("price") or None

    def _pct_delta(val, px):
        try:
            if val is None or px in (None, 0):
                return "N/A"
            return f"{(float(val)/float(px)-1.0)*100.0:.1f}%"
        except Exception:
            return "N/A"

    # --- Receipts (pretty cards) ---
    receipts_payload = _load_json(Path("outputs") / f"receipts_{T}.json", {})
    receipt_map = {}
    try:
        for r in (receipts_payload.get("receipts", []) or []):
            if isinstance(r, dict) and r.get("metric"):
                receipt_map[str(r["metric"])] = r
    except Exception:
        receipt_map = {}

    def _receipt_card(metric: str, fallback_label: str) -> str:
        r = receipt_map.get(metric) or {}
        what = r.get("what_it_is") or fallback_label
        why  = r.get("why_it_matters") or ""
        if not why:
            return f"<li class=\"rct\"><div class=\"rct_title\">{htmlmod.escape(str(fallback_label))}</div></li>"
        return (
            f"<li class=\"rct\">"
            f"<div class=\"rct_title\">{htmlmod.escape(str(fallback_label))}</div>"
            f"<div class=\"rct_body\">"
            f"<div><span class=\"rct_k\">what it is:</span> <b>{htmlmod.escape(str(what))}</b></div>"
            f"<div><span class=\"rct_k\">why it matters:</span> {htmlmod.escape(str(why))}</div>"
            f"</div>"
            f"</li>"
        )

    receipts_html = "<ul class=\"receipts\">"
    receipts_html += _receipt_card("latest_free_cash_flow", "Free cash flow (TTM)")
    receipts_html += _receipt_card("latest_fcf_margin_pct", "FCF margin")
    receipts_html += _receipt_card("fcf_yield_pct", "FCF yield")
    receipts_html += _receipt_card("news_shock_30d", "News shock (30d)")
    receipts_html += _receipt_card("latest_revenue_yoy_pct", "Sales growth (YoY)")
    receipts_html += _receipt_card("mc_p10", "Monte Carlo DCF P10")
    receipts_html += _receipt_card("mc_p50", "Monte Carlo DCF P50")
    receipts_html += _receipt_card("mc_p90", "Monte Carlo DCF P90")
    receipts_html += "</ul>"
    dcf = _read_json(canon / f"{T}_DCF.json") or _read_json(ROOT / "outputs" / f"{T}_DCF.json") or {}

    price = row.get("price", None)
    mcap  = row.get("market_cap", None)
    net_debt = row.get("net_debt", None)
    nd_to_fcf = row.get("net_debt_to_fcf_ttm", None)
    if net_debt is None:
        net_debt = _m.get("net_debt")
    if nd_to_fcf is None:
        nd_to_fcf = _m.get("net_debt_to_fcf_ttm")
    fcf   = (
        row.get("free_cash_flow_ttm")
        if row.get("free_cash_flow_ttm") is not None
        else (row.get("free_cash_flow") if row.get("free_cash_flow") is not None else row.get("fcf_ttm"))
    )
    rev_yoy = row.get("revenue_ttm_yoy_pct", None)
    fcf_m = row.get("fcf_margin_ttm_pct", None)
    fcf_y = row.get("fcf_yield_pct", None)
    # Fallback: compute from DCF json if missing
    if fcf_y is None:
      v = _fallback_fcf_yield_from_dcf(ticker)
      if v is not None:
        fcf_y = float(v) * 100.0
# DCF cone
    vps = dcf.get("valuation_per_share", {})
    ups = dcf.get("upside_downside_vs_price_pct", {})
    # --- Display-ready FCF yield (use comps if present, else DCF fallback) ---
    fcf_y_display = fcf_y
    if fcf_y_display is None:
        _v = _fallback_fcf_yield_from_dcf(ticker)
        if _v is not None:
            fcf_y_display = _v * 100.0
    # --- Display-safe FCF + FCF yield (prefer comps, fallback to DCF inputs) ---
    fcf_ttm_display = fcf
    if fcf_ttm_display is None:
        try:
            _dcf = _read_json(canon / f"{T}_DCF.json") or _read_json(ROOT / "outputs" / f"{T}_DCF.json") or {}
            fcf_ttm_display = (_dcf.get("inputs", {}) or {}).get("fcf_ttm")
        except Exception:
            pass

    fcf_y_display = fcf_y
    if fcf_y_display is None:
        # 1) use DCF direct helper if available
        try:
            _v = _fallback_fcf_yield_from_dcf(ticker)
            if _v is not None:
                # helper returns fraction (0.064) OR pct (6.4) depending on earlier patches.
                fcf_y_display = (_v * 100.0) if _v < 1 else _v
        except Exception:
            pass

    # 2) final fallback: compute from DCF inputs if still missing
    if fcf_y_display is None:
        try:
            _dcf = _read_json(canon / f"{T}_DCF.json") or _read_json(ROOT / "outputs" / f"{T}_DCF.json") or {}
            _inp = _dcf.get("inputs", {}) or {}
            _fcf = _inp.get("fcf_ttm")
            _mcap = _inp.get("market_cap_used")
            if _fcf and _mcap:
                fcf_y_display = float(_fcf) / float(_mcap) * 100.0
        except Exception:
            pass

    # --- DCF cone aliases (needed for HUD formatting) ---
    _cone = (dcf or {}).get("valuation_per_share", {}) if isinstance(dcf, dict) else {}
    bear_price = _cone.get("bear_price", None)
    base_price = _cone.get("base_price", None)
    bull_price = _cone.get("bull_price", None)





    # --- VISION: Monte Carlo DCF stats (safe defaults if missing) ---




    mc_r, mc_path = _load_montecarlo(T)




    if not isinstance(mc_r, dict):




        mc_r = {}





    mc_p10 = mc_r.get("p10") if isinstance(mc_r, dict) else None




    mc_p50 = mc_r.get("p50") if isinstance(mc_r, dict) else None




    mc_p90 = mc_r.get("p90") if isinstance(mc_r, dict) else None




    mc_down20 = mc_r.get("prob_down_20pct") if isinstance(mc_r, dict) else None




    mc_up20 = mc_r.get("prob_up_20pct") if isinstance(mc_r, dict) else None
    mc_fallback_used = bool(mc_r.get("fallback_used")) if isinstance(mc_r, dict) else False
    mc_fallback_reason = mc_r.get("fallback_reason") if isinstance(mc_r, dict) else None

    # Build next links dynamically so users don't click dead tabs.
    links = []
    next_candidates = [
        (f"{T}_TIMESTONE.html", canon / f"{T}_TIMESTONE.html", "Time Stone"),
        (f"{T}_ARMOR_SYSTEMS.html", canon / f"{T}_ARMOR_SYSTEMS.html", "Armor systems"),
        (f"../../outputs/iron_legion_command_{T}.html", ROOT / "outputs" / f"iron_legion_command_{T}.html", "Iron Legion command"),
        (f"../../outputs/receipts_{T}.html", ROOT / "outputs" / f"receipts_{T}.html", "Receipts"),
        (f"decision_dashboard_{T}.html", canon / f"decision_dashboard_{T}.html", "Dashboard"),
        (f"news_clickpack_{T}.html", canon / f"news_clickpack_{T}.html", "News clickpack"),
        (f"../../outputs/claim_evidence_{T}.html", ROOT / "outputs" / f"claim_evidence_{T}.html", "Claim evidence"),
    ]
    for href, p, label in next_candidates:
        if p.exists():
            links.append(f'<a href="{href}">{label}</a>')
    if not links:
        links = ['<span style="opacity:.75;">No downstream tabs available yet. Run full Vision pipeline.</span>']
    next_links_html = " · ".join(links)

    # --- Provider provenance (per-metric source audit) ---
    metric_provider_payload = _load_json(ROOT / "outputs" / f"metric_provider_used_{T}.json", {}) or {}
    metric_provider_used = metric_provider_payload.get("metric_provider_used", {}) if isinstance(metric_provider_payload, dict) else {}

    def _provider_badge(p):
        ps = str(p or "unknown")
        cls = "neutral"
        if ps in ("fmp_paid", "massive", "yahoo_public"):
            cls = "good"
        elif ps in ("raw_cache", "last_good_cache", "yahoo_snapshot"):
            cls = "ok"
        elif ps in ("unavailable", "unknown"):
            cls = "bad"
        return f'<span class="tone {cls}">{htmlmod.escape(ps)}</span>'

    _prov_metric_order = [
        ("price", "Price", "usd"),
        ("market_cap", "Market Cap", "usd"),
        ("revenue_ttm_yoy_pct", "Sales Growth (YoY)", "pct"),
        ("fcf_ttm", "Free Cash Flow (TTM)", "usd"),
        ("fcf_margin_ttm_pct", "FCF Margin", "pct"),
    ]
    _prov_rows = []
    for mk, mlabel, unit in _prov_metric_order:
        item = metric_provider_used.get(mk, {}) if isinstance(metric_provider_used, dict) else {}
        prov = item.get("provider")
        val = item.get("value")
        if unit == "usd":
            val_s = _fmt_usd(val)
        elif unit == "pct":
            val_s = _fmt_pct(val)
        else:
            val_s = _fmt_num(val)
        _prov_rows.append(
            f"<tr><td>{htmlmod.escape(mlabel)}</td><td>{_provider_badge(prov)}</td><td>{htmlmod.escape(str(val_s))}</td></tr>"
        )
    provider_provenance_rows_html = "".join(_prov_rows) if _prov_rows else (
        "<tr><td colspan='3' style='opacity:.75;'>No provider provenance file found yet.</td></tr>"
    )

    # --- Stormbreaker claim evidence snapshot ---
    stormbreaker = _load_json(ROOT / "outputs" / f"claim_evidence_{T}.json", {}) or {}
    sb_results = stormbreaker.get("results", []) if isinstance(stormbreaker, dict) else []
    sb_pass = sum(1 for r in sb_results if str((r or {}).get("status", "")).upper() == "PASS")
    sb_fail = sum(1 for r in sb_results if str((r or {}).get("status", "")).upper() == "FAIL")
    sb_unknown = sum(1 for r in sb_results if str((r or {}).get("status", "")).upper() == "UNKNOWN")
    sb_tone = (
        '<span class="tone bad">Thesis under pressure</span>' if sb_fail > 0
        else ('<span class="tone ok">Incomplete evidence</span>' if sb_unknown > 0
              else '<span class="tone good">Thesis checks passing</span>')
    )

    # --- Iron Legion lens (public + pro explanations)
    legion = _load_json(ROOT / "outputs" / f"iron_legion_command_{T}.json", {}) or {}
    lfocus = legion.get("focus", {}) if isinstance(legion, dict) else {}
    street_simple = str(lfocus.get("explain_public") or "Accuracy-adjusted conviction explanation unavailable.")
    desk_deep = str(lfocus.get("explain_pro") or "Quant breakdown unavailable for this run.")
    leg_raw = lfocus.get("conviction_raw_score")
    leg_adj = lfocus.get("conviction_score")
    leg_pen = lfocus.get("conviction_penalty")




    def _safe_float(v):
        try:
            return float(v)
        except Exception:
            return None

    def _tone_badge(value, good, ok):
        fv = _safe_float(value)
        if fv is None:
            return '<span class="tone neutral">Insufficient data</span>'
        if good(fv):
            return '<span class="tone good">Strong</span>'
        if ok(fv):
            return '<span class="tone ok">Mixed</span>'
        return '<span class="tone bad">Weak</span>'

    fcf_tone = _tone_badge(fcf_y_display, lambda x: x >= 8, lambda x: x >= 4)
    growth_tone = _tone_badge(rev_yoy, lambda x: x >= 12, lambda x: x >= 4)
    shock_tone = _tone_badge(risk_shock, lambda x: x >= 30, lambda x: x >= 10)
    risk_tone = _tone_badge(risk_total, lambda x: x <= 2, lambda x: x <= 5)
    space_tone = _tone_badge(nd_to_fcf, lambda x: x <= 2, lambda x: x <= 4)

    base_delta = _pct_delta(base, price_used)
    base_delta_f = _safe_float(str(base_delta).replace("%", ""))
    misprice_tone = (
        '<span class="tone neutral">Unknown</span>'
        if base_delta_f is None
        else ('<span class="tone good">Potential upside</span>' if base_delta_f > 0 else '<span class="tone ok">At/above model value</span>')
    )
    macro_tone = (
        '<span class="tone neutral">Unknown</span>'
        if "Unknown" in macro_regime
        else ('<span class="tone bad">Headwind</span>' if ("Tight Policy" in macro_regime or "Higher Yield" in macro_regime)
              else ('<span class="tone good">Tailwind</span>' if "Lower Yield" in macro_regime else '<span class="tone ok">Neutral</span>'))
    )

    def _label_from_value(v, good_min=None, ok_min=None, good_max=None, ok_max=None):
        fv = _safe_float(v)
        if fv is None:
            return "unknown"
        if good_min is not None:
            if fv >= good_min:
                return "good"
            if ok_min is not None and fv >= ok_min:
                return "ok"
            return "bad"
        if good_max is not None:
            if fv <= good_max:
                return "good"
            if ok_max is not None and fv <= ok_max:
                return "ok"
            return "bad"
        return "unknown"

    signal_labels = {
        "growth": _label_from_value(rev_yoy, good_min=12, ok_min=4),
        "cash_return": _label_from_value(fcf_y_display, good_min=8, ok_min=4),
        "mispricing": "unknown" if base_delta_f is None else ("good" if base_delta_f > 0 else "ok"),
        "headline": _label_from_value(risk_shock, good_min=30, ok_min=10),
        "balance_sheet": _label_from_value(nd_to_fcf, good_max=2, ok_max=4),
        "risk_load": _label_from_value(risk_total, good_max=2, ok_max=5),
    }
    good_count = sum(1 for v in signal_labels.values() if v == "good")
    bad_count = sum(1 for v in signal_labels.values() if v == "bad")
    unknown_count = sum(1 for v in signal_labels.values() if v == "unknown")

    if bad_count >= 3:
        one_line_call = "Caution setup: too many core signals are weak right now."
        one_line_tone = '<span class="tone bad">High caution</span>'
    elif good_count >= 4 and bad_count == 0:
        one_line_call = "Constructive setup: most core signals are supportive."
        one_line_tone = '<span class="tone good">Constructive</span>'
    else:
        one_line_call = "Mixed setup: some strengths exist, but conviction is not clean yet."
        one_line_tone = '<span class="tone ok">Mixed conviction</span>'

    takeaways = []
    if signal_labels["growth"] == "good":
        takeaways.append(f"Demand trajectory is healthy with {fmt_pct(rev_yoy)} sales growth.")
    elif signal_labels["growth"] == "bad":
        takeaways.append(f"Sales momentum is weak at {fmt_pct(rev_yoy)}; thesis needs stronger growth proof.")
    if signal_labels["cash_return"] == "good":
        takeaways.append(f"Cash generation is attractive with {fmt_pct(fcf_y_display)} FCF yield.")
    elif signal_labels["cash_return"] == "bad":
        takeaways.append(f"Cash return is light at {fmt_pct(fcf_y_display)} FCF yield.")
    if signal_labels["mispricing"] == "good":
        takeaways.append(f"Model-implied base case shows upside ({base_delta}).")
    elif signal_labels["mispricing"] == "ok":
        takeaways.append(f"Model-implied base case is not clearly above price ({base_delta}).")
    if signal_labels["headline"] == "bad" or signal_labels["risk_load"] == "bad":
        takeaways.append("Headline pressure is elevated; position sizing should stay conservative.")
    if not takeaways:
        takeaways.append("Not enough clean data yet; run refresh and re-check before acting.")
    takeaways_html = "".join(f"<li>{htmlmod.escape(t)}</li>" for t in takeaways[:4])

    html = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>IRONMAN HUD — {T}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap');
:root {{
  --bg:#070b12;
  --bg2:#101a2d;
  --card:#111a2b;
  --line:#243754;
  --text:#e3eeff;
  --muted:#9db0ce;
  --good:#1fd18b;
  --ok:#f4c267;
  --bad:#ff6f6f;
  --neutral:#8ca2c8;
}}
*{{box-sizing:border-box}}
body {{
  font-family:"Space Grotesk", ui-sans-serif, system-ui;
  background:
    radial-gradient(1000px 500px at 8% -12%, #28497d 0%, transparent 50%),
    radial-gradient(850px 450px at 95% 0%, #5b2459 0%, transparent 45%),
    linear-gradient(180deg, var(--bg2) 0%, var(--bg) 55%);
  color:var(--text); margin:0;
}}
.wrap {{ max-width: 1160px; margin: 0 auto; padding: 26px 20px 36px; }}
.hdr {{ display:flex; justify-content:space-between; align-items:flex-end; gap:16px; }}
h1 {{ margin:0; font-size: 34px; letter-spacing:0.2px; }}
.sub {{ color:var(--muted); font-size:14px; }}
.grid {{ display:grid; grid-template-columns: repeat(12, 1fr); gap: 14px; margin-top: 18px; }}
.card {{
  background:linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.00)), var(--card);
  border:1px solid var(--line);
  border-radius:16px; padding:14px;
  box-shadow: 0 10px 25px rgba(0,0,0,.25);
}}
.span-12 {{ grid-column: span 12; }}
.span-6 {{ grid-column: span 6; }}
.span-4 {{ grid-column: span 4; }}
.span-3 {{ grid-column: span 3; }}
.k {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.1em; }}
.v {{ font-size:24px; margin-top:7px; font-weight:700; }}
.small {{ font-size:14px; color:#c3d2eb; margin-top:8px; line-height:1.4; }}
.row {{ display:flex; justify-content:space-between; gap:10px; margin-top:9px; align-items:center; }}
.pill {{ padding:3px 9px; border-radius:999px; background:#10263f; border:1px solid #254a73; font-size:12px; }}
.tone {{ font-size:11px; border-radius:999px; padding:3px 8px; border:1px solid transparent; }}
.tone.good {{ color:var(--good); border-color:rgba(31,209,139,.35); background:rgba(31,209,139,.08); }}
.tone.ok {{ color:var(--ok); border-color:rgba(244,194,103,.35); background:rgba(244,194,103,.08); }}
.tone.bad {{ color:var(--bad); border-color:rgba(255,111,111,.35); background:rgba(255,111,111,.08); }}
.tone.neutral {{ color:var(--neutral); border-color:rgba(140,162,200,.35); background:rgba(140,162,200,.08); }}
.stone-grid {{ display:grid; grid-template-columns: repeat(6, 1fr); gap:10px; margin-top:10px; }}
.stone {{ border:1px solid var(--line); border-radius:12px; padding:10px; background:#0d1627; }}
.stone h4 {{ margin:0 0 6px 0; font-size:13px; }}
a {{ color:#8fd3ff; text-decoration:none; }}
.receipts{{margin:10px 0 0 0;padding:0;list-style:none;display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}}
.rct{{background:#0d1627;border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:10px 12px}}
.rct_title{{font-weight:700;font-size:13px;letter-spacing:.2px;margin-bottom:6px}}
.rct_body{{font-size:12px;line-height:1.35;opacity:.92}}
.rct_k{{opacity:.65;margin-right:6px}}
.pvt th, .pvt td {{ border-bottom:1px solid #1f2a3a; padding:8px 6px; text-align:left; font-size:13px; }}
.pvt th {{ color:var(--muted); text-transform:uppercase; letter-spacing:.08em; font-size:11px; }}
.aha {{
  border-left: 3px solid #3ea5ff;
  background: rgba(62,165,255,.07);
  padding: 10px 12px;
  border-radius: 10px;
  margin-top: 8px;
}}
.aha ul {{ margin:8px 0 0 16px; padding:0; }}
.aha li {{ margin: 5px 0; }}
@media (max-width: 980px) {{
  .stone-grid {{ grid-template-columns: repeat(2,1fr); }}
  .span-6,.span-4,.span-3 {{ grid-column: span 12; }}
}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <div>
      <h1>IRONMAN HUD — {T}</h1>
      <div class="sub">Clear, numbers-first decision cockpit with plain-English interpretation and audit trail.</div>
    </div>
    <div class="sub">File: {T}_IRONMAN_HUD.html</div>
  </div>

  <div class="grid">
    <div class="card span-12">
      <div class="k">1-Minute Mission Brief (Start Here)</div>
      <div class="row"><div>Verdict</div><div>{one_line_tone}</div></div>
      <div class="v" style="font-size:21px;">{htmlmod.escape(one_line_call)}</div>
      <div class="aha">
        <b>Why this verdict:</b>
        <ul>
          {takeaways_html}
        </ul>
      </div>
      <div class="small">Signal coverage: {good_count} strong, {bad_count} weak, {unknown_count} unknown.</div>
    </div>

    <div class="card span-12">
      <div class="k">Dual Audience Lens (Street-Simple + Desk-Deep)</div>
      <div class="row"><div>Accuracy-adjusted conviction</div><div><span class="pill">raw { _fmt_num(leg_raw) } -> adjusted { _fmt_num(leg_adj) } (penalty { _fmt_num(leg_pen) })</span></div></div>
      <div class="small"><b>Street-Simple:</b> {htmlmod.escape(street_simple)}</div>
      <div class="small"><b>Desk-Deep:</b> {htmlmod.escape(desk_deep)}</div>
    </div>

    <div class="card span-12">
      <div class="k">Ticker Lock (What You Are Viewing)</div>
      <div class="row"><div>Active ticker</div><div><span class="pill" style="font-weight:800;">{T}</span></div></div>
      <div class="small">Armor-themed labels are shown with plain-English meaning so any user can follow the decision path.</div>
    </div>

    <div class="card span-12">
      <div class="k">Infinity Readout (At a Glance / Core Signals)</div>
      <div class="stone-grid">
        <div class="stone"><h4>🔵 Time (Growth)</h4>{growth_tone}<div class="small">{fmt_pct(rev_yoy)} YoY sales growth.</div></div>
        <div class="stone"><h4>🟢 Power (Cash)</h4>{fcf_tone}<div class="small">{_fmt_usd(fcf_ttm_display)} FCF, margin {fmt_pct(fcf_m)}.</div></div>
        <div class="stone"><h4>🟡 Mind (Range)</h4>{'<span class="tone bad">Fallback cone</span>' if mc_fallback_used else '<span class="tone neutral">Probabilistic</span>'}<div class="small">P10 { _fmt_usd(mc_p10) } · P50 { _fmt_usd(mc_p50) } · P90 { _fmt_usd(mc_p90) }.</div></div>
        <div class="stone"><h4>🔴 Reality (Price Gap)</h4>{misprice_tone}<div class="small">Base vs price: {base_delta}.</div></div>
        <div class="stone"><h4>🟣 Space (Balance)</h4>{space_tone}<div class="small">Net debt { _fmt_usd(net_debt) } · ND/FCF { _fmt_x(nd_to_fcf) }.</div></div>
        <div class="stone"><h4>🟠 Soul (Risk)</h4>{shock_tone}<div class="small">News shock { _fmt_num(risk_shock) }, risk total { _fmt_num(risk_total) }.</div></div>
      </div>
    </div>

    <div class="card span-6">
      <div class="k">How To Read Outcomes (Plain-English Guide)</div>
      <div class="small">
        <b>Strong case:</b> positive growth, solid FCF, positive base-vs-price gap, and calm headline risk.<br/>
        <b>Mixed case:</b> decent cash metrics but uncertain valuation or rising headline pressure.<br/>
        <b>Weak case:</b> low/negative cash returns plus persistent negative risk headlines.
      </div>
      <div class="row"><div>FCF Yield Signal</div><div>{fcf_tone}</div></div>
      <div class="row"><div>Growth Signal</div><div>{growth_tone}</div></div>
      <div class="row"><div>News Shock Signal</div><div>{shock_tone}</div></div>
      <div class="row"><div>Risk Count Signal</div><div>{risk_tone}</div></div>
    </div>

    <div class="card span-6">
      <div class="k">Macro Context (Plain-English Impact)</div>
      <div class="row"><div>Regime</div><div>{macro_tone} <span class="pill">{htmlmod.escape(macro_regime)}</span></div></div>
      <div class="row"><div>10Y yield (DGS10)</div><div>{_fmt_num(macro_dgs10)}%</div></div>
      <div class="row"><div>Fed funds</div><div>{_fmt_num(macro_ff)}%</div></div>
      <div class="small">{htmlmod.escape(macro_explain)}</div>
      <div class="small">Source: {htmlmod.escape(macro_source)} · generated {htmlmod.escape(str(macro_generated))}{' · cached' if macro_used_cache else ''}</div>
    </div>

    <div class="card span-6">
      <div class="k">Core Snapshot (Key Numbers)</div>
      <div class="row"><div>Price</div><div><span class="pill">{_fmt_usd(price)}</span></div></div>
      <div class="row"><div>Market Cap</div><div><span class="pill">{_fmt_usd(mcap)}</span></div></div>
      <div class="row"><div>Sales growth (YoY)</div><div><span class="pill">{fmt_pct(rev_yoy)}</span></div></div>
      <div class="row"><div>Free cash flow (TTM)</div><div><span class="pill">{_fmt_usd(fcf_ttm_display)}</span></div></div>
      <div class="row"><div>FCF margin</div><div><span class="pill">{fmt_pct(fcf_m)}</span></div></div>
      <div class="row"><div>FCF yield</div><div><span class="pill">{fmt_pct(fcf_y_display)}</span></div></div>
      <div class="row"><div>Net debt</div><div><span class="pill">{_fmt_usd(net_debt)}</span></div></div>
      <div class="row"><div>Net debt / FCF</div><div><span class="pill">{_fmt_x(nd_to_fcf)}</span></div></div>
    </div>

    <div class="card span-6">
      <div class="k">Monte Carlo DCF (Distribution / Probability View)</div>
      <div class="row"><div>P10</div><div><span class="pill">{_fmt_usd(mc_p10)}</span></div></div>
      <div class="row"><div>P50</div><div><span class="pill">{_fmt_usd(mc_p50)}</span></div></div>
      <div class="row"><div>P90</div><div><span class="pill">{_fmt_usd(mc_p90)}</span></div></div>
      <div class="row"><div>Prob down ≥20%</div><div>{_fmt_pct((mc_down20 or 0)*100.0)}</div></div>
      <div class="row"><div>Prob up ≥20%</div><div>{_fmt_pct((mc_up20 or 0)*100.0)}</div></div>
      {f'<div class="small"><span class="tone bad">Monte Carlo fallback active</span> Synthetic cone used ({htmlmod.escape(str(mc_fallback_reason or "unknown_reason"))}).</div>' if mc_fallback_used else ''}
      <div class="small">Interpretation: this is a range of plausible values, not one exact target.</div>
      <div class="small">Source: {mc_path or "N/A"} (triangular assumptions over DCF cone)</div>
    </div>

    <div class="card span-6">
      <div class="k">DCF Cone (Price vs Intrinsic / Mispricing Check)</div>
      <div class="row"><div>Bear</div><div><span class="pill">{_fmt_usd(bear)}</span> <span class="sub">({_pct_delta(bear, price_used)})</span></div></div>
      <div class="row"><div>Base</div><div><span class="pill">{_fmt_usd(base)}</span> <span class="sub">({_pct_delta(base, price_used)})</span></div></div>
      <div class="row"><div>Bull</div><div><span class="pill">{_fmt_usd(bull)}</span> <span class="sub">({_pct_delta(bull, price_used)})</span></div></div>
      <div class="small">If Base is above market price, model implies potential upside (and vice versa).</div>
    </div>

    <div class="card span-12">
      <div class="k">Risk Counts (30d / Headline Pressure)</div>
      <div class="row"><div>Labor</div><div>{risk_labor}</div></div>
      <div class="row"><div>Regulatory</div><div>{risk_reg}</div></div>
      <div class="row"><div>Insurance</div><div>{risk_ins}</div></div>
      <div class="row"><div>Safety</div><div>{risk_safe}</div></div>
      <div class="row"><div>Competition</div><div>{risk_comp}</div></div>
      <div class="row"><div><b>Total</b></div><div><b>{risk_total}</b>{_pill("count")}</div></div>
      <div class="row"><div>News shock (30d)</div><div>{_fmt_num(risk_shock)}{_pill("score")}</div></div>
      <div class="small">Source: news_risk_summary_{T}.json — {risk_generated}</div>
    </div>

    <div class="card span-12">
      <div class="k">Stormbreaker Verdict (Thesis Stress Tests)</div>
      <div class="row"><div>Overall</div><div>{sb_tone}</div></div>
      <div class="row"><div>PASS</div><div><b>{sb_pass}</b></div></div>
      <div class="row"><div>FAIL</div><div><b>{sb_fail}</b></div></div>
      <div class="row"><div>UNKNOWN</div><div><b>{sb_unknown}</b></div></div>
      <div class="small">Stormbreaker checks whether your thesis claims are supported by current data.</div>
      <div class="small">Open full diagnostics: <a href="../../outputs/claim_evidence_{T}.html">claim_evidence_{T}.html</a></div>
    </div>

    <div class="card span-12">
      <div class="k">Receipts (Why These Numbers Matter / Audit Trail)</div>
      <div class="sub">Pulled from <code>outputs/receipts_{T}.json</code></div>
      {receipts_html}
    </div>

    <div class="card span-12">
      <div class="k">J.A.R.V.I.S. Sensor Bus (Metric Provenance)</div>
      <div class="small">Where each critical metric came from in this run (live provider vs cache).</div>
      <table class="pvt" style="width:100%; margin-top:8px; border-collapse:collapse;">
        <thead>
          <tr><th>Metric</th><th>Provider Used</th><th>Value Used</th></tr>
        </thead>
        <tbody>
          {provider_provenance_rows_html}
        </tbody>
      </table>
      <div class="small">Source file: <code>outputs/metric_provider_used_{T}.json</code></div>
    </div>

    <div class="card span-12">
      <div class="k">Quick Glossary (No Finance Background Needed)</div>
      <div class="small"><b>FCF (Free Cash Flow):</b> Cash left after running the business. More is better.</div>
      <div class="small"><b>FCF Yield:</b> Cash return relative to company value. Higher usually means better value.</div>
      <div class="small"><b>P10 / P50 / P90:</b> Conservative / middle / optimistic valuation scenarios.</div>
      <div class="small"><b>News Shock:</b> Headline mood score. More negative means more stress around the stock.</div>
      <div class="small"><b>Net Debt / FCF:</b> Years of current cash flow needed to repay net debt. Lower is safer.</div>
    </div>
  </div>

  <div class="small" style="margin-top:14px;">
    Open next: {next_links_html}
  </div>
</div>
</body>
</html>
"""

    # final sanitization: never show raw N/A in HUD
    html = html.replace("N/A", "—")

    out = canon / f"{T}_IRONMAN_HUD.html"
    out.write_text(html, encoding="utf-8")
    print("DONE ✅ wrote:", out)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)
