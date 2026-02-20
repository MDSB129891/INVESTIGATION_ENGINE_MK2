#!/usr/bin/env python3
from pathlib import Path
import argparse
import pandas as pd
import json

ROOT = Path(__file__).resolve().parents[1]

def _num(x, default=None):
    try:
        if x is None:
            return default
        if isinstance(x, str) and x.strip() == "":
            return default
        return float(x)
    except Exception:
        return default

def load_snapshot_row(ticker: str):
    p = ROOT / "data" / "processed" / "comps_snapshot.csv"
    df = pd.read_csv(p)
    tcol = "ticker" if "ticker" in df.columns else ("symbol" if "symbol" in df.columns else None)
    if not tcol:
        raise SystemExit("No ticker/symbol column found in comps_snapshot.csv")
    df[tcol] = df[tcol].astype(str).str.upper()
    row = df[df[tcol] == ticker.upper()]
    if row.empty:
        raise SystemExit(f"{ticker} not found in {p}")
    return row.iloc[0]

def load_price_from_quotes(ticker: str):
    # fallback: raw quotes file (format may vary)
    p = ROOT / "data" / "raw" / "quotes_universe_raw.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    tcol = None
    for c in df.columns:
        if c.lower() in ("ticker", "symbol"):
            tcol = c
            break
    if not tcol:
        return None
    df[tcol] = df[tcol].astype(str).str.upper()
    r = df[df[tcol] == ticker.upper()]
    if r.empty:
        return None

    # try common price fields
    for c in ["price", "last", "close", "adjClose", "adj_close", "previousClose", "previous_close"]:
        if c in r.columns:
            px = _num(r.iloc[-1][c])
            if px and px > 0:
                return px
    return None

def dcf_enterprise_value(fcf, growth, discount, terminal_growth, years=5):
    # simple 5y + terminal DCF on FCF
    pv = 0.0
    f = fcf
    for i in range(1, years + 1):
        f = f * (1 + growth)
        pv += f / ((1 + discount) ** i)
    tv = (f * (1 + terminal_growth)) / (discount - terminal_growth)
    pv += tv / ((1 + discount) ** years)
    return pv

def main(ticker: str):
    row = load_snapshot_row(ticker)

    fcf = _num(row.get("fcf_ttm"), 0.0)
    net_debt = _num(row.get("net_debt"), 0.0)

    # Try to get price + market cap + shares
    price = _num(row.get("price"), None) or _num(row.get("share_price"), None) or _num(row.get("last_price"), None)
    market_cap = _num(row.get("market_cap"), None) or _num(row.get("marketcap"), None)

    shares = _num(row.get("shares_outstanding"), None) or _num(row.get("shares"), None)

    # fallback price from quotes CSV
    if (price is None or price <= 0) and ticker:
        price = load_price_from_quotes(ticker)

    # derive shares if missing
    if (shares is None or shares <= 0) and market_cap and price and price > 0:
        shares = market_cap / price

    if not fcf or fcf <= 0:
        raise SystemExit("FCF not positive. DCF not meaningful.")

    if not shares or shares <= 0:
        raise SystemExit(
            "Could not determine shares_outstanding. "
            "Add shares_outstanding or (market_cap + price) to comps_snapshot.csv."
        )

    # Assumptions (edit later)
    discount = 0.10
    terminal_growth = 0.02

    bear_growth = 0.03
    base_growth = 0.08
    bull_growth = 0.12

    # Enterprise value from DCF, then equity value
    bear_ev = dcf_enterprise_value(fcf, bear_growth, discount, terminal_growth)
    base_ev = dcf_enterprise_value(fcf, base_growth, discount, terminal_growth)
    bull_ev = dcf_enterprise_value(fcf, bull_growth, discount, terminal_growth)

    bear_equity = bear_ev - net_debt
    base_equity = base_ev - net_debt
    bull_equity = bull_ev - net_debt

    bear_px = bear_equity / shares
    base_px = base_equity / shares
    bull_px = bull_equity / shares

    def pct_upside(target, ref):
        if not ref or ref <= 0:
            return None
        return (target / ref - 1.0) * 100.0

    result = {
        "ticker": ticker.upper(),
        "inputs": {
            "fcf_ttm": fcf,
            "net_debt": net_debt,
            "shares_used": shares,
            "price_used": price,
            "market_cap_used": market_cap
        },
        "assumptions": {
            "discount_rate": discount,
            "terminal_growth": terminal_growth,
            "bear_growth": bear_growth,
            "base_growth": base_growth,
            "bull_growth": bull_growth
        },
        "valuation_per_share": {
            "bear_price": round(bear_px, 2),
            "base_price": round(base_px, 2),
            "bull_price": round(bull_px, 2),
        },
        "upside_downside_vs_price_pct": {
            "bear": None if price is None else round(pct_upside(bear_px, price), 1),
            "base": None if price is None else round(pct_upside(base_px, price), 1),
            "bull": None if price is None else round(pct_upside(bull_px, price), 1),
        }
    }

    out = ROOT / "export" / f"CANON_{ticker.upper()}" / f"{ticker.upper()}_DCF.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("DONE ✅ wrote:", out)
    print(json.dumps(result, indent=2))

    # sanity note
    if price is None:
        print("\n⚠️ Note: price_used is missing, so upside/downside is N/A.")
    else:
        print(f"\n✅ price_used: {price:.2f}")
        print("✅ per-share values look sane if they are in the same *ballpark* as price.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)
