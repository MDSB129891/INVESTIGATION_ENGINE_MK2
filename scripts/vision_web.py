#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import os
import shlex
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote

ROOT = Path(__file__).resolve().parents[1]


def _run_vision(ticker: str, thesis: str, peers: str, strict: bool) -> tuple[int, str]:
    py = os.environ.get("PYTHON", "python3")
    cmd = [py, str(ROOT / "scripts" / "vision.py"), ticker, thesis]
    if peers.strip():
        cmd += ["--peers", peers.strip()]
    if strict:
        cmd += ["--strict"]
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
<div class="card"><h2>Vision Iron Legion App</h2>
<div>Run the full armor pipeline using only ticker + thesis.</div></div>
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

        form = """
<div class="card">
  <form method="POST" action="/run">
    <label>Ticker</label><input name="ticker" value="GM"/>
    <label>Thesis</label><textarea name="thesis" rows="4">GM is going to increase in value due to its pivot to EV and hybrid vehicles.</textarea>
    <label>Peers (optional, comma-separated)</label><input name="peers" value="F,TM"/>
    <label><input type="checkbox" name="strict" checked/> Strict mode</label><br/><br/>
    <button type="submit">Run Vision</button>
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
        peers = (q.get("peers", [""])[0] or "").strip()
        strict = "strict" in q

        if not ticker or not thesis:
            self._send(400, _page("<div class='card'>Ticker and thesis are required.</div>"))
            return

        rc, out = _run_vision(ticker, thesis, peers, strict)
        safe_out = html.escape(out[-30000:])
        canon = ROOT / "export" / f"CANON_{ticker}"
        hud_rel = f"export/CANON_{ticker}/{ticker}_IRONMAN_HUD.html"
        il_rel = f"outputs/iron_legion_command_{ticker}.html"
        mr_rel = f"outputs/mission_report_{ticker}.html"
        pi_rel = f"outputs/pipeline_integrity_{ticker}.json"
        body = f"""
<div class="card">
  <div><b>Status:</b> {"SUCCESS" if rc == 0 else "DEGRADED / FAILED STEP"}</div>
  <div><b>Command:</b> <code>{html.escape('python3 scripts/vision.py ' + shlex.quote(ticker) + ' ' + shlex.quote(thesis))}</code></div>
  <div style="margin-top:8px;">Open outputs:</div>
  <ul>
    <li><a href="/artifact?path={quote(hud_rel)}">{ticker}_IRONMAN_HUD.html</a></li>
    <li><a href="/artifact?path={quote(il_rel)}">iron_legion_command_{ticker}.html</a></li>
    <li><a href="/artifact?path={quote(mr_rel)}">mission_report_{ticker}.html</a></li>
    <li><a href="/artifact?path={quote(pi_rel)}">pipeline_integrity_{ticker}.json</a></li>
  </ul>
  <div><b>Log tail:</b></div>
  <code>{safe_out}</code>
</div>
<div class="card"><a href="/">Run another ticker</a></div>
"""
        self._send(200, _page(body))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Vision web app at http://{args.host}:{args.port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
