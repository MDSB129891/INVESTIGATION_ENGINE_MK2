#!/usr/bin/env python3
from __future__ import annotations



import sys
from pathlib import Path as _Path
_REPO_ROOT = _Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"

def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def main(ticker: str):
    t = ticker.upper()
    sig_path = OUTPUTS / f"hybrid_signals_{t}.json"
    ver_path = OUTPUTS / f"veracity_{t}.json"
    dash_path = OUTPUTS / f"decision_dashboard_{t}.html"
    click_path = OUTPUTS / f"news_clickpack_{t}.html"

    sig = json.loads(sig_path.read_text(encoding="utf-8")) if sig_path.exists() else {}
    ver = json.loads(ver_path.read_text(encoding="utf-8")) if ver_path.exists() else {}

    tactical = sig.get("tactical", {})
    inst = sig.get("institutional", {})
    mix = sig.get("source_mix", {})

    confirmed = inst.get("confirmed_tags") or {}
    confirmed_list = "\n".join([f"- **{k}** confirmed by {v.get('confirmations')} sources ({', '.join(v.get('sources', []))})"
                               for k, v in confirmed.items()]) or "- None confirmed (good: avoids single-source panic)"

    top_source = mix.get("top_source")
    top_share = mix.get("source_share_top")
    div = mix.get("source_diversity")
    cred_avg = mix.get("cred_weighted_avg")

    md = f"""# Iron Man Trust Appendix — {t}
*Generated: {now_utc()}*

## What this is
This appendix explains **why the model’s news/risk signals are (or are not) trustworthy** — in plain English.

## The key idea
Not all sources are equal:
- **SEC filings** = ground truth
- **Top-tier journalism** = strong evidence
- **Aggregators** = good for *detecting* something happened, weaker for *confirming* it

So we:
1) detect spikes fast (“tactical”)
2) only escalate if **confirmed by multiple credible sources** (“institutional”)

## Tactical signal (fast)
- Articles (7d): **{tactical.get('articles_7d')}**
- Negatives (7d): **{tactical.get('neg_7d')}**
- News shock (7d): **{tactical.get('shock_7d')}**
- Tactical alert: **{tactical.get('tactical_alert')}**
> If this is True, the model is saying: “headlines are unusually negative recently.”

## Institutional confirmation (slow, trusted)
- Confirmed risk themes: **{bool(confirmed)}**
{confirmed_list}

> A theme is *confirmed* only if it appears in multiple **independent, credible** sources.
> This prevents “one noisy outlet” from driving decisions.

## Source mix (what you should worry about)
- Top source: **{top_source}**
- Top source share: **{(round(top_share*100,1) if isinstance(top_share,(int,float)) else 'N/A')}%**
- Source diversity (count): **{div}**
- Average credibility weight: **{cred_avg}**

If top source share is very high (like 90%+), confidence should be lower because you’re not getting independent confirmation.

## Where to click-verify
- Dashboard: `{dash_path.name}`
- Clickpack: `{click_path.name}`

**Best verification habit (60 seconds):**
1) Open clickpack
2) Click the **top negative** headlines
3) If 2+ credible sources independently report the same risk theme → treat it as real.

## Veracity score (optional)
The engine also writes `veracity_{t}.json`. This is the machine-readable view of “how strong is the evidence mix”.
"""

    out = OUTPUTS / f"ironman_appendix_{t}.md"
    out.write_text(md, encoding="utf-8")
    print(f"DONE ✅ appendix: {out}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="AAPL")
    args = ap.parse_args()
    main(args.ticker)
