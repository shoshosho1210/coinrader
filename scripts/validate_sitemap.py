#!/usr/bin/env python3
"""Sitemap quality checks (canonical-only policy) with optional auto-fix."""
from __future__ import annotations

import argparse
import re
from pathlib import Path
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
SITEMAP = ROOT / "sitemap.xml"


def canonicalize(url: str) -> str:
    """Return canonical form for CoinRader URLs.

    Policy:
    - daily: extensionless canonical (except /daily/ as directory)
    - hubs with index.html are canonicalized to trailing slash (e.g. /coins/, /guide/, /dictionary/)
    - legacy static pages .html -> extensionless (about.html -> /about)
    """
    u = (url or "").strip()
    if not u:
        return u

    # normalize scheme-less input? (keep as-is if it's not a full URL)
    # ---- daily ----
    if u.endswith("/daily/index.html"):
        return u.replace("/daily/index.html", "/daily/")
    if u.endswith("/daily/latest.html"):
        return u.replace("/daily/latest.html", "/daily/latest")
    if re.search(r"/daily/\d{8}\.html$", u):
        return re.sub(r"(\/daily\/\d{8})\.html$", r"\1", u)
    if re.search(r"/daily/tags/[a-z0-9_-]+\.html$", u):
        return re.sub(r"(\/daily\/tags\/[a-z0-9_-]+)\.html$", r"\1", u)

    # ---- hubs (directory index) ----
    for hub in ("/coins", "/guide", "/dictionary", "/daily"):
        if u.endswith(hub):
            return u + "/"
        if u.endswith(hub + "/index.html"):
            return u.replace(hub + "/index.html", hub + "/")

    # ---- coins/guide/dictionary subpages as directories ----
    # /coins/btc/index.html -> /coins/btc/
    u = re.sub(r"(\/coins\/[A-Za-z0-9_-]+)\/index\.html$", r"\1/", u)
    u = re.sub(r"(\/guide\/[A-Za-z0-9_-]+)\/index\.html$", r"\1/", u)
    u = re.sub(r"(\/dictionary\/[A-Za-z0-9_-]+)\/index\.html$", r"\1/", u)

    # if someone mistakenly put /coins/btc (no slash) and directory exists, canonical would be /coins/btc/
    u = re.sub(r"(\/coins\/[A-Za-z0-9_-]+)$", r"\1/", u) if re.search(r"\/coins\/[A-Za-z0-9_-]+$", u) else u
    u = re.sub(r"(\/guide\/[A-Za-z0-9_-]+)$", r"\1/", u) if re.search(r"\/guide\/[A-Za-z0-9_-]+$", u) else u
    u = re.sub(r"(\/dictionary\/[A-Za-z0-9_-]+)$", r"\1/", u) if re.search(r"\/dictionary\/[A-Za-z0-9_-]+$", u) else u

    # ---- static pages ----
    # about.html -> /about
    u = re.sub(r"/(about|start|data-sources|ads-pr|privacy|disclaimer|contact|sponsor|en)/index\.html$", r"/\1/", u)
    u = re.sub(r"/(about|start|data-sources|ads-pr|privacy|disclaimer|contact|sponsor|en)\.html$", r"/\1", u)

    return u

def _iter_loc_elements(root: ET.Element):
    # namespace-agnostic: find any element whose localname is "loc"
    for el in root.iter():
        if el.tag.endswith("loc"):
            yield el

def _read_sitemap_urlset(path: Path, seen: set[Path]) -> tuple[list[str], list[ET.Element]]:
    if path in seen or not path.exists():
        return [], []
    seen.add(path)

    root = ET.fromstring(path.read_text(encoding="utf-8"))
    if root.tag.endswith("urlset"):
        locs = [((el.text or "").strip()) for el in _iter_loc_elements(root) if (el.text or "").strip()]
        return locs, [root]

    if root.tag.endswith("sitemapindex"):
        locs: list[str] = []
        roots: list[ET.Element] = []
        for sm in root:
            if not sm.tag.endswith("sitemap"):
                continue
            child_loc = None
            for c in sm:
                if c.tag.endswith("loc"):
                    child_loc = (c.text or "").strip()
                    break
            if not child_loc:
                continue
            child_name = Path(child_loc).name
            child_path = ROOT / child_name
            c_locs, c_roots = _read_sitemap_urlset(child_path, seen)
            locs.extend(c_locs)
            roots.extend(c_roots)
        return locs, roots

    return [], []


