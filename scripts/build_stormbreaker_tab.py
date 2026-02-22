#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
EXPORT = ROOT / "export"


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _safe_float(v):
    try:
        return float(v)
    except Exception:
        return None


def _fmt_num(v):
    x = _safe_float(v)
    if x is None:
        return "N/A"
    if math.isnan(x) or math.isinf(x):
        return "N/A"
    if abs(x) >= 1_000_000_000:
        return f"{x/1_000_000_000:.2f}B"
    if abs(x) >= 1_000_000:
        return f"{x/1_000_000:.2f}M"
    if abs(x) >= 1_000:
        return f"{x/1_000:.2f}K"
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.3f}"


def _status_class(status: str) -> str:
    s = (status or "").upper()
    if s == "PASS":
        return "good"
    if s == "FAIL":
        return "bad"
    return "neutral"


def _explain(status: str, metric: str, op: str, threshold, actual, rationale: str, meaning: str) -> str:
    s = (status or "").upper()
    th = _fmt_num(threshold)
    ac = _fmt_num(actual)
    if s == "PASS":
        return f"This check passed because `{metric}` is {ac}, which satisfies `{metric} {op} {th}`. {rationale or ''} {meaning or ''}".strip()
    if s == "FAIL":
        return f"This check failed because `{metric}` is {ac}, which does not satisfy `{metric} {op} {th}`. {rationale or ''} {meaning or ''}".strip()
    return f"This check is unknown because data was missing for `{metric}`. Required rule: `{metric} {op} {th}`. {rationale or ''} {meaning or ''}".strip()


def build(ticker: str):
    t = ticker.upper().strip()
    claim = _read_json(OUT / f"claim_evidence_{t}.json", {})
    results = claim.get("results", []) if isinstance(claim, dict) else []
    thesis = claim.get("thesis") or f"{t}: Custom thesis"
    generated = claim.get("as_of") or datetime.now(timezone.utc).isoformat()

    pass_n = sum(1 for r in results if str((r or {}).get("status", "")).upper() == "PASS")
    fail_n = sum(1 for r in results if str((r or {}).get("status", "")).upper() == "FAIL")
    unk_n = sum(1 for r in results if str((r or {}).get("status", "")).upper() == "UNKNOWN")
    total = len(results)

    if fail_n == 0 and pass_n > 0:
        verdict = "THESIS SUPPORTED"
        verdict_cls = "good"
        verdict_explain = "Most available checks support your thesis with current data."
    elif fail_n > 0:
        verdict = "THESIS UNDER PRESSURE"
        verdict_cls = "bad"
        verdict_explain = "At least one key check failed. The thesis may still work, but risk is higher."
    else:
        verdict = "INSUFFICIENT EVIDENCE"
        verdict_cls = "neutral"
        verdict_explain = "Not enough reliable data to confidently confirm or reject the thesis."

    rows = []
    for r in results:
        cl = r.get("claim", {}) if isinstance(r, dict) else {}
        status = str(r.get("status") or "UNKNOWN").upper()
        metric = str(cl.get("metric") or "")
        op = str(cl.get("operator") or "")
        threshold = cl.get("threshold")
        actual = r.get("actual")
        rationale = str(cl.get("rationale") or "")
        meaning = str(r.get("meaning") or "")
        why = _explain(status, metric, op, threshold, actual, rationale, meaning)
        rows.append(
            "<tr>"
            f"<td>{cl.get('id','')}</td>"
            f"<td><span class='pill {_status_class(status)}'>{status}</span></td>"
            f"<td>{metric}</td>"
            f"<td>{metric} {op} {_fmt_num(threshold)}</td>"
            f"<td>{_fmt_num(actual)}</td>"
            f"<td>{rationale}</td>"
            f"<td>{why}</td>"
            "</tr>"
        )

    canon = EXPORT / f"CANON_{t}"
    canon.mkdir(parents=True, exist_ok=True)
    html_path = canon / f"{t}_STORMBREAKER.html"

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Stormbreaker Evidence — {t}</title>
<style>
body{{font-family:ui-sans-serif,system-ui;background:#0b1220;color:#e9f1ff;margin:0}}
.wrap{{max-width:1180px;margin:0 auto;padding:24px 18px 40px}}
.card{{background:#111a2b;border:1px solid #263a5a;border-radius:14px;padding:14px;margin-top:12px}}
.k{{font-size:11px;letter-spacing:.1em;color:#97add0;text-transform:uppercase}}
.v{{font-size:26px;font-weight:800;margin-top:8px}}
.pill{{padding:3px 8px;border-radius:999px;border:1px solid transparent;font-size:12px}}
.pill.good{{color:#23d18b;background:rgba(35,209,139,.1);border-color:rgba(35,209,139,.3)}}
.pill.bad{{color:#ff7a7a;background:rgba(255,122,122,.1);border-color:rgba(255,122,122,.3)}}
.pill.neutral{{color:#9db2d4;background:rgba(157,178,212,.1);border-color:rgba(157,178,212,.3)}}
table{{width:100%;border-collapse:collapse;margin-top:10px}}
th,td{{border-bottom:1px solid #1f2d44;padding:8px 6px;text-align:left;vertical-align:top;font-size:13px}}
th{{font-size:11px;letter-spacing:.08em;color:#9bb0d1;text-transform:uppercase}}
a{{color:#8fd3ff;text-decoration:none}}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <div class="k">Stormbreaker · Thesis Evidence Console</div>
    <div class="v">{t}</div>
    <div style="margin-top:8px;"><span class="pill {verdict_cls}">{verdict}</span></div>
    <div style="margin-top:8px;">{verdict_explain}</div>
    <div style="margin-top:10px;"><b>Thesis:</b> {thesis}</div>
    <div style="margin-top:6px;color:#9bb0d1;">Generated: {generated}</div>
    <div style="margin-top:10px;">Summary: <b>{pass_n} PASS</b> · <b>{fail_n} FAIL</b> · <b>{unk_n} UNKNOWN</b> · <b>{total} total checks</b></div>
  </div>

  <div class="card">
    <div class="k">How To Read This (High-School Friendly)</div>
    <div style="margin-top:8px;">1) Each row is one test of your thesis.</div>
    <div>2) Rule = what must be true. Actual = what data says now.</div>
    <div>3) PASS means evidence supports the claim. FAIL means evidence contradicts it.</div>
    <div>4) UNKNOWN means missing data, so confidence should be lower.</div>
  </div>

  <div class="card">
    <div class="k">Evidence Table</div>
    <table>
      <thead>
        <tr><th>ID</th><th>Status</th><th>Metric</th><th>Rule</th><th>Actual</th><th>Why This Rule Exists</th><th>Plain-English Verdict</th></tr>
      </thead>
      <tbody>
        {''.join(rows) if rows else "<tr><td colspan='7'>No claim evidence available for this ticker yet.</td></tr>"}
      </tbody>
    </table>
  </div>

  <div class="card">
    <div class="k">Source Files</div>
    <div><code>outputs/claim_evidence_{t}.json</code></div>
    <div><code>outputs/claim_evidence_{t}.html</code></div>
    <div style="margin-top:8px;"><a href="../../outputs/claim_evidence_{t}.html">Open raw Stormbreaker evidence page</a></div>
  </div>
</div>
</body>
</html>"""

    html_path.write_text(html, encoding="utf-8")
    print("DONE ✅ wrote:", html_path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build dedicated Stormbreaker evidence tab.")
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    build(args.ticker)
