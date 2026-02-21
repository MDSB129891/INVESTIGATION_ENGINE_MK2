#!/usr/bin/env python3
import argparse, json
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = REPO_ROOT / "data" / "processed"

def _load_csv(path: Path):
    import pandas as pd
    if not path.exists():
        return None
    return pd.read_csv(path)

def _fmt_money(x):
    try:
        if x is None: return "N/A"
        x = float(x)
    except Exception:
        return "N/A"
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e12: return f"{sign}${x/1e12:.2f}T"
    if x >= 1e9:  return f"{sign}${x/1e9:.2f}B"
    if x >= 1e6:  return f"{sign}${x/1e6:.2f}M"
    if x >= 1e3:  return f"{sign}${x/1e3:.2f}K"
    return f"{sign}${x:.0f}"

def _fmt_pct(x):
    try:
        if x is None: return "N/A"
        return f"{float(x):.2f}%"
    except Exception:
        return "N/A"

def _coerce_date(df, col):
    # keep as string YYYY-MM-DD for chart labels
    df[col] = df[col].astype(str)

def main(ticker: str):
    import pandas as pd

    T = ticker.upper()
    q_path = PROCESSED / "fundamentals_quarterly_history_universe.csv"
    a_path = PROCESSED / "fundamentals_annual_history.csv"

    q = _load_csv(q_path)
    a = _load_csv(a_path)

    if q is None:
        raise SystemExit(f"❌ missing: {q_path}")
    if a is None:
        raise SystemExit(f"❌ missing: {a_path}")

    q["ticker"] = q["ticker"].astype(str).str.upper()
    q = q[q["ticker"] == T].copy()
    if q.empty:
        raise SystemExit(f"❌ no quarterly history rows for {T} in {q_path}")

    _coerce_date(q, "period_end")
    _coerce_date(a, "period_end")

    # sort
    q = q.sort_values("period_end")
    a = a.sort_values("period_end")

    # derive helpful series
    q["fcf_margin_pct"] = (q["free_cash_flow"] / q["revenue"]) * 100.0

    # pack series for JS
    def pack(df, xcol, ycol):
        xs = df[xcol].astype(str).tolist()
        ys = []
        for v in df[ycol].tolist():
            try:
                ys.append(None if pd.isna(v) else float(v))
            except Exception:
                ys.append(None)
        return xs, ys

    qx, q_rev = pack(q, "period_end", "revenue")
    _,  q_ocf = pack(q, "period_end", "operating_cash_flow")
    _,  q_cap = pack(q, "period_end", "capex_spend")
    _,  q_fcf = pack(q, "period_end", "free_cash_flow")
    _,  q_cash= pack(q, "period_end", "cash")
    _,  q_debt= pack(q, "period_end", "debt")
    _,  q_mrg = pack(q, "period_end", "fcf_margin_pct")

    ax, a_rev = pack(a, "period_end", "revenue")
    _,  a_fcf = pack(a, "period_end", "free_cash_flow")
    _,  a_rev_yoy = pack(a, "period_end", "revenue_yoy_pct")
    _,  a_fcf_yoy = pack(a, "period_end", "fcf_yoy_pct")
    _,  a_mrg = pack(a, "period_end", "fcf_margin_pct")

    canon = REPO_ROOT / "export" / f"CANON_{T}"
    canon.mkdir(parents=True, exist_ok=True)
    out = canon / f"{T}_TIMESTONE.html"

    generated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # last snapshots for “take by the hand” explainers
    q_last = q.iloc[-1].to_dict()
    a_last = a.iloc[-1].to_dict() if len(a) else {}

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>TIME STONE — {T}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body {{ font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Arial; background:#0b0f14; color:#d7e3f4; margin:0; }}
    .wrap {{ max-width:1100px; margin:0 auto; padding:24px; }}
    h1 {{ margin:0; font-size:28px; }}
    .sub {{ opacity:.75; margin-top:6px; }}
    .grid {{ display:grid; grid-template-columns:1fr; gap:14px; margin-top:16px; }}
    .card {{ background:#121a24; border:1px solid #1f2a3a; border-radius:14px; padding:14px; }}
    .k {{ opacity:.75; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
    .small {{ opacity:.85; line-height:1.45; margin-top:8px; }}
    .row {{ display:flex; justify-content:space-between; gap:12px; margin-top:8px; }}
    .pill {{ padding:2px 8px; border-radius:999px; background:#0e2236; border:1px solid #1a3a5a; }}
    a {{ color:#7cc4ff; text-decoration:none; }}
    canvas {{ margin-top:10px; }}
    .two {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
    @media (max-width: 900px) {{ .two {{ grid-template-columns:1fr; }} }}
    table {{ width:100%; border-collapse:collapse; margin-top:10px; }}
    th, td {{ border-bottom:1px solid #1f2a3a; padding:8px; font-size:13px; text-align:left; }}
    th {{ opacity:.8; }}
  </style>
</head>
<body>
<div class="wrap">
  <h1>TIME STONE — {T}</h1>
  <div class="sub">“What changed over time?” (Revenue, Cash, Debt, Free Cash Flow). Generated: {generated}</div>

  <div class="grid">

    <div class="card">
      <div class="k">How to read this (plain English)</div>
      <div class="small">
        This page is your <b>company time machine</b>.
        <ul>
          <li><b>Revenue</b> = money coming in.</li>
          <li><b>Operating cash flow</b> = cash the business generates from operations.</li>
          <li><b>Capex</b> = cash spent to maintain/grow the business (we treat it as a cash outflow).</li>
          <li><b>Free cash flow (FCF)</b> = operating cash flow minus capex (cash left over).</li>
          <li><b>Cash & Debt</b> = safety vs pressure.</li>
        </ul>
        The goal: understand whether today’s “good numbers” are <b>new</b>, <b>stable</b>, or <b>fragile</b>.
      </div>
    </div>

    <div class="card two">
      <div>
        <div class="k">Quarterly “engine” (last datapoint)</div>
        <div class="row"><div>Period</div><div><span class="pill">{q_last.get("period_end","N/A")}</span></div></div>
        <div class="row"><div>Revenue</div><div><span class="pill">{_fmt_money(q_last.get("revenue"))}</span></div></div>
        <div class="row"><div>Operating cash flow</div><div><span class="pill">{_fmt_money(q_last.get("operating_cash_flow"))}</span></div></div>
        <div class="row"><div>Capex (spend)</div><div><span class="pill">{_fmt_money(q_last.get("capex_spend"))}</span></div></div>
        <div class="row"><div>Free cash flow</div><div><span class="pill">{_fmt_money(q_last.get("free_cash_flow"))}</span></div></div>
        <div class="row"><div>FCF margin (derived)</div><div><span class="pill">{_fmt_pct(q_last.get("fcf_margin_pct"))}</span></div></div>
        <div class="small">If Revenue rises but FCF falls, it can mean growth is getting more expensive.</div>
      </div>
      <div>
        <div class="k">Annual “big picture” (last datapoint)</div>
        <div class="row"><div>Period</div><div><span class="pill">{a_last.get("period_end","N/A")}</span></div></div>
        <div class="row"><div>Revenue</div><div><span class="pill">{_fmt_money(a_last.get("revenue"))}</span></div></div>
        <div class="row"><div>Free cash flow</div><div><span class="pill">{_fmt_money(a_last.get("free_cash_flow"))}</span></div></div>
        <div class="row"><div>Revenue YoY</div><div><span class="pill">{_fmt_pct(a_last.get("revenue_yoy_pct"))}</span></div></div>
        <div class="row"><div>FCF YoY</div><div><span class="pill">{_fmt_pct(a_last.get("fcf_yoy_pct"))}</span></div></div>
        <div class="row"><div>FCF margin</div><div><span class="pill">{_fmt_pct(a_last.get("fcf_margin_pct"))}</span></div></div>
        <div class="small">YoY shows “how fast it’s changing” — margin shows “how healthy the growth is.”</div>
      </div>
    </div>

    <div class="card">
      <div class="k">Quarterly trends</div>
      <div class="small">These charts answer: “Is the cash engine improving or wobbling?”</div>
      <canvas id="q_rev"></canvas>
      <canvas id="q_fcf"></canvas>
      <canvas id="q_cash_debt"></canvas>
      <canvas id="q_margin"></canvas>
    </div>

    <div class="card">
      <div class="k">Annual trends</div>
      <div class="small">These charts answer: “What did the whole year look like?”</div>
      <canvas id="a_rev_fcf"></canvas>
      <canvas id="a_yoy"></canvas>
      <canvas id="a_margin"></canvas>
    </div>

    <div class="card">
      <div class="k">Data source</div>
      <div class="small">
        Quarterly: <span class="pill">{q_path}</span><br/>
        Annual: <span class="pill">{a_path}</span><br/>
        Built for: <b>{T}</b>
      </div>
    </div>

  </div>
</div>

<script>
const QX = {json.dumps(qx)};
const AX = {json.dumps(ax)};

function lineChart(id, labels, series, title) {{
  new Chart(document.getElementById(id), {{
    type: 'line',
    data: {{
      labels,
      datasets: series.map(s => ({{
        label: s.label,
        data: s.data,
        tension: 0.2
      }}))
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ display: true }},
        title: {{ display: true, text: title }}
      }},
      scales: {{
        y: {{
          ticks: {{
            callback: (v) => {{
              // money-ish formatting (best-effort)
              const x = Number(v);
              if (!isFinite(x)) return v;
              const abs = Math.abs(x);
              const sign = x < 0 ? "-" : "";
              if (abs >= 1e12) return sign + "$" + (abs/1e12).toFixed(2) + "T";
              if (abs >= 1e9)  return sign + "$" + (abs/1e9).toFixed(2) + "B";
              if (abs >= 1e6)  return sign + "$" + (abs/1e6).toFixed(2) + "M";
              if (abs >= 1e3)  return sign + "$" + (abs/1e3).toFixed(2) + "K";
              return sign + "$" + abs.toFixed(0);
            }}
          }}
        }}
      }}
    }}
  }});
}}

function pctChart(id, labels, series, title) {{
  new Chart(document.getElementById(id), {{
    type: 'line',
    data: {{
      labels,
      datasets: series.map(s => ({{
        label: s.label,
        data: s.data,
        tension: 0.2
      }}))
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ display: true }},
        title: {{ display: true, text: title }}
      }},
      scales: {{
        y: {{
          ticks: {{
            callback: (v) => {{
              const x = Number(v);
              if (!isFinite(x)) return v;
              return x.toFixed(1) + "%";
            }}
          }}
        }}
      }}
    }}
  }});
}}

lineChart("q_rev", QX, [
  {{label:"Revenue", data:{json.dumps(q_rev)}}},
  {{label:"Operating cash flow", data:{json.dumps(q_ocf)}}},
], "Quarterly Revenue + Operating Cash Flow");

lineChart("q_fcf", QX, [
  {{label:"Free cash flow", data:{json.dumps(q_fcf)}}},
  {{label:"Capex spend", data:{json.dumps(q_cap)}}},
], "Quarterly Free Cash Flow + Capex");

lineChart("q_cash_debt", QX, [
  {{label:"Cash", data:{json.dumps(q_cash)}}},
  {{label:"Debt", data:{json.dumps(q_debt)}}},
], "Quarterly Cash vs Debt (safety vs pressure)");

pctChart("q_margin", QX, [
  {{label:"FCF margin (derived)", data:{json.dumps(q_mrg)}}},
], "Quarterly FCF Margin (%)");

lineChart("a_rev_fcf", AX, [
  {{label:"Revenue", data:{json.dumps(a_rev)}}},
  {{label:"Free cash flow", data:{json.dumps(a_fcf)}}},
], "Annual Revenue + Free Cash Flow");

pctChart("a_yoy", AX, [
  {{label:"Revenue YoY %", data:{json.dumps(a_rev_yoy)}}},
  {{label:"FCF YoY %", data:{json.dumps(a_fcf_yoy)}}},
], "Annual YoY Growth (%): Revenue vs FCF");

pctChart("a_margin", AX, [
  {{label:"FCF margin %", data:{json.dumps(a_mrg)}}},
], "Annual FCF Margin (%)");
</script>

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
