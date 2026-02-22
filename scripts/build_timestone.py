#!/usr/bin/env python3
import argparse, math
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]

def _safe_float(x):
    try:
        if x is None: return None
        if isinstance(x, float) and math.isnan(x): return None
        return float(x)
    except Exception:
        return None

def _fmt_usd(x):
    x = _safe_float(x)
    if x is None: return "—"
    ax = abs(x)
    if ax >= 1e12: return f"${x/1e12:.2f}T"
    if ax >= 1e9:  return f"${x/1e9:.2f}B"
    if ax >= 1e6:  return f"${x/1e6:.2f}M"
    if ax >= 1e3:  return f"${x/1e3:.2f}K"
    return f"${x:,.0f}"

def _fmt_pct(x, digits=2):
    x = _safe_float(x)
    if x is None: return "—"
    return f"{x:.{digits}f}%"

def _fmt_num(x):
    x = _safe_float(x)
    if x is None: return "—"
    if abs(x) >= 1e9:  return f"{x/1e9:.2f}B"
    if abs(x) >= 1e6:  return f"{x/1e6:.2f}M"
    if abs(x) >= 1e3:  return f"{x/1e3:.2f}K"
    return f"{x:.0f}"

def _spark(vals):
    # tiny sparkline using unicode blocks
    blocks = "▁▂▃▄▅▆▇█"
    xs = [v for v in vals if v is not None]
    if len(xs) < 2:
        return "—"
    lo, hi = min(xs), max(xs)
    if hi == lo:
        return blocks[0] * len(vals)
    out = []
    for v in vals:
        if v is None:
            out.append("·")
        else:
            t = (v - lo) / (hi - lo)
            idx = int(round(t * (len(blocks)-1)))
            idx = max(0, min(len(blocks)-1, idx))
            out.append(blocks[idx])
    return "".join(out)

def _load_csv(path: Path):
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if "period_end" in df.columns:
        df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
        df = df.sort_values("period_end")
    return df

def _latest_nonnull(df, col):
    if df is None or col not in df.columns:
        return None
    s = df[col]
    s = s.dropna()
    return None if s.empty else s.iloc[-1]

def _table_rows(df, cols, n=8):
    if df is None or df.empty:
        return []
    view = df.tail(n).copy()
    rows = []
    for _, r in view.iterrows():
        pe = r.get("period_end")
        pe_str = pe.strftime("%Y-%m-%d") if hasattr(pe, "strftime") else str(pe)
        out = [pe_str]
        for c in cols:
            out.append(r.get(c))
        rows.append(out)
    return rows

def _html_table(title, subtitle, headers, rows, formatters):
    # formatters: list of callables aligned to headers
    th = "".join([f"<th>{h}</th>" for h in headers])
    body = []
    for row in rows:
        tds = []
        for i, cell in enumerate(row):
            fmt = formatters[i] if i < len(formatters) else (lambda x: x)
            tds.append(f"<td>{fmt(cell)}</td>")
        body.append("<tr>" + "".join(tds) + "</tr>")
    tbody = "\n".join(body) if body else '<tr><td colspan="99" style="opacity:.75">—</td></tr>'
    return f"""
    <div class="card wide">
      <div class="k">{title}</div>
      <div class="small">{subtitle}</div>
      <table>
        <thead><tr>{th}</tr></thead>
        <tbody>{tbody}</tbody>
      </table>
    </div>
    """

