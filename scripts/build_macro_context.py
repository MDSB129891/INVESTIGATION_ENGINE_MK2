#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "macro_context.json"


def main():
    prev = {}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            prev = {}

    series = prev.get("series") or {
        "DGS10": None,
        "CPIAUCSL": None,
        "FEDFUNDS": None,
    }
    regime = prev.get("macro_regime") or "Neutral Macro"
    src = prev.get("source") or "cached/default"

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source": src,
        "used_cache": bool(prev),
        "series": series,
        "macro_regime": regime,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("DONE ✅ wrote:", OUT)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

