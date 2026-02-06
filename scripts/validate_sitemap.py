#!/usr/bin/env python3
"""Sitemap quality checks (canonical-only policy) with optional auto-fix."""
from __future__ import annotations

import argparse
import re
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITEMAP = ROOT / "sitemap.xml"

# non-canonical URLs (we want directory-style canonical)
BANNED = {
    "https://coinrader.net/daily/index.html",
    "https://coinrader.net/daily/latest.html",
    "https://coinrader.net/daily/tags/bear.html",
    "https://coinrader.net/daily/tags/bull.html",
    "https://coinrader.net/daily/tags/wait.html",
}

# If a banned URL is found, replace with canonical URL (instead of dropping)
CANONICAL_MAP = {
    "https://coinrader.net/daily/index.html": "https://coinrader.net/daily/",
    "https://coinrader.net/daily/latest.html": "https://coinrader.net/daily/latest",
    "https://coinrader.net/daily/tags/bear.html": "https://coinrader.net/daily/tags/bear",
    "https://coinrader.net/daily/tags/bull.html": "https://coinrader.net/daily/tags/bull",
    "https://coinrader.net/daily/tags/wait.html": "https://coinrader.net/daily/tags/wait",
}


def _scan(xml: str) -> tuple[list[str], list[str], list[str]]:
    ET.fromstring(xml)  # well-formed check
    locs = re.findall(r"<loc>\s*([^<]+)\s*</loc>", xml)
    dups = sorted({u for u in locs if locs.count(u) > 1})
    bad = sorted([u for u in locs if u in BANNED])
    return locs, dups, bad


def _iter_url_nodes(root: ET.Element) -> list[ET.Element]:
    """
    Return <url> nodes regardless of sitemap namespace.
    Supports:
      - <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      - <urlset> (no namespace)
    """
    urls = []

    # Case 1: standard sitemap namespace
    urls.extend(root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}url"))

    # Case 2: no namespace
    if not urls:
        urls.extend(root.findall(".//url"))

    # Fallback: any element whose tag endswith 'url'
    if not urls:
        for el in root.iter():
            if isinstance(el.tag, str) and el.tag.endswith("url"):
                urls.append(el)

    return urls


def _find_loc_el(url_el: ET.Element) -> ET.Element | None:
    # standard namespace
    loc = url_el.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
    if loc is not None:
        return loc
    # no namespace
    loc = url_el.find("loc")
    if loc is not None:
        return loc
    # fallback: first child whose tag endswith 'loc'
    for ch in list(url_el):
        if isinstance(ch.tag, str) and ch.tag.endswith("loc"):
            return ch
    return None


def _autofix(xml: str) -> str:
    root = ET.fromstring(xml)
    seen: set[str] = set()

    for url in list(_iter_url_nodes(root)):
        loc_el = _find_loc_el(url)
        loc = (loc_el.text or "").strip() if loc_el is not None else ""

        if not loc:
            urlset_parent = root
            urlset_parent.remove(url)
            continue

        # replace banned -> canonical
        if loc in CANONICAL_MAP:
            loc = CANONICAL_MAP[loc]
            loc_el.text = loc

        # drop any still-banned (in case) or duplicates
        if loc in BANNED or loc in seen:
            root.remove(url)
            continue

        seen.add(loc)

    return ET.tostring(root, encoding="unicode")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true", help="Auto-fix banned/duplicate URLs in sitemap")
    args = parser.parse_args()

    xml = SITEMAP.read_text(encoding="utf-8")
    locs, dups, bad = _scan(xml)

    if (dups or bad) and args.fix:
        fixed = _autofix(xml)
        SITEMAP.write_text(
            "\n".join(['<?xml version="1.0" encoding="UTF-8"?>', fixed, ""]),
            encoding="utf-8",
        )
        xml = SITEMAP.read_text(encoding="utf-8")
        locs, dups, bad = _scan(xml)
        print("SITEMAP AUTO-FIX APPLIED")

    errors: list[str] = []
    if dups:
        errors.append(f"duplicate loc entries: {dups}")
    if bad:
        errors.append(f"non-canonical URLs in sitemap: {bad}")

    if errors:
        print("SITEMAP VALIDATION FAILED")
        for e in errors:
            print(f"- {e}")
        return 1

    print("SITEMAP VALIDATION OK")
    print(f"- entries: {len(locs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
