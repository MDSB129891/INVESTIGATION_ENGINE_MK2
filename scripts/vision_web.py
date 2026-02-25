#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import os
import shlex
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote

ROOT = Path(__file__).resolve().parents[1]
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _python_ge_311(py: str) -> bool:
    try:
        p = subprocess.run(
            [py, "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        return p.returncode == 0
    except Exception:
        return False


def _select_python() -> str:
    env_py = os.environ.get("PYTHON", "").strip()
    candidates = []
    if env_py:
        candidates.append(env_py)
    venv_py = ROOT / ".venv" / "bin" / "python"
    if venv_py.exists():
        candidates.append(str(venv_py))
    candidates += ["python3.14", "python3.13", "python3.12", "python3.11", "python3"]
    for c in candidates:
        if _python_ge_311(c):
            return c
    return "python3"


def _run_vision(ticker: str, thesis: str) -> tuple[int, str]:
    py = _select_python()
    cmd = [py, str(ROOT / "scripts" / "vision.py"), ticker, thesis]
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
        return p.returncode, out
    except Exception as e:
        return 1, f"Failed to run vision: {e}"


def _page(body: str) -> bytes:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Vision Iron Legion App</title>
<style>
body{{font-family:ui-sans-serif,system-ui;background:#0b1220;color:#e6ecfa;margin:0;padding:24px}}
.card{{background:#131d32;border:1px solid #243754;border-radius:12px;padding:14px;margin-bottom:14px}}
input,textarea{{width:100%;padding:10px;border-radius:8px;border:1px solid #324d77;background:#0f1728;color:#e6ecfa}}
button{{padding:10px 14px;border-radius:8px;border:1px solid #3d78d8;background:#1955b8;color:#fff;cursor:pointer}}
a{{color:#8fd3ff}}
code{{white-space:pre-wrap}}
</style></head><body>
<div class="card"><h2>Iron Legion Mobile Console</h2>
<div>Run the full pipeline using only ticker + thesis, then open outputs from your phone.</div></div>
{body}
</body></html>""".encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, _page("<div class='card'>ok</div>"))
            return

        if self.path.startswith("/run/"):
            job_id = self.path.split("?", 1)[0].rsplit("/", 1)[-1].strip()
            with JOBS_LOCK:
                job = JOBS.get(job_id)
            if not job:
                self._send(404, _page("<div class='card'>Run not found.</div>"))
                return

            ticker = str(job.get("ticker", ""))
            thesis = str(job.get("thesis", ""))
            status = str(job.get("status", "unknown")).lower()
            created = float(job.get("created_at", time.time()))
            elapsed = max(0, int(time.time() - created))
            out = str(job.get("log_tail", ""))
            rc = job.get("returncode")

            if status in {"queued", "running"}:
                refresh = '<meta http-equiv="refresh" content="3">'
                body = f"""
<div class="card">
  {refresh}
  <div><b>Status:</b> {status.upper()}</div>
  <div><b>Ticker:</b> {html.escape(ticker)}</div>
  <div><b>Elapsed:</b> {elapsed}s</div>
  <div style="margin-top:8px;opacity:.8;">Pipeline is running in background. This page auto-refreshes.</div>
  <div style="margin-top:8px;"><a href="/">Start another run</a></div>
</div>
"""
                self._send(200, _page(body))
                return

            safe_out = html.escape(out[-30000:])
            hud_rel = f"export/CANON_{ticker}/{ticker}_IRONMAN_HUD.html"
            ns_rel = f"export/CANON_{ticker}/{ticker}_NEWS_SOURCES.html"
            il_rel = f"outputs/iron_legion_command_{ticker}.html"
            sb_rel = f"export/CANON_{ticker}/{ticker}_STORMBREAKER.html"
            ts_rel = f"export/CANON_{ticker}/{ticker}_TIMESTONE.html"
            rcpt_rel = f"outputs/receipts_{ticker}.html"
            pdf_rel = f"export/{ticker}_Full_Investment_Memo.pdf"
            pi_rel = f"outputs/pipeline_integrity_{ticker}.json"
            body = f"""
<div class="card">
  <div><b>Status:</b> {"SUCCESS" if rc == 0 else "DEGRADED / FAILED STEP"}</div>
  <div><b>Ticker:</b> {html.escape(ticker)}</div>
  <div><b>Thesis:</b> {html.escape(thesis)}</div>
  <div style="margin-top:8px;"><b>Open outputs:</b></div>
  <ul>
    <li><a target="_blank" href="/artifact?path={quote(hud_rel)}">{ticker}_IRONMAN_HUD.html</a></li>
    <li><a target="_blank" href="/artifact?path={quote(ns_rel)}">{ticker}_NEWS_SOURCES.html</a></li>
    <li><a target="_blank" href="/artifact?path={quote(sb_rel)}">{ticker}_STORMBREAKER.html</a></li>
    <li><a target="_blank" href="/artifact?path={quote(il_rel)}">iron_legion_command_{ticker}.html</a></li>
    <li><a target="_blank" href="/artifact?path={quote(rcpt_rel)}">receipts_{ticker}.html</a></li>
    <li><a target="_blank" href="/artifact?path={quote(ts_rel)}">{ticker}_TIMESTONE.html</a></li>
    <li><a target="_blank" href="/artifact?path={quote(pdf_rel)}">{ticker}_Full_Investment_Memo.pdf</a></li>
    <li><a target="_blank" href="/artifact?path={quote(pi_rel)}">pipeline_integrity_{ticker}.json</a></li>
  </ul>
  <div><b>Log tail:</b></div>
  <code>{safe_out}</code>
</div>
<div class="card"><a href="/">Run another ticker</a></div>
"""
            self._send(200, _page(body))
            return

        if self.path.startswith("/artifact?"):
            qs = parse_qs(self.path.split("?", 1)[1])
            raw = (qs.get("path", [""])[0] or "").strip()
            if not raw:
                self._send(400, _page("<div class='card'>Missing artifact path.</div>"))
                return
            p = (ROOT / raw).resolve()
            if ROOT not in p.parents and p != ROOT:
                self._send(403, _page("<div class='card'>Forbidden path.</div>"))
                return
            if not p.exists():
                self._send(404, _page(f"<div class='card'>Artifact not found: {html.escape(raw)}</div>"))
                return
            try:
                if p.suffix.lower() == ".json":
                    body = f"<div class='card'><h3>{html.escape(raw)}</h3><code>{html.escape(p.read_text(encoding='utf-8', errors='ignore'))}</code></div>"
                else:
                    body = f"<div class='card'><h3>{html.escape(raw)}</h3><div><a href='/'>Back</a></div></div>"
                    body += p.read_text(encoding="utf-8", errors="ignore")
                self._send(200, _page(body))
                return
            except Exception as e:
                self._send(500, _page(f"<div class='card'>Failed to read artifact: {html.escape(str(e))}</div>"))
                return

        with JOBS_LOCK:
            running = next((jid for jid, j in JOBS.items() if str(j.get("status")) in {"queued", "running"}), "")

        running_note = ""
        if running:
            running_note = f"<div class='card'><b>Active run:</b> <a href='/run/{html.escape(running)}'>Open status</a></div>"

        form = f"""
{running_note}
<div class="card">
  <form method="POST" action="/run">
    <label>Ticker</label><input name="ticker" value="" placeholder="e.g. GOOGL"/>
    <label>Thesis</label><textarea name="thesis" rows="4" placeholder="e.g. AI demand can support revenue and margin expansion over the next 6-12 months."></textarea>
    <br/><button type="submit">Run Full Pipeline</button>
  </form>
</div>
"""
        self._send(200, _page(form))

    def do_POST(self):
        if self.path != "/run":
            self._send(404, _page("<div class='card'>Not found.</div>"))
            return
        n = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(n).decode("utf-8", errors="ignore")
        q = parse_qs(raw)
        ticker = (q.get("ticker", [""])[0] or "").strip().upper()
        thesis = (q.get("thesis", [""])[0] or "").strip()

        if not ticker or not thesis:
            self._send(400, _page("<div class='card'>Ticker and thesis are required.</div>"))
            return

        with JOBS_LOCK:
            running = next((jid for jid, j in JOBS.items() if str(j.get("status")) in {"queued", "running"}), "")
            if running:
                body = f"<div class='card'>A run is already active. <a href='/run/{html.escape(running)}'>Open status</a></div>"
                self._send(409, _page(body))
                return

            job_id = uuid.uuid4().hex[:12]
            JOBS[job_id] = {
                "id": job_id,
                "ticker": ticker,
                "thesis": thesis,
                "status": "queued",
                "created_at": time.time(),
                "returncode": None,
                "log_tail": "",
            }

        def _worker(jid: str, tk: str, th: str):
            with JOBS_LOCK:
                if jid in JOBS:
                    JOBS[jid]["status"] = "running"
            rc, out = _run_vision(tk, th)
            with JOBS_LOCK:
                if jid in JOBS:
                    JOBS[jid]["status"] = "done" if rc == 0 else "failed"
                    JOBS[jid]["returncode"] = rc
                    JOBS[jid]["log_tail"] = out[-120000:]
                    JOBS[jid]["finished_at"] = time.time()

        threading.Thread(target=_worker, args=(job_id, ticker, thesis), daemon=True).start()
        self.send_response(303)
        self.send_header("Location", f"/run/{job_id}")
        self.end_headers()


def main():
    if sys.version_info < (3, 11):
        print("WARNING: vision_web.py is running on Python < 3.11. It will invoke a 3.11+ interpreter if available.")
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Vision web app at http://{args.host}:{args.port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
