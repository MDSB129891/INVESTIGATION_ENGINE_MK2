#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
DATA = ROOT / "data" / "processed"


def _read_json(path: Path, default=None):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {} if default is None else default


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        if path.exists():
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame()


def _fmt_status(ok, enabled: bool):
    if not enabled:
        return ("Disabled", "neutral")
    if ok is True:
        return ("Online", "good")
    if ok is False:
        return ("Failing", "bad")
    return ("Unknown", "neutral")


def _safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


def _headline_rows_html(df: pd.DataFrame, limit: int = 18) -> str:
    if df.empty:
        return "<tr><td colspan='5' style='opacity:.75;'>No headline evidence rows available for this ticker yet.</td></tr>"
    rows = []
    for _, r in df.head(limit).iterrows():
        dt = html.escape(str(r.get("published_at", "—")))
        src = html.escape(str(r.get("source", "—")))
        tag = html.escape(str(r.get("risk_tag", "—")))
        impact = html.escape(str(r.get("impact_score", "—")))
        title = html.escape(str(r.get("title", "Untitled headline")))
        url = str(r.get("url", "") or "").strip()
        if url and url != "nan":
            title_html = f"<a href='{html.escape(url)}' target='_blank' rel='noopener noreferrer'>{title}</a>"
        else:
            title_html = title
        rows.append(
            "<tr>"
            f"<td>{dt}</td>"
            f"<td>{src}</td>"
            f"<td>{tag}</td>"
            f"<td>{impact}</td>"
            f"<td>{title_html}</td>"
            "</tr>"
        )
    return "".join(rows)


