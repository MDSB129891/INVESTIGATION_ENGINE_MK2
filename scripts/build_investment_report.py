#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import pandas as pd

from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.worksheet.table import Table, TableStyleInfo


# --- bootstrap: allow imports reliably if we add them later ---
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# ------------------------------------------------------------

DATA_PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"
EXPORT = ROOT / "export"

TICKER = os.getenv("TICKER", "AAPL").upper()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _safe_read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def extract_domain(url: str) -> str:
    if not url or str(url).strip() in ("None", ""):
        return ""
    try:
        u = str(url).strip()
        if not u.startswith("http"):
            return ""
        netloc = urlparse(u).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


# ---------------------------
# Pretty Word helpers
# ---------------------------
def _shade_cell(cell, fill_hex: str = "F2F2F2"):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex)
    tcPr.append(shd)


def _format_table(table, header_fill="E8EEF7", header_font_size=10, body_font_size=9):
    hdr = table.rows[0].cells
    for c in hdr:
        _shade_cell(c, header_fill)
        for p in c.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(header_font_size)

    for row in table.rows[1:]:
        for c in row.cells:
            for p in c.paragraphs:
                p.paragraph_format.space_after = Pt(2)
                for r in p.runs:
                    r.font.size = Pt(body_font_size)


def _bullet(doc: Document, text: str, level: int = 0):
    style = "List Bullet" if level == 0 else "List Bullet 2"
    doc.add_paragraph(text, style=style)


# ---------------------------
# Interpretation keys
# ---------------------------
def metric_cheat_sheet() -> pd.DataFrame:
    rows = [
        {"Metric": "Revenue Growth (YoY %)", "Meaning": "Is the company getting bigger?", "Good": "> 10%", "OK": "0–10%", "Bad": "< 0%", "Why it matters": "Growth supports future cash and valuation."},
        {"Metric": "Free Cash Flow (FCF)", "Meaning": "Cash left after running the business + capex.", "Good": "Positive and rising", "OK": "Positive but flat", "Bad": "Negative", "Why it matters": "FCF funds buybacks, debt paydown, and growth."},
        {"Metric": "FCF Margin (%)", "Meaning": "How much cash is produced per $1 of sales.", "Good": "> 10%", "OK": "0–10%", "Bad": "< 0%", "Why it matters": "Higher = better business economics."},
        {"Metric": "FCF Yield", "Meaning": "Cash return vs price you pay (FCF / Market Cap).", "Good": "> 5%", "OK": "2–5%", "Bad": "< 2%", "Why it matters": "Higher yield often means cheaper vs cash."},
        {"Metric": "Net Debt / FCF", "Meaning": "Years of FCF needed to pay net debt.", "Good": "< 3x", "OK": "3–6x", "Bad": "> 6x", "Why it matters": "Lower = safer in downturns."},
        {"Metric": "News Shock (7d/30d)", "Meaning": "Severity of negative headlines (more negative = worse).", "Good": "Near 0", "OK": "-1 to -10", "Bad": "< -10", "Why it matters": "Large shocks often reflect real events."},
        {"Metric": "Confidence (Veracity)", "Meaning": "How easy it is to verify sources quickly.", "Good": "> 70", "OK": "40–70", "Bad": "< 40", "Why it matters": "Low confidence = more manual verification needed."},
    ]
    return pd.DataFrame(rows)


def curated_evidence_pack(news_df: pd.DataFrame, ticker: str, top_n: int = 12) -> pd.DataFrame:
    if news_df.empty:
        return pd.DataFrame(columns=["published_at", "risk_tag", "impact_score", "source", "domain", "title", "url"])

    df = news_df.copy()
    df["ticker"] = df.get("ticker", "").astype(str).str.upper()
    df = df[df["ticker"] == ticker.upper()].copy()

    df["published_at_dt"] = pd.to_datetime(df.get("published_at", None), errors="coerce", utc=True)
    df["impact_score"] = pd.to_numeric(df.get("impact_score", 0), errors="coerce").fillna(0)
    df["risk_tag"] = df.get("risk_tag", "OTHER").astype(str).str.upper()
    df["source"] = df.get("source", "unknown").astype(str)
    df["title"] = df.get("title", "").astype(str)
    df["url"] = df.get("url", "").astype(str)
    df["domain"] = df["url"].apply(extract_domain)

    # prioritize negative / risk-tagged / recent
    tag_weight = {"REGULATORY": 3, "INSURANCE": 3, "LABOR": 2, "SAFETY": 2, "OTHER": 1}
    df["_tag_w"] = df["risk_tag"].map(tag_weight).fillna(1)
    df["_recency"] = df["published_at_dt"].rank(ascending=False, method="dense").fillna(999)
    df["_priority"] = (-df["impact_score"]) * 4 + df["_tag_w"] * 3 + (1000 - df["_recency"])

    df = df.sort_values("_priority", ascending=False).head(top_n)
    df["published_at"] = df["published_at_dt"].dt.strftime("%Y-%m-%d %H:%M UTC")

    return df[["published_at", "risk_tag", "impact_score", "source", "domain", "title", "url"]].copy()


