#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CoinRader: data/daily/*.json から daily/ 配下のHTMLを自動生成します。
- daily/YYYYMMDD.html
- daily/index.html (一覧)
- daily/latest.html (最新へのリダイレクト)

前提:
- JSONファイル名: data/daily/20260204.json のように8桁日付
- JSON内に必要キーが無い場合でも、落ちないようにフォールバックします。

2026-02: JSON構造が
  {
    "summary": {
      "date": "YYYY-MM-DD",
      "fgi": {"value": 14, "label": "Extreme Fear"},
      "technical": {"btc_rsi": 46.63, "btc_ma_distance": -11.6},
      "trending": ["HYPE","TRIA","BTC"],
      ...
    },
    ...
  }
のようなネストになったため、summary.* から値を抽出するように対応。

※ 2026-02-05 patch:
- タグページ（bull/wait）が更新されないケースの対策として、
  index.html と tags/*.html に build marker コメントを埋め込み、
  「最新日付が進んだタイミング」で必ず差分が出るようにしています。
  （最新日が変わらない日は差分が出ないので、無駄なコミット増加を避けます）
"""
from __future__ import annotations

import os
import re
import json
import glob
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

STATIC_PATHS = [
    "/",               # root
    "/about",
    "/start",

    # hubs (canonical)
    "/guide/",
    "/coins/",
    "/dictionary/",
    "/daily/",

    "/data-sources",
    "/ads-pr",
    "/privacy",
    "/disclaimer",
    "/contact",
]
# COINS_ALIAS_SLUGS は /coins/btc 等の「別名スラッグ」を管理するための集合。
# 目的:
# - sitemap / 内部リンクで alias にリンクして重複URLを増やさない（canonical /coins/bitcoin/ に統一）
# - daily → coins ハブリンク生成時も canonical を優先し、alias は弾く保険として使う
COINS_ALIAS_SLUGS = {"btc", "eth", "sol"}  # sitemapに載せない（301で正規へ集約）
# --- coins hub link map (daily -> /coins/<canonical>/ ) ---
SYMBOL_TO_COIN_SLUG = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XRP": "xrp",
    # ここに必要なものを順次追加（例: "DOGE":"dogecoin"）
}
# --- minimal CSS for injected blocks (coin hubs etc.) ---
COIN_HUBS_CSS = """
<style>
/* injected by build_daily_pages.py */
.coin-hubs{ margin:10px 0 6px; }
.coin-hubs-h{ font-size:12px; opacity:.85; margin:0 0 6px; }
.coin-hubs-links{ display:flex; gap:8px; flex-wrap:wrap; }
.chip-coin{
  display:inline-flex; align-items:center; gap:6px;
  border:1px solid rgba(56,189,248,.35);
  padding:4px 10px; border-radius:999px;
  font-size:12px; text-decoration:none;
}
</style>
""".strip()

# scripts/ の1つ上を repo root として想定
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "daily"
OUT_DIR  = ROOT / "daily"
TEMPL_DIR = ROOT / "templates"

SITE_ORIGIN = os.environ.get("CR_SITE_ORIGIN", "https://coinrader.net").rstrip("/")
# OGP: daily画像のURLプレフィックス（例: https://coinrader.net/ogp/daily）
OGP_DAILY_PREFIX = os.environ.get("CR_OGP_DAILY_PREFIX", f"{SITE_ORIGIN}/ogp/daily").rstrip("/")
TZ_NAME = "JST"


# ---------- utils ----------
def strip_build_markers(html: str) -> str:
    # 既存の build マーカーを全部除去（重複防止）
    return re.sub(r"<!--\s*build:\d{8}\s*-->\s*", "", html)

def inject_build_marker_once(html: str, latest_ymd: str) -> str:
    html = strip_build_markers(html)
    # </body> の直前に 1回だけ差し込む
    if "</body>" in html:
        return html.replace("</body>", f"<!-- build:{latest_ymd} -->\n</body>", 1)
    return html + f"\n<!-- build:{latest_ymd} -->\n"

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def read_text_optional(paths: List[Path]) -> str:
    """Return the content of the first existing file in paths."""
    for p in paths:
        if p.exists():
            return read_text(p)
    raise FileNotFoundError("None of the optional template files exist: " + ", ".join(str(x) for x in paths))


def read_text_optional_with_path(paths: List[Path]) -> tuple[Path, str]:
    """Return (path, text) for the first existing file in paths."""
    for p in paths:
        if p.exists():
            return p, read_text(p)
    raise FileNotFoundError("None of the optional template files exist: " + ", ".join(str(x) for x in paths))

def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")

def escape_html(s: str) -> str:
    return (s.replace("&", "&amp;")
              .replace("<", "&lt;")
              .replace(">", "&gt;")
              .replace('"', "&quot;")
              .replace("'", "&#39;"))


def iso_today() -> str:
    # sitemap lastmod などで使う ISO 日付
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def build_seo_meta(date_iso: str, ymd: str, judge: str, sentiment_value, btc_rsi, trend, trending: List[str], top_gainer=None) -> Dict[str, str]:
    # title/description は検索結果でのクリック率を意識して具体的な数値を含める
    try:
        rsi_s = f"{float(btc_rsi):.2f}" if btc_rsi is not None else "-"
    except Exception:
        rsi_s = "-"
    try:
        trend_s = f"{float(trend):.1f}" if trend is not None else "-"
    except Exception:
        trend_s = "-"
    fgi_s = str(sentiment_value) if sentiment_value is not None else "-"
    trend_str = "/".join([t.upper() for t in (trending or [])][:3])
    gain_str = ""
    if isinstance(top_gainer, dict) and top_gainer.get("symbol"):
        ch = top_gainer.get("change")
        try:
            ch_s = f"{float(ch):.2f}" if ch is not None else ""
        except Exception:
            ch_s = str(ch) if ch is not None else ""
        gain_str = f" 上昇トップ:{top_gainer.get('symbol').upper()}(+{ch_s}%)" if ch_s else f" 上昇トップ:{top_gainer.get('symbol').upper()}"

    title = f"BTC AI分析 {date_iso}｜Fear&Greed {fgi_s} / RSI {rsi_s} / Trend {trend_s}（CoinRader）"
    desc = f"{date_iso}のBTCをAIが日次分析。市場心理(Fear&Greed)={fgi_s}、RSI={rsi_s}、Trend={trend_s}。総合判断={judge}。注目トレンド:{trend_str}.{gain_str}".strip()
    og_title = f"BTC AI分析 {date_iso}｜AI判定 {judge}"
    og_desc = f"Fear&Greed={fgi_s} / RSI={rsi_s} / Trend={trend_s}。注目:{trend_str}"
    canonical = f"{SITE_ORIGIN}/daily/{ymd}"
    return {
        "TITLE": title,
        "DESCRIPTION": desc,
        "OG_TITLE": og_title,
        "OG_DESCRIPTION": og_desc,
        "CANONICAL": canonical,
    }


def build_jsonld(canonical: str, title: str, description: str, date_iso: str, updated_at_jst: str) -> str:
    # 日次ページは Article として扱う
    # updated_at_jst: 'YYYY-MM-DD 09:00' のような文字列を想定
    def to_iso(dt_s: str) -> str:
        try:
            # allow 'YYYY-MM-DD HH:MM' (JST)
            dt = datetime.datetime.strptime(dt_s, "%Y-%m-%d %H:%M")
            # JST +09:00
            return dt.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=9))).isoformat()
        except Exception:
            return date_iso + "T09:00:00+09:00"

    data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": description,
        "datePublished": date_iso + "T09:00:00+09:00",
        "dateModified": to_iso(updated_at_jst),
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
        "publisher": {"@type": "Organization", "name": "CoinRader"},
    }
    s = json.dumps(data, ensure_ascii=False)
    return s.replace("</", "<\/")



def build_recent_days_html(dated_all: List[str], current_ymd: str, n: int = 7) -> str:
    if not dated_all or current_ymd not in dated_all:
        return ""

    idx = dated_all.index(current_ymd)
    window = dated_all[-n:] if len(dated_all) > n else list(dated_all)
    if current_ymd not in window:
        window = window + [current_ymd]

    parts: list[str] = []

    if idx > 0:
        prev_ymd = dated_all[idx - 1]
        parts.append(f"<a class='chip chip-nav' href='/daily/{prev_ymd}'>← 前日</a>")
    if idx < (len(dated_all) - 1):
        next_ymd = dated_all[idx + 1]
        parts.append(f"<a class='chip chip-nav' href='/daily/{next_ymd}'>翌日 →</a>")

    for ymd in window:
        mmdd = f"{ymd[4:6]}/{ymd[6:8]}"
        href = f"/daily/{ymd}"
        is_current = (ymd == current_ymd)
        extra_cls = " is-active" if is_current else ""
        aria = " aria-current='page'" if is_current else ""
        style = " style='border-color:rgba(56,189,248,.6);background:rgba(56,189,248,.10)'" if is_current else ""
        parts.append(f"<a class='chip{extra_cls}' href='{href}'{aria}{style}><small>{mmdd}</small></a>")

    parts.append("<a class='chip' href='/daily/'><small>LIST</small>一覧</a>")
    parts.append("<a class='chip' href='/daily/latest'><small>NEW</small>最新</a>")
    return "\n      ".join(parts)


def build_same_judge_days_html(judge: str, judge_days_all: List[str], current_ymd: str, n: int = 5) -> str:
    judge = (judge or "").strip()
    if not judge or not judge_days_all or current_ymd not in judge_days_all:
        return ""
    idx = judge_days_all.index(current_ymd)
    half = n // 2
    start = max(0, idx - half)
    end = min(len(judge_days_all), idx + half + 1)
    while (end - start) < n and start > 0:
        start -= 1
    while (end - start) < n and end < len(judge_days_all):
        end += 1

    window = judge_days_all[start:end]
    parts = []

    tag_lower = escape_html(judge.lower())
    parts.append(
        f"<a class='chip' href='/daily/tags/{tag_lower}' style='opacity:.75'><small>SAME</small>{escape_html(judge)}</a>"
    )

    for ymd in window:
        mmdd = f"{ymd[4:6]}/{ymd[6:8]}"
        label = "" if ymd != current_ymd else "現在"
        href = f"/daily/{ymd}"
        inner = f"<small>{mmdd}</small>{escape_html(label)}" if label else f"<small>{mmdd}</small>"
        parts.append(f"<a class='chip' href='{href}'>{inner}</a>")
    return "\n      ".join(parts)


def escape_xml(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")


def rebuild_sitemap_with_daily(
    sitemap_path: Path,
    *,
    site_origin: str,
    daily_pages: list[dict],
    include_extensionless_tag_pages: bool = False,
) -> None:
    """既存の sitemap.xml を壊さずに、daily 系URLを「正しい <url> ブロック」で差し込む。

    - 既存 sitemap の <url> を loc でユニーク化して保持
    - daily のURLは lastmod/changefreq/priority を付与して上書き（または新規追加）
    - 旧版で混入した「<url><loc>..</loc></url> だけ」形式も正規化される
    - タグの canonical は拡張子なし（/daily/tags/bear 等）。必要なら .html を sitemap に併記できる。
    """

    def _parse_existing(xml: str) -> dict[str, dict[str, str]]:
        # <url> ... </url> をざっくり抽出して、loc/lastmod/changefreq/priority を拾う
        out: dict[str, dict[str, str]] = {}
        for block in re.findall(r"<url>.*?</url>", xml, flags=re.DOTALL):
            loc_m = re.search(r"<loc>\s*([^<]+)\s*</loc>", block)
            if not loc_m:
                continue
            loc = loc_m.group(1).strip()
            if not loc:
                continue
            def _get(tag: str) -> str:
                m = re.search(rf"<{tag}>\s*([^<]+)\s*</{tag}>", block)
                return m.group(1).strip() if m else ""
            out[loc] = {
                "lastmod": _get("lastmod"),
                "changefreq": _get("changefreq"),
                "priority": _get("priority"),
            }
        return out

    def _url_block(loc: str, meta: dict[str, str]) -> str:
        # meta は空文字なら出力しない
        parts = ["  <url>", f"    <loc>{escape_xml(loc)}</loc>"]
        if meta.get("lastmod"):
            parts.append(f"    <lastmod>{escape_xml(meta['lastmod'])}</lastmod>")
        if meta.get("changefreq"):
            parts.append(f"    <changefreq>{escape_xml(meta['changefreq'])}</changefreq>")
        if meta.get("priority"):
            parts.append(f"    <priority>{escape_xml(meta['priority'])}</priority>")
        parts.append("  </url>")
        return "\n".join(parts)

    # 1) 既存 sitemap を読み取り
    existing: dict[str, dict[str, str]] = {}
    if sitemap_path.exists():
        existing = _parse_existing(read_text(sitemap_path))
  
    # 2) daily 系URLを構築
    site_origin = (site_origin or "").rstrip("/")

    # --- remove coins alias URLs from existing sitemap (canonical only) ---
    coins_prefix = f"{site_origin}/coins/"
    for alias in COINS_ALIAS_SLUGS:
        existing.pop(f"{coins_prefix}{alias}/", None)
        existing.pop(f"{coins_prefix}{alias}", None)  # 念のため末尾/なしも落とす

    # --- extra: ensure guide/coins pages are included (directory index style) ---
    project_root = sitemap_path.parent

    def _collect_dir_index_urls(dir_name: str, base_path: str) -> list[str]:
        """Collect URLs like /guide/<slug>/ from <dir_name>/<slug>/index.html.

        - Excludes the hub index.html (e.g., guide/index.html)
        - Includes only directories that contain index.html
        """
        urls: list[str] = []
        base = project_root / dir_name
        if not base.exists() or not base.is_dir():
            return urls

        for p in base.iterdir():
            if p.name == "index.html":
                continue
            if not p.is_dir():
                continue
            if (p / "index.html").exists():
                slug = p.name
                urls.append(f"{site_origin}{base_path}{slug}/")
        return urls

    def _ensure_urls(urls: list[str], *, changefreq: str = "weekly", priority: str = "0.6") -> None:
        # Existing map key is loc; keep if already present
        today = iso_today()
        for u in urls:
            if u not in existing:
                existing[u] = {
                    "loc": u,
                    "lastmod": today,
                    "changefreq": changefreq,
                    "priority": priority,
                }

    # Hubs (already covered by STATIC_PATHS in the base sitemap, but ensure anyway)
    _ensure_urls([f"{site_origin}/guide/", f"{site_origin}/coins/", f"{site_origin}/dictionary/", f"{site_origin}/daily/"],
                changefreq="daily", priority="0.8")

    # Subpages
    _ensure_urls(_collect_dir_index_urls("guide", "/guide/"), changefreq="weekly", priority="0.6")
    _ensure_urls([u for u in _collect_dir_index_urls("coins", "/coins/") if (u.rsplit('/',2)[-2] not in COINS_ALIAS_SLUGS)], changefreq="daily", priority="0.7")
    _ensure_urls(_collect_dir_index_urls("dictionary", "/dictionary/"), changefreq="monthly", priority="0.5")
    pages = list(daily_pages or [])
    pages_sorted = sorted(pages, key=lambda d: str(d.get("ymd") or ""), reverse=True)
    latest_iso = (pages_sorted[0].get("date_iso") if pages_sorted else "") or iso_today()

    # --- dictionary canonical cleanup ---
    # dictionaryのtermは canonical が ".../dictionary/<slug>/"（末尾スラあり）なので、
    # sitemapに残っている ".../dictionary/<slug>"（末尾スラなし）を削除する
    dict_prefix = f"{site_origin}/dictionary/"
    dict_hub = dict_prefix  # ".../dictionary/"
    for loc in list(existing.keys()):
        if isinstance(loc, str) and loc.startswith(dict_prefix) and loc != dict_hub:
            if not loc.endswith("/"):
                existing.pop(loc, None)

    # --- coins/guide canonical cleanup ---
    # hubs must end with '/', and subpages should also end with '/'
    for bad in (f"{site_origin}/coins", f"{site_origin}/guide", f"{site_origin}/daily", f"{site_origin}/dictionary"):
        existing.pop(bad, None)

    coins_prefix = f"{site_origin}/coins/"
    coins_hub = coins_prefix
    for loc in list(existing.keys()):
        if isinstance(loc, str) and loc.startswith(coins_prefix) and loc != coins_hub:
            if not loc.endswith("/"):
                existing.pop(loc, None)

    guide_prefix = f"{site_origin}/guide/"
    guide_hub = guide_prefix
    for loc in list(existing.keys()):
        if isinstance(loc, str) and loc.startswith(guide_prefix) and loc != guide_hub:
            if not loc.endswith("/"):
                existing.pop(loc, None)

    # ---- dictionary pages (auto-discover) ----
    root_dir = sitemap_path.parent
    dict_dir = root_dir / "dictionary"

    # hub
    dict_hub = f"{site_origin}/dictionary/"
    existing[dict_hub] = {
        "lastmod": latest_iso,
        "changefreq": "weekly",
        "priority": "0.8",
    }

    # term pages: dictionary/<slug>/index.html => /dictionary/<slug>/
    if dict_dir.exists():
        for idx_html in sorted(dict_dir.glob("*/index.html")):
            slug = idx_html.parent.name
            if not slug or slug == ".":
                continue
            if not re.fullmatch(r"[a-z0-9\-]+", slug):
                continue
            u = f"{site_origin}/dictionary/{slug}/"
            existing[u] = {
                "lastmod": latest_iso,
                "changefreq": "monthly",
                "priority": "0.7",
            }

    # --- canonical-only cleanup: remove old non-canonical URLs that may remain in existing sitemap ---
    drop_locs = {
        f"{site_origin}/daily/index.html",
        f"{site_origin}/daily/latest",
        f"{site_origin}/daily/tags/bear.html",
        f"{site_origin}/daily/tags/bull.html",
        f"{site_origin}/daily/tags/wait.html",
        f"{site_origin}/daily/latest/",
        f"{site_origin}/daily/tags/bear/",
        f"{site_origin}/daily/tags/bull/",
        f"{site_origin}/daily/tags/wait/",
    }

    for loc in list(existing.keys()):
        if loc in drop_locs:
            existing.pop(loc, None)

    # 2.5) static pages (extensionless canonical)
    static_urls = []
    for p in (STATIC_PATHS or []):
        if not isinstance(p, str):
            continue
        p = p.strip()
        if not p:
            continue

        if p == "/":
            u = f"{site_origin}/"
        else:
            if not p.startswith("/"):
                p = "/" + p
            u = f"{site_origin}{p}"
        static_urls.append(u)

    for u in static_urls:
        if u == f"{site_origin}/":
            existing[u] = {"lastmod": latest_iso, "changefreq": "hourly", "priority": "1.0"}
        else:
            existing[u] = {"lastmod": latest_iso, "changefreq": "monthly", "priority": "0.5"}

    # daily ルート（canonical: extensionless）
    daily_root_urls = [
        f"{site_origin}/daily/",
        f"{site_origin}/daily/latest",
        f"{site_origin}/daily/tags/bear",
        f"{site_origin}/daily/tags/bull",
        f"{site_origin}/daily/tags/wait",
    ]

    # 互換性: タグの .html URL を sitemap に併記したい場合のみ True
    # ※ canonical は拡張子なしに統一しているため、通常は False 推奨
    if include_extensionless_tag_pages:
        daily_root_urls += [
            f"{site_origin}/daily/tags/bear.html",
            f"{site_origin}/daily/tags/bull.html",
            f"{site_origin}/daily/tags/wait.html",
        ]

    for u in daily_root_urls:
        existing[u] = {
            "lastmod": latest_iso,
            "changefreq": "daily",
            "priority": "0.9" if (u.endswith("/daily/") or u.endswith("/daily/latest")) else "0.6",
        }

    # 日次ページ
    for d in pages_sorted:
        ymd = str(d.get("ymd") or "").strip()
        date_iso = str(d.get("date_iso") or "").strip()
        if not (ymd and re.fullmatch(r"\d{8}", ymd) and date_iso):
            continue
        u = f"{site_origin}/daily/{ymd}"
        existing[u] = {
            "lastmod": date_iso,
            "changefreq": "daily",
            "priority": "0.8",
        }

    # 3) 出力順: static -> daily root -> daily dates
    ordered_locs: list[str] = []

    # 既存 sitemap の順序は「daily 以外」だけ参考にする（daily は後で決め打ち順で入れる）
    if sitemap_path.exists():
        xml0 = read_text(sitemap_path)
        for loc in re.findall(r"<loc>\s*([^<]+)\s*</loc>", xml0):
            loc = (loc or "").strip()
            if not loc or loc not in existing:
                continue
            # daily系はここでは入れない（後で正規順序でまとめて入れる）
            if re.search(r"/daily(/|$)", loc):
                continue
            if loc not in ordered_locs:
                ordered_locs.append(loc)

    # static pages first (keep canonical order)
    static_first = [f"{site_origin}/"]
    for p in (STATIC_PATHS or []):
        if p in ("/", "", None):
            continue
        if not p.startswith("/"):
            p = "/" + p
        static_first.append(f"{site_origin}{p}")

    for loc in static_first:
        if loc in existing and loc not in ordered_locs:
            ordered_locs.append(loc)

    # daily系を最後にまとめて追加（重複排除）
    daily_first = [
        f"{site_origin}/daily/",
        f"{site_origin}/daily/latest",
        f"{site_origin}/daily/tags/bear",
        f"{site_origin}/daily/tags/bull",
        f"{site_origin}/daily/tags/wait",
    ]

    if include_extensionless_tag_pages:
        daily_first += [
            f"{site_origin}/daily/tags/bear",
            f"{site_origin}/daily/tags/bull",
            f"{site_origin}/daily/tags/wait",
        ]
    daily_dates = [
        f"{site_origin}/daily/{d['ymd']}"
        for d in pages_sorted
        if str(d.get("ymd") or "").strip()
    ]

    dict_first = [f"{site_origin}/dictionary/"]
    dict_terms = []
    if (sitemap_path.parent / "dictionary").exists():
        for idx_html in sorted((sitemap_path.parent / "dictionary").glob("*/index.html")):
            slug = idx_html.parent.name
            if re.fullmatch(r"[a-z0-9\-]+", slug):
                u = f"{site_origin}/dictionary/{slug}/"
                dict_terms.append(u)

    for loc in dict_first + dict_terms:
        if loc in existing and loc not in ordered_locs:
            ordered_locs.append(loc)

    for loc in daily_first + daily_dates:
        if loc in existing and loc not in ordered_locs:
            ordered_locs.append(loc)

    # 4) 正規化: 旧版で混入した「/daily/tags/bear/」や「/daily/tags/bear.html/」等は落とす（.html を優先）
    drop_suffixes = [
        f"{site_origin}/daily/index.html",
        f"{site_origin}/daily/tags/bear/",
        f"{site_origin}/daily/tags/bull/",
        f"{site_origin}/daily/tags/wait/",
    ]
    ordered_locs = [loc for loc in ordered_locs if loc not in drop_suffixes]

    # 5) XML出力
    header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    header += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    body = "\n".join(_url_block(loc, existing[loc]) for loc in ordered_locs) + "\n"
    footer = "</urlset>\n"
    write_text(sitemap_path, header + body + footer)

def build_tag_jsonld(site_origin: str, tag_key: str, rows: list[dict]) -> str:
    tag = (tag_key or "").lower()
    tag_u = (tag_key or "").upper()
    url = f"{site_origin}/daily/tags/{tag}"

    items = []
    for i, r in enumerate(rows, start=1):
        ymd = (r.get("ymd") or "").strip()
        date_iso = r.get("date_iso", "")
        if not ymd or not date_iso:
            continue
        items.append({
            "@type": "ListItem",
            "position": i,
            "url": f"{site_origin}/daily/{ymd}",
            "name": date_iso
        })

    data = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"AI {tag_u} の日一覧（CoinRader）",
        "description": f"CoinRaderのAI判定が{tag_u}の日をまとめた一覧ページ。",
        "url": url,
        "mainEntity": {
            "@type": "ItemList",
            "itemListOrder": "https://schema.org/ItemListOrderDescending",
            "numberOfItems": len(items),
            "itemListElement": items
        },
        "publisher": {"@type": "Organization", "name": "CoinRader"}
    }

    s = json.dumps(data, ensure_ascii=False)
    return s.replace("</", "<\\/")


def get_path(obj: Any, path: str, default: Any = "") -> Any:
    """
    dict のネストを "summary.technical.btc_rsi" のようなドット区切りで取得。
    """
    cur = obj
    for key in path.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur if cur is not None else default

def to_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        if s == "":
            return None
        return float(s)
    except Exception:
        return None

def fmt_num(x: Any, ndigits: int = 2) -> str:
    v = to_float(x)
    if v is None:
        return ""
    return f"{v:.{ndigits}f}".rstrip("0").rstrip(".")

def normalize_symbol_list(items: Any) -> List[str]:
    if not isinstance(items, list):
        return []
    out: List[str] = []
    for it in items:
        s = ""
        if isinstance(it, str):
            s = it
        elif isinstance(it, dict):
            for k in ("symbol", "label", "name", "id"):
                v = it.get(k)
                if isinstance(v, str) and v.strip():
                    s = v
                    break
        if s:
            out.append(s.strip().upper())
    seen = set()
    uniq: List[str] = []
    for s in out:
        if s in seen:
            continue
        seen.add(s)
        uniq.append(s)
    return uniq


def compute_judge(fgi_value: Any, btc_rsi: Any, ma_dist: Any) -> str:
    fgi = to_float(fgi_value)
    rsi = to_float(btc_rsi)
    mad = to_float(ma_dist)
    if fgi is None or rsi is None or mad is None:
        return "WAIT"
    if fgi <= 25 and mad <= -5:
        if rsi <= 30:
            return "WAIT"
        return "BEAR"
    if fgi >= 75 and mad >= 5:
        if rsi >= 70:
            return "WAIT"
        return "BULL"
    if rsi <= 30:
        return "WAIT"
    if rsi >= 70:
        return "WAIT"
    if mad >= 3:
        return "BULL"
    if mad <= -3:
        return "BEAR"
    return "WAIT"

def build_reason_html(payload: Dict[str, Any], judge: str) -> str:
    reasons: List[str] = []
    for path in [
        "ai.reasons","ai.reason_lines","ai.reason",
        "reasons","reason_lines","reason",
        "summary.reason_lines","summary.reason",
    ]:
        v = get_path(payload, path, default=None)
        if isinstance(v, list) and v:
            reasons = [str(x).strip() for x in v if str(x).strip()]
            break
        if isinstance(v, str) and v.strip():
            reasons = [v.strip()]
            break

    fgi_value = get_path(payload, "summary.fgi.value", default=get_path(payload, "fear_greed", default=""))
    fgi_label = get_path(payload, "summary.fgi.label", default="")
    btc_rsi   = get_path(payload, "summary.technical.btc_rsi", default=get_path(payload, "btc_rsi", default=""))
    ma_dist   = get_path(payload, "summary.technical.btc_ma_distance",
                          default=get_path(payload, "summary.technical.ma_distance",
                              default=get_path(payload, "btc_ma_distance",
                                  default=get_path(payload, "ma_distance", default=""))))
    if isinstance(ma_dist, (list, dict)):
        ma_dist = ""
    trending  = get_path(payload, "summary.trending", default=get_path(payload, "trending", default=get_path(payload, "trend", default=[])))
    top_gainer_symbol = get_path(payload, "summary.top_gainer.symbol", default="")
    top_gainer_change = get_path(payload, "summary.top_gainer.change", default="")

    if not reasons:
        fgi = to_float(fgi_value)
        if fgi is not None:
            if fgi < 25:
                label = fgi_label or "Extreme Fear"
                reasons.append(f"Fear & Greed が {fmt_num(fgi,0)}（{label}）で、市場心理は強い悲観に寄っています。")
            elif fgi < 45:
                reasons.append(f"Fear & Greed が {fmt_num(fgi,0)} で弱気寄りです。")
            elif fgi < 55:
                reasons.append(f"Fear & Greed が {fmt_num(fgi,0)} で中立付近です。")
            elif fgi < 75:
                reasons.append(f"Fear & Greed が {fmt_num(fgi,0)} で強気寄りです。")
            else:
                label = fgi_label or "Extreme Greed"
                reasons.append(f"Fear & Greed が {fmt_num(fgi,0)}（{label}）で過熱感があります。")

        rsi = to_float(btc_rsi)
        if rsi is not None:
            if rsi < 30:
                reasons.append(f"BTC RSI が {fmt_num(rsi,1)} で売られ過ぎ水準です。")
            elif rsi < 45:
                reasons.append(f"BTC RSI が {fmt_num(rsi,1)} で弱めです。")
            elif rsi < 55:
                reasons.append(f"BTC RSI が {fmt_num(rsi,1)} で中立付近です。")
            elif rsi < 70:
                reasons.append(f"BTC RSI が {fmt_num(rsi,1)} で堅調です。")
            else:
                reasons.append(f"BTC RSI が {fmt_num(rsi,1)} で買われ過ぎ水準です。")

        mad = to_float(ma_dist)
        if mad is not None:
            if mad <= -8:
                reasons.append(f"MA距離が {fmt_num(mad,1)}% と大きくマイナスで、下方向の圧力が強い状態です。")
            elif mad <= -3:
                reasons.append(f"MA距離が {fmt_num(mad,1)}% で、弱含みです。")
            elif mad < 3:
                reasons.append(f"MA距離が {fmt_num(mad,1)}% で、方向感は限定的です。")
            elif mad < 8:
                reasons.append(f"MA距離が {fmt_num(mad,1)}% で、上向きの勢いがあります。")
            else:
                reasons.append(f"MA距離が {fmt_num(mad,1)}% と大きくプラスで、上昇が加速しています。")

        if isinstance(trending, list) and trending:
            top3 = [str(x).strip().upper() for x in trending[:3] if str(x).strip()]
            if top3:
                reasons.append(f"注目トレンド: {' / '.join(top3)}")

    # --- ここが追加：結論1行 ---
    j = (judge or "").strip().upper()
    lead_map = {
        "BEAR": "結論：弱気優勢（戻りは売られやすい局面）",
        "BULL": "結論：強気優勢（押し目が買われやすい局面）",
        "WAIT": "結論：様子見（方向感が弱い局面）",
    }
    lead = lead_map.get(j, "")

    li = "\n".join([f"<li>{escape_html(x)}</li>" for x in reasons[:6]])
    if not li and not lead:
        return ""

    lead_html = f"<div class='judge-lead'>{escape_html(lead)}</div>" if lead else ""
    ul_html = f"<ul class='why-list'>{li}</ul>" if li else ""
    return lead_html + ul_html


def build_takeaways_html(payload: Dict[str, Any], judge: str, sent: str, rsi: str, trend: str,
                         trending: List[str], top_gainer: Dict[str, Any]) -> str:
    """Key Takeaways: dailyページ冒頭に置く短い要点（AI引用されやすい箇条書き）。"""
    take: List[str] = []
    j = (judge or "").upper().strip()
    jm = {
        "BEAR": "AI判定：弱気優勢",
        "BULL": "AI判定：強気優勢",
        "WAIT": "AI判定：様子見",
    }
    if j in jm:
        take.append(jm[j])

    if sent and sent != "—":
        lab = get_path(payload, "summary.fgi.label", default="")
        if lab:
            take.append(f"Fear & Greed：{sent}（{lab}）")
        else:
            take.append(f"Fear & Greed：{sent}")

    if rsi and rsi != "—":
        take.append(f"BTC RSI：{rsi}")

    if trend and trend != "—":
        take.append(f"Trend：{trend}")

    # トレンド銘柄 TOP3
    if trending:
        top3 = [str(x).strip().upper() for x in (trending or [])[:3] if str(x).strip()]
        if top3:
            take.append(f"注目トレンド：{' / '.join(top3)}")

    # 上昇トップ
    if isinstance(top_gainer, dict):
        sym = str(top_gainer.get("symbol", "")).strip().upper()
        ch = top_gainer.get("change", None)
        ch_s = ""
        try:
            if ch is not None and ch != "":
                ch_s = f"{float(ch):.2f}".rstrip("0").rstrip(".")
        except Exception:
            ch_s = str(ch).strip() if ch is not None else ""
        if sym and ch_s:
            take.append(f"急上昇：{sym} +{ch_s}%")
        elif sym:
            take.append(f"急上昇：{sym}")

    # reasons の1行目があるなら最後に添える（長すぎない範囲）
    r1 = build_reason_1line(payload)
    if r1:
        take.append(r1)

    # 3〜5行に絞る
    take = [t for t in take if t][:5]
    if not take:
        return ""

    lis = "".join([f"<li>{escape_html(t)}</li>" for t in take])
    return f"<section class='takeaways' aria-label='Key Takeaways'><h2 class='takeaways-h'>Key Takeaways</h2><ul class='takeaways-ul'>{lis}</ul></section>"

from pathlib import Path

from urllib.parse import quote_plus

import os
import re

from pathlib import Path

def build_coin_hub_links_html(site_origin: str, trending=None, top_gainer=None, coins_dir: str = "coins") -> str:
    """
    Dailyページ用：関連銘柄(/coins/)へのリンクを生成する。
    - trending: ["BTC","ETH",...] のようなシンボル配列を想定
    - top_gainer: {"symbol":"BNKR", ...} のようなdictを想定
    """

    # --- local helper (位置事故防止) ---
    from pathlib import Path

    def list_existing_coin_slugs_local(_coins_dir: str = "coins") -> set:
        base = Path(_coins_dir)
        if not base.exists():
            return set()
        slugs = set()
        for p in base.glob("*/index.html"):
            try:
                slugs.add(p.parent.name)
            except Exception:
                pass
        return slugs

    # 既存 /coins/ slug を確認（存在するものだけリンクに出す）
    available = list_existing_coin_slugs_local(coins_dir)

    # 候補シンボルを集める（重複排除・順序維持）
    cand = []

    def add_sym(s):
        if not s:
            return
        s = str(s).strip().upper()
        if not s:
            return
        if s not in cand:
            cand.append(s)

    if isinstance(trending, (list, tuple)):
        for s in trending:
            add_sym(s)

    if isinstance(top_gainer, dict):
        add_sym(top_gainer.get("symbol"))

    SYMBOL_TO_SLUG = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "XRP": "xrp",
        "BNB": "bnb",
        "DOGE": "dogecoin",
        "ADA": "cardano",
        "TRX": "tron",
        "AVAX": "avalanche",
        "DOT": "polkadot",
        "LINK": "chainlink",
        "MATIC": "polygon",
    }

    links = []
    for sym in cand:
        slug = SYMBOL_TO_SLUG.get(sym)

        # 固定マップに無い場合： /coins/<lower>/ が存在するならそれを使う
        if not slug:
            guess = sym.lower()
            if guess in available:
                slug = guess

        if not slug:
            continue
        if slug not in available:
            continue

        links.append(f"<a class='chip chip-coin' href='/coins/{slug}/'>{sym}</a>")

    if not links:
        return ""

    return (
        "<section class='coin-hubs' aria-label='Related coins'>"
        "<div class='coin-hubs-h'>関連銘柄</div>"
        "<div class='coin-hubs-links'>"
        + "".join(links)
        + "</div></section>"
    )

def shorten_one_line(s: str, max_len: int = 70) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    s = " ".join(s.split())
    return (s[:max_len].rstrip() + "…") if len(s) > max_len else s


def build_reason_1line(payload: Dict[str, Any]) -> str:
    for path in [
        "ai.reasons","ai.reason_lines","ai.reason",
        "reasons","reason_lines","reason",
        "summary.reason_lines","summary.reason",
    ]:
        v = get_path(payload, path, default=None)
        if isinstance(v, list) and v:
            reasons = [str(x).strip() for x in v if str(x).strip()]
            if reasons:
                return shorten_one_line(reasons[0])
        if isinstance(v, str) and v.strip():
            return shorten_one_line(v.strip())

    candidates: List[str] = []
    judge = str(get_path(payload, "summary.judge", default=get_path(payload, "judge", default="")) or "").upper()

    fgi_value = get_path(payload, "summary.fgi.value", default=get_path(payload, "fear_greed", default=""))
    fgi_label = get_path(payload, "summary.fgi.label", default="")
    btc_rsi   = get_path(payload, "summary.technical.btc_rsi", default=get_path(payload, "btc_rsi", default=""))
    ma_dist   = get_path(
        payload,
        "summary.technical.btc_ma_distance",
        default=get_path(
            payload,
            "summary.technical.ma_distance",
            default=get_path(
                payload,
                "btc_ma_distance",
                default=get_path(payload, "ma_distance", default=""),
            ),
        ),
    )
    if isinstance(ma_dist, (list, dict)):
        ma_dist = ""

    trending = normalize_symbol_list(
        get_path(payload, "summary.trending",
            default=get_path(payload, "trending",
                default=get_path(payload, "trend", default=[])))
    )
    top_gainer = get_path(payload, "summary.top_gainer", default=get_path(payload, "top_gainer", default=get_path(payload, "top_gainer", default=None)))
    tg_text = ""
    if isinstance(top_gainer, dict):
        sym = str(top_gainer.get("symbol", "")).strip().upper()
        ch = top_gainer.get("change", None)
        ch_s = ""
        try:
            if ch is not None and ch != "":
                ch_s = f"{float(ch):.2f}".rstrip("0").rstrip(".")
        except Exception:
            ch_s = str(ch).strip() if ch is not None else ""
        if sym and ch_s:
            tg_text = f"{sym} +{ch_s}%"
        elif sym:
            tg_text = sym

    fgi = to_float(fgi_value)
    rsi = to_float(btc_rsi)
    mad = to_float(ma_dist)

    if rsi is not None:
        if rsi < 30:
            candidates.append(f"BTC RSI が {fmt_num(rsi)} で売られ過ぎ水準。")
        elif rsi >= 70:
            candidates.append(f"BTC RSI が {fmt_num(rsi)} で買われ過ぎ水準。")

    if mad is not None:
        if mad <= -3:
            candidates.append(f"MA距離が {fmt_num(mad)}% で弱含み。")
        elif mad >= 3:
            candidates.append(f"MA距離が {fmt_num(mad)}% で上向き。")

    if tg_text:
        candidates.append(f"上昇トップは {tg_text} で強い動き。")

    if trending:
        top3 = "/".join(trending[:3])
        candidates.append(f"注目トレンドは {top3}。")

    if fgi is not None:
        if fgi < 25:
            label = fgi_label or "Extreme Fear"
            if judge == "BEAR":
                candidates.append(f"Fear & Greed が {fmt_num(fgi,0)}（{label}）で強い悲観。")
            else:
                candidates.append(f"Fear & Greed が {fmt_num(fgi,0)}（{label}）で警戒ムード。")
        elif fgi >= 75:
            label = fgi_label or "Extreme Greed"
            if judge == "BULL":
                candidates.append(f"Fear & Greed が {fmt_num(fgi,0)}（{label}）で過熱気味。")
            else:
                candidates.append(f"Fear & Greed が {fmt_num(fgi,0)}（{label}）で楽観優勢。")

    if judge:
        if judge == "WAIT":
            candidates.append("材料が揃わず、いったん様子見。")
        elif judge == "BEAR":
            candidates.append("反発弱く、戻り売りに注意。")
        elif judge == "BULL":
            candidates.append("上向き基調だが、急変には注意。")

    return shorten_one_line(candidates[0] if candidates else "")


def main() -> None:
    tmpl = read_text(TEMPL_DIR / "daily_template.html")
    tmpl_index = read_text_optional([
        TEMPL_DIR / "daily_index.html",
        TEMPL_DIR / "daily_index_template.html",
    ])
    tmpl_latest = read_text(TEMPL_DIR / "latest_template.html")

    files = sorted(glob.glob(str(DATA_DIR / "*.json")))
    dated: List[str] = []
    for f in files:
        name = Path(f).stem
        if re.fullmatch(r"\d{8}", name):
            dated.append(name)
    dated = sorted(set(dated))
    if not dated:
        raise SystemExit(f"No daily json files found in: {DATA_DIR}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    latest_ymd = dated[-1]

    items: List[Dict[str, Any]] = []
    for ymd in reversed(dated):
        json_path = DATA_DIR / f"{ymd}.json"
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}

        date_iso = get_path(payload, "summary.date", default="")
        if not date_iso:
            try:
                date_iso = datetime.datetime.strptime(ymd, "%Y%m%d").strftime("%Y-%m-%d")
            except Exception:
                date_iso = ymd

        fgi_value = get_path(payload, "summary.fgi.value", default=get_path(payload, "fear_greed", default=""))
        btc_rsi   = get_path(payload, "summary.technical.btc_rsi", default=get_path(payload, "btc_rsi", default=""))
        ma_dist   = get_path(payload, "summary.technical.btc_ma_distance",
                          default=get_path(payload, "summary.technical.ma_distance",
                              default=get_path(payload, "btc_ma_distance",
                                  default=get_path(payload, "ma_distance", default=""))))
        if isinstance(ma_dist, (list, dict)):
            ma_dist = ""

        trending_raw = get_path(payload, "summary.trending",
                                default=get_path(payload, "trending",
                                                default=get_path(payload, "trend", default=[])))
        trending = normalize_symbol_list(trending_raw)

        top_gainer = get_path(payload, "summary.top_gainer", default=get_path(payload, "top_gainer", default={}))
        if not isinstance(top_gainer, dict):
            top_gainer = {}

        judge = get_path(payload, "ai_judge", default=get_path(payload, "ai.judge", default=""))
        if not str(judge).strip():
            judge = compute_judge(fgi_value, btc_rsi, ma_dist)

        updated_at = get_path(payload, "updated_at", default=get_path(payload, "timestamp", default=""))
        if not str(updated_at).strip():
            updated_at = f"{date_iso} 09:00"

        seo_meta = build_seo_meta(date_iso, ymd, judge, fgi_value, btc_rsi, ma_dist, trending, top_gainer=top_gainer)
        jsonld = build_jsonld(
            seo_meta.get("CANONICAL",""),
            seo_meta.get("TITLE",""),
            seo_meta.get("DESCRIPTION",""),
            date_iso,
            str(updated_at),
        )

        sent = fmt_num(fgi_value, 0)
        sent = sent if sent != "" else "—"

        rsi_num = fmt_num(btc_rsi, 1)          # RSIは小数1桁
        rsi = rsi_num if rsi_num != "" else "—"

        trend_num = fmt_num(ma_dist, 1)        # Trendは小数1桁
        trend = (trend_num + "%") if trend_num != "" else "—"   # %を明示

        title = seo_meta.get("TITLE") or f"BTC AI分析（{date_iso}）"
        desc  = seo_meta.get("DESCRIPTION") or f"CoinRaderの日次AI分析レポート（{date_iso}）。Fear&Greed={sent}, RSI={rsi}, Trend={trend}。"
        canonical = seo_meta.get("CANONICAL") or f"{SITE_ORIGIN}/daily/{ymd}"
        og_image = f"{OGP_DAILY_PREFIX}/{ymd}.png"

        items.append({
            "ymd": ymd,
            "date_iso": date_iso,
            "payload": payload,
            "judge": str(judge),
            "fgi_value": fgi_value,
            "btc_rsi": btc_rsi,
            "ma_dist": ma_dist,
            "trending": trending,
            "top_gainer": top_gainer,
            "updated_at": updated_at,
            "seo_meta": seo_meta,
            "jsonld": jsonld,
            "title": title,
            "desc": desc,
            "canonical": canonical,
            "sent": sent,
            "rsi": rsi,
            "trend": trend,
        })

    judge_days: Dict[str, List[str]] = {}
    for it in items:
        j = (it.get("judge") or "").strip()
        y = it.get("ymd") or ""
        if j and y:
            judge_days.setdefault(j, []).append(y)
    for j in list(judge_days.keys()):
        judge_days[j] = sorted(set(judge_days[j]))

    pages: List[Dict[str, str]] = []
    for it in items:
        ymd = it["ymd"]
        date_iso = it["date_iso"]
        payload = it["payload"]
        judge = it["judge"]
        sent = it["sent"]
        rsi = it["rsi"]
        trend = it["trend"]
        updated_at = it["updated_at"]
        title = it["title"]
        desc = it["desc"]
        canonical = it["canonical"]
        jsonld = it["jsonld"]
        trending = it["trending"]
        top_gainer = it["top_gainer"]

        fgi_label = get_path(payload, "summary.fgi.label", default="")
        trend_top3 = " / ".join(trending[:3]) if trending else ""

        recent_days_html = build_recent_days_html(dated, ymd, n=7)
        why_html = build_reason_html(payload, judge)
        takeaways_html = build_takeaways_html(payload, judge, sent, rsi, trend, trending, top_gainer)
        coin_hubs_html = build_coin_hub_links_html(SITE_ORIGIN, trending, top_gainer)

        print("[DBG] trending=", trending, "top_gainer=", top_gainer)
        print("[DBG] coin_hubs_html_len=", len(coin_hubs_html or ""))

        html = tmpl
        repl = {
            "{{TITLE}}": title,
            "{{DESCRIPTION}}": desc,
            "{{CANONICAL}}": canonical,
            "{{JSONLD}}": jsonld,
            "{{OG_TITLE}}": title,
            "{{OG_DESCRIPTION}}": desc,
            "{{DATE}}": date_iso,
            "{{H1}}": f"BTC AI分析（{date_iso}）",
            "{{UPDATED_AT}}": str(updated_at),
            "{{JUDGE}}": escape_html(str(judge)),
            "{{SENTIMENT_VALUE}}": escape_html(str(sent)),
            "{{SENTIMENT}}": escape_html(str(sent)),
            "{{BTC_RSI}}": escape_html(str(rsi)),
            "{{TREND}}": escape_html(str(trend)),
            "{{SENTIMENT_LABEL}}": escape_html(str(fgi_label)),
            "{{TRENDING_TOP3}}": escape_html(str(trend_top3)),
            "{{TAKEAWAYS_HTML}}": takeaways_html,
            "{{TAKEAWAYS}}": takeaways_html,
            "{{OG_URL}}": canonical,
            "{{TW_CARD}}": "summary_large_image",
            "{{TW_TITLE}}": title,
            "{{TW_DESCRIPTION}}": desc,
            "{{OG_IMAGE}}": og_image,
            "{{TW_IMAGE}}": og_image,
            "{{WHY_HTML}}": why_html,
            "{{WHY}}": why_html,
            "{{RECENT_DAYS_HTML}}": recent_days_html,
            "{{RECENT_DAYS}}": recent_days_html,
        }
        for k, v in repl.items():
            html = html.replace(k, v)

        # --- inject minimal CSS (once) ---
        if "</head>" in html and "/* injected by build_daily_pages.py */" not in html:
            html = html.replace("</head>", COIN_HUBS_CSS + "\n</head>", 1)
          
        # coin hubs: テンプレにプレースホルダが無くても差し込む（安定アンカー方式）
        if coin_hubs_html:
            inserted = False

            # 1) まず「日付チップ(.chips)の直後」に入れる（ここが一番自然で崩れにくい）
            if re.search(r"</div>\s*<!--\s*Main\s*-->", html):
                html = re.sub(r"(</div>\s*<!--\s*Main\s*-->)", r"\1\n" + coin_hubs_html, html, count=1)
                inserted = True
            elif re.search(r"</div>\s*<div class=\"grid\">", html):
                html = re.sub(r"(</div>\s*<div class=\"grid\">)", r"\1\n" + coin_hubs_html, html, count=1)
                inserted = True
            elif re.search(r"<div class=\"chips\">.*?</div>", html, flags=re.DOTALL):
                # chips ブロック末尾の </div> の直後に入れる
                html = re.sub(r"(<div class=\"chips\">.*?</div>)", r"\1\n" + coin_hubs_html, html, count=1, flags=re.DOTALL)
                inserted = True

            # 2) だめなら h1 直後
            if (not inserted) and re.search(r"</div>\s*<!-- Meta", html):
                html = re.sub(r"(</div>\s*<!-- Meta)", r"\1\n" + coin_hubs_html + "\n", html, count=1)
                inserted = True
            if (not inserted) and re.search(r"</div>\s*<div class=\"meta\">", html):
                html = re.sub(r"(</div>\s*<div class=\"meta\">)", r"\1\n" + coin_hubs_html, html, count=1)
                inserted = True

            # 3) 最後の保険：<body>直後
            if (not inserted) and re.search(r"<body\b[^>]*>", html):
                html = re.sub(r"(<body\b[^>]*>)", r"\1\n" + coin_hubs_html, html, count=1)
      
        # TAKEAWAYS: テンプレにプレースホルダが無い場合でも、wrap直後に安全に挿入する
        if takeaways_html and ("{{TAKEAWAYS" not in tmpl):
            inserted = False

            # 1) <div class="wrap"> の直後（レイアウトに乗るので最優先）
            if re.search(r"<div class=\"wrap\">", html):
                html = re.sub(r"(<div class=\"wrap\">)", r"\1\n" + takeaways_html, html, count=1)
                inserted = True

            # 2) だめなら h1 直後
            if (not inserted) and re.search(r"(</div>\s*<!-- Meta)", html):
                html = re.sub(r"(</div>\s*<!-- Meta)", r"</div>\n" + takeaways_html + "\n<!-- Meta", html, count=1)
                inserted = True

            # 3) 最後の保険：<main> / <body>
            if (not inserted) and re.search(r"<main\b[^>]*>", html):
                html = re.sub(r"(<main\b[^>]*>)", r"\1\n" + takeaways_html, html, count=1)
                inserted = True
            if (not inserted) and re.search(r"<body\b[^>]*>", html):
                html = re.sub(r"(<body\b[^>]*>)", r"\1\n" + takeaways_html, html, count=1)

        out_file = OUT_DIR / f"{ymd}.html"
        write_text(out_file, html)

        trend_top3 = "/".join(trending[:3]) if trending else ""

        top_gainer_label = ""
        if isinstance(top_gainer, dict) and str(top_gainer.get("symbol","")).strip():
            sym = str(top_gainer.get("symbol","")).strip().upper()
            ch = top_gainer.get("change")
            ch_s = ""
            try:
                ch_s = f"{float(ch):.2f}".rstrip("0").rstrip(".") if ch is not None else ""
            except Exception:
                ch_s = str(ch).strip() if ch is not None else ""
            top_gainer_label = f"{sym} +{ch_s}%" if ch_s else sym

        reason_1line = build_reason_1line(payload)

        pages.append({
            "ymd": ymd,
            "date_iso": date_iso,
            "title": title,
            "href": f"{ymd}",
            "judge": str(judge),
            "fgi": sent,
            "btc_rsi": rsi,
            "trend": trend,
            "trend_top3": trend_top3,
            "top_gainer": top_gainer_label,
            "reason_1line": reason_1line,
        })

    pages_desc = sorted(pages, key=lambda p: p.get("ymd",""), reverse=True)

    def _pill(text: str, cls: str = "") -> str:
        if not text:
            return ""
        cls_attr = ("pill " + cls).strip()
        return f"<span class='{cls_attr}'>{escape_html(text)}</span>"

    def _fmt_meta_html(p: dict) -> str:
        parts = []
        j = (p.get("judge") or "").upper()
        if j:
            cls = "pill-ai"
            if j == "BULL":
                cls += " bull"
            elif j == "BEAR":
                cls += " bear"
            elif j == "WAIT":
                cls += " wait"
            parts.append(_pill(f"AI {j}", cls))
        if p.get("fgi") is not None:
            parts.append(_pill(f"FGI {p['fgi']}", "pill-kpi"))
        if p.get("btc_rsi") is not None:
            parts.append(_pill(f"RSI {p['btc_rsi']}", "pill-kpi"))
        if p.get("trend") is not None:
            parts.append(_pill(f"Trend {p['trend']}", "pill-kpi"))
        if p.get("trend_top3"):
            parts.append(_pill(f"注目 {p['trend_top3']}", "pill-hot"))
        if p.get("top_gainer"):
            parts.append(_pill(f"上昇 {p['top_gainer']}", "pill-up"))
        return "".join([x for x in parts if x])

    def _reason_line(p: dict) -> str:
        r = (p.get("reason_1line") or "").strip()
        if not r:
            return ""
        r = shorten_one_line(r, max_len=95)
        return f"<div class='rowreason'>{escape_html(r)}</div>"

    rows_html = "\n".join([
        "<div class='row'>"
        f"<a class='rowlink' href='{escape_html(p['href'])}'>"
        f"<div class='date'>{escape_html(p['date_iso'])}</div>"
        f"<div class='meta'>{_fmt_meta_html(p)}</div>"
        f"{_reason_line(p)}"
        "</a>"
        "</div>"
        for p in pages_desc
    ])

    items_html = "\n".join([
        f"<li><a href='{escape_html(p['href'])}'>{escape_html(p['title'])}</a></li>"
        for p in pages_desc
    ])

    index_html = tmpl_index
    rows_pat = re.compile(r"\{\{\s*ROWS\s*\}\}")
    items_pat = re.compile(r"\{\{\s*ITEMS\s*\}\}")
    latest_pat = re.compile(r"\{\{\s*LATEST_HREF\s*\}\}")

    index_html, n_rows = rows_pat.subn(rows_html, index_html)
    index_html, n_items = items_pat.subn(items_html, index_html)
    index_html, n_latest = latest_pat.subn(f"{latest_ymd}", index_html)

    if re.search(r"\{\{\s*(ROWS|ITEMS|LATEST_HREF)\s*\}\}", index_html):
        raise RuntimeError("daily_index.html: placeholder が残っています（ROWS/ITEMS/LATEST_HREF）")
    if (n_rows + n_items + n_latest) == 0:
        raise RuntimeError("daily_index.html: placeholder が見つからず置換できませんでした（テンプレの {{ROWS}}/{{ITEMS}}/{{LATEST_HREF}} を確認してください）")

    # ★ build marker
    index_html = strip_orphan_script_closers(index_html)
    index_html = inject_build_marker_once(index_html, latest_ymd)
    write_text(OUT_DIR / "index.html", index_html)

    tags_dir = OUT_DIR / "tags"
    tags_dir.mkdir(parents=True, exist_ok=True)

    for judge_key in ["BEAR", "BULL", "WAIT"]:
        filtered = [p for p in pages_desc if str(p.get("judge","")).upper() == judge_key]
        tag_lower = judge_key.lower()

        # tagページはテンプレ側にh1/説明/タブ/検索UIが既にある前提なので
        # list内に taghead を追加しない（見出し二重を防ぐ）
        rows_html_tag = "\n".join([
            "<div class='row'>"
            f"<a class='rowlink' href='/daily/{escape_html(p['ymd'])}'>"
            f"<div class='date'>{escape_html(p['date_iso'])}</div>"
            f"<div class='meta'>{_fmt_meta_html(p)}</div>"
            f"{_reason_line(p)}"
            "</a>"
            "</div>"
            for p in filtered
        ])

        items_html_tag = "\n".join([
            f"<li><a href='/daily/{escape_html(p['ymd'])}'>{escape_html(p['title'])}</a></li>"
            for p in filtered
        ])

        tag_html = tmpl_index
        tag_html, _ = rows_pat.subn(rows_html_tag, tag_html)
        tag_html, _ = items_pat.subn(items_html_tag, tag_html)

        # テンプレの「最新」リンクは extensionless に統一
        # （daily/latest は _redirects で daily/yyyymmdd に飛ぶ想定）
        tag_html, _ = latest_pat.subn("/daily/latest", tag_html)

        if re.search(r"\{\{\s*(ROWS|ITEMS|LATEST_HREF)\s*\}\}", tag_html):
            raise RuntimeError("tag page: placeholder が残っています（ROWS/ITEMS/LATEST_HREF）")

        tag_lower = judge_key.lower()
        tag_suffix = {"bear":"弱気局面", "bull":"強気局面", "wait":"様子見"}.get(tag_lower, "")
        new_title = f"AI {judge_key} の日一覧" + (f"（{tag_suffix}）" if tag_suffix else "") + " | CoinRader"
        tag_html = re.sub(r"<title>.*?</title>", f"<title>{escape_html(new_title)}</title>", tag_html, flags=re.DOTALL)

        desc_map = {
            "bear": "AI判定がBEARの日を一覧化。弱気局面の推移を日次で確認できます。",
            "bull": "AI判定がBULLの日を一覧化。強気局面の推移を日次で確認できます。",
            "wait": "AI判定がWAITの日を一覧化。様子見局面の推移を日次で確認できます。",
        }
        new_desc = desc_map.get(tag_lower, "CoinRaderの日次AIレポート一覧（判定別）。")
        tag_html = re.sub(
            r'<meta\s+name="description"\s+content="[^"]*"\s*/?>',
            f'<meta name="description" content="{escape_html(new_desc)}" />',
            tag_html
        )


        canon_url = f"{SITE_ORIGIN}/daily/tags/{tag_lower}"

        # og/twitter placeholders (if present in template)
        tag_html = tag_html.replace("{{OG_URL}}", canon_url)
        tag_html = tag_html.replace("{{TW_CARD}}", "summary_large_image")
        tag_html = tag_html.replace("{{TW_TITLE}}", f"AI {judge_key} の日一覧 | CoinRader")
        tag_html = tag_html.replace("{{TW_DESCRIPTION}}", new_desc)
        tag_html = re.sub(
            r'<link\s+rel="canonical"\s+href="[^"]*"\s*/?>',
            f'<link rel="canonical" href="{escape_html(canon_url)}" />',
            tag_html
        )

        # --- 見出し置換：<h1> / <h1 ...> どちらでも当たるようにする ---
        tag_html = re.sub(
            r"<h1[^>]*>.*?</h1>",
            f"<h1>AI {escape_html(judge_key)} の日一覧</h1>",
            tag_html,
            flags=re.DOTALL
        )
        # テンプレが <div class="h1">...</div> 形式の場合も置換する（daily_index系）
        tag_html = re.sub(
            r"<div[^>]*class=['\"][^'\"]*\bh1\b[^'\"]*['\"][^>]*>.*?</div>",
            f"<div class=\"h1\">AI {escape_html(judge_key)} の日一覧</div>",
            tag_html,
            flags=re.DOTALL
        )

        tag_html = re.sub(r'(class="tab[^"]*?)\s+current', r'\1', tag_html)
        tag_html = tag_html.replace(f'class="tab tab-{tag_lower}"', f'class="tab tab-{tag_lower} current"', 1)

        jsonld = build_tag_jsonld(SITE_ORIGIN, judge_key, filtered)
        tag_html = tag_html.replace("</head>", f'  <script type="application/ld+json">{jsonld}</script>\n</head>', 1)

        # ★ build marker
        tag_html = strip_orphan_script_closers(tag_html)
        tag_html = inject_build_marker_once(tag_html, latest_ymd)

        out_path_html = tags_dir / f"{tag_lower}.html"

        # --- 失敗検知を「見出しに残っている場合」だけに絞る（広すぎチェックを廃止） ---
        if re.search(r"<h1[^>]*>\s*Daily AIレポート一覧\s*</h1>", tag_html):
            raise RuntimeError("tag page: heading replacement failed (h1)")
        if re.search(r"<div[^>]*class=['\"][^'\"]*\bh1\b[^'\"]*['\"][^>]*>\s*Daily AIレポート一覧\s*</div>", tag_html):
            raise RuntimeError("tag page: heading replacement failed (div.h1)")

        write_text(out_path_html, tag_html)

        # NOTE: tag pages are canonicalized to .html via _redirects, so do not generate extensionless files.

    latest_target = f"{latest_ymd}.html"
    latest_page_path = OUT_DIR / latest_target
    latest_page_html = read_text(latest_page_path)
    write_text(OUT_DIR / "latest.html", latest_page_html)

    rebuild_sitemap_with_daily(
        ROOT / "sitemap.xml",
        site_origin=SITE_ORIGIN,
        daily_pages=pages,
        include_extensionless_tag_pages=False,
    )
    print(f"[OK] Generated {len(pages)} pages into: {OUT_DIR} (latest={latest_target})")

def strip_orphan_script_closers(html: str) -> str:
    """
    本当に「孤立している </script>」だけ除去する。
    直前に未クローズの <script ...> が存在するなら、それは孤立ではないので消さない。
    """
    # </script> を見つけて、直前の <script ...> と </script> の数で整合を取る
    parts = re.split(r"(</script\s*>)", html, flags=re.IGNORECASE)
    if len(parts) == 1:
        return html

    out = []
    open_count = 0

    # 開始側は <script ...>（ただし <script type="application/ld+json"> も含む）
    script_open_re = re.compile(r"<script\b[^>]*>", re.IGNORECASE)

    for chunk in parts:
        if chunk.lower().startswith("</script"):
            if open_count > 0:
                # 対応する <script> がある → 正常な </script>
                out.append(chunk)
                open_count -= 1
            else:
                # 対応する <script> が無い → 孤立なので除去（何も出力しない）
                continue
        else:
            # chunk 内の <script ...> の数を加算
            opens = len(script_open_re.findall(chunk))
            open_count += opens
            out.append(chunk)

    return "".join(out)


if __name__ == "__main__":
    main()
