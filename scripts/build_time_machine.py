#!/usr/bin/env python3
from pathlib import Path
import argparse
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def pick_date_col(df):
    candidates = ["date","asOfDate","as_of_date","fiscalDateEnding","fiscal_date","period_end","endDate","calendarYear"]
    for c in candidates:
        if c in df.columns:
            return c
    # last resort: any column with 'date' in name
    for c in df.columns:
        if "date" in c.lower():
            return c
    return None

def main(ticker: str):
    T = ticker.upper()
    canon = ROOT / "export" / f"CANON_{T}"
    canon.mkdir(parents=True, exist_ok=True)

    # Prefer TTM history file if present
    candidates = [
        ROOT / "data" / "processed" / "fundamentals_ttm_universe.csv",
        ROOT / "data" / "processed" / "fundamentals_quarterly_history_universe.csv",
    ]
    p = None
    for c in candidates:
        if c.exists():
            p = c
            break
    if not p:
        raise SystemExit("No fundamentals history CSV found in data/processed/")

    df = pd.read_csv(p)
    tcol = "ticker" if "ticker" in df.columns else ("symbol" if "symbol" in df.columns else None)
    if not tcol:
        raise SystemExit("No ticker/symbol col in fundamentals history file")

    df[tcol] = df[tcol].astype(str).str.upper()
    df = df[df[tcol] == T].copy()
    if df.empty:
        raise SystemExit(f"No rows for {T} in {p}")

    dcol = pick_date_col(df)
    if dcol:
        df["_date"] = pd.to_datetime(df[dcol], errors="coerce")
        df = df.sort_values("_date")
    else:
        df["_date"] = range(len(df))

    # pick a few interesting columns that usually exist
    interesting = []
    for c in ["revenue","revenue_ttm","fcf","fcf_ttm","ebitda","ebitda_ttm","netIncome","net_income","operatingCashFlow","operating_cash_flow"]:
        if c in df.columns:
            interesting.append(c)

    # fallback: show numeric columns if the usual ones aren't present
    if not interesting:
        nums = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        interesting = nums[:6]

    slim = df[["_date"] + interesting].tail(16).copy()

    # html table
    html = "<html><head><meta charset='utf-8'><title>TIME MACHINE — %s</title>" % T
    html += "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Arial;background:#0b0f14;color:#d7e3f4;padding:20px} table{border-collapse:collapse;width:100%%} td,th{border:1px solid #1f2a3a;padding:8px} th{background:#121a24}</style>"
    html += "</head><body>"
    html += f"<h1>TIME MACHINE — {T}</h1>"
    html += f"<p>Source: {p.name}</p>"
    html += slim.to_html(index=False)
    html += "</body></html>"

    out = canon / f"{T}_TIME_MACHINE.html"
    out.write_text(html, encoding="utf-8")
    print("DONE ✅ wrote:", out)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)
