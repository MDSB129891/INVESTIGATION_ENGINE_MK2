#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
TEST_TICKER="$(printf "%s" "${1:-${TICKER:-AAPL}}" | tr '[:lower:]' '[:upper:]')"

DATE_TO="$(python3 - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).date().isoformat())
PY
)"
DATE_FROM="$(python3 - <<'PY'
from datetime import datetime, timezone, timedelta
print((datetime.now(timezone.utc).date() - timedelta(days=30)).isoformat())
PY
)"

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

pass() { echo "PASS  $*"; PASS_COUNT=$((PASS_COUNT + 1)); }
warn() { echo "WARN  $*"; WARN_COUNT=$((WARN_COUNT + 1)); }
fail() { echo "FAIL  $*"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

section() {
  echo ""
  echo "== $* =="
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

load_env() {
  if [[ -f ".env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
    pass ".env loaded"
  else
    warn ".env not found (continuing with current shell env)"
  fi
}

check_key() {
  local key="$1"
  local value="${!key:-}"
  if [[ -n "$value" ]]; then
    pass "$key is set"
  else
    fail "$key is missing"
  fi
}

dns_check() {
  local host="$1"
  if have_cmd nslookup; then
    if nslookup "$host" >/tmp/check_dns_"$host".log 2>&1; then
      pass "DNS resolves $host"
    else
      fail "DNS cannot resolve $host"
    fi
  elif have_cmd dig; then
    if dig +short "$host" | grep -q "."; then
      pass "DNS resolves $host"
    else
      fail "DNS cannot resolve $host"
    fi
  else
    warn "Neither nslookup nor dig found; skipping DNS check for $host"
  fi
}

http_status() {
  local name="$1"
  local url="$2"
  local code
  code="$(curl -sS -L --max-time 20 -o /tmp/check_http_code.out -w "%{http_code}" "$url" 2>/tmp/check_http_err.log || true)"
  if [[ "$code" =~ ^[23] ]]; then
    pass "$name reachable (HTTP $code)"
  elif [[ -n "$code" && "$code" != "000" ]]; then
    warn "$name responded HTTP $code"
  else
    fail "$name unreachable (curl failed)"
  fi
}

http_status_header() {
  local name="$1"
  local url="$2"
  local ua="$3"
  local code
  code="$(curl -sS -A "$ua" -L --max-time 20 -o /tmp/check_http_code.out -w "%{http_code}" "$url" 2>/tmp/check_http_err.log || true)"
  if [[ "$code" =~ ^[23] ]]; then
    pass "$name reachable with UA (HTTP $code)"
  elif [[ "$code" == "403" ]]; then
    fail "$name returned HTTP 403 even with SEC_USER_AGENT"
  elif [[ -n "$code" && "$code" != "000" ]]; then
    warn "$name responded HTTP $code"
  else
    fail "$name unreachable (curl failed)"
  fi
}

section "Context"
echo "Repo: $ROOT"
echo "UTC : $(date -u +"%Y-%m-%d %H:%M:%S UTC")"
echo "Ticker under test: ${TEST_TICKER}"

section "Environment"
load_env
check_key "FMP_API_KEY"
check_key "FINNHUB_API_KEY"
check_key "SEC_USER_AGENT"
check_key "SEC_NEWS_USER_AGENT"

section "DNS"
dns_check "finnhub.io"
dns_check "data.sec.gov"
dns_check "financialmodelingprep.com"
dns_check "query1.finance.yahoo.com"

section "Base HTTPS Reachability"
http_status "finnhub root" "https://finnhub.io"
http_status "SEC submissions" "https://data.sec.gov/submissions/CIK0000320193.json"
http_status "FMP quote (public URL shape)" "https://financialmodelingprep.com/stable/quote?symbol=${TEST_TICKER}"
http_status "Yahoo quote API" "https://query1.finance.yahoo.com/v7/finance/quote?symbols=${TEST_TICKER}"

section "Authenticated Endpoint Checks"
if [[ -n "${FINNHUB_API_KEY:-}" ]]; then
  FINN_URL="https://finnhub.io/api/v1/company-news?symbol=${TEST_TICKER}&from=${DATE_FROM}&to=${DATE_TO}&token=${FINNHUB_API_KEY}"
  http_status "Finnhub company-news auth check" "$FINN_URL"
else
  warn "Skipping Finnhub auth check (FINNHUB_API_KEY missing)"
fi

if [[ -n "${FMP_API_KEY:-}" ]]; then
  FMP_URL="https://financialmodelingprep.com/stable/quote?symbol=${TEST_TICKER}&apikey=${FMP_API_KEY}"
  http_status "FMP quote auth check" "$FMP_URL"
else
  warn "Skipping FMP auth check (FMP_API_KEY missing)"
fi

if [[ -n "${SEC_USER_AGENT:-}" ]]; then
  http_status_header "SEC submissions auth-style check" "https://data.sec.gov/submissions/CIK0000320193.json" "${SEC_USER_AGENT}"
else
  warn "Skipping SEC user-agent check (SEC_USER_AGENT missing)"
fi

section "Summary"
echo "PASS: $PASS_COUNT"
echo "WARN: $WARN_COUNT"
echo "FAIL: $FAIL_COUNT"

if [[ $FAIL_COUNT -gt 0 ]]; then
  echo "OVERALL: FAIL"
  exit 1
fi

if [[ $WARN_COUNT -gt 0 ]]; then
  echo "OVERALL: WARN"
  exit 0
fi

echo "OVERALL: PASS"
exit 0
