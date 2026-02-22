#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/run_galactus.sh TICKER THESIS_JSON [PEERS_CSV]

TICKER="${1:-}"
THESIS_FILE="${2:-}"
PEERS_CSV="${3:-}"

if [[ -z "${TICKER}" || -z "${THESIS_FILE}" ]]; then
  echo "❌ Usage: ./scripts/run_galactus.sh TICKER THESIS_JSON [PEERS_CSV]"
  exit 1
fi

if [[ ! -f "${THESIS_FILE}" ]]; then
  echo "❌ Thesis file not found: ${THESIS_FILE}"
  echo "Tip: generate it with:"
  echo "  python3 scripts/new_thesis.py ${TICKER} \"your thesis text\""
  exit 1
fi

# Uppercase safely without bash-specific ${VAR^^}
TICKER_UC="$(printf "%s" "${TICKER}" | tr '[:lower:]' '[:upper:]')"

# Default peers if user didn't pass them
# IMPORTANT: these are literals, not variables like $DASH
if [[ -z "${PEERS_CSV}" ]]; then
  case "${TICKER_UC}" in
    LYFT|DASH)
      PEERS_CSV="LYFT,DASH"
      ;;
    TSLA)
      PEERS_CSV="GM,F"
      ;;
    GM)
      PEERS_CSV="F,TM"
      ;;
    F)
      PEERS_CSV="GM,TM"
      ;;
    *)
      PEERS_CSV="SPY"
      ;;
  esac
fi

echo "🌌 GALACTUS RUN
SOFFICE="/opt/homebrew/bin/soffice"
"
echo "Ticker: ${TICKER_UC}"
echo "Thesis file: ${THESIS_FILE}"
echo "Peers: ${PEERS_CSV}"
echo

export PEERS="${PEERS_CSV}"

./scripts/run_thanos.sh "${TICKER_UC}" "${THESIS_FILE}"

echo
echo "🚀 OPENING RESULTS (dopamine mode)"
# open "outputs/decision_dashboard_${TICKER_UC}.html" 2>/dev/null || true  # disabled: no tab spam
# open "outputs/news_clickpack_${TICKER_UC}.html" 2>/dev/null || true  # disabled: no tab spam
# open "export/${TICKER_UC}_Full_Investment_Memo.pdf" 2>/dev/null || true  # disabled: no tab spam
# open "export/${TICKER_UC}_Full_Investment_Memo.docx" 2>/dev/null || true  # disabled: no tab spam

echo
echo "
# --- PDF conversion (dopamine lock) ---
if [ -f "export/${TICKER}_SUPER_Memo.docx" ]; then
  "$SOFFICE" --headless --convert-to pdf --outdir export "export/${TICKER}_SUPER_Memo.docx" >/dev/null 2>&1 || true
fi
if [ -f "export/${TICKER}_Full_Investment_Memo.docx" ]; then
  "$SOFFICE" --headless --convert-to pdf --outdir export "export/${TICKER}_Full_Investment_Memo.docx" >/dev/null 2>&1 || true
fi

🧠 GALACTUS COMPLETE"

echo ""
echo "🚀 OPENING RESULTS (all-eggs mode)"
./scripts/open_pack.sh "$TICKER" || true


# =========================
# GALACTUS AUTO-DEPLOY PACK
# =========================
echo ""
echo "=== 7) BIG memo (full detailed) ==="
# NOTE: assumes run_galactus.sh defines TICKER and THESIS_FILE variables
python3 scripts/build_big_memo.py --ticker "$TICKER" --thesis "$THESIS_FILE" || true

echo ""
echo "=== 7b) Export BIG memo PDF ==="
if [ -f "export/${TICKER}_BIG_Memo.docx" ]; then
  python3 scripts/export_pdf.py "export/${TICKER}_BIG_Memo.docx" "export/${TICKER}_BIG_Memo.pdf" || true
fi

echo ""
echo "🚀 OPENING RESULTS (dopamine mode)"
# Open the BIG memo first
if [ -f "export/${TICKER}_BIG_Memo.docx" ]; then open "export/${TICKER}_BIG_Memo.docx" || true; fi
if [ -f "export/${TICKER}_BIG_Memo.pdf" ]; then open "export/${TICKER}_BIG_Memo.pdf" || true; fi

# Then open the core HTML packs
if [ -f "outputs/decision_dashboard_${TICKER}.html" ]; then open "outputs/decision_dashboard_${TICKER}.html" || true; fi
if [ -f "outputs/news_clickpack_${TICKER}.html" ]; then open "outputs/news_clickpack_${TICKER}.html" || true; fi
if [ -f "outputs/claim_evidence_${TICKER}.html" ]; then open "outputs/claim_evidence_${TICKER}.html" || true; fi

