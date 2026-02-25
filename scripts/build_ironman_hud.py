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
    mc_conf_grade = str(mc_r.get("confidence_grade") or ("LOW" if mc_fallback_used else "HIGH")).upper()
    mc_conf_reason = str(mc_r.get("confidence_reason") or ("Synthetic cone used due to missing valuation cone." if mc_fallback_used else "Simulation used full valuation cone inputs."))
    mc_conf_tone = (
        '<span class="tone good">High confidence</span>' if mc_conf_grade == "HIGH"
        else ('<span class="tone ok">Medium confidence</span>' if mc_conf_grade == "MEDIUM" else '<span class="tone bad">Low confidence</span>')
    )

    # Build next links dynamically so users don't click dead tabs.
    links = []
    next_candidates = [
        (f"{T}_TIMESTONE.html", canon / f"{T}_TIMESTONE.html", "Time Stone"),
        (f"{T}_NEWS_SOURCES.html", canon / f"{T}_NEWS_SOURCES.html", "J.A.R.V.I.S. News Sources"),
        (f"{T}_STORMBREAKER.html", canon / f"{T}_STORMBREAKER.html", "Stormbreaker"),
        (f"{T}_ARMOR_SYSTEMS.html", canon / f"{T}_ARMOR_SYSTEMS.html", "Armor systems"),
        (f"../../outputs/iron_legion_command_{T}.html", ROOT / "outputs" / f"iron_legion_command_{T}.html", "Iron Legion command"),
        (f"../../outputs/receipts_{T}.html", ROOT / "outputs" / f"receipts_{T}.html", "Receipts"),
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

    def _provider_metric_value(metric_key):
        item = metric_provider_used.get(metric_key, {}) if isinstance(metric_provider_used, dict) else {}
        return item.get("value") if isinstance(item, dict) else None

    # Fallback fills for core snapshot so HUD does not lose key values when one artifact is sparse.
    if price is None:
        price = _provider_metric_value("price")
    if mcap is None:
        mcap = _provider_metric_value("market_cap")
    if rev_yoy is None:
        rev_yoy = _provider_metric_value("revenue_ttm_yoy_pct")
    if fcf_ttm_display is None:
        fcf_ttm_display = _provider_metric_value("fcf_ttm")
    if fcf_m is None:
        fcf_m = _provider_metric_value("fcf_margin_ttm_pct")

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

    # --- Company Intel (free multi-source profile aggregator) ---
    ci = _load_json(ROOT / "outputs" / f"company_intel_{T}.json", {}) or {}
    ci_company = ci.get("company", {}) if isinstance(ci, dict) else {}
    ci_market = ci.get("market", {}) if isinstance(ci, dict) else {}
    ci_x = ci.get("crosscheck", {}) if isinstance(ci, dict) else {}
    ci_grade = str(ci.get("confidence_grade") or "UNKNOWN").upper()
    ci_cov = ci.get("coverage_fields_present")
    ci_tone = (
        '<span class="tone good">High</span>' if ci_grade == "HIGH"
        else ('<span class="tone ok">Medium</span>' if ci_grade == "MEDIUM" else '<span class="tone bad">Low</span>')
    )
    ci_name = ci_company.get("name") or T
    ci_sector = ci_company.get("sector") or "—"
    ci_industry = ci_company.get("industry") or "—"
    ci_country = ci_company.get("country") or "—"
    ci_exchange = ci_company.get("exchange") or "—"
    ci_cik = ci_company.get("sec_cik") or "—"
    ci_website = ci_company.get("website") or "—"
    ci_desc = (ci_company.get("description") or "No description available.").strip()
    ci_desc = (ci_desc[:280] + "...") if len(ci_desc) > 280 else ci_desc
    ci_price = _fmt_usd(ci_market.get("price"))
    ci_mcap = _fmt_usd(ci_market.get("market_cap"))
    ci_pvar = _fmt_pct(ci_x.get("price_variance_pct_fmp_vs_massive")) if ci_x.get("price_variance_pct_fmp_vs_massive") is not None else "—"
    ci_mvar = _fmt_pct(ci_x.get("market_cap_variance_pct")) if ci_x.get("market_cap_variance_pct") is not None else "—"
    snap_period_end = row.get("period_end") or "—"
    snap_revenue_ttm = row.get("revenue_ttm")
    snap_cash = row.get("cash")
    snap_debt = row.get("debt")

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

    # --- News source health snapshot ---
    news_sources_payload = _load_json(ROOT / "outputs" / f"news_sources_{T}.json", {}) or {}
    news_sources_enabled = news_sources_payload.get("enabled_sources") if isinstance(news_sources_payload, dict) else []
    if not isinstance(news_sources_enabled, list):
        news_sources_enabled = []
    news_sources_enabled_s = ", ".join(str(x).upper() for x in news_sources_enabled) if news_sources_enabled else "—"
    news_source_counts = news_sources_payload.get("source_counts_30d", {}) if isinstance(news_sources_payload, dict) else {}
    if not isinstance(news_source_counts, dict):
        news_source_counts = {}
    news_source_mix = ", ".join(
        f"{str(k).lower()}:{_fmt_num(v)}"
        for k, v in sorted(news_source_counts.items(), key=lambda kv: (-float(kv[1] or 0), str(kv[0])))
    ) if news_source_counts else "—"
    news_checks_passed = news_sources_payload.get("checks_passed") if isinstance(news_sources_payload, dict) else None
    news_checks_total = news_sources_payload.get("checks_total_enabled") if isinstance(news_sources_payload, dict) else None
    news_evidence_rows = news_sources_payload.get("evidence_rows_30d") if isinstance(news_sources_payload, dict) else None
    news_trust_grade = str(news_sources_payload.get("trust_grade") or "UNKNOWN").upper() if isinstance(news_sources_payload, dict) else "UNKNOWN"
    news_trust_tone = (
        '<span class="tone good">High</span>' if news_trust_grade == "HIGH"
        else ('<span class="tone ok">Medium</span>' if news_trust_grade == "MEDIUM" else '<span class="tone bad">Low</span>')
    )
    news_tab_path = canon / f"{T}_NEWS_SOURCES.html"
    news_tab_link = (
        f'<a href="{T}_NEWS_SOURCES.html">Open J.A.R.V.I.S. News Sources (Primary)</a>'
        if news_tab_path.exists()
        else f'<a href="../../outputs/news_evidence_{T}.html">Open raw news evidence</a>'
    )

    # --- Closest competitors snapshot (peer universe first, then market-cap proximity fallback) ---
    decision_summary = _load_json(ROOT / "outputs" / f"decision_summary_{T}.json", {}) or {}
    competitors_context = (
        "Competitor view unavailable right now. Run with peers (example: --peers MSFT,AMZN) to compare side-by-side."
    )
    competitors_rows_html = "<tr><td colspan='9' style='opacity:.75;'>No competitor rows available.</td></tr>"
    try:
        comps_all = pd.read_csv(ROOT / "data" / "processed" / "comps_snapshot.csv")
    except Exception:
        comps_all = pd.DataFrame()

    if not comps_all.empty and "ticker" in comps_all.columns:
        comps_all = comps_all.copy()
        comps_all["ticker"] = comps_all["ticker"].astype(str).str.upper()
        focus_comp = comps_all[comps_all["ticker"] == T]
        focus_comp_row = focus_comp.iloc[0].to_dict() if not focus_comp.empty else {}

        def _sf(v):
            try:
                return float(v)
            except Exception:
                return None

        # Risk totals from risk dashboard (TOTAL row)
        risk_total_map = {}
        try:
            risk_df = pd.read_csv(ROOT / "data" / "processed" / "news_risk_dashboard.csv")
            if not risk_df.empty and "ticker" in risk_df.columns:
                risk_df = risk_df.copy()
                risk_df["ticker"] = risk_df["ticker"].astype(str).str.upper()
                if "risk_tag" in risk_df.columns and "neg_count_30d" in risk_df.columns:
                    rr = risk_df[risk_df["risk_tag"].astype(str).str.upper() == "TOTAL"]
                    for _, rv in rr.iterrows():
                        risk_total_map[str(rv.get("ticker", "")).upper()] = _sf(rv.get("neg_count_30d"))
                elif "risk_total_30d" in risk_df.columns:
                    for _, rv in risk_df.iterrows():
                        risk_total_map[str(rv.get("ticker", "")).upper()] = _sf(rv.get("risk_total_30d"))
        except Exception:
            pass

        # 1) Use explicit run universe peers if present.
        ds_universe = decision_summary.get("universe", []) if isinstance(decision_summary, dict) else []
        if not isinstance(ds_universe, list):
            ds_universe = []
        peer_candidates = []
        for u in ds_universe:
            tu = str(u).upper().strip()
            if tu and tu != T and (comps_all["ticker"] == tu).any():
                peer_candidates.append(tu)
        method = "from your selected peers (run universe)"

        # 2) Fallback: closest by market-cap distance.
        if not peer_candidates:
            others = comps_all[comps_all["ticker"] != T].copy()
            if not others.empty:
                focus_mcap = _sf(focus_comp_row.get("market_cap"))
                if focus_mcap is not None and focus_mcap > 0:
                    others["_dist"] = (
                        (pd.to_numeric(others["market_cap"], errors="coerce") - focus_mcap).abs()
                        / max(abs(focus_mcap), 1.0)
                    )
                else:
                    others["_dist"] = pd.to_numeric(others["market_cap"], errors="coerce").isna().astype(float)
                others = others.sort_values(["_dist", "ticker"], ascending=[True, True])
                peer_candidates = others["ticker"].astype(str).tolist()
                method = "closest by market-cap distance"

        peer_rows = []
        focus_growth = _sf(focus_comp_row.get("revenue_ttm_yoy_pct"))
        focus_fcf_margin = _sf(focus_comp_row.get("fcf_margin_ttm_pct"))
        focus_risk_total = _sf(risk_total_map.get(T))
        for pt in peer_candidates[:4]:
            pr_df = comps_all[comps_all["ticker"] == pt]
            if pr_df.empty:
                continue
            pr = pr_df.iloc[0].to_dict()
            p_price = _sf(pr.get("price"))
            p_mcap = _sf(pr.get("market_cap"))
            p_growth = _sf(pr.get("revenue_ttm_yoy_pct"))
            p_fcf_margin = _sf(pr.get("fcf_margin_ttm_pct"))
            p_fcf_yield = _sf(pr.get("fcf_yield"))
            p_nd_fcf = _sf(pr.get("net_debt_to_fcf_ttm"))
            p_risk_total = _sf(risk_total_map.get(pt))

            compare_notes = []
            if focus_growth is not None and p_growth is not None:
                if p_growth >= focus_growth + 2:
                    compare_notes.append(f"faster growth than {T}")
                elif p_growth <= focus_growth - 2:
                    compare_notes.append(f"slower growth than {T}")
            if focus_fcf_margin is not None and p_fcf_margin is not None:
                if p_fcf_margin >= focus_fcf_margin + 2:
                    compare_notes.append(f"stronger cash margin than {T}")
                elif p_fcf_margin <= focus_fcf_margin - 2:
                    compare_notes.append(f"weaker cash margin than {T}")
            if focus_risk_total is not None and p_risk_total is not None:
                if p_risk_total >= focus_risk_total + 2:
                    compare_notes.append(f"higher headline risk than {T}")
                elif p_risk_total <= focus_risk_total - 2:
                    compare_notes.append(f"lower headline risk than {T}")

            issues = []
            if p_growth is not None and p_growth < 0:
                issues.append("shrinking sales")
            if p_fcf_margin is not None and p_fcf_margin < 5:
                issues.append("thin cash margin")
            if p_fcf_yield is not None and (p_fcf_yield * 100.0) < 4:
                issues.append("low cash yield")
            if p_nd_fcf is not None and p_nd_fcf > 4:
                issues.append("heavy debt load")
            if p_risk_total is not None and p_risk_total > 5:
                issues.append("elevated headline risk")

            quick_parts = []
            if compare_notes:
                quick_parts.append("Relative: " + ", ".join(compare_notes[:2]))
            if issues:
                quick_parts.append("Flags: " + ", ".join(issues[:3]))
            if not quick_parts:
                quick_parts.append("Quick scan: no major stress flags vs current thresholds.")
            quick_read = ". ".join(quick_parts) + "."

            peer_rows.append(
                "<tr>"
                f"<td><b>{htmlmod.escape(pt)}</b></td>"
                f"<td>{_fmt_usd(p_price)}</td>"
                f"<td>{_fmt_usd(p_mcap)}</td>"
                f"<td>{_fmt_pct(p_growth)}</td>"
                f"<td>{_fmt_pct(p_fcf_margin)}</td>"
                f"<td>{_fmt_pct((p_fcf_yield * 100.0) if p_fcf_yield is not None else None)}</td>"
                f"<td>{_fmt_x(p_nd_fcf)}</td>"
                f"<td>{_fmt_num(p_risk_total) if p_risk_total is not None else '—'}</td>"
                f"<td>{htmlmod.escape(quick_read)}</td>"
                "</tr>"
            )

        if peer_rows:
            competitors_rows_html = "".join(peer_rows)
            competitors_context = (
                f"Peers chosen {method}. This is a quick side-by-side read to show if {T} looks stronger or weaker than nearby alternatives."
            )
        else:
            competitors_context = (
                "No peers were available in `comps_snapshot.csv` for this run. Add peers in your run command to unlock this comparison."
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

    # --- Red flags (model + interpreted from current data/news) ---
    decision_red_flags = decision_summary.get("red_flags", []) if isinstance(decision_summary, dict) else []
    if not isinstance(decision_red_flags, list):
        decision_red_flags = []

    interpreted_flags = []
    rev_yoy_f = _safe_float(rev_yoy)
    fcf_y_f = _safe_float(fcf_y_display)
    fcf_margin_f = _safe_float(fcf_m)
    risk_shock_f = _safe_float(risk_shock)
    risk_total_f = _safe_float(risk_total)
    nd_to_fcf_f = _safe_float(nd_to_fcf)
    if rev_yoy_f is not None and rev_yoy_f < 0:
        interpreted_flags.append("Revenue is shrinking year-over-year.")
    if fcf_margin_f is not None and fcf_margin_f < 5:
        interpreted_flags.append("FCF margin is thin (<5%), so cash cushion is limited.")
    if fcf_y_f is not None and fcf_y_f < 4:
        interpreted_flags.append("FCF yield is low (<4%), so valuation support from cash return is weak.")
    if nd_to_fcf_f is not None and nd_to_fcf_f > 4:
        interpreted_flags.append("Debt load is high relative to cash generation (Net Debt / FCF > 4x).")
    if risk_shock_f is not None and risk_shock_f < 0:
        interpreted_flags.append("Headline tone is negative (news shock below 0).")
    if risk_total_f is not None and risk_total_f > 5:
        interpreted_flags.append("Risk-tagged negative headlines are elevated (risk total > 5).")
    if news_trust_grade == "LOW":
        interpreted_flags.append("News source coverage is weak this run; headline conclusions carry lower confidence.")

    combined_flags = []
    seen_flags = set()
    for f in [*decision_red_flags, *interpreted_flags]:
        fs = str(f).strip()
        if not fs:
            continue
        key = fs.lower()
        if key in seen_flags:
            continue
        seen_flags.add(key)
        combined_flags.append(fs)

    def _flag_explain(flag: str) -> str:
        x = str(flag).lower()
        if "revenue" in x and ("declin" in x or "shrink" in x):
            return "Falling sales can break growth-based thesis assumptions."
        if "fcf yield" in x:
            return "Lower cash return versus company value reduces valuation margin-of-safety."
        if "fcf margin" in x or "cash cushion" in x:
            return "Thin margin means less flexibility to absorb shocks."
        if "debt" in x or "net debt" in x:
            return "Higher leverage increases downside if business slows."
        if "headline" in x or "news shock" in x:
            return "Negative headlines can pressure price even when fundamentals are stable."
        if "risk-tag" in x or "risk total" in x:
            return "Repeated negative events raise probability of thesis disruption."
        if "freshness sla" in x or "data" in x:
            return "If data is stale, recommendations are less trustworthy."
        return "This condition weakens conviction and should be monitored before sizing up."

    red_flags_html = "".join(
        f"<tr><td>{htmlmod.escape(f)}</td><td>{htmlmod.escape(_flag_explain(f))}</td></tr>"
        for f in combined_flags[:12]
    ) if combined_flags else (
        "<tr><td colspan='2' style='opacity:.75;'>No major red flags detected in this run.</td></tr>"
    )

    confgov = _load_json(ROOT / "outputs" / f"confidence_governor_{T}.json", {}) or {}
    trust_pass = str(confgov.get("governed_action") or "").upper() != "HOLD FIRE"
    trust_badge = '<span class="tone good">TRUST PASS</span>' if trust_pass else '<span class="tone bad">TRUST FAIL</span>'
    trust_explain = "All trust gates passed." if trust_pass else "One or more trust gates failed (data quality/conviction/tests/MC)."

    def _signal_story(metric_name: str, value, unit: str, good_rule: str, okay_rule: str, meaning_good: str, meaning_ok: str, meaning_bad: str):
        fv = _safe_float(value)
        if fv is None:
            return {
                "metric": metric_name,
                "value": "—",
                "zone": "Unknown",
                "rule": f"Good: {good_rule} | Okay: {okay_rule}",
                "meaning": "Data missing right now. Wait for refresh before trusting this line.",
            }
        if metric_name == "Sales Growth (YoY)":
            zone = "Good" if fv >= 12 else ("Okay" if fv >= 4 else "Weak")
        elif metric_name == "FCF Margin":
            zone = "Good" if fv >= 12 else ("Okay" if fv >= 5 else "Weak")
        elif metric_name == "FCF Yield":
            zone = "Good" if fv >= 8 else ("Okay" if fv >= 4 else "Weak")
        elif metric_name == "Net Debt / FCF":
            zone = "Good" if fv <= 2 else ("Okay" if fv <= 4 else "Weak")
        elif metric_name == "News Shock (30d)":
            zone = "Good" if fv >= 20 else ("Okay" if fv >= 0 else "Weak")
        else:
            zone = "Unknown"

        if zone == "Good":
            meaning = meaning_good
        elif zone == "Okay":
            meaning = meaning_ok
        else:
            meaning = meaning_bad

        if unit == "pct":
            disp = _fmt_pct(fv)
        elif unit == "usd":
            disp = _fmt_usd(fv)
        elif unit == "x":
            disp = _fmt_x(fv)
        else:
            disp = _fmt_num(fv)

        return {
            "metric": metric_name,
            "value": disp,
            "zone": zone,
            "rule": f"Good: {good_rule} | Okay: {okay_rule}",
            "meaning": meaning,
            "today_plain": f"{metric_name} is {zone.lower()} right now ({disp}). {meaning}",
        }

    aha_rows = [
        _signal_story(
            "Sales Growth (YoY)", rev_yoy, "pct",
            ">= 12%", "4% to < 12%",
            "Demand is clearly expanding; story has momentum.",
            "Business is growing, but not fast enough to be a clear breakout.",
            "Growth is weak or shrinking; thesis needs stronger proof.",
        ),
        _signal_story(
            "FCF Margin", fcf_m, "pct",
            ">= 12%", "5% to < 12%",
            "Company converts sales into cash efficiently.",
            "Cash conversion is acceptable but not elite.",
            "Cash efficiency is thin; harder to self-fund growth.",
        ),
        _signal_story(
            "FCF Yield", fcf_y_display, "pct",
            ">= 8%", "4% to < 8%",
            "Cash return vs valuation is attractive.",
            "Valuation is fair to slightly expensive.",
            "Cash return is low for the price being paid.",
        ),
        _signal_story(
            "Net Debt / FCF", nd_to_fcf, "x",
            "<= 2.0x", "> 2.0x to 4.0x",
            "Balance sheet is flexible; lower solvency stress.",
            "Debt load is manageable but should be watched.",
            "Debt burden is heavy relative to cash generation.",
        ),
        _signal_story(
            "News Shock (30d)", risk_shock, "score",
            ">= 20", "0 to < 20",
            "Headline flow is stable; fewer negative surprises.",
            "Noise exists but not a full risk alarm.",
            "Headline pressure is elevated; expect volatility.",
        ),
    ]
    _zone_class = {"Good": "good", "Okay": "ok", "Weak": "bad", "Unknown": "neutral"}
    core_signal_rows_html = "".join(
        f"<tr>"
        f"<td><b>{htmlmod.escape(r['metric'])}</b></td>"
        f"<td>{htmlmod.escape(r['value'])}</td>"
        f"<td><span class=\"tone {_zone_class.get(r['zone'], 'neutral')}\">{htmlmod.escape(r['zone'])}</span></td>"
        f"<td>{htmlmod.escape(r.get('today_plain') or r['meaning'])}</td>"
        f"</tr>"
        for r in aha_rows
    )

    # --- Deep explanation layer: panel guide + metric field manual ---
    part_guide = [
        {
            "part": "Trust Gate",
            "question": "Can this run be trusted enough for a real decision?",
            "how": "If TRUST FAIL, treat the run as research only and refresh data before any position.",
            "mistake": "Using a failed-trust run as a buy/sell trigger.",
        },
        {
            "part": "1-Minute Mission Brief",
            "question": "What is the single-sentence conclusion right now?",
            "how": "Use this as a summary, then verify with Red Flags and Aha tables below.",
            "mistake": "Reading only the headline without checking why.",
        },
        {
            "part": "Company Intel",
            "question": "Who is this business and what balance-sheet shape does it have?",
            "how": "Confirm sector, debt load, cash, and coverage confidence before judging valuation.",
            "mistake": "Comparing companies from different sectors without context.",
        },
        {
            "part": "Closest Competitors",
            "question": "Is this ticker stronger or weaker than nearby alternatives?",
            "how": "Compare growth, cash margin, leverage, and risk totals side-by-side.",
            "mistake": "Comparing against unrelated tickers instead of true peers.",
        },
        {
            "part": "Infinity Readout",
            "question": "What do the 6 core dimensions say at a glance?",
            "how": "Look for agreement across Growth + Cash + Risk; mixed readings mean lower conviction.",
            "mistake": "Overweighting one good metric while ignoring weak risk or debt signals.",
        },
        {
            "part": "Aha Scoreboard",
            "question": "How does each key metric rank by fixed thresholds?",
            "how": "Use the same threshold table every run to compare apples-to-apples.",
            "mistake": "Changing thresholds mentally between tickers.",
        },
        {
            "part": "Monte Carlo + DCF Cone",
            "question": "What range of values is plausible, and how far is price from value?",
            "how": "Use P10/P50/P90 as probability range; avoid treating one point estimate as certainty.",
            "mistake": "Reading model outputs as guarantees.",
        },
        {
            "part": "Risk + News + Stormbreaker",
            "question": "Is the thesis being weakened by headlines or failing evidence checks?",
            "how": "Cross-check Risk Total, News Shock, and Stormbreaker fail count before sizing up.",
            "mistake": "Ignoring repeated negative headlines because fundamentals look good.",
        },
        {
            "part": "Red Flags + Receipts + Sensor Bus",
            "question": "What can break the thesis and where did each number come from?",
            "how": "Use Red Flags to spot failure modes; use Receipts/Sensor Bus for auditability.",
            "mistake": "Trusting numbers without checking source/provenance.",
        },
    ]
    part_guide_rows_html = "".join(
        "<tr>"
        f"<td><b>{htmlmod.escape(p['part'])}</b></td>"
        f"<td>{htmlmod.escape(p['question'])}</td>"
        f"<td>{htmlmod.escape(p['how'])}</td>"
        f"<td>{htmlmod.escape(p['mistake'])}</td>"
        "</tr>"
        for p in part_guide
    )

    def _metric_read(name: str, value):
        fv = _safe_float(value)
        if fv is None:
            return "Value is missing in this run; treat this metric as unresolved."
        if name == "growth":
            if fv >= 12:
                return "Strong demand momentum. Growth supports thesis expansion."
            if fv >= 4:
                return "Moderate growth. Thesis is alive but not dominant."
            return "Weak/negative growth. Thesis needs stronger confirmation."
        if name == "fcf_margin":
            if fv >= 12:
                return "Cash efficiency is strong. Business converts revenue into usable cash well."
            if fv >= 5:
                return "Cash efficiency is acceptable but not elite."
            return "Thin cash conversion. Company has less room for error."
        if name == "fcf_yield":
            if fv >= 8:
                return "Attractive cash return versus valuation."
            if fv >= 4:
                return "Fair cash return; valuation is not obviously cheap."
            return "Low cash return for valuation paid."
        if name == "nd_to_fcf":
            if fv <= 2:
                return "Debt appears manageable relative to cash generation."
            if fv <= 4:
                return "Debt is serviceable but worth monitoring."
            return "Debt burden is high relative to current cash output."
        if name == "news_shock":
            if fv >= 20:
                return "Headline tone is mostly stable."
            if fv >= 0:
                return "Mixed headline climate; monitor for trend deterioration."
            return "Negative headline pressure is elevated."
        if name == "risk_total":
            if fv <= 2:
                return "Low count of risk-tag negatives."
            if fv <= 5:
                return "Moderate risk event count."
            return "High risk-event frequency; thesis fragility is higher."
        if name == "mispricing":
            if fv > 0:
                return "Model base value is above price (potential upside gap)."
            return "Model base value is at/below price (limited upside by this model)."
        if name == "prob_up20":
            if fv >= 60:
                return "Model sees meaningful upside-skew probability."
            if fv >= 30:
                return "Upside scenario exists but not dominant."
            return "Low probability of +20% upside in this setup."
        if name == "prob_down20":
            if fv <= 20:
                return "Lower modeled downside-tail risk."
            if fv <= 40:
                return "Moderate downside-tail risk."
            return "High modeled downside-tail risk."
        return "Interpret with surrounding metrics for context."

    metric_manual = [
        {
            "metric": "Price",
            "value": _fmt_usd(price),
            "what": "Latest traded share price used as valuation anchor.",
            "why": "All upside/downside math is measured versus this anchor.",
            "formula": "Market last trade (provider quote)",
            "read": "Price alone does not imply cheap or expensive; compare with DCF/MC range.",
            "watch": "Intraday noise can be high; avoid overreacting to single prints.",
        },
        {
            "metric": "Market Cap",
            "value": _fmt_usd(mcap),
            "what": "Equity value = share price x shares outstanding.",
            "why": "Used in FCF yield and relative size comparisons.",
            "formula": "Price x Shares Outstanding",
            "read": "Larger cap often means stability but can reduce growth velocity.",
            "watch": "Share count changes (buybacks/dilution) shift comparability.",
        },
        {
            "metric": "Sales Growth (YoY)",
            "value": _fmt_pct(rev_yoy),
            "what": "Percent change in trailing-12-month revenue vs prior year.",
            "why": "Shows whether demand and adoption are expanding.",
            "formula": "((Revenue_TTM / Revenue_TTM_1Y_Ago) - 1) x 100",
            "read": _metric_read("growth", rev_yoy),
            "watch": "Acquisitions and one-time comps can distort true organic growth.",
        },
        {
            "metric": "FCF (TTM)",
            "value": _fmt_usd(fcf_ttm_display),
            "what": "Cash left after operating needs and capex over trailing 12 months.",
            "why": "Funds debt service, buybacks, reinvestment, and resilience.",
            "formula": "Operating Cash Flow - Capital Expenditures",
            "read": "Higher sustained FCF improves survival and optionality.",
            "watch": "One-off working-capital swings can temporarily inflate/deflate FCF.",
        },
        {
            "metric": "FCF Margin",
            "value": _fmt_pct(fcf_m),
            "what": "Share of revenue converted into free cash flow.",
            "why": "Measures operating quality and efficiency.",
            "formula": "(FCF_TTM / Revenue_TTM) x 100",
            "read": _metric_read("fcf_margin", fcf_m),
            "watch": "Capex cycles can compress margin temporarily in growth phases.",
        },
        {
            "metric": "FCF Yield",
            "value": _fmt_pct(fcf_y_display),
            "what": "Cash return generated relative to equity value.",
            "why": "Helps judge valuation support from real cash production.",
            "formula": "(FCF_TTM / Market_Cap) x 100",
            "read": _metric_read("fcf_yield", fcf_y_display),
            "watch": "Very low yield can be fine for high-growth firms only if growth is real.",
        },
        {
            "metric": "Net Debt / FCF",
            "value": _fmt_x(nd_to_fcf),
            "what": "Debt burden relative to annual cash generation.",
            "why": "Approximates balance-sheet stress and flexibility.",
            "formula": "Net_Debt / FCF_TTM",
            "read": _metric_read("nd_to_fcf", nd_to_fcf),
            "watch": "If FCF turns down, this ratio can deteriorate quickly.",
        },
        {
            "metric": "News Shock (30d)",
            "value": _fmt_num(risk_shock),
            "what": "Aggregate headline tone score over 30 days.",
            "why": "Captures sentiment pressure that fundamentals may not show yet.",
            "formula": "Sum of weighted negative/positive headline impacts",
            "read": _metric_read("news_shock", risk_shock),
            "watch": "Short-term media clusters can overstate near-term risk.",
        },
        {
            "metric": "Risk Total (30d)",
            "value": _fmt_num(risk_total),
            "what": "Count of risk-tagged negative events in the last 30 days.",
            "why": "Tracks event frequency (regulatory/labor/insurance/etc.).",
            "formula": "Count of negative risk-tag headlines",
            "read": _metric_read("risk_total", risk_total),
            "watch": "Repeated moderate negatives can matter more than one severe headline.",
        },
        {
            "metric": "Base-vs-Price Gap",
            "value": base_delta,
            "what": "Difference between model base valuation and current market price.",
            "why": "Primary mispricing signal for upside/downside framing.",
            "formula": "((DCF_Base / Price) - 1) x 100",
            "read": _metric_read("mispricing", base_delta_f),
            "watch": "Model quality depends on input freshness and assumptions.",
        },
        {
            "metric": "Prob Up >=20% (MC)",
            "value": _fmt_pct((mc_up20 * 100.0) if mc_up20 is not None else None),
            "what": "Simulated probability that valuation lands at least 20% above current price.",
            "why": "Quantifies upside scenario likelihood, not just direction.",
            "formula": "Monte Carlo share of outcomes with return >= +20%",
            "read": _metric_read("prob_up20", (mc_up20 * 100.0) if mc_up20 is not None else None),
            "watch": "If fallback cone is active, treat this as lower-confidence guidance.",
        },
        {
            "metric": "Prob Down >=20% (MC)",
            "value": _fmt_pct((mc_down20 * 100.0) if mc_down20 is not None else None),
            "what": "Simulated probability of at least 20% downside.",
            "why": "Helps size risk and avoid asymmetric downside setups.",
            "formula": "Monte Carlo share of outcomes with return <= -20%",
            "read": _metric_read("prob_down20", (mc_down20 * 100.0) if mc_down20 is not None else None),
            "watch": "Use with reliability grade; stale inputs can under/overstate tails.",
        },
    ]
    metric_manual_rows_html = "".join(
        "<tr>"
        f"<td><b>{htmlmod.escape(m['metric'])}</b></td>"
        f"<td>{htmlmod.escape(m['value'])}</td>"
        f"<td>{htmlmod.escape(m['what'])}</td>"
        f"<td>{htmlmod.escape(m['why'])}</td>"
        f"<td><code>{htmlmod.escape(m['formula'])}</code></td>"
        f"<td>{htmlmod.escape(m['read'])}</td>"
        f"<td>{htmlmod.escape(m['watch'])}</td>"
        "</tr>"
        for m in metric_manual
    )

    aha_decoder_html = "".join(
        f"<li><b>{htmlmod.escape(r['metric'])}</b>: {htmlmod.escape(r['value'])} -> "
        f"<span class=\"tone {_zone_class.get(r['zone'], 'neutral')}\">{htmlmod.escape(r['zone'])}</span>. "
        f"{htmlmod.escape(r.get('today_plain') or r['meaning'])}</li>"
        for r in aha_rows
    )
    aha_rows_html = "".join(
        "<tr>"
        f"<td>{htmlmod.escape(r['metric'])}</td>"
        f"<td>{htmlmod.escape(r['value'])}</td>"
        f"<td><span class=\"tone {_zone_class.get(r['zone'], 'neutral')}\">{htmlmod.escape(r['zone'])}</span></td>"
        f"<td>{htmlmod.escape(r['rule'])}</td>"
        f"<td>{htmlmod.escape(r['meaning'])}</td>"
        f"<td>{htmlmod.escape(r.get('today_plain') or r['meaning'])}</td>"
        "</tr>"
        for r in aha_rows
    )

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
.navstrip {{
  display:flex; flex-wrap:wrap; gap:8px; margin-top:12px;
  padding:10px; border:1px solid var(--line); border-radius:12px; background:#0d1627;
}}
.navstrip a {{
  border:1px solid #2a4468; background:#12233a; border-radius:999px; padding:6px 10px; font-size:12px;
}}
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
.aha-table th, .aha-table td {{ border-bottom:1px solid #1f2a3a; padding:8px 6px; text-align:left; font-size:13px; vertical-align:top; }}
.aha-table th {{ color:var(--muted); text-transform:uppercase; letter-spacing:.08em; font-size:11px; }}
.aha {{
  border-left: 3px solid #3ea5ff;
  background: rgba(62,165,255,.07);
  padding: 10px 12px;
  border-radius: 10px;
  margin-top: 8px;
}}
.aha ul {{ margin:8px 0 0 16px; padding:0; }}
.aha li {{ margin: 5px 0; }}
.fold {{ margin-top:8px; border:1px solid #274566; border-radius:12px; background:#0d1627; }}
.fold > summary {{
  cursor:pointer; list-style:none; padding:10px 12px; font-weight:700;
  display:flex; justify-content:space-between; align-items:center;
}}
.fold > summary::-webkit-details-marker {{ display:none; }}
.fold .fold-body {{ padding:0 12px 12px 12px; }}
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
  <div class="navstrip">
    <a href="#mission">Start Here</a>
    <a href="#core-signals">Core Signals</a>
    <a href="#infinity">Infinity Readout</a>
    <a href="#stormbreaker">Thesis Checks</a>
    <a href="#risk">Risk</a>
    <a href="#receipts">Receipts</a>
    <a href="#glossary">Glossary</a>
  </div>

  <div class="grid">
    <div class="card span-12">
      <div class="k">Trust Gate</div>
      <div class="row"><div>System trust status</div><div>{trust_badge}</div></div>
      <div class="small">{htmlmod.escape(trust_explain)}</div>
    </div>

    <div class="card span-12" id="mission">
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

    <div class="card span-12" id="core-signals">
      <div class="k">Reading Order (For New Users)</div>
      <div class="small">1) Read Mission Brief. 2) Check Core Signals table. 3) Verify Stormbreaker + Risk. 4) Open Deep Dive sections only if you need detail.</div>
      <table class="aha-table" style="width:100%; margin-top:8px; border-collapse:collapse;">
        <thead>
          <tr><th>Signal</th><th>Current</th><th>Zone</th><th>Plain-English Meaning</th></tr>
        </thead>
        <tbody>
          {core_signal_rows_html}
        </tbody>
      </table>
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
      <div class="k">Company Intel (Identity + Structure)</div>
      <div class="row"><div><b>{htmlmod.escape(str(ci_name))}</b> · {htmlmod.escape(str(ci_sector))} / {htmlmod.escape(str(ci_industry))}</div><div>{ci_tone} <span class="pill">{htmlmod.escape(ci_grade)}</span></div></div>
      <div class="row"><div>Exchange / Country</div><div>{htmlmod.escape(str(ci_exchange))} / {htmlmod.escape(str(ci_country))}</div></div>
      <div class="row"><div>SEC CIK</div><div>{htmlmod.escape(str(ci_cik))}</div></div>
      <div class="row"><div>Intel price / market cap</div><div>{ci_price} · {ci_mcap}</div></div>
      <div class="row"><div>Snapshot period end</div><div>{htmlmod.escape(str(snap_period_end))}</div></div>
      <div class="row"><div>Revenue (TTM)</div><div>{_fmt_usd(snap_revenue_ttm)}</div></div>
      <div class="row"><div>Cash / Debt</div><div>{_fmt_usd(snap_cash)} / {_fmt_usd(snap_debt)}</div></div>
      <div class="row"><div>Net debt / FCF</div><div>{_fmt_x(nd_to_fcf)}</div></div>
      <div class="row"><div>Provider variance (price / mcap)</div><div>{ci_pvar} / {ci_mvar}</div></div>
      <div class="small"><b>Coverage:</b> {htmlmod.escape(str(ci_cov if ci_cov is not None else '—'))} fields populated. <b>Website:</b> {htmlmod.escape(str(ci_website))}</div>
      <div class="small">{htmlmod.escape(ci_desc)}</div>
      <div class="small">Source file: <code>outputs/company_intel_{T}.json</code></div>
    </div>

    <div class="card span-12">
      <details class="fold">
        <summary><span>Closest Competitors (Deep Dive)</span><span class="small">Expand/Collapse</span></summary>
        <div class="fold-body">
          <div class="small">{htmlmod.escape(competitors_context)}</div>
          <table class="aha-table" style="width:100%; margin-top:8px; border-collapse:collapse;">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Price</th>
                <th>Market Cap</th>
                <th>Sales YoY</th>
                <th>FCF Margin</th>
                <th>FCF Yield</th>
                <th>Net Debt / FCF</th>
                <th>Risk Total (30d)</th>
                <th>Quick Read</th>
              </tr>
            </thead>
            <tbody>
              {competitors_rows_html}
            </tbody>
          </table>
          <div class="small">Tip: pass peers in Vision run (example: <code>--peers MSFT,AMZN</code>) for more relevant competitor matching.</div>
        </div>
      </details>
    </div>

    <div class="card span-12" id="infinity">
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
      <div class="k">Part-by-Part Walkthrough (How To Use Every Panel)</div>
      <div class="small">If you are new to finance, use this table as the HUD reading order and interpretation key.</div>
      <table class="aha-table" style="width:100%; margin-top:8px; border-collapse:collapse;">
        <thead>
          <tr><th>Panel</th><th>Question It Answers</th><th>How To Use It</th><th>Common Misread</th></tr>
        </thead>
        <tbody>
          {part_guide_rows_html}
        </tbody>
      </table>
    </div>

    <div class="card span-12">
      <details class="fold">
        <summary><span>Aha Mode: Apples-to-Apples Scoreboard (Deep Dive)</span><span class="small">Expand/Collapse</span></summary>
        <div class="fold-body">
          <div class="small">Same thresholds every run. This keeps comparisons fair and easy to understand across all tickers.</div>
          <div class="aha">
            <b>Interpretation Decoder:</b>
            <ul>
              {aha_decoder_html}
            </ul>
          </div>
          <table class="aha-table" style="width:100%; margin-top:8px; border-collapse:collapse;">
            <thead>
              <tr><th>Metric</th><th>Your Number</th><th>Zone</th><th>Rule</th><th>What It Means</th><th>Plain-English Today</th></tr>
            </thead>
            <tbody>
              {aha_rows_html}
            </tbody>
          </table>
        </div>
      </details>
    </div>

    <div class="card span-12">
      <details class="fold">
        <summary><span>Metric Field Manual (Detailed Explanations)</span><span class="small">Expand/Collapse</span></summary>
        <div class="fold-body">
          <div class="small">Each metric includes what it is, why it matters, formula, today’s interpretation, and watch-outs.</div>
          <table class="aha-table" style="width:100%; margin-top:8px; border-collapse:collapse;">
            <thead>
              <tr><th>Metric</th><th>Current</th><th>What It Is</th><th>Why It Matters</th><th>Formula</th><th>How To Read Today</th><th>Watch-Out</th></tr>
            </thead>
            <tbody>
              {metric_manual_rows_html}
            </tbody>
          </table>
        </div>
      </details>
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
      <div class="row"><div>Confidence grade</div><div>{mc_conf_tone} <span class="pill">{htmlmod.escape(mc_conf_grade)}</span></div></div>
      <div class="row"><div>P10</div><div><span class="pill">{_fmt_usd(mc_p10)}</span></div></div>
      <div class="row"><div>P50</div><div><span class="pill">{_fmt_usd(mc_p50)}</span></div></div>
      <div class="row"><div>P90</div><div><span class="pill">{_fmt_usd(mc_p90)}</span></div></div>
      <div class="row"><div>Prob down ≥20%</div><div>{_fmt_pct((mc_down20 or 0)*100.0)}</div></div>
      <div class="row"><div>Prob up ≥20%</div><div>{_fmt_pct((mc_up20 or 0)*100.0)}</div></div>
      {f'<div class="small"><span class="tone bad">Monte Carlo fallback active</span> Synthetic cone used ({htmlmod.escape(str(mc_fallback_reason or "unknown_reason"))}).</div>' if mc_fallback_used else ''}
      <div class="small"><b>Why confidence is {htmlmod.escape(mc_conf_grade)}:</b> {htmlmod.escape(mc_conf_reason)}</div>
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

    <div class="card span-12" id="risk">
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
      <div class="k">News Source Checks (Where Headlines Came From)</div>
      <div class="row"><div>Enabled sources</div><div>{htmlmod.escape(news_sources_enabled_s)}</div></div>
      <div class="row"><div>Source trust</div><div>{news_trust_tone} <span class="pill">{htmlmod.escape(news_trust_grade)}</span></div></div>
      <div class="row"><div>Preflight checks passed</div><div>{_fmt_num(news_checks_passed)} / {_fmt_num(news_checks_total)}</div></div>
      <div class="row"><div>Evidence rows (30d)</div><div>{_fmt_num(news_evidence_rows)}</div></div>
      <div class="row"><div>Source mix (30d)</div><div>{htmlmod.escape(news_source_mix)}</div></div>
      <div class="small">{news_tab_link}</div>
      <div class="small">Raw evidence: <a href="../../outputs/news_evidence_{T}.html">news_evidence_{T}.html</a></div>
    </div>

    <div class="card span-12" id="stormbreaker">
      <div class="k">Stormbreaker Verdict (Thesis Stress Tests)</div>
      <div class="row"><div>Overall</div><div>{sb_tone}</div></div>
      <div class="row"><div>PASS</div><div><b>{sb_pass}</b></div></div>
      <div class="row"><div>FAIL</div><div><b>{sb_fail}</b></div></div>
      <div class="row"><div>UNKNOWN</div><div><b>{sb_unknown}</b></div></div>
      <div class="small">Stormbreaker checks whether your thesis claims are supported by current data.</div>
      <div class="small">Open dedicated tab: <a href="{T}_STORMBREAKER.html">{T}_STORMBREAKER.html</a></div>
      <div class="small">Raw diagnostics: <a href="../../outputs/claim_evidence_{T}.html">claim_evidence_{T}.html</a></div>
    </div>

    <div class="card span-12">
      <details class="fold">
        <summary><span>Company Red Flags (Deep Dive)</span><span class="small">Expand/Collapse</span></summary>
        <div class="fold-body">
          <div class="small">Concrete issues detected in this run, translated to plain English.</div>
          <table class="aha-table" style="width:100%; margin-top:8px; border-collapse:collapse;">
            <thead>
              <tr><th>Red Flag</th><th>Why It Matters</th></tr>
            </thead>
            <tbody>
              {red_flags_html}
            </tbody>
          </table>
        </div>
      </details>
    </div>

    <div class="card span-12" id="receipts">
      <details class="fold">
        <summary><span>Receipts (Audit Trail)</span><span class="small">Expand/Collapse</span></summary>
        <div class="fold-body">
          <div class="sub">Pulled from <code>outputs/receipts_{T}.json</code></div>
          {receipts_html}
        </div>
      </details>
    </div>

    <div class="card span-12">
      <details class="fold">
        <summary><span>J.A.R.V.I.S. Sensor Bus (Metric Provenance)</span><span class="small">Expand/Collapse</span></summary>
        <div class="fold-body">
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
      </details>
    </div>

    <div class="card span-12" id="glossary">
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
