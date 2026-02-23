#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "export"

def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)

def main(ticker: str):
    ticker = ticker.upper()
    docx = EXPORT / f"{ticker}_Full_Investment_Memo.docx"
    if not docx.exists():
        raise FileNotFoundError(f"Missing DOCX: {docx}")

    # LibreOffice CLI
    # Output goes to EXPORT folder
    run([
        "soffice",
        "--headless",
        "--convert-to", "pdf",
        "--outdir", str(EXPORT),
        str(docx),
    ])

    pdf = EXPORT / f"{ticker}_Full_Investment_Memo.pdf"
    if not pdf.exists():
        # LibreOffice sometimes uses same basename; ensure match
        candidates = list(EXPORT.glob(f"{ticker}_Full_Investment_Memo*.pdf"))
        if candidates:
            pdf = candidates[0]

    print(f"DONE ✅ PDF created: {pdf}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default=os.getenv("TICKER", "").strip().upper())
    args = ap.parse_args()
    if not args.ticker:
        raise SystemExit("Missing ticker. Pass --ticker TICKER or set TICKER env var.")
    main(args.ticker)
