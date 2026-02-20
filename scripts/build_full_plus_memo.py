#!/usr/bin/env python3
from pathlib import Path
import argparse, json, datetime, subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
EXP = ROOT / "export"

def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""

def _json(p: Path):
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

def _now_utc() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

def _clean_bullets(md: str) -> str:
    # normalize odd bullets that sometimes appear after docx conversions
    return md.replace("", "-").replace("\r\n", "\n")

def main(ticker: str):
    T = ticker.upper()

    # Best human memo you already generate
    superplus_md = OUT / f"{T}_SUPERPLUS_CLEAN_Memo.md"

    # Engine outputs you already generate
    dash_html = OUT / f"decision_dashboard_{T}.html"
    clickpack_html = OUT / f"news_clickpack_{T}.html"
    claim_html = OUT / f"claim_evidence_{T}.html"
    veracity_json = OUT / f"veracity_{T}.json"
    risk_sum_json = OUT / f"news_risk_summary_{T}.json"
    decision_expl_json = OUT / "decision_explanation.json"

    # Pull rating/score from decision_explanation.json (if it matches ticker)
    rating = score = None
    d = _json(decision_expl_json)
    if isinstance(d, dict) and str(d.get("ticker", "")).upper() == T:
        rating = d.get("rating")
        score = d.get("score")

    # Pull confidence from veracity
    v = _json(veracity_json)
    conf = v.get("confidence_score")

    # Pull news risk summary
    rs = _json(risk_sum_json)
    news_shock_30d = rs.get("news_shock_30d")
    news_shock_7d = rs.get("news_shock_7d")
    labor_30d = rs.get("risk_labor_neg_30d")
    reg_30d = rs.get("risk_regulatory_neg_30d")
    ins_30d = rs.get("risk_insurance_neg_30d")

    md = []
    md.append(f"# Full+ Investment Memo — {T}")
    md.append(f"*Generated: {_now_utc()}*")
    md.append("")
    md.append("## Quick summary")
    md.append(f"- Model rating: **{rating if rating is not None else 'N/A'}** ({score if score is not None else 'N/A'}/100)")
    md.append(f"- Evidence confidence: **{conf if conf is not None else 'N/A'}** (higher = more trustworthy coverage)")
    md.append("")
    md.append("## News & risk quick check (last 30 days)")
    md.append(f"- Headline negativity score (30d): **{news_shock_30d if news_shock_30d is not None else 'N/A'}**")
    md.append(f"- Headline negativity score (7d): **{news_shock_7d if news_shock_7d is not None else 'N/A'}**")
    md.append(f"- Labor risk headlines (30d): **{labor_30d if labor_30d is not None else 'N/A'}**")
    md.append(f"- Regulatory risk headlines (30d): **{reg_30d if reg_30d is not None else 'N/A'}**")
    md.append(f"- Insurance risk headlines (30d): **{ins_30d if ins_30d is not None else 'N/A'}**")
    md.append("")
    md.append("## Full explanation (kid-friendly, linked to THIS company)")
    if superplus_md.exists():
        md.append(_clean_bullets(_read(superplus_md)).strip())
    else:
        md.append("⚠️ Missing SUPERPLUS_CLEAN memo. Generate it first, then rerun this script.")
    md.append("")
    md.append("## What to open")
    md.append(f"- Dashboard: `{dash_html}`")
    md.append(f"- News clickpack: `{clickpack_html}`")
    md.append(f"- Claim evidence: `{claim_html}`")
    md.append("")

    out_md = OUT / f"{T}_FullPLUS_Investment_Memo.md"
    out_md.write_text("\n".join(md), encoding="utf-8")

    # PDF export path: simplest + most reliable = LibreOffice convert-to pdf from a DOCX.
    # We'll create a DOCX by converting the MD->TXT then LibreOffice TXT->DOCX (works well enough).
    EXP.mkdir(parents=True, exist_ok=True)
    tmp_txt = EXP / f"{T}_FullPLUS_Investment_Memo.txt"
    tmp_txt.write_text(out_md.read_text(encoding="utf-8"), encoding="utf-8")

    soffice = "/opt/homebrew/bin/soffice"
    # Convert TXT -> DOCX
    subprocess.run([soffice, "--headless", "--convert-to", "docx", "--outdir", str(EXP), str(tmp_txt)],
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out_docx = EXP / f"{T}_FullPLUS_Investment_Memo.docx"

    # Convert DOCX -> PDF
    if out_docx.exists():
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(EXP), str(out_docx)],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    out_pdf = EXP / f"{T}_FullPLUS_Investment_Memo.pdf"

    print("DONE ✅ Full+ memo created:")
    print("-", out_md)
    if out_docx.exists(): print("-", out_docx)
    if out_pdf.exists(): print("-", out_pdf)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)