def worst_negative_news(news_df: pd.DataFrame, ticker: str, n: int = 10) -> pd.DataFrame:
    if news_df is None or news_df.empty:
        return pd.DataFrame(columns=["published_at", "risk_tag", "impact_score", "source", "domain", "title", "url"])
    df = news_df.copy()
    df["ticker"] = df.get("ticker", "").astype(str).str.upper()
    df = df[df["ticker"] == ticker.upper()].copy()
    if df.empty:
        return pd.DataFrame(columns=["published_at", "risk_tag", "impact_score", "source", "domain", "title", "url"])

    df["impact_score"] = pd.to_numeric(df.get("impact_score", 0), errors="coerce").fillna(0)
    df["published_at_dt"] = pd.to_datetime(df.get("published_at", None), errors="coerce", utc=True)
    df["source"] = df.get("source", "unknown").astype(str)
    df["title"] = df.get("title", "").astype(str)
    df["url"] = df.get("url", "").astype(str)
    df["risk_tag"] = df.get("risk_tag", "OTHER").astype(str).str.upper()
    df["domain"] = df["url"].apply(extract_domain)
    df["published_at"] = df["published_at_dt"].dt.strftime("%Y-%m-%d %H:%M UTC")

    # lower impact_score = worse (more negative)
    df = df.sort_values(["impact_score", "published_at_dt"], ascending=[True, False]).head(n)
    return df[["published_at", "risk_tag", "impact_score", "source", "domain", "title", "url"]].copy()


# ---------------------------
# Excel helpers
# ---------------------------
def _autosize_columns(ws):
    for col in ws.columns:
        max_len = 10
        col_letter = col[0].column_letter
        for cell in col:
            try:
                v = "" if cell.value is None else str(cell.value)
                max_len = max(max_len, len(v))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(60, max_len + 2)


def _style_table(ws, name: str):
    try:
        tab = Table(displayName="T" + "".join([c for c in name if c.isalnum()])[:24], ref=ws.dimensions)
        style = TableStyleInfo(name="TableStyleMedium9", showRowStripes=True, showColumnStripes=False)
        tab.tableStyleInfo = style
        ws.add_table(tab)
    except Exception:
        pass


def _add_df_sheet(wb: Workbook, name: str, df: pd.DataFrame):
    ws = wb.create_sheet(title=name)
    if df is None or df.empty:
        ws["A1"] = "No data"
        return ws
    for r in dataframe_to_rows(df, index=False, header=True):
        ws.append(r)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    _style_table(ws, name)
    _autosize_columns(ws)
    return ws


def write_excel_report(path: Path, summary: dict, card: dict, curated: pd.DataFrame):
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)

    ws = wb.create_sheet("Decision_Card")
    ws.append(["key", "value"])
    for cell in ws[1]:
        cell.font = Font(bold=True)

    rows = [
        ("ticker", TICKER),
        ("generated", _utc_now()),
        ("score", summary.get("score")),
        ("rating", summary.get("rating")),
        ("data_completeness_score", summary.get("data_completeness_score")),
        ("confidence_score", summary.get("confidence_score")),
        ("confidence_explainer", "Higher = easier to verify sources quickly. Low = concentrated sources / fewer top-tier links."),
        ("bucket_scores", json.dumps(summary.get("bucket_scores", {}))),
        ("lights", json.dumps(card.get("lights", {}))),
        ("red_flags", json.dumps(summary.get("red_flags", []))),
    ]
    for k, v in rows:
        ws.append([k, v])
    ws.freeze_panes = "A2"
    _autosize_columns(ws)

    _add_df_sheet(wb, "Curated_Evidence", curated)
    _add_df_sheet(wb, "Metric_Cheat_Sheet", metric_cheat_sheet())

    # Key inputs (human readable)
    ki = summary.get("key_inputs_used", {}) or {}
    df_ki = pd.DataFrame([{"Metric": k, "Raw": v} for k, v in ki.items()])

    def to_num(x):
        try:
            return float(x)
        except Exception:
            return None

    def dollars_to_b(x):
        n = to_num(x)
        if n is None:
            return None
        return n / 1e9

    if not df_ki.empty:
        df_ki["Value ($B)"] = df_ki["Raw"].apply(dollars_to_b)

    ws2 = _add_df_sheet(wb, "Key_Inputs_Human", df_ki)
    # format $B column
    if "Value ($B)" in df_ki.columns:
        col_idx = list(df_ki.columns).index("Value ($B)") + 1
        for r in range(2, ws2.max_row + 1):
            ws2.cell(row=r, column=col_idx).number_format = "0.00"

    wb.save(path)


