#!/usr/bin/env python3
import argparse, html, json, urllib.parse, urllib.request
from pathlib import Path
from datetime import datetime
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
CANON_ROOT = ROOT / "export"

def fetch_rss(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def parse_google_news_rss(ticker: str, query: str):
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    raw = fetch_rss(url)
    root = ET.fromstring(raw)

    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        try:
            dt = parsedate_to_datetime(pub).astimezone()
            pub_iso = dt.isoformat()
        except Exception:
            pub_iso = pub
        source = ""
        s = item.find("source")
        if s is not None and s.text:
            source = s.text.strip()
        items.append({
            "ticker": ticker,
            "query": query,
            "title": title,
            "link": link,
            "source": source,
            "published": pub_iso,
        })
    return url, items

def main(ticker: str):
    T = ticker.upper().strip()
    canon = CANON_ROOT / f"CANON_{T}"
    canon.mkdir(parents=True, exist_ok=True)

    # Queries: general + risk-themed (labor/regulatory/insurance)
    queries = [
        f"{T} stock",
        f"{T} earnings",
        f"{T} regulation",
        f"{T} labor drivers employees",
        f"{T} insurance lawsuits",
    ]

    all_items = []
    urls = []
    for q in queries:
        try:
            u, items = parse_google_news_rss(T, q)
            urls.append({"query": q, "rss_url": u, "count": len(items)})
            all_items.extend(items)
        except Exception as e:
            urls.append({"query": q, "error": str(e)})

    # De-dupe by link
    seen = set()
    uniq = []
    for it in all_items:
        k = it.get("link") or it.get("title")
        if not k or k in seen:
            continue
        seen.add(k)
        uniq.append(it)

    out = {
        "ticker": T,
        "generated_utc": datetime.utcnow().isoformat() + "Z",
        "feeds": urls,
        "items": uniq[:80],
    }

    jpath = canon / f"{T}_FREE_NEWS.json"
    jpath.write_text(json.dumps(out, indent=2), encoding="utf-8")

    # HTML clickpack (phone-friendly)
    hpath = canon / f"{T}_FREE_NEWS.html"
    rows = []
    rows.append(f"<h1>{T} — FREE NEWS (Google News RSS)</h1>")
    rows.append("<p>No API key. De-duped. Risk-themed queries included.</p>")
    rows.append("<h2>Feeds</h2><pre>" + html.escape(json.dumps(urls, indent=2)) + "</pre>")
    rows.append("<h2>Top Items</h2><ol>")
    for it in out["items"]:
        title = html.escape(it.get("title",""))
        link = html.escape(it.get("link",""))
        src = html.escape(it.get("source",""))
        pub = html.escape(it.get("published",""))
        rows.append(f"<li><a href='{link}' target='_blank' rel='noreferrer'>{title}</a>"
                    f"<br><small>{src} — {pub}</small></li>")
    rows.append("</ol>")
    hpath.write_text("\n".join(rows), encoding="utf-8")

    print("DONE ✅ wrote:", jpath)
    print("DONE ✅ wrote:", hpath)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)
