from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from threading import Lock
from typing import Dict, Optional, Tuple

import requests


_TIMEOUT_BUDGETS = {
    "fmp": float(os.getenv("PROVIDER_TIMEOUT_FMP_SEC", "12")),
    "finnhub": float(os.getenv("PROVIDER_TIMEOUT_FINNHUB_SEC", "12")),
    "sec": float(os.getenv("PROVIDER_TIMEOUT_SEC_SEC", "12")),
    "massive": float(os.getenv("PROVIDER_TIMEOUT_MASSIVE_SEC", "12")),
    "yahoo": float(os.getenv("PROVIDER_TIMEOUT_YAHOO_SEC", "8")),
    "tiingo": float(os.getenv("PROVIDER_TIMEOUT_TIINGO_SEC", "12")),
    "marketaux": float(os.getenv("PROVIDER_TIMEOUT_MARKETAUX_SEC", "12")),
    "alphavantage": float(os.getenv("PROVIDER_TIMEOUT_ALPHAVANTAGE_SEC", "12")),
}

_MAX_RETRIES = int(os.getenv("PROVIDER_MAX_RETRIES", "3"))
_BACKOFF_BASE = float(os.getenv("PROVIDER_BACKOFF_BASE_SEC", "0.6"))
_BACKOFF_JITTER = float(os.getenv("PROVIDER_BACKOFF_JITTER_SEC", "0.35"))
_CIRCUIT_FAILURE_THRESHOLD = int(os.getenv("PROVIDER_CB_FAILURE_THRESHOLD", "4"))
_CIRCUIT_OPEN_SEC = float(os.getenv("PROVIDER_CB_OPEN_SEC", "45"))


@dataclass
class _ProviderState:
    failures: int = 0
    open_until_ts: float = 0.0
    last_error: str = ""


_LOCK = Lock()
_STATE: Dict[str, _ProviderState] = {}


def _now() -> float:
    return time.time()


def _state(provider: str) -> _ProviderState:
    with _LOCK:
        if provider not in _STATE:
            _STATE[provider] = _ProviderState()
        return _STATE[provider]


def provider_circuit_status(provider: str) -> dict:
    s = _state(provider)
    now = _now()
    return {
        "provider": provider,
        "open": bool(s.open_until_ts > now),
        "open_until_epoch": s.open_until_ts,
        "consecutive_failures": s.failures,
        "last_error": s.last_error or None,
    }


def provider_timeout(provider: str, default_timeout: Optional[float] = None) -> float:
    if default_timeout is not None:
        return float(default_timeout)
    return float(_TIMEOUT_BUDGETS.get(provider, 12.0))


def _record_success(provider: str) -> None:
    s = _state(provider)
    with _LOCK:
        s.failures = 0
        s.open_until_ts = 0.0
        s.last_error = ""


def _record_failure(provider: str, err: str) -> None:
    s = _state(provider)
    with _LOCK:
        s.failures += 1
        s.last_error = err[:500]
        if s.failures >= _CIRCUIT_FAILURE_THRESHOLD:
            s.open_until_ts = _now() + _CIRCUIT_OPEN_SEC


def _circuit_open(provider: str) -> Tuple[bool, float]:
    s = _state(provider)
    now = _now()
    return (s.open_until_ts > now, max(0.0, s.open_until_ts - now))


def request_with_resilience(
    provider: str,
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
) -> requests.Response:
    """HTTP GET with per-provider timeout budget, exponential backoff + jitter, and circuit breaker."""
    is_open, wait_s = _circuit_open(provider)
    if is_open:
        raise RuntimeError(f"Circuit open for provider={provider}; retry after {wait_s:.1f}s")

    retries = _MAX_RETRIES if max_retries is None else int(max_retries)
    to = provider_timeout(provider, timeout)

    last_err: Optional[Exception] = None
    for i in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=to)
            if r.status_code in (429, 500, 502, 503, 504):
                err = RuntimeError(f"HTTP {r.status_code}")
                _record_failure(provider, str(err))
                last_err = err
            else:
                r.raise_for_status()
                _record_success(provider)
                return r
        except Exception as e:
            _record_failure(provider, str(e))
            last_err = e

        if i < retries:
            sleep_s = (_BACKOFF_BASE * (2 ** i)) + random.uniform(0.0, _BACKOFF_JITTER)
            time.sleep(sleep_s)

    raise RuntimeError(f"{provider} request failed after retries: {last_err}")