def main(ticker: str):
    t = ticker.upper().strip()
    canon = ROOT / "export" / f"CANON_{t}"
    canon.mkdir(parents=True, exist_ok=True)

    ds = _read_json(OUT / f"decision_summary_{t}.json", _read_json(OUT / "decision_summary.json", {}))
    ph = _read_json(OUT / f"provider_health_{t}.json", {})
    evidence_csv = DATA / f"news_evidence_{t}.csv"
    evidence_df = _read_csv(evidence_csv)
    unified_df = _read_csv(DATA / "news_unified.csv")

    enabled_sources = [str(x).lower() for x in (ds.get("news_sources_enabled") or [])]
    checks = (ph.get("checks") or []) if isinstance(ph, dict) else []
    checks_by_name = {str(c.get("name")): c for c in checks if isinstance(c, dict)}

    source_key_present = {
        "sec": True,
        "finnhub": bool(ph.get("finnhub_api_key_present")),
        "tiingo": bool(ph.get("tiingo_api_key_present")),
        "marketaux": bool(ph.get("marketaux_api_key_present")),
        "alphavantage": bool(ph.get("alphavantage_api_key_present")),
    }
    source_check_name = {
        "sec": "news_sec_submissions",
        "finnhub": "news_finnhub_company_news",
        "tiingo": "news_tiingo_news",
        "marketaux": "news_marketaux_news",
        "alphavantage": "news_alphavantage_news",
    }
    source_label = {
        "sec": "SEC Filings",
        "finnhub": "Finnhub",
        "tiingo": "Tiingo",
        "marketaux": "Marketaux",
        "alphavantage": "AlphaVantage",
    }

    source_counts_30d = {}
    if not unified_df.empty and {"ticker", "source", "published_at"}.issubset(set(unified_df.columns)):
        x = unified_df.copy()
        x["ticker"] = x["ticker"].astype(str).str.upper()
        x = x[x["ticker"] == t]
        x["published_at"] = pd.to_datetime(x["published_at"], utc=True, errors="coerce")
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        x = x[x["published_at"] >= cutoff]
        if not x.empty:
            source_counts_30d = x["source"].astype(str).str.lower().value_counts().to_dict()

    source_rows = []
    for src in ["sec", "finnhub", "tiingo", "marketaux", "alphavantage"]:
        enabled = src in enabled_sources
        key_ok = bool(source_key_present.get(src, False))
        ck = checks_by_name.get(source_check_name[src]) or {}
        preflight_ok = ck.get("ok") if isinstance(ck, dict) else None
        status_code = ck.get("status_code") if isinstance(ck, dict) else None
        endpoint = (ck.get("url") if isinstance(ck, dict) else None) or "—"
        err = (ck.get("error") if isinstance(ck, dict) else None) or ""
        article_count = _safe_int(source_counts_30d.get(src, 0), 0)
        status_text, status_cls = _fmt_status(preflight_ok, enabled)

        if not enabled:
            note = "Source is not enabled for this run."
        elif article_count > 0:
            note = f"Collected {article_count} article(s) in last 30 days."
        elif preflight_ok is True:
            note = "Provider reachable but no recent headlines for this ticker window."
        else:
            note = str(err or "Source check failed. Use fallback sources.")

        source_rows.append(
            {
                "source": src,
                "source_label": source_label[src],
                "enabled": enabled,
                "api_key_present": key_ok,
                "preflight_ok": preflight_ok,
                "status_code": status_code,
                "endpoint": endpoint,
                "articles_30d": article_count,
                "status_text": status_text,
                "status_cls": status_cls,
                "note": note,
            }
        )

    enabled_count = sum(1 for r in source_rows if r["enabled"])
    checks_passed = sum(1 for r in source_rows if r["enabled"] and r["preflight_ok"] is True)
    evidence_rows = int(len(evidence_df.index)) if not evidence_df.empty else 0
    news_age_days = ((ph.get("freshness_sla") or {}).get("ages_days") or {}).get("news")
    if news_age_days is not None:
        try:
            news_age_days = round(float(news_age_days), 2)
        except Exception:
            news_age_days = None

    if enabled_count >= 2 and checks_passed >= 2 and evidence_rows >= 20:
        trust_grade = "HIGH"
        trust_explain = "News layer has multi-source coverage and enough evidence rows."
        trust_cls = "good"
    elif checks_passed >= 1 and evidence_rows > 0:
        trust_grade = "MEDIUM"
        trust_explain = "News layer is usable, but coverage is partial."
        trust_cls = "ok"
    else:
        trust_grade = "LOW"
        trust_explain = "News layer is thin or failing checks; treat news signals as weak."
        trust_cls = "bad"

    payload = {
        "ticker": t,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "enabled_sources": enabled_sources,
        "source_counts_30d": source_counts_30d,
        "evidence_rows_30d": evidence_rows,
        "checks_passed": checks_passed,
        "checks_total_enabled": enabled_count,
        "freshness_news_age_days": news_age_days,
        "trust_grade": trust_grade,
        "trust_explain": trust_explain,
        "source_checks": source_rows,
        "files": {
            "provider_health": f"outputs/provider_health_{t}.json",
            "decision_summary": f"outputs/decision_summary_{t}.json",
            "news_evidence_csv": f"data/processed/news_evidence_{t}.csv",
            "news_evidence_html": f"outputs/news_evidence_{t}.html",
        },
    }

    out_json = OUT / f"news_sources_{t}.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    source_rows_html = []
    for r in source_rows:
        endpoint_html = html.escape(str(r["endpoint"]))
        note_html = html.escape(str(r["note"]))
        sc = "—" if r["status_code"] is None else str(r["status_code"])
        source_rows_html.append(
            "<tr>"
            f"<td><b>{html.escape(r['source_label'])}</b></td>"
            f"<td>{'Yes' if r['enabled'] else 'No'}</td>"
            f"<td>{'Yes' if r['api_key_present'] else ('N/A' if r['source'] == 'sec' else 'No')}</td>"
            f"<td><span class='tone {r['status_cls']}'>{html.escape(r['status_text'])}</span></td>"
            f"<td>{html.escape(sc)}</td>"
            f"<td>{r['articles_30d']}</td>"
            f"<td><code>{endpoint_html}</code></td>"
            f"<td>{note_html}</td>"
            "</tr>"
        )

    evidence_html = _headline_rows_html(evidence_df, limit=20)
    source_mix = ", ".join(f"{k}:{v}" for k, v in sorted(source_counts_30d.items(), key=lambda kv: (-kv[1], kv[0])))
    if not source_mix:
        source_mix = "—"

    html_doc = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>J.A.R.V.I.S. News Sensor Grid — {t}</title>
  <style>
    :root {{ --bg:#0b1220; --card:#111a2b; --line:#243451; --txt:#e8efff; --muted:#9fb2d1; }}
    body {{ margin:0; font-family: ui-sans-serif, system-ui; background: var(--bg); color: var(--txt); }}
    .wrap {{ max-width: 1280px; margin: 0 auto; padding: 22px; }}
    .card {{ background: var(--card); border:1px solid var(--line); border-radius: 14px; padding: 14px; margin-top: 12px; }}
    .k {{ color: var(--muted); text-transform: uppercase; letter-spacing: .08em; font-size: 11px; margin-bottom: 8px; }}
    .row {{ display:flex; justify-content:space-between; gap:12px; margin: 6px 0; }}
    .small {{ font-size: 13px; color: var(--muted); }}
    table {{ width:100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #22314b; padding: 8px 6px; font-size: 13px; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); text-transform: uppercase; letter-spacing: .08em; font-size: 11px; }}
    a {{ color: #8fd2ff; text-decoration: none; }}
    code {{ background:#0d1628; border:1px solid #1f3254; padding:2px 6px; border-radius:999px; }}
    .tone {{ font-size:11px; border-radius:999px; padding:3px 8px; border:1px solid transparent; }}
    .tone.good {{ color:#23d18b; border-color:rgba(35,209,139,.35); background:rgba(35,209,139,.08); }}
    .tone.ok {{ color:#f4c267; border-color:rgba(244,194,103,.35); background:rgba(244,194,103,.08); }}
    .tone.bad {{ color:#ff7b7b; border-color:rgba(255,123,123,.35); background:rgba(255,123,123,.08); }}
    .tone.neutral {{ color:#9cb1d0; border-color:rgba(156,177,208,.35); background:rgba(156,177,208,.08); }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="k">News Sources</div>
      <h1 style="margin:0;">J.A.R.V.I.S. News Sensor Grid — {t}</h1>
      <div class="small">This page shows exactly which news providers were used, whether they passed checks, and where each headline can be verified.</div>
      <div class="row"><div>Trust grade</div><div><span class="tone {trust_cls}">{trust_grade}</span></div></div>
      <div class="small">{html.escape(trust_explain)}</div>
      <div class="row"><div>Enabled sources</div><div>{", ".join(s.upper() for s in enabled_sources) if enabled_sources else "—"}</div></div>
      <div class="row"><div>Preflight checks passed</div><div>{checks_passed}/{enabled_count if enabled_count else 0}</div></div>
      <div class="row"><div>Evidence rows (30d)</div><div>{evidence_rows}</div></div>
      <div class="row"><div>News data age (days)</div><div>{news_age_days if news_age_days is not None else "—"}</div></div>
      <div class="small">Source mix (30d): {html.escape(source_mix)}</div>
    </div>

    <div class="card">
      <div class="k">Provider Checks</div>
      <table>
        <thead>
          <tr>
            <th>Source</th><th>Enabled</th><th>API Key</th><th>Preflight</th><th>HTTP</th><th>30d Articles</th><th>Endpoint</th><th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {"".join(source_rows_html)}
        </tbody>
      </table>
    </div>

    <div class="card">
      <div class="k">Headline Evidence (Clickable)</div>
      <div class="small">Open these for raw verification:</div>
      <div class="small"><a href="../../outputs/news_evidence_{t}.html">outputs/news_evidence_{t}.html</a></div>
      <div class="small"><a href="../../data/processed/news_evidence_{t}.csv">data/processed/news_evidence_{t}.csv</a></div>
      <table style="margin-top:8px;">
        <thead>
          <tr><th>Published</th><th>Source</th><th>Risk Tag</th><th>Impact</th><th>Headline</th></tr>
        </thead>
        <tbody>
          {evidence_html}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""

    out_html = canon / f"{t}_NEWS_SOURCES.html"
    out_html.write_text(html_doc, encoding="utf-8")
    print("DONE ✅ wrote:", out_json)
    print("DONE ✅ wrote:", out_html)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)
