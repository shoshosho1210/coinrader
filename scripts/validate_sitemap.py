#!/usr/bin/env python3
"""Sitemap quality checks (canonical-only policy) with optional auto-fix."""
from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
SITEMAP = ROOT / "sitemap.xml"


def canonicalize(url: str) -> str:
    """Return canonical form for CoinRader daily URLs (.html canonical)."""
    u = (url or "").strip()
    if not u:
        return u

    # daily index is not canonical; prefer /daily/
    if u.endswith("/daily/index.html"):
        return u.replace("/daily/index.html", "/daily/")

    # If someone wrote extensionless, canonical is .html
    # tags
    if u.endswith("/daily/tags/bear"):
        return u + ".html"
    if u.endswith("/daily/tags/bull"):
        return u + ".html"
    if u.endswith("/daily/tags/wait"):
        return u + ".html"

    # daily pages
    import re
    m = re.search(r"/daily/(\d{8})$", u)
    if m:
        return u + ".html"

    return u


def _iter_loc_elements(root: ET.Element):
    # namespace-agnostic: find any element whose localname is "loc"
    for el in root.iter():
        if el.tag.endswith("loc"):
            yield el


def _scan(xml: str):
    root = ET.fromstring(xml)
    loc_els = list(_iter_loc_elements(root))
    locs = [((el.text or "").strip()) for el in loc_els if (el.text or "").strip()]

    # duplicates based on canonicalized loc (because different forms are effectively same)
    canon = [canonicalize(u) for u in locs]
    cnt = Counter(canon)
    dups = sorted([u for u, c in cnt.items() if c > 1])

    # non-canonical: loc itself isn't equal to canonicalized
    bad = sorted([u for u in locs if canonicalize(u) != u])

    return root, loc_els, locs, dups, bad


def _autofix(xml: str) -> str:
    root = ET.fromstring(xml)

    # Build mapping from canonical -> first url node, and remove others
    seen: set[str] = set()
    to_remove = []

    # iterate <url> nodes namespace-agnostic (tag endswith 'url')
    for url_node in list(root):
        if not url_node.tag.endswith("url"):
            continue

        loc_el = None
        for child in url_node:
            if child.tag.endswith("loc"):
                loc_el = child
                break

        loc = ((loc_el.text or "").strip()) if loc_el is not None else ""
        if not loc:
            to_remove.append(url_node)
            continue

        canon = canonicalize(loc)
        # rewrite to canonical
        if loc_el is not None:
            loc_el.text = canon

        if canon in seen:
            to_remove.append(url_node)
            continue
        seen.add(canon)

    for n in to_remove:
        root.remove(n)

    # preserve namespaces as much as ET allows
    return ET.tostring(root, encoding="unicode")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true", help="Auto-fix non-canonical/duplicate URLs in sitemap")
    args = parser.parse_args()

    xml = SITEMAP.read_text(encoding="utf-8")
    root, loc_els, locs, dups, bad = _scan(xml)

    if (dups or bad) and args.fix:
        fixed = _autofix(xml)
        # Keep xml declaration
        SITEMAP.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + fixed + '\n', encoding="utf-8")
        xml = SITEMAP.read_text(encoding="utf-8")
        root, loc_els, locs, dups, bad = _scan(xml)
        print("SITEMAP AUTO-FIX APPLIED")

    errors = []
    if not locs:
        errors.append("no <loc> entries found (sitemap namespace/format issue?)")
    if dups:
        errors.append(f"duplicate (canonical) loc entries: {dups}")
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