echo ""
echo "✅ GALACTUS AUTO-DEPLOY COMPLETE"


echo "=== X) ULTRA memo (novice / explain-everything) ==="
# If thesis override exists, pass it through; otherwise ULTRA still works.
if [ -n "${THESIS_OVERRIDE:-}" ] && [ -f "${THESIS_OVERRIDE}" ]; then
  python3 scripts/build_ultra_memo.py --ticker "$TICKER" --thesis "${THESIS_OVERRIDE}" || true
else
  python3 scripts/build_ultra_memo.py --ticker "$TICKER" || true
fi

echo ""
echo "🚀 OPENING ULTRA RESULTS"
if [ -f "export/${TICKER}_ULTRA_Memo.docx" ]; then open "export/${TICKER}_ULTRA_Memo.docx" || true; fi
if [ -f "outputs/decision_dashboard_${TICKER}.html" ]; then open "outputs/decision_dashboard_${TICKER}.html" || true; fi
if [ -f "outputs/news_clickpack_${TICKER}.html" ]; then open "outputs/news_clickpack_${TICKER}.html" || true; fi
if [ -f "outputs/claim_evidence_${TICKER}.html" ]; then open "outputs/claim_evidence_${TICKER}.html" || true; fi


# DOPAMINE_OPEN_BLOCK_V1
echo ""
echo "🚀 OPENING RESULTS (dopamine order)"
echo "1) Dashboard"
if [ -f "outputs/decision_dashboard_${TICKER}.html" ]; then open "outputs/decision_dashboard_${TICKER}.html" || true; fi

echo "2) SUPER memo"
if [ -f "outputs/${TICKER}_SUPER_Memo.md" ]; then open "outputs/${TICKER}_SUPER_Memo.md" || true; fi
if [ -f "export/${TICKER}_SUPER_Memo.docx" ]; then open "export/${TICKER}_SUPER_Memo.docx" || true; fi

echo "3) News clickpack"
if [ -f "outputs/news_clickpack_${TICKER}.html" ]; then open "outputs/news_clickpack_${TICKER}.html" || true; fi

echo "4) Claim evidence"
if [ -f "outputs/claim_evidence_${TICKER}.html" ]; then open "outputs/claim_evidence_${TICKER}.html" || true; fi



### CLEAN DOPAMINE OPEN (dashboard + SUPER pdf only) ###
# Build SUPER memo (this is the storytime + good/bad one)
python3 scripts/build_super_memo.py --ticker "$TICKER_UPPER" --thesis "${THESIS_OVERRIDE:-theses/${TICKER_UPPER}_custom.json}" || true

# Convert SUPER docx -> pdf (LibreOffice)
if [ -f "export/${TICKER_UPPER}_SUPER_Memo.docx" ]; then
  if command -v soffice >/dev/null 2>&1; then
    soffice --headless --convert-to pdf --outdir export "export/${TICKER_UPPER}_SUPER_Memo.docx" >/dev/null 2>&1 || true
  elif [ -x "/Applications/LibreOffice.app/Contents/MacOS/soffice" ]; then
    "/Applications/LibreOffice.app/Contents/MacOS/soffice" --headless --convert-to pdf --outdir export "export/${TICKER_UPPER}_SUPER_Memo.docx" >/dev/null 2>&1 || true
  fi
fi

echo "🚀 OPENING RESULTS (clean dopamine mode)"

# OPEN IN ORDER: 1) dashboard 2) SUPER pdf
if [ -f "outputs/decision_dashboard_${TICKER_UPPER}.html" ]; then
#   open "outputs/decision_dashboard_${TICKER_UPPER}.html" || true  # disabled: no tab spam
fi
if [ -f "export/${TICKER_UPPER}_SUPER_Memo.pdf" ]; then
#   open "export/${TICKER_UPPER}_SUPER_Memo.pdf" || true  # disabled: no tab spam
fi

echo ""
echo "🚀 OPENING RESULTS (ordered, no spam)"
if [ -f "outputs/decision_dashboard_${TICKER}.html" ]; then
  open "outputs/decision_dashboard_${TICKER}.html" || true
fi
if [ -f "export/${TICKER}_SUPER_Memo.pdf" ]; then
  open "export/${TICKER}_SUPER_Memo.pdf" || true
fi
if [ -f "export/${TICKER}_Full_Investment_Memo.pdf" ]; then
  open "export/${TICKER}_Full_Investment_Memo.pdf" || true
fi
