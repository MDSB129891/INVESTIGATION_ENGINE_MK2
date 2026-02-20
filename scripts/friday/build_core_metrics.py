#!/usr/bin/env python3
import argparse, json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed"
OUT_CANON = ROOT / "export"

def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)

def main(ticker: str):
    T = ticker.upper().strip()
    canon = OUT_CANON / f"CANON_{T}"
    canon.mkdir(parents=True, exist_ok=True)

    # Try the best structured sources first
    comps = _read_csv(DATA / "comps_snapshot.csv")
    score = _read_csv(DATA / "score_components.csv")
    summary = None

    # Fallback: decision_summary.json (if your engine writes it)
    ds = ROOT / "outputs" / f"decision_summary_{T}.json"
    if not ds.exists():
        ds = ROOT / "outputs" / "decision_summary.json"
    if ds.exists():
        try:
            summary = json.loads(ds.read_text(encoding="utf-8"))
        except Exception:
            summary = None

    out = {"ticker": T, "sources": {}, "metrics": {}}

    # --- Pull key financial metrics (best effort) ---
    if not comps.empty:
        tcol = None
        for c in comps.columns:
            if c.lower() in ("ticker","symbol"):
                tcol = c
                break
        if tcol:
            comps[tcol] = comps[tcol].astype(str).str.upper()
            row = comps[comps[tcol] == T]
            if len(row):
                r = row.iloc[-1].to_dict()
                want = [
                    "revenue_ttm_yoy_pct",
                    "fcf_ttm",
                    "fcf_margin_ttm_pct",
                    "fcf_yield_pct",
                    "fcf_yield",
                    "market_cap",
                    "cash_and_equivalents",
                    "total_debt",
                    "net_debt",
                    "net_debt_fcf",
                    "ev",
                    "ev_ebitda",
                    "pe_ttm",
                    "eps_ttm",
                    "gross_margin_ttm_pct",
                    "operating_margin_ttm_pct",
                    "roe_ttm_pct",
                    "roic_ttm_pct",
                ]
                for k in want:
                    if k in r and pd.notna(r[k]):
                        out["metrics"][k] = r[k]
                out["sources"]["comps_snapshot"] = str(DATA / "comps_snapshot.csv")

    # --- Pull score/rating buckets if available ---
    if not score.empty:
        tcol = None
        for c in score.columns:
            if c.lower() in ("ticker","symbol"):
                tcol = c
                break
        if tcol:
            score[tcol] = score[tcol].astype(str).str.upper()
            row = score[score[tcol] == T]
            if len(row):
                r = row.iloc[-1].to_dict()
                for k in r.keys():
                    if k.lower().startswith("bucket_") or k.lower() in ("score","rating"):
                        if pd.notna(r[k]):
                            out["metrics"][k] = r[k]
                out["sources"]["score_components"] = str(DATA / "score_components.csv")

    # --- Fallback: decision_summary json (if present) ---
    if summary and isinstance(summary, dict):
        for k in ("score","rating","bucket_scores","bucket_breakdown"):
            if k in summary:
                out["metrics"][k] = summary[k]
        out["sources"]["decision_summary"] = str(ds)

    # Write JSON
    out_path = canon / f"{T}_CORE_METRICS.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    # Make a tiny HTML viewer too (nice for phone)
    html_path = canon / f"{T}_CORE_METRICS.html"
    rows = []
    rows.append(f"<h1>{T} — CORE METRICS</h1>")
    rows.append("<p>Best-effort pull from your processed data + decision summary.</p>")
    rows.append("<h2>Metrics</h2>")
    rows.append("<table border='1' cellpadding='6' cellspacing='0'>")
    rows.append("<tr><th>Key</th><th>Value</th></tr>")
    for k in sorted(out["metrics"].keys()):
        v = out["metrics"][k]
        rows.append(f"<tr><td><code>{k}</code></td><td>{v}</td></tr>")
    rows.append("</table>")
    rows.append("<h2>Sources</h2><pre>" + json.dumps(out["sources"], indent=2) + "</pre>")
    html_path.write_text("\n".join(rows), encoding="utf-8")

    print("DONE ✅ wrote:", out_path)
    print("DONE ✅ wrote:", html_path)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)
