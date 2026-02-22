import os
import pandas as pd
from dotenv import load_dotenv
from analytics.provider_net import request_with_resilience

load_dotenv()

BASE = "https://financialmodelingprep.com/stable"


def _key() -> str:
    k = os.getenv("FMP_API_KEY")
    if not k:
        raise RuntimeError("Missing FMP_API_KEY in .env")
    return k


def _get(endpoint: str, params: dict) -> list:
    url = f"{BASE}/{endpoint}"
    r = request_with_resilience("fmp", url, params=params)
    data = r.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected response type from FMP: {type(data)} => {data}")
    return data


def fetch_quote(ticker: str) -> pd.DataFrame:
    data = _get("quote", {"apikey": _key(), "symbol": ticker})
    return pd.DataFrame(data)


def fetch_quotes(tickers: list) -> pd.DataFrame:
    """
    Multi-ticker quotes. We try a comma-separated query first, and if it fails,
    we fall back to looping (safe + reliable).
    """
    tickers = [t.strip().upper() for t in tickers if t and str(t).strip()]
    if not tickers:
        return pd.DataFrame()

    # Try one request with comma-separated symbols (if supported)
    try:
        data = _get("quote", {"apikey": _key(), "symbol": ",".join(tickers)})
        df = pd.DataFrame(data)
        # Some APIs might return only one row; validate coverage
        if not df.empty and "symbol" in df.columns:
            got = set(df["symbol"].astype(str).str.upper().tolist())
            if got.issuperset(set(tickers)):
                return df
    except Exception:
        pass

    # Fallback: loop (always works if single quote works)
    frames = []
    for t in tickers:
        df = fetch_quote(t)
        if not df.empty:
            frames.append(df)
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame()


def fetch_income_statement(ticker: str, period: str = "annual", limit: int = 12) -> pd.DataFrame:
    data = _get(
        "income-statement",
        {"apikey": _key(), "symbol": ticker, "period": period, "limit": limit},
    )
    return pd.DataFrame(data)


def fetch_cashflow_statement(ticker: str, period: str = "annual", limit: int = 12) -> pd.DataFrame:
    data = _get(
        "cash-flow-statement",
        {"apikey": _key(), "symbol": ticker, "period": period, "limit": limit},
    )
    return pd.DataFrame(data)


def fetch_balance_sheet(ticker: str, period: str = "annual", limit: int = 12) -> pd.DataFrame:
    data = _get(
        "balance-sheet-statement",
        {"apikey": _key(), "symbol": ticker, "period": period, "limit": limit},
    )
    return pd.DataFrame(data)
