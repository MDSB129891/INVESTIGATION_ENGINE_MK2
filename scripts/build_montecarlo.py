#!/usr/bin/env python3
import json, random, math
from pathlib import Path
from datetime import datetime

REPO = Path(__file__).resolve().parents[1]

def load_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _num(x):
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def main(ticker: str, n: int = 20000, seed: int = 7):
    random.seed(seed)
    T = ticker.upper()
    canon = REPO / "export" / f"CANON_{T}"
    canon.mkdir(parents=True, exist_ok=True)

    dcf_path = canon / f"{T}_DCF.json"
    core_path = canon / f"{T}_DECISION_CORE.json"

    dcf = load_json(dcf_path, {})
    core = load_json(core_path, {})

    metrics = (core.get("metrics") or {}) if isinstance(core, dict) else {}
    price = _num(metrics.get("price_used"))

    # Try multiple shapes for bear/base/bull
    bear = _num(dcf.get("bear")) if isinstance(dcf, dict) else None
    base = _num(dcf.get("base")) if isinstance(dcf, dict) else None
    bull = _num(dcf.get("bull")) if isinstance(dcf, dict) else None

    bear = bear if bear is not None else _num(metrics.get("bear_price"))
    base = base if base is not None else _num(metrics.get("base_price"))
    bull = bull if bull is not None else _num(metrics.get("bull_price"))

    fallback_used = False
    fallback_reason = None
    cone_source = "dcf_or_decision_core"
    price_source = "decision_core"
    if any(v is None for v in (bear, base, bull)):
        # Fallback mode: create a synthetic cone around current price.
        # Keep this explicit in output so users know it's a resilience mode.
        if price in (None, 0):
            # Try pulling price from comps snapshot
            try:
                import pandas as pd
                comps = REPO / "data" / "processed" / "comps_snapshot.csv"
                if comps.exists():
                    df = pd.read_csv(comps)
                    df["ticker"] = df["ticker"].astype(str).str.upper()
                    r = df[df["ticker"] == T]
                    if not r.empty:
                        price = _num(r.iloc[0].get("price"))
                        if price not in (None, 0):
                            price_source = "comps_snapshot"
            except Exception:
                pass

        if price in (None, 0):
            # Try live quote as a second fallback.
            try:
                import os
                import requests

                key = (os.getenv("FMP_API_KEY") or "").strip()
                if key:
                    url = "https://financialmodelingprep.com/stable/quote"
                    r = requests.get(url, params={"symbol": T, "apikey": key}, timeout=12)
                    if 200 <= r.status_code < 300:
                        arr = r.json() or []
                        if isinstance(arr, list) and arr:
                            price = _num((arr[0] or {}).get("price"))
                            if price not in (None, 0):
                                price_source = "fmp_live_quote"
            except Exception:
                pass

        if price in (None, 0):
            # Last-resort anchor: keep pipeline operational for any ticker.
            price = 100.0
            fallback_reason = "missing_dcf_and_price_used_default_anchor"
            price_source = "default_anchor"

        price = _num(price) or 100.0
        bear = price * 0.80
        base = price * 1.00
        bull = price * 1.35
        fallback_used = True
        if fallback_reason is None:
            fallback_reason = "missing_dcf_cone_price_anchored"
        cone_source = "synthetic_from_price"

    confidence_grade = "HIGH"
    confidence_reason = "Monte Carlo uses explicit valuation cone with market price context."
    if fallback_used:
        if price_source == "default_anchor":
            confidence_grade = "LOW"
            confidence_reason = "Synthetic cone used with default price anchor due to missing live inputs."
        else:
            confidence_grade = "MEDIUM"
            confidence_reason = "Synthetic cone used from price anchor because DCF cone was unavailable."

    a = float(min(bear, base, bull))
    b = float(max(bear, base, bull))
    c = float(base)  # mode = base

    sims = [random.triangular(a, b, c) for _ in range(n)]
    sims.sort()

    def q(pct):
        idx = int(round((pct/100.0) * (len(sims)-1)))
        idx = max(0, min(len(sims)-1, idx))
        return sims[idx]

    p10, p50, p90 = q(10), q(50), q(90)

    prob_down_20 = None
    prob_up_20 = None
    if price not in (None, 0):
        price = float(price)
        prob_down_20 = sum(1 for x in sims if x <= price*0.80) / len(sims)
        prob_up_20 = sum(1 for x in sims if x >= price*1.20) / len(sims)

    out = {
        "ticker": T,
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "method": "triangular_over_dcf_cone",
        "inputs": {
            "bear": float(bear), "base": float(base), "bull": float(bull),
            "price_used": price, "n": n, "seed": seed
        },
        "p10": float(p10),
        "p50": float(p50),
        "p90": float(p90),
        "prob_down_20pct": prob_down_20,
        "prob_up_20pct": prob_up_20,
        "source": {
            "dcf": str(dcf_path),
            "decision_core": str(core_path)
        },
        "results": {
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "confidence_grade": confidence_grade,
            "confidence_reason": confidence_reason,
            "cone_source": cone_source,
            "price_source": price_source,
            "p10": float(p10),
            "p50": float(p50),
            "p90": float(p90),
            "prob_down_20pct": prob_down_20,
            "prob_up_20pct": prob_up_20,
        },
    }

    out_path = canon / f"{T}_MONTECARLO.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("✅ wrote:", out_path)
    print("P10/P50/P90:", round(p10,2), round(p50,2), round(p90,2))
    if price not in (None, 0):
        print("Prob down ≥20%:", round(prob_down_20*100,2), "% | Prob up ≥20%:", round(prob_up_20*100,2), "%")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    main(args.ticker, n=args.n, seed=args.seed)
