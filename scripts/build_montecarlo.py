#!/usr/bin/env python3
import json, random
from pathlib import Path
from datetime import datetime

REPO = Path(__file__).resolve().parents[1]

def load_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default

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
    price = metrics.get("price_used")

    # Try multiple shapes for bear/base/bull
    bear = dcf.get("bear") if isinstance(dcf, dict) else None
    base = dcf.get("base") if isinstance(dcf, dict) else None
    bull = dcf.get("bull") if isinstance(dcf, dict) else None

    bear = bear if bear is not None else metrics.get("bear_price")
    base = base if base is not None else metrics.get("base_price")
    bull = bull if bull is not None else metrics.get("bull_price")

    if any(v is None for v in (bear, base, bull)):
        raise SystemExit(f"❌ Missing bear/base/bull. Found bear={bear}, base={base}, bull={bull}. "
                         f"Need {dcf_path} and/or {core_path} to contain these.")

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
        }
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
