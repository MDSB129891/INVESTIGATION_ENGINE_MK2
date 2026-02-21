#!/usr/bin/env python3
import argparse, json, random
from pathlib import Path
from statistics import mean, pstdev

def load_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def tri(lo, mode, hi):
    return random.triangular(lo, hi, mode)

def q(sorted_vals, p):
    idx = int(round(p * (len(sorted_vals) - 1)))
    return sorted_vals[idx]

def run_mc(price, fcf_ttm, shares, net_debt,
           disc_tri, tg_tri, g1_tri, g2_tri,
           years_1=5, years_2=5, n=20000, seed=7):

    random.seed(seed)
    vals = []
    for _ in range(n):
        r  = tri(*disc_tri)
        tg = tri(*tg_tri)
        g1 = tri(*g1_tri)
        g2 = tri(*g2_tri)

        r  = clamp(r, 0.03, 0.20)
        tg = clamp(tg, -0.02, 0.06)

        f = fcf_ttm
        pv = 0.0

        for y in range(1, years_1 + 1):
            f *= (1.0 + g1)
            pv += f / ((1.0 + r) ** y)

        for y in range(years_1 + 1, years_1 + years_2 + 1):
            f *= (1.0 + g2)
            pv += f / ((1.0 + r) ** y)

        denom = (r - tg)
        if denom <= 0.002:
            continue

        f_terminal = f * (1.0 + tg)
        tv = f_terminal / denom
        pv += tv / ((1.0 + r) ** (years_1 + years_2))

        equity = pv - net_debt
        per_share = equity / shares if shares > 0 else None
        if per_share is None or per_share <= 0 or per_share != per_share:
            continue

        vals.append(per_share)

    if not vals:
        raise SystemExit("❌ Monte Carlo produced no valid samples (inputs/assumptions too tight).")

    vals.sort()
    p10, p50, p90 = q(vals, 0.10), q(vals, 0.50), q(vals, 0.90)
    mu = mean(vals)
    sd = pstdev(vals) if len(vals) > 1 else 0.0

    prob_down_20 = sum(1 for v in vals if v <= price * 0.80) / len(vals)
    prob_up_20   = sum(1 for v in vals if v >= price * 1.20) / len(vals)

    return {
        "n_requested": n,
        "n_used": len(vals),
        "inputs": {
            "price": price,
            "fcf_ttm": fcf_ttm,
            "shares": shares,
            "net_debt": net_debt,
            "years_stage1": years_1,
            "years_stage2": years_2,
            "discount_rate_tri": list(disc_tri),
            "terminal_growth_tri": list(tg_tri),
            "fcf_growth_stage1_tri": list(g1_tri),
            "fcf_growth_stage2_tri": list(g2_tri),
            "seed": seed
        },
        "results": {
            "p10": round(p10, 2),
            "p50": round(p50, 2),
            "p90": round(p90, 2),
            "mean": round(mu, 2),
            "stdev": round(sd, 2),
            "prob_down_20pct": round(prob_down_20, 4),
            "prob_up_20pct": round(prob_up_20, 4),
            "upside_vs_price_pct": {
                "p10": round((p10/price - 1)*100, 2),
                "p50": round((p50/price - 1)*100, 2),
                "p90": round((p90/price - 1)*100, 2),
                "mean": round((mu/price - 1)*100, 2),
            },
        }
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    T = args.ticker.upper()
    canon = Path(f"export/CANON_{T}")
    dc = load_json(canon / f"{T}_DECISION_CORE.json", {})
    cm = load_json(canon / f"{T}_CORE_METRICS.json", {})

    metrics = {}
    for src in (dc, cm):
        if isinstance(src, dict):
            m = src.get("metrics", {})
            if isinstance(m, dict):
                metrics.update(m)

    price = float(metrics.get("price_used") or metrics.get("price") or 0.0)
    fcf   = float(metrics.get("fcf_ttm") or metrics.get("latest_free_cash_flow") or 0.0)
    net_debt = float(metrics.get("net_debt") or 0.0)

    mcap = metrics.get("market_cap_used") or metrics.get("market_cap") or metrics.get("mcap")
    mcap = float(mcap or 0.0)
    shares = (mcap / price) if price > 0 and mcap > 0 else 0.0

    if price <= 0 or fcf == 0 or shares <= 0:
        raise SystemExit(f"❌ Missing inputs. price={price} fcf={fcf} shares={shares} mcap={mcap}")

    payload = run_mc(
        price=price, fcf_ttm=fcf, shares=shares, net_debt=net_debt,
        disc_tri=(0.08, 0.10, 0.12),
        tg_tri=(0.00, 0.02, 0.03),
        g1_tri=(0.04, 0.08, 0.12),
        g2_tri=(0.02, 0.04, 0.07),
        years_1=5, years_2=5,
        n=args.n, seed=args.seed
    )

    out = canon / f"{T}_MONTECARLO.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("✅ wrote:", out)

if __name__ == "__main__":
    main()
