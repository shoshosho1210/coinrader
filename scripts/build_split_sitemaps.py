#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = os.environ.get("CR_SITE_ORIGIN", "https://coinrader.net").rstrip("/")
DICT_ALIAS_SLUGS = {"fear-and-greed"}


def ymd2iso(ymd: str) -> str:
    return f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"


def make_urlset(entries: list[tuple[str, str | None]]) -> str:
    body: list[str] = []
    for loc, lastmod in entries:
        if lastmod:
            body.append(f"<url><loc>{loc}</loc><lastmod>{lastmod}</lastmod></url>")
        else:
            body.append(f"<url><loc>{loc}</loc></url>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(body)
        + '\n</urlset>\n'
    )


def collect_daily_ids() -> list[str]:
    out: list[str] = []
    for fp in sorted((ROOT / "data" / "daily").glob("*.json")):
        m = re.fullmatch(r"(\d{8})\.json", fp.name)
        if m:
            out.append(m.group(1))
    return out


def build() -> tuple[int, int, int, str | None]:
    daily_ids = collect_daily_ids()
    latest = daily_ids[-1] if daily_ids else None

    static_paths = [
        "/", "/about", "/start", "/data-sources", "/ads-pr", "/privacy", "/disclaimer", "/contact", "/sponsor", "/en/",
        "/coins/", "/dictionary/", "/guide/",
    ]

    static_entries: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for u in static_paths:
        if u in seen:
            continue
        seen.add(u)
        static_entries.append((f"{ORIGIN}{u}", None))

    guide_dir = ROOT / "guide"
    if guide_dir.exists():
        for pdir in sorted(guide_dir.glob("*/")):
            if (pdir / "index.html").exists():
                static_entries.append((f"{ORIGIN}/guide/{pdir.name}/", None))

    coins_dir = ROOT / "coins"
    if coins_dir.exists():
        for pdir in sorted(coins_dir.glob("*/")):
            if (pdir / "index.html").exists():
                static_entries.append((f"{ORIGIN}/coins/{pdir.name}/", None))

    dictionary_entries: list[tuple[str, str | None]] = []
    dict_dir = ROOT / "dictionary"
    if dict_dir.exists():
        for pdir in sorted(dict_dir.glob("*/")):
            slug = pdir.name.rstrip("/")
            if slug in DICT_ALIAS_SLUGS:
                continue
            if (pdir / "index.html").exists():
                dictionary_entries.append((f"{ORIGIN}/dictionary/{slug}/", None))

    daily_entries: list[tuple[str, str | None]] = []
    if latest:
        lm_latest = ymd2iso(latest)
        for u in ("/daily/", "/daily/tags/bear", "/daily/tags/bull", "/daily/tags/wait"):
            daily_entries.append((f"{ORIGIN}{u}", lm_latest))
    for ymd in daily_ids:
        daily_entries.append((f"{ORIGIN}/daily/{ymd}", ymd2iso(ymd)))

    (ROOT / "sitemap-static.xml").write_text(make_urlset(static_entries), encoding="utf-8")
    (ROOT / "sitemap-dictionary.xml").write_text(make_urlset(dictionary_entries), encoding="utf-8")
    (ROOT / "sitemap-daily.xml").write_text(make_urlset(daily_entries), encoding="utf-8")

    index_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'  <sitemap><loc>{ORIGIN}/sitemap-static.xml</loc></sitemap>\n'
        f'  <sitemap><loc>{ORIGIN}/sitemap-dictionary.xml</loc></sitemap>\n'
        f'  <sitemap><loc>{ORIGIN}/sitemap-daily.xml</loc></sitemap>\n'
        '</sitemapindex>\n'
    )
    (ROOT / "sitemap.xml").write_text(index_xml, encoding="utf-8")

    return len(static_entries), len(dictionary_entries), len(daily_entries), latest


def main() -> int:
    s, d, day, latest = build()
    print(f"wrote split sitemaps: static={s} dictionary={d} daily={day} latest={latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
