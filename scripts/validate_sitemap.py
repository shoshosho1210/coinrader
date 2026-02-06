#!/usr/bin/env python3
"""Basic sitemap quality checks (canonical-only policy)."""
from __future__ import annotations

import re
import sys
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


def main() -> int:
    xml = SITEMAP.read_text(encoding="utf-8")
    ET.fromstring(xml)

    locs = re.findall(r"<loc>\s*([^<]+)\s*</loc>", xml)
    errors: list[str] = []

    dups = sorted({u for u in locs if locs.count(u) > 1})
    if dups:
        errors.append(f"duplicate loc entries: {dups}")

    bad = sorted([u for u in locs if u in BANNED])
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
