from pathlib import Path

def patch_file(path: Path, snippet: str):
    txt = path.read_text(encoding="utf-8")

    if "build_ultra_memo.py" in txt:
        print(f"SKIP (already patched): {path}")
        return

    # Append near the end: build ultra memo + open key files
    txt = txt.rstrip() + "\n\n" + snippet + "\n"
    path.write_text(txt, encoding="utf-8")
    print(f"PATCHED ✅ {path}")

SNIPPET = r'''
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
if [ -f "outputs/decision_dashboard_${TICKER}.html" ]; then # DISABLED (JARVIS controls opening): open "outputs/decision_dashboard_${TICKER}.html" || true; fi
if [ -f "outputs/news_clickpack_${TICKER}.html" ]; then open "outputs/news_clickpack_${TICKER}.html" || true; fi
if [ -f "outputs/claim_evidence_${TICKER}.html" ]; then open "outputs/claim_evidence_${TICKER}.html" || true; fi
'''

for f in ["scripts/run_thanos.sh", "scripts/run_galactus.sh"]:
    p = Path(f)
    if p.exists():
        patch_file(p, SNIPPET)
    else:
        print(f"Missing: {p}")
