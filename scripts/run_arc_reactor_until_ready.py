#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_PROCESSED = ROOT / "data" / "processed"
DEFAULT_DNS_HOSTS = "finnhub.io,data.sec.gov,financialmodelingprep.com,query1.finance.yahoo.com"


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        if path.exists() and path.stat().st_size > 0:
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame()


def _news_age_hours(news_df: pd.DataFrame, ticker: str) -> float | None:
    if news_df.empty or "published_at" not in news_df.columns:
        return None

    df = news_df.copy()
    if "ticker" in df.columns:
        df = df[df["ticker"].astype(str).str.upper() == ticker]
    if df.empty:
        return None

    ts = pd.to_datetime(df["published_at"], utc=True, errors="coerce").dropna()
    if ts.empty:
        return None

    newest = ts.max().to_pydatetime()
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    age_h = (datetime.now(timezone.utc) - newest).total_seconds() / 3600.0
    return max(0.0, float(age_h))


def _validate_outputs(
    ticker: str,
    min_news_rows: int,
    min_comps_rows: int,
    require_primary_in_news: bool,
    require_primary_in_comps: bool,
    max_news_age_hours: int,
) -> Tuple[bool, str]:
    news_path = DATA_PROCESSED / "news_unified.csv"
    comps_path = DATA_PROCESSED / "comps_snapshot.csv"

    news = _read_csv(news_path)
    comps = _read_csv(comps_path)

    news_rows = len(news)
    comps_rows = len(comps)

    news_primary = 0
    if not news.empty and "ticker" in news.columns:
        news_primary = int((news["ticker"].astype(str).str.upper() == ticker).sum())

    comps_primary = 0
    if not comps.empty and "ticker" in comps.columns:
        comps_primary = int((comps["ticker"].astype(str).str.upper() == ticker).sum())

    reasons = []
    if news_rows < min_news_rows:
        reasons.append(f"news rows {news_rows} < required {min_news_rows}")
    if comps_rows < min_comps_rows:
        reasons.append(f"comps rows {comps_rows} < required {min_comps_rows}")
    if require_primary_in_news and news_primary == 0:
        reasons.append(f"no {ticker} rows in news_unified.csv")
    if require_primary_in_comps and comps_primary == 0:
        reasons.append(f"no {ticker} row in comps_snapshot.csv")

    news_age_h = _news_age_hours(news, ticker)
    if max_news_age_hours > 0:
        if news_age_h is None:
            reasons.append(f"cannot compute {ticker} news freshness")
        elif news_age_h > max_news_age_hours:
            reasons.append(
                f"{ticker} newest news is {news_age_h:.1f}h old (> {max_news_age_hours}h)"
            )

    status = (
        f"news_rows={news_rows}, comps_rows={comps_rows}, "
        f"{ticker}_news_rows={news_primary}, {ticker}_comps_rows={comps_primary}"
    )
    if news_age_h is not None:
        status += f", {ticker}_news_age_hours={news_age_h:.1f}"

    if reasons:
        return False, status + " | " + "; ".join(reasons)
    return True, status


def _dns_preflight(hosts: list[str]) -> tuple[bool, str]:
    failed = []
    for h in hosts:
        host = str(h).strip()
        if not host:
            continue
        try:
            socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except Exception:
            failed.append(host)
    if failed:
        return False, "dns_unresolved=" + ",".join(failed)
    return True, "dns_ok"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run arc reactor update repeatedly until required data exists."
    )
    ap.add_argument("--ticker", default=os.getenv("TICKER", ""))
    ap.add_argument("--peers", default=os.getenv("PEERS", ""))
    ap.add_argument("--universe", default=os.getenv("UNIVERSE", ""))
    ap.add_argument("--max-attempts", type=int, default=int(os.getenv("ARC_REACTOR_MAX_ATTEMPTS", "0")))
    ap.add_argument("--sleep-seconds", type=int, default=int(os.getenv("ARC_REACTOR_RETRY_SLEEP_SEC", "30")))
    ap.add_argument("--min-news-rows", type=int, default=int(os.getenv("ARC_REACTOR_MIN_NEWS_ROWS", "1")))
    ap.add_argument("--min-comps-rows", type=int, default=int(os.getenv("ARC_REACTOR_MIN_COMPS_ROWS", "1")))
    ap.add_argument("--max-news-age-hours", type=int, default=int(os.getenv("ARC_REACTOR_MAX_NEWS_AGE_HOURS", "72")))
    ap.add_argument("--no-require-primary-in-news", action="store_true")
    ap.add_argument("--no-require-primary-in-comps", action="store_true")
    ap.add_argument("--dns-preflight", action="store_true", default=True)
    ap.add_argument("--no-dns-preflight", dest="dns_preflight", action="store_false")
    ap.add_argument("--dns-hosts", default=os.getenv("ARC_REACTOR_DNS_HOSTS", DEFAULT_DNS_HOSTS))
    args = ap.parse_args()

    ticker = args.ticker.upper().strip()
    if not ticker:
        raise SystemExit("Missing ticker. Pass --ticker or set TICKER in environment.")
    require_primary_in_news = not args.no_require_primary_in_news
    require_primary_in_comps = not args.no_require_primary_in_comps
    attempt = 0

    print(
        "ARC REACTOR PERSIST MODE: "
        f"ticker={ticker}, max_attempts={args.max_attempts or 'infinite'}, "
        f"sleep={args.sleep_seconds}s"
    )

    while True:
        attempt += 1
        if args.dns_preflight:
            hosts = [h.strip() for h in str(args.dns_hosts or "").split(",") if h.strip()]
            ok_dns, dns_status = _dns_preflight(hosts)
            if not ok_dns:
                print(f"[attempt {attempt}] DNS preflight failed: {dns_status}")
                if args.max_attempts > 0 and attempt >= args.max_attempts:
                    print("FAILED ❌ hit max attempts while DNS remained unresolved")
                    return 1
                print(f"[attempt {attempt}] waiting {args.sleep_seconds}s before retry")
                time.sleep(max(1, args.sleep_seconds))
                continue

        print(f"[attempt {attempt}] running scripts/run_arc_reactor_update.py")
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "run_arc_reactor_update.py"),
            "--ticker",
            ticker,
        ]
        if args.universe:
            cmd.extend(["--universe", args.universe])
        elif args.peers:
            cmd.extend(["--peers", args.peers])

        run = subprocess.run(
            cmd,
            cwd=str(ROOT),
        )
        if run.returncode != 0:
            print(f"[attempt {attempt}] updater exited with code {run.returncode}")

        ok, details = _validate_outputs(
            ticker=ticker,
            min_news_rows=args.min_news_rows,
            min_comps_rows=args.min_comps_rows,
            require_primary_in_news=require_primary_in_news,
            require_primary_in_comps=require_primary_in_comps,
            max_news_age_hours=args.max_news_age_hours,
        )
        print(f"[attempt {attempt}] {details}")
        if ok:
            print(f"READY ✅ required data is available for {ticker}")
            return 0

        if args.max_attempts > 0 and attempt >= args.max_attempts:
            print("FAILED ❌ hit max attempts before required data became available")
            return 1

        print(f"[attempt {attempt}] waiting {args.sleep_seconds}s before retry")
        time.sleep(max(1, args.sleep_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
