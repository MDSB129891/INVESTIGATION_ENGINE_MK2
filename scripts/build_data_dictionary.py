import argparse, json
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[1]

# Minimal dictionary — expand anytime
DICT = [
  {
    "key": "revenue",
    "name": "Revenue",
    "plain_english": "How much the company sold.",
    "units": "USD",
    "where_used": ["Time Stone tables", "Growth % calculations"]
  },
  {
    "key": "free_cash_flow",
    "name": "Free cash flow (FCF)",
    "plain_english": "Cash left after running the business and investments (OCF - Capex).",
    "units": "USD",
    "where_used": ["HUD", "SUPER+", "Decision score", "Time Stone"]
  },
  {
    "key": "fcf_margin_pct",
    "name": "FCF margin",
    "plain_english": "FCF divided by revenue. Tells you cash efficiency.",
    "units": "Percent",
    "where_used": ["HUD", "SUPER+", "Time Stone"]
  },
  {
    "key": "news_shock_30d",
    "name": "News shock (30d)",
    "plain_english": "A score summarizing headline tone over the last 30 days. More negative = worse.",
    "units": "Score",
    "where_used": ["HUD", "SUPER+ claim checks"]
  },
  {
    "key": "risk_*_neg_30d",
    "name": "Risk counts (30d)",
    "plain_english": "Counts of negative news tagged to each risk bucket (labor/regulatory/insurance/etc).",
    "units": "Count",
    "where_used": ["HUD", "SUPER+ claim checks"]
  },
  {
    "key": "dcf_cone_prices",
    "name": "DCF cone (bear/base/bull)",
    "plain_english": "Intrinsic value estimates under pessimistic/base/optimistic assumptions.",
    "units": "USD per share",
    "where_used": ["HUD", "Monte Carlo"]
  },
  {
    "key": "montecarlo_p10_p50_p90",
    "name": "Monte Carlo percentiles",
    "plain_english": "P10/P50/P90 are valuation percentiles from repeated random draws of assumptions.",
    "units": "USD per share",
    "where_used": ["HUD"]
  }
]

def main(ticker: str):
  T = ticker.upper()
  out = REPO_ROOT / "export" / f"CANON_{T}" / f"{T}_DATA_DICTIONARY.json"
  out.parent.mkdir(parents=True, exist_ok=True)

  payload = {
    "ticker": T,
    "generated_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "dictionary": DICT,
    "sources": {
      "annual_history": str(REPO_ROOT / "data" / "processed" / "fundamentals_annual_history.csv"),
      "quarterly_history": str(REPO_ROOT / "data" / "processed" / "fundamentals_quarterly_history_universe.csv"),
      "news_risk_summary": str(REPO_ROOT / "export" / f"CANON_{T}" / f"news_risk_summary_{T}.json"),
      "dcf": str(REPO_ROOT / "export" / f"CANON_{T}" / f"{T}_DCF.json"),
      "montecarlo": str(REPO_ROOT / "export" / f"CANON_{T}" / f"{T}_MONTECARLO.json"),
      "decision_summary": str(REPO_ROOT / "outputs" / "decision_summary.json"),
      "decision_core": str(REPO_ROOT / "export" / f"CANON_{T}" / f"{T}_DECISION_CORE.json"),
      "core_metrics": str(REPO_ROOT / "export" / f"CANON_{T}" / f"{T}_CORE_METRICS.json"),
    }
  }

  out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
  print("✅ wrote:", out)

if __name__ == "__main__":
  ap = argparse.ArgumentParser()
  ap.add_argument("--ticker", required=True)
  args = ap.parse_args()
  main(args.ticker)
