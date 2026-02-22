#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _exists(p: Path) -> bool:
    return p.exists() and p.stat().st_size > 0


def _read_json(p: Path, default=None):
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default if default is not None else {}


def main(ticker: str):
    t = ticker.upper()
    canon = ROOT / "export" / f"CANON_{t}"
    outputs = ROOT / "outputs"

    required = {
        "decision_summary": outputs / f"decision_summary_{t}.json",
        "claim_evidence": outputs / f"claim_evidence_{t}.json",
        "receipts": outputs / f"receipts_{t}.json",
        "iron_legion": outputs / f"iron_legion_command_{t}.json",
        "mission_report": outputs / f"mission_report_{t}.json",
        "hud": canon / f"{t}_IRONMAN_HUD.html",
        "core_metrics": canon / f"{t}_CORE_METRICS.json",
        "decision_core": canon / f"{t}_DECISION_CORE.json",
        "montecarlo": canon / f"{t}_MONTECARLO.json",
    }

    missing = [k for k, p in required.items() if not _exists(p)]
    present = {k: str(p) for k, p in required.items() if _exists(p)}

    ds = _read_json(outputs / f"decision_summary_{t}.json", {})
    mp = _read_json(outputs / f"metric_provider_used_{t}.json", {})
    il = _read_json(outputs / f"iron_legion_command_{t}.json", {})
    mc = _read_json(canon / f"{t}_MONTECARLO.json", {})

    metric_prov = (mp.get("metric_provider_used") or {})
    missing_metric_prov = [k for k in ["price", "market_cap", "revenue_ttm_yoy_pct", "fcf_ttm", "fcf_margin_ttm_pct"]
                           if not isinstance(metric_prov.get(k), dict) or metric_prov.get(k, {}).get("value") is None]

    hud_path = canon / f"{t}_IRONMAN_HUD.html"
    hud_na_count = 0
    if hud_path.exists():
        try:
            hud_na_count = hud_path.read_text(encoding="utf-8", errors="ignore").count("N/A")
        except Exception:
            pass

    result = {
        "ticker": t,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if not missing and not missing_metric_prov else "degraded",
        "missing_files": missing,
        "present_files": present,
        "missing_metric_provider_fields": missing_metric_prov,
        "hud_na_count": hud_na_count,
        "refresh_warnings": ds.get("refresh_warnings", []),
        "iron_legion_reliability": (il.get("focus", {}).get("reliability_details") or {}),
        "montecarlo_fallback": ((mc.get("results") or {}).get("fallback_used")),
    }

    out = outputs / f"pipeline_integrity_{t}.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("DONE ✅ wrote:", out)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)

