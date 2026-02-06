#!/usr/bin/env python3
"""Sitemap quality checks (canonical-only policy) with optional auto-fix."""
from __future__ import annotations

import argparse
import re
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITEMAP = ROOT / "sitemap.xml"

BANNED = {
    "https://coinrader.net/daily/index.html",
    "https://coinrader.net/daily/latest.html",
    "https://coinrader.net/daily/tags/bear.html",
    "https://coinrader.net/daily/tags/bull.html",
    "https://coinrader.net/daily/tags/wait.html",
}


def _scan(xml: str) -> tuple[list[str], list[str], list[str]]:
    ET.fromstring(xml)
    locs = re.findall(r"<loc>\s*([^<]+)\s*</loc>", xml)
    dups = sorted({u for u in locs if locs.count(u) > 1})
    bad = sorted([u for u in locs if u in BANNED])
    return locs, dups, bad


def _autofix(xml: str) -> str:
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.fromstring(xml)
    seen: set[str] = set()
    for url in list(root.findall("sm:url", ns)):
        loc_el = url.find("sm:loc", ns)
        loc = (loc_el.text or "").strip() if loc_el is not None else ""
        if not loc or loc in BANNED or loc in seen:
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
        SITEMAP.write_text('\n'.join(['<?xml version="1.0" encoding="UTF-8"?>', fixed, '']), encoding="utf-8")
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