def main(ticker: str):
    T = ticker.upper()
    annual_path = REPO_ROOT / "data" / "processed" / "fundamentals_annual_history.csv"
    q_path = REPO_ROOT / "data" / "processed" / "fundamentals_quarterly_history_universe.csv"

    ann = _load_csv(annual_path)
    q = _load_csv(q_path)

    # filter to ticker if present
    if ann is not None and "ticker" in ann.columns:
        ann = ann[ann["ticker"].astype(str).str.upper() == T]
    if q is not None and "ticker" in q.columns:
        q = q[q["ticker"].astype(str).str.upper() == T]

    gen = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build a simple “what changed over time” snapshot (annual)
    ann_rev = list(ann["revenue"].tail(8)) if (ann is not None and "revenue" in ann.columns) else []
    ann_fcf = list(ann["free_cash_flow"].tail(8)) if (ann is not None and "free_cash_flow" in ann.columns) else []
    ann_margin = list(ann["fcf_margin_pct"].tail(8)) if (ann is not None and "fcf_margin_pct" in ann.columns) else []

    spark_rev = _spark([_safe_float(x) for x in ann_rev])
    spark_fcf = _spark([_safe_float(x) for x in ann_fcf])
    spark_mrg = _spark([_safe_float(x) for x in ann_margin])

    # Latest values for quick read
    latest_rev = _latest_nonnull(ann, "revenue")
    latest_fcf = _latest_nonnull(ann, "free_cash_flow")
    latest_mrg = _latest_nonnull(ann, "fcf_margin_pct")
    latest_cash = _latest_nonnull(ann, "cash")
    latest_debt = _latest_nonnull(ann, "debt")

    # Tables
    ann_rows = _table_rows(ann, ["revenue","free_cash_flow","fcf_margin_pct","revenue_yoy_pct","fcf_yoy_pct","cash","debt"], n=10)
    q_rows = _table_rows(q, ["revenue","free_cash_flow","cash","debt"], n=12)

    out = REPO_ROOT / "export" / f"CANON_{T}" / f"{T}_TIMESTONE.html"
    out.parent.mkdir(parents=True, exist_ok=True)

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>TIME STONE — {T}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Arial; background:#0b0f14; color:#d7e3f4; margin:0; }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 24px; }}
  h1 {{ margin:0; font-size: 28px; letter-spacing:0.5px; }}
  .sub {{ opacity:0.75; }}
  .grid {{ display:grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 18px; }}
  .card {{ background:#121a24; border:1px solid #1f2a3a; border-radius:14px; padding:14px; }}
  .wide {{ grid-column: 1 / -1; }}
  .k {{ opacity:0.7; font-size:12px; text-transform:uppercase; letter-spacing:0.08em; }}
  .v {{ font-size:22px; margin-top:6px; }}
  .small {{ font-size:14px; opacity:0.85; margin-top:8px; line-height:1.35; }}
  .pill {{ padding:2px 8px; border-radius:999px; background:#0e2236; border:1px solid #1a3a5a; display:inline-block; }}
  table {{ width:100%; border-collapse:collapse; margin-top:10px; }}
  th, td {{ border-bottom:1px solid #1f2a3a; padding:10px 8px; text-align:left; font-size:14px; }}
  th {{ opacity:.75; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
  a {{ color:#7cc4ff; text-decoration:none; }}
</style>
</head>
<body>
<div class="wrap">
  <div style="display:flex;justify-content:space-between;align-items:flex-end;gap:16px;">
    <div>
      <h1>TIME STONE — {T}</h1>
      <div class="sub">Company history view (what changed over time) · Generated: {gen}</div>
    </div>
    <div class="sub">File: {T}_TIMESTONE.html</div>
  </div>

  <div class="grid">
    <div class="card wide">
      <div class="k">WHAT YOU’RE LOOKING AT (plain English)</div>
      <div class="small" style="line-height:1.45;margin-top:6px;">
        <b>Goal:</b> show the company’s “movie” (revenue, cash, debt, free cash flow) so you can see trend + stability.<br/>
        <b>How to use:</b> growing revenue + growing free cash flow + stable debt is generally a healthy story.
      </div>

      <div class="small" style="margin-top:12px;">
        <span class="pill"><b>Revenue trend</b> {spark_rev}</span>
        <span class="pill" style="margin-left:10px;"><b>FCF trend</b> {spark_fcf}</span>
        <span class="pill" style="margin-left:10px;"><b>FCF margin trend</b> {spark_mrg}</span>
      </div>
    </div>

    <div class="card">
      <div class="k">Latest annual revenue</div>
      <div class="v">{_fmt_usd(latest_rev)}</div>
      <div class="small">How much the company sold in the most recent year.</div>
    </div>

    <div class="card">
      <div class="k">Latest annual free cash flow</div>
      <div class="v">{_fmt_usd(latest_fcf)}</div>
      <div class="small">Cash left after running the business + investments.</div>
    </div>

    <div class="card">
      <div class="k">Latest annual FCF margin</div>
      <div class="v">{_fmt_pct(latest_mrg)}</div>
      <div class="small">Of each $1 of sales, how much became real cash.</div>
    </div>

    <div class="card">
      <div class="k">Latest cash</div>
      <div class="v">{_fmt_usd(latest_cash)}</div>
      <div class="small">Cash on hand (financial flexibility).</div>
    </div>

    <div class="card">
      <div class="k">Latest debt</div>
      <div class="v">{_fmt_usd(latest_debt)}</div>
      <div class="small">Total debt (risk if it grows too fast).</div>
    </div>

    {_html_table(
      "Annual history (last 10 years shown)",
      "Bigger picture: use this to judge whether the business is improving year by year.",
      ["Period end","Revenue","Free cash flow","FCF margin","Revenue YoY","FCF YoY","Cash","Debt"],
      ann_rows,
      [lambda x: x, _fmt_usd, _fmt_usd, _fmt_pct, _fmt_pct, _fmt_pct, _fmt_usd, _fmt_usd]
    )}

    {_html_table(
      "Quarterly history (last 12 quarters shown)",
      "Short-term pulse: use this to spot recent acceleration/slowdown.",
      ["Period end","Revenue","Free cash flow","Cash","Debt"],
      q_rows,
      [lambda x: x, _fmt_usd, _fmt_usd, _fmt_usd, _fmt_usd]
    )}

    <div class="card wide">
      <div class="k">Sources</div>
      <div class="small">
        Annual: {annual_path}<br/>
        Quarterly: {q_path}
      </div>
    </div>

    <div class="small" style="margin-top:14px;">
      Open next: <a href="{T}_IRONMAN_HUD.html">IRONMAN HUD</a>
    </div>

  </div>
</div>
</body>
</html>
"""
    out.write_text(html, encoding="utf-8")
    print("DONE ✅ wrote:", out)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)
