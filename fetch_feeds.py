#!/usr/bin/env python3
"""Fetch RSS/Atom feeds listed in feeds.json and write articles.json.

Only title, link, date and a short excerpt are saved. Full articles stay on
the original sites.
"""
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PER_FEED = 12
EXCERPT_CHARS = 220


def strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


def parse_date(text):
    if not text:
        return None
    text = text.strip()
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def local(tag):
    return tag.rsplit("}", 1)[-1]


def child_text(el, *names):
    for c in el:
        if local(c.tag) in names and (c.text or "").strip():
            return c.text
    return ""


def parse_feed(xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = [e for e in root.iter() if local(e.tag) in ("item", "entry")]
    out = []
    for it in items:
        title = strip_html(child_text(it, "title"))
        link = ""
        for c in it:
            if local(c.tag) == "link":
                link = c.get("href") or (c.text or "").strip()
                if link and c.get("rel", "alternate") == "alternate":
                    break
        summary = strip_html(child_text(it, "description", "summary", "encoded", "content"))
        date = parse_date(child_text(it, "pubDate", "published", "updated", "date"))
        if title and link:
            if len(summary) > EXCERPT_CHARS:
                summary = summary[:EXCERPT_CHARS].rsplit(" ", 1)[0] + "…"
            out.append({
                "title": title,
                "link": link,
                "excerpt": summary,
                "date": date.isoformat() if date else None,
            })
    out.sort(key=lambda a: a["date"] or "", reverse=True)
    return out[:PER_FEED]


def main():
    feeds = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))
    articles, status = [], []
    for f in feeds:
        try:
            req = urllib.request.Request(f["url"], headers={"User-Agent": "Tarew2a-feed-reader/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                items = parse_feed(r.read())
            for a in items:
                a["source"], a["topic"] = f["name"], f["topic"]
            articles.extend(items)
            status.append({"source": f["name"], "ok": True, "count": len(items)})
            print(f"OK    {f['name']}: {len(items)}")
        except Exception as e:  # keep going if one feed breaks
            status.append({"source": f["name"], "ok": False, "error": str(e)[:120]})
            print(f"FAIL  {f['name']}: {e}", file=sys.stderr)
    articles.sort(key=lambda a: a["date"] or "", reverse=True)
    data = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "articles": articles,
    }
    (ROOT / "articles.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {len(articles)} articles")


if __name__ == "__main__":
    main()