def _scan(xml: str):
    root = ET.fromstring(xml)
    if root.tag.endswith("sitemapindex"):
        locs, roots = _read_sitemap_urlset(SITEMAP, set())
        loc_els = []
    else:
        roots = [root]
        loc_els = list(_iter_loc_elements(root))
        locs = [((el.text or "").strip()) for el in loc_els if (el.text or "").strip()]

    canon = [canonicalize(u) for u in locs]
    cnt = Counter(canon)
    dups = sorted([u for u, c in cnt.items() if c > 1])

    bad = sorted([u for u in locs if canonicalize(u) != u])

    return root, roots, loc_els, locs, dups, bad


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

import re
from urllib.parse import urlparse

def validate_dictionary_trailing_slash(locs: list[str]) -> list[str]:
    """
    dictionary の canonical を末尾スラッシュ有りに統一する再発防止チェック。
    - OK:  /dictionary/ , /dictionary/<slug>/
    - NG:  /dictionary/<slug>   （末尾なし）
    """
    paths = []
    for u in locs:
        try:
            paths.append(urlparse(u).path or "")
        except Exception:
            continue

    bad = sorted({p for p in paths if re.fullmatch(r"/dictionary/[a-z0-9\-]+", p)})
    return bad

def validate_daily_lastmod_required(root: ET.Element) -> list[str]:
    """
    /daily/YYYYMMDD は lastmod 必須、かつ YYYY-MM-DD 形式であることをチェック。
    戻り値: 不備のある loc の一覧
    """
    bad = []

    # namespace-agnostic: <url> を走査
    for url_node in root.iter():
        if not url_node.tag.endswith("url"):
            continue

        loc = None
        lastmod = None
        for child in url_node:
            if child.tag.endswith("loc"):
                loc = (child.text or "").strip()
            elif child.tag.endswith("lastmod"):
                lastmod = (child.text or "").strip()

        if not loc:
            continue

        path = ""
        try:
            path = urlparse(loc).path or ""
        except Exception:
            continue

        m = re.fullmatch(r"/daily/(\d{8})", path)
        if not m:
            continue

        ymd = m.group(1)
        expected = f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"

        # lastmod 必須
        if not lastmod:
            bad.append(loc)
            continue

        # 形式チェック（YYYY-MM-DD）
        try:
            datetime.strptime(lastmod, "%Y-%m-%d")
        except Exception:
            bad.append(loc)
            continue

        # dailyは日付一致が望ましい（ズレていたらエラー）
        if lastmod != expected:
            bad.append(loc)

    return sorted(set(bad))

def validate_daily_latest_excluded(locs: list[str]) -> list[str]:
    """/daily/latest は sitemap から除外する。"""
    bad = []
    for u in locs:
        try:
            path = urlparse(u).path or ""
        except Exception:
            continue
        if path in {"/daily/latest", "/daily/latest/", "/daily/latest.html"}:
            bad.append(u)
    return sorted(set(bad))

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true", help="Auto-fix non-canonical/duplicate URLs in sitemap")
    args = parser.parse_args()

    xml = SITEMAP.read_text(encoding="utf-8")
    root, roots, loc_els, locs, dups, bad = _scan(xml)
    # --- dictionary: trailing slash canonical enforcement ---
    dict_bad = validate_dictionary_trailing_slash(locs)

    daily_lastmod_bad = sorted(set(sum((validate_daily_lastmod_required(r) for r in roots), [])))
    daily_latest_bad = validate_daily_latest_excluded(locs)

    if (dups or bad) and args.fix and root.tag.endswith("urlset"):
        fixed = _autofix(xml)
        # Keep xml declaration
        SITEMAP.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + fixed + '\n', encoding="utf-8")
        xml = SITEMAP.read_text(encoding="utf-8")
        root, roots, loc_els, locs, dups, bad = _scan(xml)
        print("SITEMAP AUTO-FIX APPLIED")
    elif args.fix and root.tag.endswith("sitemapindex"):
        print("SITEMAP AUTO-FIX SKIPPED: sitemapindex mode")
    
    errors = []
    if not locs:
        errors.append("no <loc> entries found (sitemap namespace/format issue?)")
    if dups:
        errors.append(f"duplicate (canonical) loc entries: {dups}")
    if bad:
        errors.append(f"non-canonical URLs in sitemap: {bad}")
    if dict_bad:
        errors.append(f"dictionary term URLs must end with '/': {dict_bad}")
    if daily_lastmod_bad:
        errors.append(f"/daily/YYYYMMDD entries must have correct <lastmod> (YYYY-MM-DD and match date): {daily_lastmod_bad}")
    if daily_latest_bad:
        errors.append(f"/daily/latest must not be included in sitemap: {daily_latest_bad}")
    
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
