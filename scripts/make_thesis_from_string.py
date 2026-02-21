#!/usr/bin/env python3
import argparse, json
from pathlib import Path
from datetime import datetime

def main(ticker: str, thesis: str, out: Path):
    T = ticker.upper()
    payload = {
        "ticker": T,
        "name": f"{T}: Custom thesis",
        "headline": thesis.strip(),
        "description": thesis.strip(),
        "generated_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        # empty rules by default — you can later let user add constraints
        "claims": []
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("✅ wrote:", out)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--thesis", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    main(args.ticker, args.thesis, Path(args.out))
