#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate sitemap.xml (canonical-only policy aligned with current _redirects)

Canon:
- /daily/ (index)
- /daily/latest.html
- /daily/YYYYMMDD.html
- /daily/tags/{bear|bull|wait}.html
- static pages: /about, /start, /guide, /data-sources, /ads-pr, /privacy, /disclaimer, /contact
- root: /
"""
from __future__ import annotations

import os
import re
import glob
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "daily"
SITEMAP = ROOT / "sitemap.xml"

SITE_ORIGIN = os.environ.get("CR_SITE_ORIGIN", "https://coinrader.net").rstrip("/")


def iso_today_jst() -> str:
    now = dt.datetime.utcnow() + dt.timedelta(hours=9)
    return now.strftime("%Y-%m-%d")


def ymd_to_iso(ymd: str) -> str:
    try:
        return dt.datetime.strptime(ymd, "%Y%m%d").strftime("%Y-%m-%d")
    except Exception:
        return iso_today_jst()


def escape_xml(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") \
                    .replace('"', "&quot;").replace("'", "&apos;")


def url_block(loc: str, lastmod: str = "", changefreq: str = "", priority: str = "") -> str:
    parts = ["  <url>", f"    <loc>{escape_xml(loc)}</loc>"]
    if lastmod:
        parts.append(f"    <lastmod>{escape_xml(lastmod)}</lastmod>")
    if changefreq:
        parts.append(f"    <changefreq>{escape_xml(changefreq)}</changefreq>")
    if priority:
        parts.append(f"    <priority>{escape_xml(priority)}</priority>")
    parts.append("  </url>")
    return "\n".join(parts)


def list_daily_ymds() -> list[str]:
    files = sorted(glob.glob(str(DATA_DIR / "*.json")))
    ymds = []
    for f in files:
        stem = Path(f).stem
        if re.fullmatch(r"\d{8}", stem):
            ymds.append(stem)
    return sorted(set(ymds))


def main() -> None:
    ymds = list_daily_ymds()
    latest_ymd = ymds[-1] if ymds else ""
    latest_iso = ymd_to_iso(latest_ymd) if latest_ymd else iso_today_jst()

    urls: list[tuple[str, str, str, str]] = []

    # Root
    urls.append((f"{SITE_ORIGIN}/", latest_iso, "hourly", "1.0"))

    # Static pages (extensionless canonical)
    static_paths = [
        "/about",
        "/start",
        "/guide",
        "/data-sources",
        "/ads-pr",
        "/privacy",
        "/disclaimer",
        "/contact",
    ]
    for p in static_paths:
        urls.append((f"{SITE_ORIGIN}{p}", latest_iso, "monthly", "0.5"))

    # Daily hub
    urls.append((f"{SITE_ORIGIN}/daily/", latest_iso, "daily", "0.9"))
    urls.append((f"{SITE_ORIGIN}/daily/latest.html", latest_iso, "daily", "0.9"))

    # Tag pages (canonical .html)
    for tag in ["bear", "bull", "wait"]:
        urls.append((f"{SITE_ORIGIN}/daily/tags/{tag}.html", latest_iso, "daily", "0.6"))

    # Daily pages
    for ymd in sorted(ymds, reverse=True):
        urls.append((f"{SITE_ORIGIN}/daily/{ymd}.html", ymd_to_iso(ymd), "daily", "0.8"))

    header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    header += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    body = "\n".join(url_block(*u) for u in urls) + "\n"
    footer = "</urlset>\n"

    SITEMAP.write_text(header + body + footer, encoding="utf-8")
    print(f"[OK] sitemap.xml generated: {SITEMAP} (daily={len(ymds)}, latest={latest_ymd or 'n/a'})")


if __name__ == "__main__":
    main()
