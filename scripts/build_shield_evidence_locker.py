#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _sha(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(8192)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main(ticker: str):
    t = ticker.upper()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = ROOT / "outputs" / "evidence_locker" / f"{ts}_{t}"
    base.mkdir(parents=True, exist_ok=True)
    files = [
        ROOT / "outputs" / f"decision_summary_{t}.json",
        ROOT / "outputs" / f"claim_evidence_{t}.json",
        ROOT / "outputs" / f"receipts_{t}.json",
        ROOT / "outputs" / f"iron_legion_command_{t}.json",
        ROOT / "outputs" / f"metric_provider_used_{t}.json",
        ROOT / "outputs" / f"provider_health_{t}.json",
        ROOT / "export" / f"CANON_{t}" / f"{t}_IRONMAN_HUD.html",
    ]
    manifest = {"ticker": t, "created_utc": datetime.now(timezone.utc).isoformat(), "files": []}
    for src in files:
        if not src.exists():
            continue
        dst = base / src.name
        shutil.copy2(src, dst)
        manifest["files"].append({"file": src.name, "sha256": _sha(dst), "bytes": dst.stat().st_size})

    m = base / "manifest.json"
    m.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    out = ROOT / "outputs" / f"shield_evidence_locker_{t}.json"
    out.write_text(json.dumps({"ticker": t, "snapshot_dir": str(base), "manifest": str(m)}, indent=2), encoding="utf-8")
    print("DONE ✅ wrote:", out)
    print("DONE ✅ snapshot:", base)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)

