# Calculation Methodology — UBER
*Generated: 2026-02-20 03:09 UTC*

## Purpose
This document explains how the engine calculates metrics, bucket scores, and the final rating.
Implementation reference: `scripts/run_uber_update.py`.

## Data Inputs
- `data/processed/fundamentals_annual_history.csv`
- `data/processed/comps_snapshot.csv`
- `data/processed/news_sentiment_proxy.csv`
- `data/processed/news_risk_dashboard.csv`
- `outputs/decision_summary.json` or `outputs/decision_summary_<T>.json`

## Derived Metric Formulas
- `capex_spend = abs(capitalExpenditure)`
- `free_cash_flow = operating_cash_flow - capex_spend`
- `revenue_ttm = rolling_4q_sum(revenue)`
- `fcf_ttm = rolling_4q_sum(free_cash_flow)`
- `fcf_margin_ttm_pct = (fcf_ttm / revenue_ttm) * 100`
- `revenue_ttm_yoy_pct = pct_change_4q(revenue_ttm) * 100`
- `fcf_ttm_yoy_pct = pct_change_4q(fcf_ttm) * 100`
- `net_debt = debt - cash`
- `fcf_yield = fcf_ttm / market_cap`
- `net_debt_to_fcf_ttm = net_debt / fcf_ttm` (only if `fcf_ttm > 0`)
- `rank_percentile(metric) = mean(peer_values <= company_value) * 100`

## Score Construction (0-100)
- `score = clamp(cash_level + valuation + growth + quality + balance_risk, 0, 100)`
- Rating bands: `BUY` if score >= 80, `HOLD` if score >= 65, else `AVOID`.

### Bucket Rules
- Cash Level (max 25): thresholded by `fcf_ttm` (>=12B, >=8B, >=4B, >=1B, else low).
- Valuation (max 20): absolute `fcf_yield` points + relative peer-rank points.
- Growth (max 20): revenue YoY leg + FCF YoY leg + two peer-rank legs.
- Quality (max 15): FCF margin leg + peer-rank leg.
- Balance/Risk (max 20): starts at 20 then subtracts debt/news/shock/core-risk penalties, with proxy-score adjustment.

## Worked Example (Current Run)
- Model score/rating: **83 / BUY**
- Reconstructed score from current inputs: **83**

### Inputs Used
- FCF TTM: $9.76B
- FCF Yield: 6.44%
- Revenue YoY: 18.28%
- FCF YoY: 41.60%
- FCF Margin TTM: 18.77%
- Net Debt / FCF: 0.59
- Peer rank (FCF Yield): 66.67%
- Peer rank (Revenue YoY): 66.67%
- Peer rank (FCF YoY): 66.67%
- Peer rank (FCF Margin): 100.00%
- News neg 7d: 1
- News shock 7d: -3
- Core risk hits 30d (LABOR+INSURANCE+REGULATORY): 3
- Proxy score 7d: 54.00

### Bucket Contributions (Reconstructed)
- Cash Level: **21** | FCF TTM >= 8B
- Valuation: **15** | absolute leg: +8 (fcf_yield >= 6%); relative leg: +7 (rank >= 50)
- Growth: **16** | rev_yoy: +4; fcf_yoy: +6; rev rank leg applied; fcf rank leg applied
- Quality: **15** | margin leg: +9; rank leg applied
- Balance/Risk: **16** | start at 20; -2 news neg penalty (neg_7d >= 1); -2 core-risk frequency penalty (>= 3)

### Bucket Contributions (From Engine Output)
- cash_level: **21**
- valuation: **15**
- growth: **16**
- quality: **15**
- balance_risk: **16**

## Notes
- If reconstructed score and model score differ, the run may have mixed ticker-scoped vs shared summary files.
- This document is generated from current output files and mirrors current scoring logic.