def _df_to_html(df: pd.DataFrame, max_rows=50, link_title_col="title", url_col="url") -> str:
    if df is None or df.empty:
        return "<p><em>No data.</em></p>"
    d = df.head(max_rows).copy()
    if link_title_col in d.columns and url_col in d.columns:
        def linkify(row):
            u = str(row.get(url_col, ""))
            t = str(row.get(link_title_col, ""))
            if u.startswith("http"):
                return f'<a href="{u}" target="_blank" rel="noopener noreferrer">{t}</a>'
            return t
        d[link_title_col] = d.apply(linkify, axis=1)
    return d.to_html(index=False, escape=False)


def write_html_report(path: Path, summary: dict, card: dict, curated: pd.DataFrame, worst: pd.DataFrame, news_df: pd.DataFrame):
    path.parent.mkdir(parents=True, exist_ok=True)

    score = summary.get("score")
    rating = summary.get("rating")
    completeness = summary.get("data_completeness_score")
    confidence = summary.get("confidence_score")
    conf_reasons = summary.get("confidence_reasons", []) or []
    conf_meta = summary.get("confidence_meta", {}) or {}
    red_flags = summary.get("red_flags", []) or []
    red_flags_structured = summary.get("red_flags_structured", []) or []
    buckets = summary.get("bucket_scores", {}) or {}
    lights = card.get("lights", {}) or {}

    # quick helper text for confidence
    if confidence is None:
        confidence_label = "N/A"
        confidence_help = "Confidence is not computed."
    else:
        c = float(confidence)
        if c >= 70:
            confidence_label = f"{int(c)}/100 (High)"
        elif c >= 40:
            confidence_label = f"{int(c)}/100 (Medium)"
        else:
            confidence_label = f"{int(c)}/100 (Low)"
        confidence_help = "This is veracity/ease-of-verification. Low usually means evidence is concentrated in 1 source or few top-tier publisher links."

    def bucket_rows():
        rows = ""
        for k, v in buckets.items():
            rows += f"<tr><td>{k}</td><td>{v}</td><td>{lights.get(k,'')}</td></tr>"
        return rows

    def red_flag_cards():
        if not red_flags_structured:
            return "<p><em>No structured red flags found this run.</em></p>"
        blocks = []
        for rf in red_flags_structured[:12]:
            blocks.append(
                f"""
                <div class="rf">
                  <div class="rf-title">[{rf.get('severity')}] {rf.get('title')}</div>
                  <div class="rf-body">
                    <b>Plain English:</b> {rf.get('plain_english','')}<br/>
                    <b>Why it matters:</b> {rf.get('why_it_matters','')}<br/>
                    <b>What to check:</b> {rf.get('what_to_check','')}
                  </div>
                </div>
                """
            )
        return "\n".join(blocks)

    conf_reason_html = "<ul>" + "".join([f"<li>{r}</li>" for r in conf_reasons[:8]]) + "</ul>" if conf_reasons else "<p><em>No reasons.</em></p>"

    html = f"""
    <html><head><meta charset="utf-8"/>
    <title>Decision Report — {TICKER}</title>
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; padding: 24px; background:#fbfbfb; }}
      .muted {{ color:#666; }}
      .grid {{ display:grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
      .card {{ border:1px solid #e6e6e6; border-radius: 12px; padding: 14px; background: #fff; }}
      .score {{ font-size: 30px; font-weight: 800; }}
      .pill {{ display:inline-block; padding: 6px 10px; border-radius: 999px; background:#f2f2f2; font-weight:700; }}
      table {{ border-collapse: collapse; width: 100%; background:#fff; }}
      th, td {{ border: 1px solid #ddd; padding: 8px; font-size: 13px; vertical-align: top; }}
      th {{ background: #f5f5f5; }}
      .rf {{ border:1px solid #eee; border-radius: 12px; padding: 12px; margin: 10px 0; background:#fff; }}
      .rf-title {{ font-weight: 800; margin-bottom: 6px; }}
      .rf-body {{ line-height: 1.4; }}
      .mini {{ font-size: 12px; }}
      .section {{ margin-top: 18px; }}
    </style>
    </head><body>
      <h1>Decision Report — {TICKER}</h1>
      <div class="muted">Generated: {_utc_now()}</div>

      <div class="grid section">
        <div class="card">
          <div class="score">{score}/100</div>
          <div><span class="pill">{rating}</span></div>
          <p><b>Completeness:</b> {completeness}/100</p>
          <p><b>Confidence (veracity):</b> {confidence_label}</p>
          <p class="mini muted">{confidence_help}</p>
        </div>

        <div class="card">
          <h3 style="margin-top:0;">Buckets</h3>
          <table>
            <tr><th>Bucket</th><th>Points</th><th>Light</th></tr>
            {bucket_rows()}
          </table>
        </div>
      </div>

      <div class="card section">
        <h2 style="margin-top:0;">Red Flags (Risks You Must Read)</h2>
        {red_flag_cards()}
        <p class="mini muted">Tip: these are generated from cash-flow volatility, leverage, repeated risk-tag themes, and news shock.</p>
      </div>

      <div class="card section">
        <h2 style="margin-top:0;">Worst Negative Headlines (Top {min(10, len(worst))})</h2>
        {_df_to_html(worst, 50)}
        <p class="mini muted">These are the most negative-impact items. Click to verify.</p>
      </div>

      <div class="card section">
        <h2 style="margin-top:0;">Curated Evidence Pack (Start here)</h2>
        {_df_to_html(curated, 50)}
      </div>

      <div class="card section">
        <h2 style="margin-top:0;">Confidence Breakdown (Why it is {confidence_label})</h2>
        {conf_reason_html}
        <pre class="mini muted" style="white-space: pre-wrap;">{json.dumps(conf_meta, indent=2)[:2500]}</pre>
      </div>

      <div class="card section">
        <h2 style="margin-top:0;">All News (first 200)</h2>
        {_df_to_html(news_df, 200)}
      </div>

    </body></html>
    """
    path.write_text(html, encoding="utf-8")


