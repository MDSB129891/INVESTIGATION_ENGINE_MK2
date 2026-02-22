#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


STARTER_CLAIMS = [
    {
        "id": "rev_growth",
        "statement": "Revenue is still growing at a healthy pace",
        "metric": "latest_revenue_yoy_pct",
        "operator": ">=",
        "threshold": 10.0,
        "weight": 2,
    },
    {
        "id": "fcf_positive",
        "statement": "Free cash flow is positive",
        "metric": "latest_free_cash_flow",
        "operator": ">",
        "threshold": 0.0,
        "weight": 3,
    },
    {
        "id": "fcf_margin",
        "statement": "Free cash flow margin is solid",
        "metric": "latest_fcf_margin_pct",
        "operator": ">=",
        "threshold": 10.0,
        "weight": 2,
    },
    {
        "id": "valuation_fcf_yield",
        "statement": "Valuation is not expensive versus cash (FCF yield is decent)",
        "metric": "fcf_yield_pct",
        "operator": ">=",
        "threshold": 3.0,
        "weight": 2,
    },
    {
        "id": "news_shock_ok",
        "statement": "Recent news shock is not severe (not a headline crisis)",
        "metric": "news_shock_30d",
        "operator": ">=",
        "threshold": -15.0,
        "weight": 1,
    },
    {
        "id": "insurance_not_spiking",
        "statement": "Insurance risk is not spiking recently",
        "metric": "risk_insurance_neg_30d",
        "operator": "<=",
        "threshold": 3.0,
        "weight": 1,
    },
    {
        "id": "regulatory_not_spiking",
        "statement": "Regulatory risk is not spiking recently",
        "metric": "risk_regulatory_neg_30d",
        "operator": "<=",
        "threshold": 3.0,
        "weight": 1,
    },
    {
        "id": "labor_not_spiking",
        "statement": "Labor risk is not spiking recently",
        "metric": "risk_labor_neg_30d",
        "operator": "<=",
        "threshold": 3.0,
        "weight": 1,
    },
]


def _prompt(msg: str, default: str | None = None) -> str:
    if default is None:
        return input(msg).strip()
    v = input(f"{msg} [{default}]: ").strip()
    return v if v else default


def _prompt_yesno(msg: str, default_yes: bool = True) -> bool:
    d = "y" if default_yes else "n"
    v = input(f"{msg} (y/n) [{d}]: ").strip().lower()
    if not v:
        return default_yes
    return v.startswith("y")


def build_thesis(
    ticker: str,
    thesis_text: str,
    name: str | None,
    description: str | None,
    claims: List[Dict[str, Any]] | None,
) -> Dict[str, Any]:
    t = (ticker or "").upper().strip()
    if not t:
        raise SystemExit("Ticker is required.")

    desc = (description or "").strip()
    if not desc:
        desc = thesis_text.strip()

    nm = (name or "").strip()
    if not nm:
        # short headline from thesis text
        short = thesis_text.strip()
        if len(short) > 70:
            short = short[:67].rstrip() + "..."
        nm = f"{t}: {short}" if short else f"{t}: Thesis"

    return {
        "name": nm,
        "ticker": t,
        "description": desc,
        "claims": claims if claims is not None else list(STARTER_CLAIMS),
    }


def interactive_mode(ticker_arg: str | None, thesis_text_arg: str | None, out_path: str | None) -> Path:
    ticker = _prompt("Ticker", (ticker_arg or "AAPL").upper())
    thesis_text = _prompt("One-paragraph thesis description", thesis_text_arg or "")

    default_name = f"{ticker}: Thesis"
    name = _prompt("Thesis name (headline)", default_name)

    # if user didn’t provide description, use thesis_text
    description = thesis_text

    print("\nWe'll build claims (rules). Press Enter to accept defaults.\n")
    use_defaults = _prompt_yesno("Use default starter claims?", True)

    claims: List[Dict[str, Any]] = []
    base = list(STARTER_CLAIMS) if use_defaults else []

    for i, c in enumerate(base, start=1):
        keep = _prompt_yesno(f"Keep claim #{i}: {c['statement']}?", True)
        if not keep:
            continue
        thr = _prompt(f"  Threshold for {c['metric']} ({c['operator']})", str(c["threshold"]))
        w = _prompt("  Weight (importance)", str(c["weight"]))
        cc = dict(c)
        try:
            cc["threshold"] = float(thr)
        except Exception:
            cc["threshold"] = c["threshold"]
        try:
            cc["weight"] = int(float(w))
        except Exception:
            cc["weight"] = c["weight"]
        claims.append(cc)

    while _prompt_yesno("\nAdd another custom claim?", False):
        cid = _prompt("  id (short name)", "custom_claim")
        stmt = _prompt("  statement (plain English)", "My claim")
        metric = _prompt("  metric key (must exist in outputs)", "news_shock_30d")
        op = _prompt("  operator (>=, <=, >, <, ==)", ">=")
        thr = _prompt("  threshold (number)", "0")
        w = _prompt("  weight (1-5)", "1")
        try:
            thr_v: Any = float(thr)
        except Exception:
            thr_v = thr
        try:
            w_v: Any = int(float(w))
        except Exception:
            w_v = 1
        claims.append({
            "id": cid,
            "statement": stmt,
            "metric": metric,
            "operator": op,
            "threshold": thr_v,
            "weight": w_v,
        })

    thesis = build_thesis(ticker, thesis_text, name, description, claims)

    if out_path:
        out = Path(out_path)
    else:
        out = Path("theses") / f"{ticker}_custom.json"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(thesis, indent=2), encoding="utf-8")
    return out


def non_interactive_mode(ticker: str, thesis_text: str, out_path: str | None) -> Path:
    ticker = ticker.upper().strip()
    thesis_text = thesis_text.strip()

    thesis = build_thesis(
        ticker=ticker,
        thesis_text=thesis_text,
        name=None,
        description=thesis_text,
        claims=None,
    )

    out = Path(out_path) if out_path else Path("theses") / f"{ticker}_custom.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(thesis, indent=2), encoding="utf-8")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Create a thesis JSON for the engine.")
    p.add_argument("ticker", nargs="?", help="Ticker (e.g., GM)")
    p.add_argument("thesis", nargs="?", help='Thesis sentence/paragraph, e.g. "EV expansion drives margin recovery"')
    p.add_argument("--out", help="Output path (default: theses/<TICKER>_custom.json)")
    p.add_argument("--interactive", action="store_true", help="Force interactive prompts")
    args = p.parse_args()

    # If user provided ticker+thesis and didn't force interactive -> non-interactive
    if args.ticker and args.thesis and not args.interactive:
        out = non_interactive_mode(args.ticker, args.thesis, args.out)
        print("DONE ✅ Thesis created:")
        print(f"- {out.resolve()}")
        print("\nRun it like:")
        print(f"./scripts/run_galactus.sh {args.ticker.upper()} {out.as_posix()}")
        return

    # Otherwise interactive
    out = interactive_mode(args.ticker, args.thesis, args.out)
    print("\nDONE ✅ Thesis created:")
    print(f"- {out.resolve()}")
    print("\nRun it like:")
    # try to infer ticker from filename
    t = out.stem.split("_")[0].upper()
    print(f"./scripts/run_galactus.sh {t} {out.as_posix()}")


if __name__ == "__main__":
    main()
