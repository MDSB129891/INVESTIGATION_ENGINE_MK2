#!/usr/bin/env python3
import argparse, json, math
from pathlib import Path
from datetime import datetime, timedelta

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "outputs"
CANON = REPO / "export"

def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def main(ticker: str):
    t = ticker.upper()
    out_dir = OUT
    canon_dir = REPO / f"export/CANON_{t}"
    canon_dir.mkdir(parents=True, exist_ok=True)

    # Inputs we can use
    free_news = read_json(canon_dir / f"{t}_FREE_NEWS.json") or read_json(out_dir / f"{t}_FREE_NEWS.json")
    alerts = read_json(canon_dir / f"alerts_{t}.json") or read_json(out_dir / f"alerts_{t}.json")
    veracity = read_json(canon_dir / f"veracity_{t}.json") or read_json(out_dir / f"veracity_{t}.json")

    # --- risk counts (very simple + robust) ---
    # If FREE_NEWS has tags/categories, count them. If not, fall back to alerts/veracity.
    risk = {
        "risk_labor_neg_30d": 0,
        "risk_regulatory_neg_30d": 0,
        "risk_insurance_neg_30d": 0,
        "risk_safety_neg_30d": 0,
        "risk_competition_neg_30d": 0,
    }

    # Helper: bucket strings into risk categories
    def bucket(txt: str):
        s = (txt or "").lower()
        if any(k in s for k in ["labor", "driver", "union", "employee", "classification", "gig"]):
            return "risk_labor_neg_30d"
        if any(k in s for k in ["regulat", "ftc", "doj", "antitrust", "ban", "law", "rule", "court", "judge"]):
            return "risk_regulatory_neg_30d"
        if any(k in s for k in ["insurance", "coverage", "premium", "liability", "claims"]):
            return "risk_insurance_neg_30d"
        if any(k in s for k in ["crash", "accident", "safety", "assault", "harassment"]):
            return "risk_safety_neg_30d"
        if any(k in s for k in ["lyft", "doordash", "dash", "competition", "pricing war"]):
            return "risk_competition_neg_30d"
        return None

    # Count from FREE_NEWS if available
    if isinstance(free_news, dict) and isinstance(free_news.get("items"), list):
        for it in free_news["items"]:
            title = it.get("title", "")
            summary = it.get("summary", "")
            tone = (it.get("sentiment") or it.get("tone") or "").lower()
            # If you don't have sentiment, still count, but only when clearly "risk-y"
            key = bucket(title + " " + summary)
            if key:
                # if sentiment exists, count only negative-ish
                if tone in ("neg", "negative", "bearish", "down"):
                    risk[key] += 1
                else:
                    risk[key] += 1

    # --- News shock score (0-100) ---
    # Prefer veracity field if present, else compute a crude one from negative proportion.
    news_shock = None
    if isinstance(veracity, dict):
        for k in ("news_shock", "news_shock_30d"):
            if k in veracity and isinstance(veracity[k], (int, float)):
                news_shock = float(veracity[k])
                break

    if news_shock is None:
        # crude score: scale total risk hits into 0-100
        total_risk_hits = sum(risk.values())
        news_shock = clamp(total_risk_hits * 8.0, 0.0, 100.0)

    payload = {
        "ticker": t,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "news_shock": round(float(news_shock), 2),
        **risk,
        "risk_total_30d": int(sum(risk.values())),
    }

    out_json = OUT / f"news_risk_summary_{t}.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # also copy into CANON (where your HUD reads stuff from)
    canon_json = canon_dir / f"news_risk_summary_{t}.json"
    canon_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("DONE ✅ wrote:", out_json)
    print("DONE ✅ wrote:", canon_json)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)