def write_word_report(path: Path, summary: dict, card: dict, curated: pd.DataFrame, worst: pd.DataFrame):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()

    score = summary.get("score")
    rating = summary.get("rating")
    buckets = summary.get("bucket_scores", {}) or {}
    lights = card.get("lights", {}) or {}
    red_flags_structured = summary.get("red_flags_structured", []) or []
    completeness = summary.get("data_completeness_score")
    missing = summary.get("data_completeness_missing", []) or []
    confidence = summary.get("confidence_score")
    conf_reasons = summary.get("confidence_reasons", []) or []
    scenario = summary.get("scenario_summary", {}) or {}

    doc.add_heading(f"Investment Decision Report — {TICKER}", level=0)
    doc.add_paragraph(f"Generated: {_utc_now()}")

    doc.add_heading("Decision Card (read this first)", level=1)
    doc.add_paragraph(f"Score: {score}/100   |   Rating: {rating}")
    doc.add_paragraph(f"Data completeness: {completeness}/100")
    doc.add_paragraph(f"Confidence (veracity): {confidence if confidence is not None else 'N/A'}/100")

    doc.add_paragraph("Bucket traffic lights:", style="List Bullet")
    for k, v in buckets.items():
        doc.add_paragraph(f"{k}: {v} points → {lights.get(k, 'GRAY')}", style="List Bullet 2")

    doc.add_heading("Next Steps (exactly what to do)", level=1)
    doc.add_paragraph("Use the time budget that fits your life. The goal is quick verification, not perfection.")
    _bullet(doc, "3 minutes:", 0)
    _bullet(doc, "1) Read Decision Card + Red Flags.", 1)
    _bullet(doc, "2) Click Worst Negative Headlines (top 3).", 1)
    _bullet(doc, "3) If the negatives are real + repeating → downgrade thesis confidence.", 1)

    _bullet(doc, "10 minutes:", 0)
    _bullet(doc, "4) Read Curated Evidence Pack (10–12 items).", 1)
    _bullet(doc, "5) Use Metric Cheat Sheet to label numbers good/ok/bad.", 1)

    _bullet(doc, "30 minutes:", 0)
    _bullet(doc, f"6) Compare {TICKER} versus its closest peers in Excel.", 1)
    _bullet(doc, "7) Check scenario ranges (bear/base/bull).", 1)

    doc.add_heading("How the engine arrives at the score", level=1)
    _bullet(doc, "1) Collect inputs: fundamentals + market + peers + news.", 0)
    _bullet(doc, "2) Convert to metrics (TTM cash, growth, margins, yield, leverage).", 0)
    _bullet(doc, "3) Score five buckets and add them.", 0)
    _bullet(doc, "4) Generate red flags + scenarios + confidence.", 0)

    doc.add_heading("Metric Cheat Sheet (good vs bad)", level=1)
    mcs = metric_cheat_sheet()
    t = doc.add_table(rows=1, cols=len(mcs.columns))
    for i, c in enumerate(mcs.columns):
        t.rows[0].cells[i].text = str(c)
    for _, row in mcs.iterrows():
        cells = t.add_row().cells
        for i, c in enumerate(mcs.columns):
            cells[i].text = str(row.get(c, ""))
    _format_table(t)

    doc.add_heading("Red Flags (Risks you must read)", level=1)
    if not red_flags_structured:
        doc.add_paragraph("No structured red flags were found this run.")
    else:
        for rf in red_flags_structured[:12]:
            doc.add_paragraph(f"[{rf.get('severity')}] {rf.get('title')}", style="Heading 2")
            doc.add_paragraph(f"Plain English: {rf.get('plain_english')}")
            doc.add_paragraph(f"Why it matters: {rf.get('why_it_matters')}")
            doc.add_paragraph(f"What to check: {rf.get('what_to_check')}")

    doc.add_heading("Worst Negative Headlines (verify these first)", level=1)
    if worst is None or worst.empty:
        doc.add_paragraph("No worst-negative list available.")
    else:
        for _, row in worst.iterrows():
            _bullet(doc, f"{row.get('published_at')} [{row.get('risk_tag')}] ({row.get('impact_score')}): {row.get('title')}", 0)
            _bullet(doc, str(row.get("url", "")), 1)

    doc.add_heading("Confidence (veracity)", level=1)
    doc.add_paragraph("This is NOT a price prediction. It measures how easy it is to verify evidence by clicking.")
    doc.add_paragraph(f"Confidence score: {confidence if confidence is not None else 'N/A'}/100")
    if conf_reasons:
        doc.add_paragraph("Reasons:", style="List Bullet")
        for r in conf_reasons[:10]:
            doc.add_paragraph(str(r), style="List Bullet 2")

    doc.add_heading("Data completeness (did anything fail?)", level=1)
    if missing:
        doc.add_paragraph("Missing / empty inputs:", style="List Bullet")
        for m in missing:
            doc.add_paragraph(str(m), style="List Bullet 2")
    else:
        doc.add_paragraph("No missing/empty core inputs detected.")

    doc.add_heading("Scenario context (Bear / Base / Bull)", level=1)
    if not scenario or not scenario.get("results"):
        doc.add_paragraph("Scenario model not available.")
    else:
        results = scenario["results"]
        for name in ("bear", "base", "bull"):
            r = results.get(name, {})
            doc.add_paragraph(f"{name.upper()} scenario", style="Heading 2")
            doc.add_paragraph(f"Projected FCF: {r.get('projected_fcf')}")
            doc.add_paragraph(f"Target FCF Yield: {r.get('target_fcf_yield')}")
            doc.add_paragraph(f"Implied Market Cap: {r.get('implied_market_cap')}")
            doc.add_paragraph(f"Implied Upside (%): {r.get('implied_upside_pct')}")

    doc.add_heading("Curated Evidence Pack (start here)", level=1)
    if curated is None or curated.empty:
        doc.add_paragraph("No curated evidence available.")
    else:
        for _, row in curated.iterrows():
            _bullet(doc, f"{row.get('published_at')} [{row.get('risk_tag')}] ({row.get('impact_score')}): {row.get('title')}", 0)
            _bullet(doc, str(row.get("url", "")), 1)

    doc.save(path)


def main():
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    EXPORT.mkdir(parents=True, exist_ok=True)

    summary = _safe_read_json(OUTPUTS / "decision_summary.json")
    card = _safe_read_json(OUTPUTS / f"decision_card_{TICKER}.json")
    news = _safe_read_csv(DATA_PROCESSED / "news_unified.csv")

    curated = curated_evidence_pack(news, TICKER, top_n=12)
    worst = worst_negative_news(news, TICKER, n=10)

    html_path = OUTPUTS / f"decision_report_{TICKER}.html"
    write_html_report(html_path, summary, card, curated, worst, news)

    docx_path = EXPORT / f"{TICKER}_Investment_Report.docx"
    write_word_report(docx_path, summary, card, curated, worst)

    xlsx_path = EXPORT / f"{TICKER}_Investment_Report.xlsx"
    write_excel_report(xlsx_path, summary, card, curated)

    print("DONE ✅ Upgraded reports created:")
    print(f"- {html_path}")
    print(f"- {docx_path}")
    print(f"- {xlsx_path}")


if __name__ == "__main__":
    main()
