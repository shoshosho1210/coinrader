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
import math
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
DICTIONARY_ALIAS_SLUGS = {"fear-and-greed"}  # /dictionary/fear-greed-index/ に301で集約
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
.chip-coin.is-missing{
  opacity:.55;
  border-style:dashed;
  cursor:default;
}
.chip-coin.is-missing:hover{ text-decoration:none; filter:none; }
</style>
""".strip()

# scripts/ の1つ上を repo root として想定
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "daily"
OUT_DIR  = ROOT / "daily"
OUT_DIR_EN = ROOT / "en" / "daily"
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


def to_en_daily_url(path: str) -> str:
    """Map /daily/... URLs to /en/daily/... for EN build."""
    return path.replace('/daily/', '/en/daily/').replace('/daily"', '/en/daily"')


def localize_daily_html_en(
    html: str,
    canonical: str,
    ja_url: str,
    en_title: str,
    en_desc: str,
    en_h1: str,
    en_jsonld: str,
    en_faq_jsonld: str,
) -> str:
    """Post-process JA daily HTML into EN route variant (/en/daily/*)."""
    en_canonical = canonical.replace(f"{SITE_ORIGIN}/daily/", f"{SITE_ORIGIN}/en/daily/")
    en_url = en_canonical

    html = re.sub(r'<html\s+lang="ja">', '<html lang="en">', html, count=1)
    html = html.replace('CoinRader</a> / <a href="/daily/">Daily</a>', 'CoinRader</a> / <a href="/en/daily/">Daily</a>')
    html = html.replace('href="/daily/', 'href="/en/daily/')
    html = html.replace("href='/daily/", "href='/en/daily/")

    html = re.sub(
        r'<link\s+rel="canonical"\s+href="[^"]*"\s*/?>',
        f'<link rel="canonical" href="{escape_html(en_canonical)}" />',
        html,
        count=1,
    )
    html = re.sub(r'<meta\s+property="og:url"\s+content="[^"]*"\s*/?>', f'<meta property="og:url" content="{escape_html(en_url)}" />', html, count=1)
    html = re.sub(r'<title>.*?</title>', f'<title>{escape_html(en_title)}</title>', html, flags=re.DOTALL, count=1)
    html = re.sub(r'<meta\s+name="description"\s+content="[^"]*"\s*/?>', f'<meta name="description" content="{escape_html(en_desc)}" />', html, count=1)
    html = re.sub(r'<meta\s+property="og:title"\s+content="[^"]*"\s*/?>', f'<meta property="og:title" content="{escape_html(en_title)}" />', html, count=1)
    html = re.sub(r'<meta\s+property="og:description"\s+content="[^"]*"\s*/?>', f'<meta property="og:description" content="{escape_html(en_desc)}" />', html, count=1)
    html = re.sub(r'<div class="h1">.*?</div>', f'<div class="h1">{escape_html(en_h1)}</div>', html, flags=re.DOTALL, count=1)
    script_pat = re.compile(r'<script type="application/ld\+json">\s*.*?\s*</script>', re.DOTALL)
    html = script_pat.sub(f'<script type="application/ld+json">\n  {en_jsonld}\n  </script>', html, count=1)
    m = script_pat.search(html)
    if m:
        m2 = script_pat.search(html, m.end())
        if m2:
            html = html[:m2.start()] + f'<script type="application/ld+json">\n  {en_faq_jsonld}\n  </script>' + html[m2.end():]

    hreflang = (
        f'<link rel="alternate" hreflang="ja" href="{escape_html(ja_url)}" />\n'
        f'  <link rel="alternate" hreflang="en" href="{escape_html(en_url)}" />\n'
        f'  <link rel="alternate" hreflang="x-default" href="{escape_html(ja_url)}" />'
    )
    if 'hreflang="ja"' not in html:
        html = html.replace('</head>', f'  {hreflang}\n</head>', 1)

    html = html.replace("const saved = localStorage.getItem(KEY) || 'ja';", "const saved = localStorage.getItem(KEY) || 'en';")

    # On /en route, make the language switch explicit via URL (to JA daily page)
    # so we don't depend on in-page JA fallback attributes.
    ja_path = ja_url.replace(SITE_ORIGIN, "")
    html = re.sub(
        r'<button class="btn" type="button" id="langToggle" aria-label="Switch language"\s*aria-pressed="false">EN</button>',
        f'<a class="btn" href="{escape_html(ja_path)}" aria-label="Switch to Japanese page">JP</a>',
        html,
        count=1,
    )

    # Prefer English static copy on /en pages (SEO / no-JS friendly)
    en_replacements = {
        "AI判定": "AI judgment",
        "結論：": "Conclusion: ",
        "注目トレンド": "Trending",
        "市場心理": "Market sentiment",
        "短期の温度感": "Short-term heat",
        "方向感": "Direction",
        "よくある質問": "FAQ",
        "このAI判断は投資助言ですか？": "Is this AI judgment investment advice?",
        "今日はなぜ下がったのですか？": "Why did the market weaken today?",
        "強気に転換する条件は？": "What would signal a bullish reversal?",
        "弱気になった場合、何を見るべき？": "What should I watch in a bearish phase?",
        "いいえ。CoinRader は公開市場データをルールベースで分析した情報提供ダッシュボードです。売買判断はご自身の責任で行ってください。": "No. CoinRader is an informational dashboard based on public market data. Make trading decisions at your own discretion.",
        "客観的な暗号資産分析ダッシュボード": "Objective crypto analytics dashboard",
        "関連銘柄": "Related coins",
        "過去の類似日 TOP5": "Top 5 similar past days",
        "FGI / RSI / Trend の近さで過去日を表示しています（投資助言ではありません）。": "Past days are ranked by similarity of FGI / RSI / Trend (not investment advice).",
        "類似度": "Similarity",
        "一覧": "List",
        "最新": "Latest",
        "前日": "Previous day",
        "翌日": "Next day",
    }
    for ja, en in en_replacements.items():
        html = html.replace(ja, en)

    # Make /en pages no-JS friendly by rendering data-en text as initial innerHTML
    i18n_block_pat = re.compile(
        r'(<(?P<tag>[a-zA-Z0-9]+)\b[^>]*\bdata-i18n\b[^>]*\bdata-en="(?P<en>[^"]*)"[^>]*>)(?P<body>.*?)(</(?P=tag)>)',
        re.DOTALL,
    )

    def _i18n_to_en(m: re.Match) -> str:
        return f"{m.group(1)}{m.group('en')}{m.group(5)}"

    html = i18n_block_pat.sub(_i18n_to_en, html)
    # Remove JA fallback attributes on /en pages to avoid shipping JP fragments in HTML source.
    html = re.sub(r"\sdata-ja=(?:\"[^\"]*\"|'[^']*')", '', html)
    return html

def normalize_i18n_for_en_html(html: str) -> str:
    """Render EN copy into data-i18n/data-ph blocks and remove JA attributes/comments."""
    i18n_block_pat = re.compile(
        r'(<(?P<tag>[a-zA-Z0-9]+)\b[^>]*\bdata-i18n\b[^>]*\bdata-en="(?P<en>[^"]*)"[^>]*>)(?P<body>.*?)(</(?P=tag)>)',
        re.DOTALL,
    )
    html = i18n_block_pat.sub(lambda m: f"{m.group(1)}{m.group('en')}{m.group(5)}", html)

    html = re.sub(
        r'(<input\b(?=[^>]*\bdata-ph-en="(?P<en>[^"]*)")(?=[^>]*\bplaceholder=")(?P<attrs>[^>]*?)\bplaceholder=")(?P<ph>[^"]*)("(?P<tail>[^>]*>))',
        lambda m: f"<input{m.group('attrs')}placeholder=\"{m.group('en')}\"{m.group('tail')}",
        html,
        flags=re.DOTALL,
    )

    html = re.sub(r"\sdata-ja=(?:\"[^\"]*\"|'[^']*')", '', html)
    html = re.sub(r"\sdata-ph-ja=(?:\"[^\"]*\"|'[^']*')", '', html)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    return html


def build_seo_meta_en(date_iso: str, ymd: str, judge: str, sentiment_value, btc_rsi, trend, trending: List[str], top_gainer=None) -> Dict[str, str]:
    fgi_s = str(sentiment_value) if sentiment_value is not None else "-"
    rsi_s = str(btc_rsi) if btc_rsi is not None else "-"
    trend_s = str(trend) if trend is not None else "-"
    trend_str = "/".join([t.upper() for t in (trending or [])][:3])
    gain_str = ""
    if isinstance(top_gainer, dict) and top_gainer.get("symbol"):
        ch = top_gainer.get("change")
        try:
            ch_s = f"{float(ch):.2f}" if ch is not None else ""
        except Exception:
            ch_s = str(ch) if ch is not None else ""
        gain_str = f" Top gainer: {top_gainer.get('symbol').upper()}(+{ch_s}%)" if ch_s else f" Top gainer: {top_gainer.get('symbol').upper()}"

    title = f"BTC Daily AI Analysis {date_iso} | Fear & Greed {fgi_s} / RSI {rsi_s} / Trend {trend_s} (CoinRader)"
    desc = f"Daily BTC AI analysis for {date_iso}. Sentiment(Fear & Greed)={fgi_s}, RSI={rsi_s}, Trend={trend_s}. Overall: {judge}. Trending: {trend_str}.{gain_str}".strip()
    canonical = f"{SITE_ORIGIN}/en/daily/{ymd}"
    return {"TITLE": title, "DESCRIPTION": desc, "CANONICAL": canonical}


def build_jsonld_en(canonical: str, title: str, description: str, date_iso: str, updated_at_jst: str) -> str:
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "@id": canonical + "#article",
                "headline": title,
                "description": description,
                "datePublished": date_iso + "T09:00:00+09:00",
                "dateModified": date_iso + "T09:00:00+09:00" if not updated_at_jst else date_iso + "T09:00:00+09:00",
                "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
                "publisher": {"@type": "Organization", "name": "CoinRader"},
            },
            {
                "@type": "FAQPage",
                "@id": canonical + "#faq",
                "mainEntity": [
                    {"@type": "Question", "name": "Is this investment advice?", "acceptedAnswer": {"@type": "Answer", "text": "No. CoinRader provides informational analytics only."}},
                    {"@type": "Question", "name": "How often is this page updated?", "acceptedAnswer": {"@type": "Answer", "text": "This page is updated daily (JST)."}},
                    {"@type": "Question", "name": "Does low Fear & Greed or RSI always mean buy?", "acceptedAnswer": {"@type": "Answer", "text": "No. Use them with trend and market context."}},
                ],
            },
            {
                "@type": "BreadcrumbList",
                "@id": canonical + "#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "CoinRader", "item": f"{SITE_ORIGIN}/"},
                    {"@type": "ListItem", "position": 2, "name": "Daily", "item": f"{SITE_ORIGIN}/en/daily/"},
                    {"@type": "ListItem", "position": 3, "name": date_iso, "item": canonical},
                ],
            },
        ],
    }
    return json.dumps(data, ensure_ascii=False)

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
        rsi_s = str(btc_rsi) if btc_rsi is not None else "-"
    except Exception:
        rsi_s = "-"
    try:
        trend_s = str(trend) if trend is not None else "-"
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
    # 日次ページは Article + FAQPage + BreadcrumbList を出力
    # updated_at_jst: 'YYYY-MM-DD HH:MM' のような文字列を想定
    def to_iso(dt_s: str) -> str:
        try:
            dt = datetime.datetime.strptime(dt_s, "%Y-%m-%d %H:%M")
            return dt.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=9))).isoformat()
        except Exception:
            return date_iso + "T09:00:00+09:00"
          
    article_id = canonical + "#article"
    faq_id = canonical + "#faq"
    breadcrumb_id = canonical + "#breadcrumb"
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "@id": article_id,
                "headline": title,
                "description": description,
                "datePublished": date_iso + "T09:00:00+09:00",
                "dateModified": to_iso(updated_at_jst),
                "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
                "publisher": {"@type": "Organization", "name": "CoinRader"},
            },
            {
                "@type": "FAQPage",
                "@id": faq_id,
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": "このAI判断は投資助言ですか？",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": "いいえ。CoinRaderは情報提供を目的としたダッシュボードです。売買判断はご自身で行ってください。",
                        },
                    },
                    {
                        "@type": "Question",
                        "name": "更新頻度は？",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": "このページは日次（JST基準）で更新されます。トップページの一部指標は数分間隔で更新される場合があります。",
                        },
                    },
                    {
                        "@type": "Question",
                        "name": "Fear & GreedやRSIが低いと必ず買いですか？",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": "必ずではありません。過熱感の目安であり、相場環境（トレンドや出来高）と併せて解釈が必要です。",
                        },
                    },
                ],
            },
            {
                "@type": "BreadcrumbList",
                "@id": breadcrumb_id,
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "CoinRader", "item": SITE_ORIGIN + "/"},
                    {"@type": "ListItem", "position": 2, "name": "Daily", "item": SITE_ORIGIN + "/daily/"},
                    {"@type": "ListItem", "position": 3, "name": date_iso, "item": canonical},
                ],
            },
        ],
    }
    s = json.dumps(data, ensure_ascii=False)
    return s.replace("</", "<\/")

def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def build_similar_days_html(current: Dict[str, Any], candidates: List[Dict[str, Any]], limit: int = 5) -> str:
    c_fgi = _safe_float(current.get("fgi_value"))
    c_rsi = _safe_float(current.get("btc_rsi"))
    c_trend = _safe_float(current.get("ma_dist"))
    c_judge = str(current.get("judge") or "").upper()
    c_ymd = str(current.get("ymd") or "")
    if not c_ymd:
        return ""

    scored: List[tuple[float, Dict[str, Any]]] = []
    for cand in candidates:
        ymd = str(cand.get("ymd") or "")
        if (not ymd) or ymd == c_ymd:
            continue

        points = []
        for key, cur, scale in (("fgi_value", c_fgi, 100.0), ("btc_rsi", c_rsi, 100.0), ("ma_dist", c_trend, 20.0)):
            val = _safe_float(cand.get(key))
            if cur is None or val is None:
                continue
            points.append((val - cur) / scale)

        if not points:
            continue

        dist = math.sqrt(sum(p * p for p in points))
        if c_judge and str(cand.get("judge") or "").upper() == c_judge:
            dist *= 0.92
        scored.append((dist, cand))

    if not scored:
        return ""

    scored.sort(key=lambda x: x[0])
    rows: List[str] = []
    for dist, cand in scored[:limit]:
        sim = max(0.0, 100.0 - (dist * 100.0))
        date_iso = escape_html(str(cand.get("date_iso") or cand.get("ymd") or ""))
        href = f"/daily/{escape_html(str(cand.get('ymd') or ''))}"
        judge = escape_html(str(cand.get("judge") or ""))
        score = f"{sim:.1f}".rstrip("0").rstrip(".")
        rows.append(
            "<li class='similar-item'>"
            f"<a href='{href}'>{date_iso}</a>"
            f"<span class='similar-meta'>AI {judge} / 類似度 {score}</span>"
            "</li>"
        )

    if not rows:
        return ""

    return (
        "<section class='card similar-days' style='margin-top:12px' aria-label='Similar Days'>"
        "<h2>過去の類似日 TOP5</h2>"
        "<p class='similar-note'>FGI / RSI / Trend の近さで過去日を表示しています（投資助言ではありません）。</p>"
        "<ul class='similar-list'>"
        + "".join(rows)
        + "</ul></section>"
    )


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
    _ensure_urls([u for u in _collect_dir_index_urls("dictionary", "/dictionary/") if u.rsplit("/", 3)[-2] not in DICTIONARY_ALIAS_SLUGS], changefreq="monthly", priority="0.5")
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

    # dictionary alias cleanup (redirect-only URLs should not be indexed)
    for alias in DICTIONARY_ALIAS_SLUGS:
        existing.pop(f"{site_origin}/dictionary/{alias}/", None)
        existing.pop(f"{site_origin}/dictionary/{alias}", None)
  
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
            if slug in DICTIONARY_ALIAS_SLUGS:
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
        f"{site_origin}/daily/latest.html",
        f"{site_origin}/daily/tags/bear.html",
        f"{site_origin}/daily/tags/bull.html",
        f"{site_origin}/daily/tags/wait.html",
        f"{site_origin}/daily/latest/",
        f"{site_origin}/daily/tags/bear/",
        f"{site_origin}/daily/tags/bull/",
        f"{site_origin}/daily/tags/wait/",
        f"{site_origin}/dictionary/fear-and-greed/",
        f"{site_origin}/dictionary/fear-and-greed",
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
            "priority": "0.9" if u.endswith("/daily/") else "0.6",
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
            if re.fullmatch(r"[a-z0-9\-]+", slug) and slug not in DICTIONARY_ALIAS_SLUGS:
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

def build_reason_html(payload: Dict[str, Any], judge: str, lang: str = "ja") -> str:
    is_en = (lang == "en")
    reasons: List[str] = []

    fgi_value = get_path(payload, "summary.fgi.value", default=get_path(payload, "fear_greed", default=""))
    fgi_label = get_path(payload, "summary.fgi.label", default="")
    btc_rsi = get_path(payload, "summary.technical.btc_rsi", default=get_path(payload, "btc_rsi", default=""))
    ma_dist = get_path(payload, "summary.technical.btc_ma_distance", default=get_path(payload, "summary.technical.ma_distance", default=get_path(payload, "btc_ma_distance", default=get_path(payload, "ma_distance", default=""))))

    if isinstance(ma_dist, (list, dict)):
        ma_dist = ""
    trending = get_path(payload, "summary.trending", default=get_path(payload, "trending", default=get_path(payload, "trend", default=[])))

    fgi = to_float(fgi_value)
    if fgi is not None:
        if is_en:
            if fgi < 25:
                reasons.append(f"Fear & Greed is {fmt_num(fgi,0)} ({fgi_label or 'Extreme Fear'}), showing heavy risk-off sentiment.")
            elif fgi < 45:
                reasons.append(f"Fear & Greed is {fmt_num(fgi,0)}, still tilted bearish.")
            elif fgi < 55:
                reasons.append(f"Fear & Greed is {fmt_num(fgi,0)}, near neutral.")
            elif fgi < 75:
                reasons.append(f"Fear & Greed is {fmt_num(fgi,0)}, leaning bullish.")
            else:
                reasons.append(f"Fear & Greed is {fmt_num(fgi,0)} ({fgi_label or 'Extreme Greed'}), suggesting overheated conditions.")
        else:
            if fgi < 25:
                reasons.append(f"Fear & Greed が {fmt_num(fgi,0)}（{fgi_label or 'Extreme Fear'}）で、市場心理は強い悲観に寄っています。")
            elif fgi < 45:
                reasons.append(f"Fear & Greed が {fmt_num(fgi,0)} で弱気寄りです。")
            elif fgi < 55:
                reasons.append(f"Fear & Greed が {fmt_num(fgi,0)} で中立付近です。")
            elif fgi < 75:
                reasons.append(f"Fear & Greed が {fmt_num(fgi,0)} で強気寄りです。")
            else:
                reasons.append(f"Fear & Greed が {fmt_num(fgi,0)}（{fgi_label or 'Extreme Greed'}）で過熱感があります。")

    rsi = to_float(btc_rsi)
    if rsi is not None:
        if is_en:
            if rsi < 30:
                reasons.append(f"BTC RSI is {fmt_num(rsi,1)}, in oversold territory.")
            elif rsi < 45:
                reasons.append(f"BTC RSI is {fmt_num(rsi,1)}, showing weak momentum.")
            elif rsi < 55:
                reasons.append(f"BTC RSI is {fmt_num(rsi,1)}, roughly neutral.")
            elif rsi < 70:
                reasons.append(f"BTC RSI is {fmt_num(rsi,1)}, indicating steady upside momentum.")
            else:
                reasons.append(f"BTC RSI is {fmt_num(rsi,1)}, in overbought territory.")
        else:
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
        if is_en:
            if mad <= -8:
                reasons.append(f"MA distance is {fmt_num(mad,1)}%, showing strong downside pressure.")
            elif mad <= -3:
                reasons.append(f"MA distance is {fmt_num(mad,1)}%, still weak versus trend.")
            elif mad < 3:
                reasons.append(f"MA distance is {fmt_num(mad,1)}%, with limited directional conviction.")
            elif mad < 8:
                reasons.append(f"MA distance is {fmt_num(mad,1)}%, supporting moderate upside bias.")
            else:
                reasons.append(f"MA distance is {fmt_num(mad,1)}%, signaling extended upside acceleration.")
        else:
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
            reasons.append(f"Trending: {' / '.join(top3)}" if is_en else f"注目トレンド: {' / '.join(top3)}")

    lead_map = {
        "BEAR": "Conclusion: Bearish bias (rebounds may face selling pressure)",
        "BULL": "Conclusion: Bullish bias (dips are more likely to be bought)",
        "WAIT": "Conclusion: Wait / range bias (weak directional conviction)",
    } if is_en else {
        "BEAR": "結論：弱気優勢（戻りは売られやすい局面）",
        "BULL": "結論：強気優勢（押し目が買われやすい局面）",
        "WAIT": "結論：様子見（方向感が弱い局面）",
    }
    lead = lead_map.get((judge or "").strip().upper(), "")

    li = "\n".join([f"<li>{escape_html(x)}</li>" for x in reasons[:6]])
    if not li and not lead:
        return ""

    return (f"<div class='judge-lead'>{escape_html(lead)}</div>" if lead else "") + (f"<ul class='why-list'>{li}</ul>" if li else "")


def build_takeaways_html(payload: Dict[str, Any], judge: str, sent: str, rsi: str, trend: str,
                         trending: List[str], top_gainer: Dict[str, Any], lang: str = "ja") -> str:
    """Key Takeaways: dailyページ冒頭に置く短い要点（AI引用されやすい箇条書き）。"""
    is_en = (lang == "en")
    take: List[str] = []
    j = (judge or "").upper().strip()
    jm = {
        "BEAR": "AI judgment: Bearish bias",
        "BULL": "AI judgment: Bullish bias",
        "WAIT": "AI judgment: Wait / range bias",
    } if is_en else {
        "BEAR": "AI判定：弱気優勢",
        "BULL": "AI判定：強気優勢",
        "WAIT": "AI判定：様子見",
    }
    if j in jm:
        take.append(jm[j])

    if sent and sent != "—":
        lab = get_path(payload, "summary.fgi.label", default="")
        take.append(f"Fear & Greed: {sent}" + (f" ({lab})" if lab else "") if is_en else (f"Fear & Greed：{sent}（{lab}）" if lab else f"Fear & Greed：{sent}"))

    if rsi and rsi != "—":
        take.append(f"BTC RSI: {rsi}" if is_en else f"BTC RSI：{rsi}")
    
    if trend and trend != "—":
        take.append(f"Trend: {trend}" if is_en else f"Trend：{trend}")

    # トレンド銘柄 TOP3
    if trending:
        top3 = [str(x).strip().upper() for x in (trending or [])[:3] if str(x).strip()]
        if top3:
            take.append(f"Trending: {' / '.join(top3)}" if is_en else f"注目トレンド：{' / '.join(top3)}")

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
            take.append(f"Top gainer: {sym} +{ch_s}%" if is_en else f"急上昇：{sym} +{ch_s}%")
        elif sym:
            take.append(f"Top gainer: {sym}" if is_en else f"急上昇：{sym}")

    if not is_en:
        r1 = build_reason_1line(payload)
        if r1:
            take.append(r1)
        
    take = [t for t in take if t][:5]
    if not take:
        return ""
    lis = "".join([f"<li>{escape_html(t)}</li>" for t in take])
    return f"<section class='takeaways' aria-label='Key Takeaways'><h2 class='takeaways-h'>Key Takeaways</h2><ul class='takeaways-ul'>{lis}</ul></section>"

def list_existing_coin_slugs(coins_dir="coins"):
    """
    Return set of existing coin slugs under /coins/.
    Accept both /coins/<slug>/ and /coins/<slug>/index.html forms.
    """
    import os
    slugs = set()
    if not os.path.isdir(coins_dir):
        return slugs

    for name in os.listdir(coins_dir):
        p = os.path.join(coins_dir, name)
        if not os.path.isdir(p):
            continue
        # /coins/<slug>/index.html があるものだけを有効扱い
        if os.path.isfile(os.path.join(p, "index.html")):
            slugs.add(name)
    return slugs


def _build_symbol_to_slug_map_from_coins_dir(coins_dir="coins"):
    """
    Scan /coins/<slug>/index.html and try to extract the ticker symbol.
    Build mapping: SYMBOL (upper) -> slug.
    """
    import os, re

    symbol_to_slug = {}
    if not os.path.isdir(coins_dir):
        return symbol_to_slug

    # よくある表記パターンを広めに拾う（安全側）
    patterns = [
        re.compile(r'"symbol"\s*:\s*"([A-Z0-9]{2,15})"'),                # JSON/LD 等
        re.compile(r'\bSymbol\s*[:：]\s*([A-Z0-9]{2,15})\b', re.I),       # "Symbol: BTC"
        re.compile(r'\bTicker\s*[:：]\s*([A-Z0-9]{2,15})\b', re.I),       # "Ticker: BTC"
        re.compile(r'data-symbol\s*=\s*["\']([A-Z0-9]{2,15})["\']', re.I),
        re.compile(r'<title[^>]*>.*?\(([A-Z0-9]{2,15})\).*?</title>', re.I | re.S),
        re.compile(r'\b\(([A-Z0-9]{2,15})\)\b'),                         # 最後の保険
    ]

    for slug in os.listdir(coins_dir):
        d = os.path.join(coins_dir, slug)
        if not os.path.isdir(d):
            continue
        fp = os.path.join(d, "index.html")
        if not os.path.isfile(fp):
            continue

        try:
            html = open(fp, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            continue

        sym = None
        for rgx in patterns:
            m = rgx.search(html)
            if m:
                sym = m.group(1).upper()
                break

        # 見つからない場合でも、slug がそのままティッカーっぽければ拾う
        if not sym:
            if slug.upper().isalnum() and 2 <= len(slug) <= 15:
                sym = slug.upper()

        if sym and sym not in symbol_to_slug:
            symbol_to_slug[sym] = slug

    return symbol_to_slug


def build_coin_hub_links_html(site_origin, trending=None, top_gainer=None, coins_dir="coins"):
    """
    Build '関連銘柄' chips.
    - If /coins/<slug>/ exists => link <a>
    - If not exists => show disabled chip <span> so daily HTML still shows all symbols
    """
    import html as _html

    trending = trending or []
    gsym = None
    if isinstance(top_gainer, dict):
        gsym = top_gainer.get("symbol") or top_gainer.get("ticker") or top_gainer.get("id")

    seen = set()
    syms = []
    for s in trending + ([gsym] if gsym else []):
        if not s:
            continue
        S = str(s).upper().strip()
        if not S or S in seen:
            continue
        seen.add(S)
        syms.append(S)

    if not syms:
        return ""

    available_slugs = list_existing_coin_slugs(coins_dir)
    sym2slug = _build_symbol_to_slug_map_from_coins_dir(coins_dir)

    chips = []
    for sym in syms:
        slug = sym2slug.get(sym)

        # 既存の手動マップがあるなら優先（あなたの BTC=bitcoin 等）
        try:
            if not slug and isinstance(SYMBOL_TO_COIN_SLUG, dict):
                slug = SYMBOL_TO_COIN_SLUG.get(sym)
        except Exception:
            pass

        # 最後に ticker小文字スラッグも試す
        if not slug:
            guess = sym.lower()
            if guess in available_slugs:
                slug = guess

        if slug and slug in available_slugs:
            href = f"/coins/{slug}/"
            chips.append(f"<a class='chip chip-coin' href='{href}'>{_html.escape(sym)}</a>")
        else:
            # coinsページが無い => 表示だけする（リンク無し）
            chips.append(f"<span class='chip chip-coin is-missing' title='Coins page not available'>{_html.escape(sym)}</span>")

    return (
        "<section class='coin-hubs' aria-label='Related coins'>"
        "<div class='coin-hubs-h'>関連銘柄</div>"
        "<div class='coin-hubs-links'>"
        + "".join(chips) +
        "</div></section>"
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

def update_daily_latest_redirect(latest_ymd: str) -> None:
    """Keep `_redirects` /daily/latest target synced to latest daily date."""
    redirects_path = ROOT / "_redirects"
    if not redirects_path.exists():
        return

    text = redirects_path.read_text(encoding="utf-8")
    target = f"/daily/latest                   /daily/{latest_ymd}         302"
    pattern = re.compile(r"^/daily/latest\s+/daily/\d{8}\s+302\s*$", re.MULTILINE)

    if pattern.search(text):
        text = pattern.sub(target, text, count=1)
    else:
        if not text.endswith("\n"):
            text += "\n"
        text += "\n# daily latest (auto-generated target)\n"
        text += target + "\n"

    redirects_path.write_text(text, encoding="utf-8")


# ============================================================================
# ★ Phase 2: Daily AI Enhancement — 新機能関数群
# ============================================================================

# ---------- A-1: シナリオ分岐 (BULL / BEAR / RANGE) ----------

def build_scenarios_html(fgi_value, btc_rsi, ma_dist, judge: str, lang: str = "ja") -> str:
    is_en = (lang == "en")

    fgi = to_float(fgi_value)
    rsi = to_float(btc_rsi)
    mad = to_float(ma_dist)

    # 信頼度: データが揃っているほど高い
    data_count = sum(1 for v in [fgi, rsi, mad] if v is not None)
    conf_label = {0: "Low", 1: "Low", 2: "Mid", 3: "High"}.get(data_count, "Low")

    # 条件テキストを動的に生成
    fgi_str = f"{fmt_num(fgi, 0)}" if fgi is not None else "—"
    rsi_str = f"{fmt_num(rsi, 1)}" if rsi is not None else "—"
    mad_str = f"{fmt_num(mad, 1)}%" if mad is not None else "—"

    if is_en:
        bull_trigger = f"FGI recovers from {fgi_str} to 45+ with improving sentiment" if (fgi is not None and fgi < 40) else (f"FGI holds around {fgi_str} while RSI breaks above 55" if fgi is not None else "FGI 45+ and RSI above 55")
        bull_watch = f"Look for RSI rebounding from {rsi_str} with rising volume" if (rsi is not None and rsi < 35) else (f"Watch whether RSI at {rsi_str} can break above 55" if rsi is not None else "Confirm RSI breakout above 55")
        bull_invalid = "Invalidated if FGI drops below 25 or MA distance falls below -8%"
        bear_trigger = f"FGI falls sharply from {fgi_str} after overheated conditions" if (fgi is not None and fgi > 60) else (f"FGI deteriorates from {fgi_str} to 25 or below" if fgi is not None else "FGI 25 or below with RSI 30 or below")
        bear_watch = f"Watch whether MA distance at {mad_str} extends further (below -10% is high risk)" if (mad is not None and mad < -5) else (f"Watch whether MA distance at {mad_str} expands further negative" if mad is not None else "Watch for deeper negative MA distance and weaker BTC volume")
        bear_invalid = "Invalidated if FGI recovers above 50 and RSI breaks above 55"
        range_trigger = f"RSI at {rsi_str} keeps trading in the neutral 40-60 zone" if (rsi is not None and 40 < rsi < 60) else "RSI converges into 40-60 with MA distance inside ±3%"
        range_watch = "Watch if volume remains below average and momentum stays muted"
        range_invalid = "Invalidated if FGI spikes to 75+ or drops to 25 or below"
    else:
        bull_trigger = f"FGI が現在 {fgi_str} → 45以上に回復し、センチメント改善" if (fgi is not None and fgi < 40) else (f"FGI が {fgi_str} を維持しつつ、RSI 55超えで勢い継続" if fgi is not None else "FGI 45以上 + RSI 55超え")
        bull_watch = f"RSI が {rsi_str} から反発する兆候（出来高増加に注目）" if (rsi is not None and rsi < 35) else (f"RSI が {rsi_str} → 55を上抜けるか" if rsi is not None else "RSI の55上抜け確認")
        bull_invalid = "FGI 25以下に再悪化 or MA距離 -8%以下に急落"
        bear_trigger = f"FGI が {fgi_str} から急落（過熱後の調整入り）" if (fgi is not None and fgi > 60) else (f"FGI が {fgi_str} → 25以下にさらに悪化" if fgi is not None else "FGI 25以下 + RSI 30以下で弱気加速")
        bear_watch = f"MA距離 {mad_str} がさらに拡大するか（-10%超えは要警戒）" if (mad is not None and mad < -5) else (f"MA距離 {mad_str} がマイナス方向に拡大するか" if mad is not None else "MA距離のマイナス拡大とBTC出来高の減少")
        bear_invalid = "FGI 50以上に回復 + RSI 55超え（センチメント反転）"
        range_trigger = f"RSI {rsi_str} が 40-60 の中立圏を推移し続ける" if (rsi is not None and 40 < rsi < 60) else "RSI 40-60圏内に収束 + MA距離 ±3%以内"
        range_watch = "出来高が平均以下の低調な推移が続くか"
        range_invalid = "FGI が 25以下 or 75以上に急変（方向感の発生）"

    scenarios = [
        {"key":"BULL","label":"Bullish Scenario" if is_en else "強気シナリオ","emoji":"📈","color":"#22c55e","trigger":bull_trigger,"invalidation":bull_invalid,"what_to_watch":bull_watch},
        {"key":"BEAR","label":"Bearish Scenario" if is_en else "弱気シナリオ","emoji":"📉","color":"#ef4444","trigger":bear_trigger,"invalidation":bear_invalid,"what_to_watch":bear_watch},
        {"key":"RANGE","label":"Range Scenario" if is_en else "レンジシナリオ","emoji":"↔️","color":"#f59e0b","trigger":range_trigger,"invalidation":range_invalid,"what_to_watch":range_watch},
    ]

    j = (judge or "").strip().upper()

    cards = []
    for sc in scenarios:
        is_active = (j == sc["key"]) or (j == "WAIT" and sc["key"] == "RANGE")
        active_badge = " <span class='scenario-now'>Closest to current regime</span>" if (is_active and is_en) else (" <span class='scenario-now'>現在の判定に近い</span>" if is_active else "")
        cards.append(f"<div class='scenario-card{' scenario-active' if is_active else ''}' style='border-color:{sc['color']}'><div class='scenario-head'><span class='scenario-emoji'>{sc['emoji']}</span><span class='scenario-title'>{escape_html(sc['label'])}</span>{active_badge}</div><div class='scenario-row'><div class='scenario-label'>{'Trigger' if is_en else '条件（Trigger）'}</div><div class='scenario-val'>{escape_html(sc['trigger'])}</div></div><div class='scenario-row'><div class='scenario-label'>{'Invalidation' if is_en else '無効化（Invalidation）'}</div><div class='scenario-val'>{escape_html(sc['invalidation'])}</div></div><div class='scenario-row'><div class='scenario-label'>{'What to watch' if is_en else '注目ポイント'}</div><div class='scenario-val'>{escape_html(sc['what_to_watch'])}</div></div></div>")
    note = "* Scenarios are auto-generated hypotheses from market data, not investment advice." if is_en else "※ シナリオは市場データから自動生成された仮説であり、投資助言ではありません。"
    return f"<section class='card scenarios' aria-label='Scenario Analysis' style='margin-top:14px'><div class='badge'>SCENARIO ANALYSIS</div><div class='scenario-conf'>Confidence: {escape_html(conf_label)}</div><div class='scenario-grid'>{''.join(cards)}</div><div class='scenario-note'>{escape_html(note)}</div></section>"

def compute_coinrader_score(fgi_value, btc_rsi, ma_dist, chg_24h=None) -> Dict[str, Any]:
    """
    市場データから CoinRader Score (0-100) を算出。
    算出根拠を完全に透明化: 各指標の正規化値と重みを返す。
    
    高スコア = 強気寄り, 低スコア = 弱気寄り, 50付近 = 中立
    """
    fgi = to_float(fgi_value)
    rsi = to_float(btc_rsi)
    mad = to_float(ma_dist)
    chg = to_float(chg_24h)

    components = []
    total_weight = 0
    weighted_sum = 0

    # 1. FGI: 0-100 そのまま (weight=0.35)
    if fgi is not None:
        fgi_norm = max(0, min(100, fgi))
        components.append({"name": "Fear & Greed Index", "raw": f"{fmt_num(fgi, 0)}", "normalized": round(fgi_norm, 1), "weight": 0.35})
        weighted_sum += fgi_norm * 0.35
        total_weight += 0.35

    # 2. RSI: 0-100 そのまま (weight=0.30)
    if rsi is not None:
        rsi_norm = max(0, min(100, rsi))
        components.append({"name": "BTC RSI(14)", "raw": f"{fmt_num(rsi, 1)}", "normalized": round(rsi_norm, 1), "weight": 0.30})
        weighted_sum += rsi_norm * 0.30
        total_weight += 0.30

    # 3. MA距離: -20%〜+20% → 0-100 (weight=0.20)
    if mad is not None:
        mad_clamped = max(-20, min(20, mad))
        mad_norm = (mad_clamped + 20) / 40 * 100  # -20→0, 0→50, +20→100
        components.append({"name": "MA距離", "raw": f"{fmt_num(mad, 1)}%", "normalized": round(mad_norm, 1), "weight": 0.20})
        weighted_sum += mad_norm * 0.20
        total_weight += 0.20

    # 4. 24h変動率: -10%〜+10% → 0-100 (weight=0.15)
    if chg is not None:
        chg_clamped = max(-10, min(10, chg))
        chg_norm = (chg_clamped + 10) / 20 * 100
        components.append({"name": "BTC 24h変動", "raw": f"{'+' if chg >= 0 else ''}{fmt_num(chg, 1)}%", "normalized": round(chg_norm, 1), "weight": 0.15})
        weighted_sum += chg_norm * 0.15
        total_weight += 0.15

    if total_weight == 0:
        return {"score": None, "components": [], "confidence": "Low", "drivers": []}

    score = round(weighted_sum / total_weight, 1)

    # Confidence
    if total_weight >= 0.85:
        confidence = "High"
    elif total_weight >= 0.5:
        confidence = "Mid"
    else:
        confidence = "Low"

    # Drivers（スコアへの寄与が大きい順にTOP3）
    drivers = sorted(components, key=lambda c: abs(c["normalized"] - 50) * c["weight"], reverse=True)[:3]
    driver_texts = []
    for d in drivers:
        direction = "↑" if d["normalized"] > 55 else "↓" if d["normalized"] < 45 else "→"
        driver_texts.append(f"{d['name']} {d['raw']} {direction}")

    return {
        "score": score,
        "components": components,
        "confidence": confidence,
        "drivers": driver_texts,
    }


def build_score_html(score_data: Dict[str, Any], lang: str = "ja") -> str:
    """CoinRader Score ゲージカードの HTML を生成。"""
    if not score_data or score_data.get("score") is None:
        return ""
    
    is_en = (lang == "en")
    score = score_data["score"]
    confidence = score_data.get("confidence", "Low")
    drivers = score_data.get("drivers", [])
    components = score_data.get("components", [])

    # スコアに応じた色
    if score >= 65:
        color = "#22c55e"; label = "Bullish" if is_en else "強気寄り"
    elif score >= 45:
        color = "#f59e0b"; label = "Neutral" if is_en else "中立"
    else:
        color = "#ef4444"; label = "Bearish" if is_en else "弱気寄り"

    if is_en:
        drivers = [d.replace('MA距離', 'MA distance').replace('BTC 24h変動', 'BTC 24h change') for d in drivers]

    drivers_html = "".join([f"<li>{escape_html(d)}</li>" for d in drivers])
    comp_rows = "".join([f"<div class='score-comp'><span class='comp-name'>{escape_html({'MA距離':'MA distance','BTC 24h変動':'BTC 24h change'}.get(c['name'], c['name']) if is_en else c['name'])}</span><span class='comp-raw'>{escape_html(c['raw'])}</span><span class='comp-weight'>×{c['weight']:.0%}</span></div>" for c in components])
    method = "CoinRader Score = weighted average of normalized indicators (0-100). Higher = more bullish." if is_en else "CoinRader Score = 各指標の正規化値(0-100) × 重みの加重平均。数値が高いほど強気シグナル。"
    return f"<section class='card score-card' aria-label='CoinRader Score' style='margin-top:14px'><div class='badge'>COINRADER SCORE</div><div class='score-gauge'><div class='score-num' style='color:{color}'>{fmt_num(score, 0)}</div><div class='score-label'>{escape_html(label)}</div><div class='score-bar'><div class='score-fill' style='width:{score}%;background:{color}'></div></div></div><div class='score-conf'>Confidence: {escape_html(confidence)}</div><div class='score-drivers'><div class='score-drivers-h'>{'Main drivers' if is_en else '主要ドライバー'}</div><ul>{drivers_html}</ul></div><details class='score-detail'><summary>{'Show calculation' if is_en else '算出根拠を表示'}</summary><div class='score-comps'>{comp_rows}</div><div class='score-method'>{escape_html(method)}</div></details></section>"


# ---------- A-2: 動的FAQ + FAQPage JSON-LD ----------

def build_dynamic_faq_html(judge: str, fgi_value, btc_rsi, ma_dist,
                           scenarios_data: Dict = None, lang: str = "ja") -> str:
    is_en = (lang == "en")
    fgi = to_float(fgi_value)
    rsi = to_float(btc_rsi)
    mad = to_float(ma_dist)
    j = (judge or "").strip().upper()

    direction_ja = "下がった" if (j == "BEAR" or (mad is not None and mad < -3)) else "上がった" if (j == "BULL" or (mad is not None and mad > 3)) else "このような状況"
    direction_en = "fell" if (j == "BEAR" or (mad is not None and mad < -3)) else "rose" if (j == "BULL" or (mad is not None and mad > 3)) else "moved like this"
    q1 = f"Why did the market {direction_en} today?" if is_en else f"今日はなぜ{direction_ja}のですか？"
    a1_parts = []
    if fgi is not None:
        if fgi < 25: a1_parts.append(f"Fear & Greed Index is {fmt_num(fgi, 0)} (Extreme Fear), indicating strong risk-off pressure" if is_en else f"Fear & Greed Index が {fmt_num(fgi, 0)}（Extreme Fear）と極度の悲観状態にあり、売り圧力が強まっています")
        elif fgi < 45: a1_parts.append(f"Fear & Greed Index is {fmt_num(fgi, 0)}, reflecting bearish sentiment" if is_en else f"Fear & Greed Index が {fmt_num(fgi, 0)} と弱気寄りのセンチメントです")
        elif fgi > 75: a1_parts.append(f"Fear & Greed Index is {fmt_num(fgi, 0)} (Extreme Greed), suggesting overheated conditions" if is_en else f"Fear & Greed Index が {fmt_num(fgi, 0)}（Extreme Greed）と過熱感が見られます")
        elif fgi > 55: a1_parts.append(f"Fear & Greed Index is {fmt_num(fgi, 0)}, reflecting optimistic sentiment" if is_en else f"Fear & Greed Index が {fmt_num(fgi, 0)} と楽観寄りのセンチメントです")
        else: a1_parts.append(f"Fear & Greed Index is {fmt_num(fgi, 0)}, broadly neutral" if is_en else f"Fear & Greed Index が {fmt_num(fgi, 0)} で中立的なセンチメントです")
    if rsi is not None:
        if rsi < 30: a1_parts.append(f"BTC RSI is {fmt_num(rsi, 1)}, in oversold territory" if is_en else f"BTC RSI が {fmt_num(rsi, 1)} と売られ過ぎ水準")
        elif rsi > 70: a1_parts.append(f"BTC RSI is {fmt_num(rsi, 1)}, in overbought territory" if is_en else f"BTC RSI が {fmt_num(rsi, 1)} と買われ過ぎ水準")
        else: a1_parts.append(f"BTC RSI is {fmt_num(rsi, 1)}" if is_en else f"BTC RSI は {fmt_num(rsi, 1)}")
    if mad is not None:
        if mad < -5: a1_parts.append(f"Price is {fmt_num(mad, 1)}% below the moving average" if is_en else f"移動平均との距離が {fmt_num(mad, 1)}% と大きく下方乖離しています")
        elif mad > 5: a1_parts.append(f"Price is {fmt_num(mad, 1)}% above the moving average" if is_en else f"移動平均との距離が {fmt_num(mad, 1)}% と上方乖離しています")
    a1 = (", ".join(a1_parts) + ".") if (is_en and a1_parts) else ("、".join(a1_parts) + "。" if a1_parts else ("This is based on a composite reading of current market indicators." if is_en else "複数の市場指標を総合した結果です。"))
    a1 += " This is a data snapshot, not a guarantee of future price action." if is_en else "ただし、これは現時点のデータ分析であり、今後の値動きを保証するものではありません。"

    faq_items = [
        {"q": q1, "a": a1},
        {"q": "What would signal a bullish reversal?" if is_en else "強気に転換する条件は？", "a": (f"FGI is currently low at {fmt_num(fgi, 0)}. A recovery above 45 plus RSI above 55 would suggest bullish reversal. Rising BTC volume would strengthen the signal." if (is_en and fgi is not None and fgi < 40) else (f"RSI is currently {fmt_num(rsi, 1)}. A breakout above 55 can indicate improving short-term momentum. Also watch whether MA distance turns positive." if (is_en and rsi is not None and rsi < 45) else ("A sustained bullish setup is more likely when FGI holds above 55, RSI remains above 55, and MA distance keeps expanding positive. Avoid relying on a single indicator." if is_en else (f"現在 FGI が {fmt_num(fgi, 0)} と低水準ですが、45以上に回復し、RSI が 55 を上回ると強気転換の兆候と見なせます。ただし BTC 出来高の増加も併せて確認することが重要です。" if (fgi is not None and fgi < 40) else (f"RSI が現在 {fmt_num(rsi, 1)} ですが、55 を上抜けると短期的なモメンタム改善のシグナルです。MA距離がプラスに転じるかも併せて注目してください。" if (rsi is not None and rsi < 45) else "FGI 55以上の維持 + RSI 55超え + MA距離のプラス拡大が揃うと、持続的な強気トレンドと見なしやすくなります。単一指標だけでの判断は避けてください。")))) )},
        {"q": "What should I watch in a bearish phase?" if is_en else "弱気になった場合、何を見るべき？", "a": (f"FGI is already at an extreme fear level ({fmt_num(fgi, 0)}). For further downside risk, watch for panic-volume spikes and MA distance expanding beyond -10%. Extreme readings can also become rebound zones historically." if (is_en and fgi is not None and fgi < 25) else ("Bearish acceleration is more likely if FGI drops below 25, RSI breaks below 30, and MA distance expands past -8%. Treat sharp volume spikes as added risk." if is_en else (f"FGI が既に {fmt_num(fgi, 0)} と極端な恐怖状態にあるため、さらなる下落には出来高の急増（パニック売り）やMA距離 -10%超えの拡大を注視してください。逆に、こうした極端な水準は歴史的に反発の起点になることもあります。" if (fgi is not None and fgi < 25) else "FGI 25以下への悪化、RSI 30割れ、MA距離の -8%超え拡大が弱気加速のシグナルです。特に出来高の急増を伴う場合は警戒が必要です。")) )},
        {"q": "Is this AI judgment investment advice?" if is_en else "このAI判断は投資助言ですか？", "a": "No. CoinRader is an informational dashboard based on public market data. Make trading decisions at your own discretion." if is_en else "いいえ。CoinRader は公開市場データをルールベースで分析した情報提供ダッシュボードです。売買判断はご自身の責任で行ってください。"},
    ]
    details = "".join([f"<details><summary>{escape_html(item['q'])}</summary><div class='a'>{escape_html(item['a'])}</div></details>" for item in faq_items])
    return f"<section class='card faq' style='margin-top:12px' aria-label='FAQ'><h2>{'FAQ' if is_en else 'よくある質問'}</h2>{details}</section>"

def build_faq_jsonld(faq_items: list) -> str:
    """FAQPage JSON-LD を生成（SERPs拡張用）。"""
    if not faq_items:
        return ""
    entities = []
    for item in faq_items:
        entities.append({
            "@type": "Question",
            "name": item["q"],
            "acceptedAnswer": {
                "@type": "Answer",
                "text": item["a"]
            }
        })
    obj = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": entities
    }
    return json.dumps(obj, ensure_ascii=False)


def _build_faq_items_for_jsonld(judge, fgi_value, btc_rsi, ma_dist) -> list:
    """動的FAQ Q&Aのリストを返す（HTML生成とJSON-LD生成で共用）。"""
    fgi = to_float(fgi_value)
    rsi = to_float(btc_rsi)
    mad = to_float(ma_dist)
    j = (judge or "").strip().upper()

    items = []
    direction = "下がった" if (j == "BEAR" or (mad is not None and mad < -3)) else "上がった" if (j == "BULL" or (mad is not None and mad > 3)) else "このような状況"

    q1 = f"今日はなぜ{direction}のですか？"
    a1_parts = []
    if fgi is not None:
        if fgi < 25:
            a1_parts.append(f"Fear & Greed Index が {fmt_num(fgi, 0)} と極度の悲観状態")
        elif fgi < 45:
            a1_parts.append(f"Fear & Greed Index が {fmt_num(fgi, 0)} と弱気寄り")
        elif fgi > 75:
            a1_parts.append(f"Fear & Greed Index が {fmt_num(fgi, 0)} と過熱状態")
        elif fgi > 55:
            a1_parts.append(f"Fear & Greed Index が {fmt_num(fgi, 0)} と楽観寄り")
        else:
            a1_parts.append(f"Fear & Greed Index が {fmt_num(fgi, 0)} で中立的")
    if rsi is not None:
        a1_parts.append(f"BTC RSI が {fmt_num(rsi, 1)}")
    a1 = "、".join(a1_parts) + "。" if a1_parts else "複数の市場指標を総合した結果です。"
    items.append({"q": q1, "a": a1})

    items.append({"q": "強気に転換する条件は？", "a": "FGI 45以上 + RSI 55超え + MA距離のプラス転換が揃うと強気トレンドの兆候です。"})
    items.append({"q": "弱気になった場合、何を見るべき？", "a": "FGI 25以下、RSI 30割れ、MA距離 -8%超えが弱気加速のシグナルです。出来高の急増も注視してください。"})
    items.append({"q": "このAI判断は投資助言ですか？", "a": "いいえ。CoinRader は情報提供ダッシュボードであり、投資助言ではありません。"})

    return items


# ---------- A-3: 辞書リンク (dictionary/) ----------

def _list_existing_dict_slugs(dict_dir: str = "dictionary") -> set:
    """Return set of existing dictionary slugs under /dictionary/."""
    slugs = set()
    if not os.path.isdir(dict_dir):
        return slugs
    for name in os.listdir(dict_dir):
        p = os.path.join(dict_dir, name)
        if os.path.isdir(p) and os.path.isfile(os.path.join(p, "index.html")):
            slugs.add(name)
    return slugs


# 指標 → 辞書slug のマッピング（日次レポートで言及する用語）
TERM_TO_DICT_SLUG = {
    "RSI": "rsi",
    "相対力指数": "rsi",
    "Fear & Greed": "fear-greed-index",
    "恐怖指数": "fear-greed-index",
    "FGI": "fear-greed-index",
    "移動平均": "moving-average",
    "MA": "moving-average",
    "ボリンジャーバンド": "bollinger-bands",
    "時価総額": "market-cap",
    "ドミナンス": "dominance",
    "BTC Dominance": "dominance",
    "Market Cap": "market-cap",
    "Volatility": "volatility",
    "Volume": "volume",
    "ボラティリティ": "volatility",
    "出来高": "volume",
    "ATH": "ath",
    "サポートライン": "support-resistance",
    "レジスタンスライン": "support-resistance",
    "MACD": "macd",
    "半減期": "halving",
}


def build_dictionary_links_html(dict_dir: str = "dictionary", lang: str = "ja") -> str:
    """日次レポートに関連する用語の辞書リンクを生成（存在するslugのみ）。"""
    is_en = (lang == "en")
    existing = _list_existing_dict_slugs(dict_dir)
    if not existing:
        return ""

    priority_terms = ["RSI", "Fear & Greed", "MA", "Market Cap", "BTC Dominance", "Volume", "Volatility"] if is_en else ["RSI", "Fear & Greed", "移動平均", "時価総額", "ドミナンス", "出来高", "ボラティリティ"]
    shown = set()
    chips = []

    for term in priority_terms:
        slug = TERM_TO_DICT_SLUG.get(term, "")
        if slug and slug in existing and slug not in shown:
            shown.add(slug)
            chips.append(f"<a class='chip chip-dict' href='/{'en/' if is_en else ''}dictionary/{slug}/'>{escape_html(term)}</a>")
        if len(chips) >= 5:
            break

    # 残りの用語も(5つまで)
    for term, slug in TERM_TO_DICT_SLUG.items():
        if slug in existing and slug not in shown:
            shown.add(slug)
            chips.append(f"<a class='chip chip-dict' href='/{'en/' if is_en else ''}dictionary/{slug}/'>{escape_html(term)}</a>")
        if len(chips) >= 5:
            break

    if not chips:
        return ""

    return (
        "<section class='card dict-links' style='margin-top:12px' aria-label='Related terms'>"
        f"<div class='badge'>{'Key Terms' if is_en else '今日学ぶべき用語'}</div>"
        "<div style='height:8px'></div>"
        "<div class='dict-chips'>" + "".join(chips) + "</div>"
        f"<div class='dict-note'>{'Learn more about the indicators used in this report' if is_en else 'レポートで使用している指標の詳細解説はこちら'}</div>"
        "</section>"
    )


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
    OUT_DIR_EN.mkdir(parents=True, exist_ok=True)
  
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

        sent = fmt_num(fgi_value, 0)
        sent = sent if sent != "" else "—"

        rsi_num = fmt_num(btc_rsi, 1)          # RSIは小数1桁
        rsi = rsi_num if rsi_num != "" else "—"

        trend_num = fmt_num(ma_dist, 1)        # Trendは小数1桁
        trend = (trend_num + "%") if trend_num != "" else "—"   # %を明示

        seo_meta = build_seo_meta(date_iso, ymd, judge, sent, rsi, trend, trending, top_gainer=top_gainer)

        jsonld = build_jsonld(
            seo_meta.get("CANONICAL",""),
            seo_meta.get("TITLE",""),
            seo_meta.get("DESCRIPTION",""),
            date_iso,
            str(updated_at),
        )

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
        similar_days_html = build_similar_days_html(it, items, limit=5)
        why_html = build_reason_html(payload, judge, lang='ja')
        takeaways_html = build_takeaways_html(payload, judge, sent, rsi, trend, trending, top_gainer, lang='ja')
        coin_hubs_html = build_coin_hub_links_html(SITE_ORIGIN, trending, top_gainer)

        # ★ Phase 2: 新機能HTML生成
        fgi_raw = it.get("fgi_value", "")
        rsi_raw = it.get("btc_rsi", "")
        mad_raw = it.get("ma_dist", "")

        # BTC 24h change (for Score)
        btc_24h_chg = None
        raw_data = payload.get("raw_data", [])
        if isinstance(raw_data, list):
            btc_entry = next((c for c in raw_data if c.get("id") == "bitcoin"), None)
            if btc_entry:
                btc_24h_chg = btc_entry.get("price_change_percentage_24h")

        scenarios_html = build_scenarios_html(fgi_raw, rsi_raw, mad_raw, judge, lang='ja')
        score_data = compute_coinrader_score(fgi_raw, rsi_raw, mad_raw, btc_24h_chg)
        score_html = build_score_html(score_data, lang='ja')
        dynamic_faq_html = build_dynamic_faq_html(judge, fgi_raw, rsi_raw, mad_raw, lang='ja')
        dict_links_html = build_dictionary_links_html(lang='ja')
        en_why_html = build_reason_html(payload, judge, lang='en')
        en_takeaways_html = build_takeaways_html(payload, judge, sent, rsi, trend, trending, top_gainer, lang='en')
        en_scenarios_html = build_scenarios_html(fgi_raw, rsi_raw, mad_raw, judge, lang='en')
        en_score_html = build_score_html(score_data, lang='en')
        en_dynamic_faq_html = build_dynamic_faq_html(judge, fgi_raw, rsi_raw, mad_raw, lang='en')
        en_dict_links_html = build_dictionary_links_html(lang='en')

        # FAQ JSON-LD
        faq_items = _build_faq_items_for_jsonld(judge, fgi_raw, rsi_raw, mad_raw)
        faq_jsonld = build_faq_jsonld(faq_items)

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
            "{{SIMILAR_DAYS_HTML}}": similar_days_html,
            "{{SIMILAR_DAYS}}": similar_days_html,
            # Phase 2 placeholders
            "{{SCENARIOS_HTML}}": scenarios_html,
            "{{SCORE_HTML}}": score_html,
            "{{FAQ_HTML}}": dynamic_faq_html,
            "{{DICT_LINKS_HTML}}": dict_links_html,
            "{{FAQ_JSONLD}}": faq_jsonld,
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
              
        # Similar Days: テンプレにプレースホルダが無い場合は FAQ の直前に差し込む
        if similar_days_html and ("{{SIMILAR_DAYS" not in tmpl):
            if "<!-- FAQ -->" in html:
                html = html.replace("<!-- FAQ -->", similar_days_html + "\n\n    <!-- FAQ -->", 1)
            elif re.search(r'<section class="card faq"', html):
                html = re.sub(r'(<section class="card faq")', similar_days_html + r"\n\n    \1", html, count=1)

                
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
      
        seo_meta_en = build_seo_meta_en(date_iso, ymd, judge, sent, rsi, trend, trending, top_gainer=top_gainer)
        en_title = seo_meta_en["TITLE"]
        en_desc = seo_meta_en["DESCRIPTION"]
        en_h1 = f"BTC Daily AI Analysis ({date_iso})"
        en_jsonld = build_jsonld_en(seo_meta_en["CANONICAL"], en_title, en_desc, date_iso, str(updated_at))
        en_faq_jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": "Is this investment advice?", "acceptedAnswer": {"@type": "Answer", "text": "No. CoinRader provides informational analytics only."}},
                {"@type": "Question", "name": "How often is this updated?", "acceptedAnswer": {"@type": "Answer", "text": "Updated daily (JST)."}},
                {"@type": "Question", "name": "How should I use RSI and Fear & Greed?", "acceptedAnswer": {"@type": "Answer", "text": "Use these as reference indicators with trend and broader market context."}},
            ]
        }, ensure_ascii=False)
        en_html = localize_daily_html_en(
            html,
            canonical=canonical,
            ja_url=f"{SITE_ORIGIN}/daily/{ymd}",
            en_title=en_title,
            en_desc=en_desc,
            en_h1=en_h1,
            en_jsonld=en_jsonld,
            en_faq_jsonld=en_faq_jsonld,
        )
        en_html = re.sub(
            r'<div class="why">.*?</div>\s*</section>',
            f'<div class="why">{en_why_html}</div>\n      </section>',
            en_html,
            count=1,
            flags=re.DOTALL,
        )
        en_html = re.sub(r"<section class='takeaways'.*?</section>", en_takeaways_html, en_html, count=1, flags=re.DOTALL)
        en_html = re.sub(r"<section class='card scenarios'.*?</section>", en_scenarios_html, en_html, count=1, flags=re.DOTALL)
        en_html = re.sub(r"<section class='card score-card'.*?</section>", en_score_html, en_html, count=1, flags=re.DOTALL)
        en_html = re.sub(r"<section class='card faq'.*?</section>", en_dynamic_faq_html, en_html, count=1, flags=re.DOTALL)
        en_html = re.sub(r"<section class='card dict-links'.*?</section>", en_dict_links_html, en_html, count=1, flags=re.DOTALL)
        write_text(OUT_DIR_EN / f"{ymd}.html", en_html)


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

    en_index_html = index_html
    en_index_html = re.sub(r'<html\s+lang="ja">', '<html lang="en">', en_index_html, count=1)
    en_index_html = en_index_html.replace('href="/daily/', 'href="/en/daily/')
    en_index_html = en_index_html.replace("href='/daily/", "href='/en/daily/")
    en_index_html = en_index_html.replace('<a href="/">CoinRader</a> / Daily', '<a href="/en/">CoinRader</a> / Daily')
    en_index_html = re.sub(r'<link\s+rel="canonical"\s+href="[^"]*"\s*/?>', f'<link rel="canonical" href="{SITE_ORIGIN}/en/daily/" />', en_index_html, count=1)
    en_index_html = en_index_html.replace('CoinRaderの日次AIレポート一覧。最新日から過去へ遡って閲覧できます。', 'Browse CoinRader daily AI reports from the latest date backward.')
    en_index_html = en_index_html.replace('<title>Daily AIレポート一覧 | CoinRader</title>', '<title>Daily AI Reports | CoinRader</title>')
    en_index_html = en_index_html.replace('<h1>Daily AIレポート一覧</h1>', '<h1>Daily AI Reports</h1>')
    en_index_html = en_index_html.replace('最新: <a href="/en/daily/latest">latest</a>', 'Latest: <a href="/en/daily/latest">latest</a>')
    en_index_html = en_index_html.replace('注目 ', 'Trending ')
    en_index_html = en_index_html.replace('上昇 ', 'Gainer ')
    en_index_html = en_index_html.replace('注目トレンドは ', 'Trending: ')
    en_index_html = en_index_html.replace('BTC RSI が ', 'BTC RSI is ')
    en_index_html = en_index_html.replace(' で売られ過ぎ水準。', ', in oversold territory.')
    en_index_html = en_index_html.replace('上昇トップは ', 'Top gainer is ')
    en_index_html = en_index_html.replace(' で強い動き。', ', showing strong momentum.')
    en_index_html = en_index_html.replace('最新日から過去へ。日付別にAI判定と指標（FGI / RSI / Trend）を確認できます。', 'Browse from latest to oldest. Check AI judgment and indicators (FGI / RSI / Trend) by date.')
    en_index_html = en_index_html.replace('毎日のAI判定と主要指標（FGI/RSI/Trend）を一覧で比較できます。気になる日の<strong>要約</strong>を見て、詳細ページへ。', 'Compare daily AI judgments and key indicators (FGI/RSI/Trend) at a glance. Review summaries and open detail pages.')
    en_index_html = en_index_html.replace('客観的な暗号資産分析ダッシュボード', 'Objective crypto analytics dashboard')
    en_index_html = en_index_html.replace('CoinRader ホーム', 'CoinRader Home')
    en_index_html = en_index_html.replace('主要リンク', 'Primary links')
    en_index_html = en_index_html.replace('活用ガイド', 'Guide')
    en_index_html = en_index_html.replace('始め方', 'Getting Started')
    en_index_html = en_index_html.replace('データ', 'Data')
    en_index_html = en_index_html.replace('運営', 'About')
    en_index_html = en_index_html.replace('連絡', 'Contact')
    en_index_html = en_index_html.replace('免責', 'Disclaimer')
    en_index_html = en_index_html.replace('法務', 'Legal')
    en_index_html = en_index_html.replace(' 件', ' results')
    en_index_html = en_index_html.replace('一覧', 'All')
    en_index_html = en_index_html.replace('検索：日付 / 注目銘柄 / 上昇銘柄 / 要約 など', 'Search: date / hot coins / top gainers / summary ...')
    en_index_html = en_index_html.replace('毎日のAI判定と主要指標（FGI/RSI/Trend）を一覧で比較できます。気になる日の<strong>要約</strong>を見て、詳細ページへ。', 'Compare daily AI judgments and key indicators (FGI/RSI/Trend) at a glance. Review summaries and open detail pages.')
    en_index_html = en_index_html.replace('毎日のAI判定と主要指標（FGI/RSI/Trend）を一覧で比較できます.気になる日の<strong>要約</strong>を見て、詳細ページへ.', 'Compare daily AI judgments and key indicators (FGI/RSI/Trend) at a glance. Review summaries and open detail pages.')
    en_index_html = re.sub(r'MA距離が\s*([^\s<]+)\s*で弱含み。', r'MA distance is \1, showing downside pressure.', en_index_html)
    en_index_html = re.sub(r'MA距離が\s*([^\s<]+)\s*で弱含み\.', r'MA distance is \1, showing downside pressure.', en_index_html)
    en_index_html = normalize_i18n_for_en_html(en_index_html)
    write_text(OUT_DIR_EN / "index.html", en_index_html)


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

        en_tag_html = tag_html
        en_tag_html = re.sub(r'<html\s+lang="ja">', '<html lang="en">', en_tag_html, count=1)
        en_tag_html = en_tag_html.replace('href="/daily/', 'href="/en/daily/')
        en_tag_html = en_tag_html.replace("href='/daily/", "href='/en/daily/")
        en_tag_html = en_tag_html.replace('<a href="/">CoinRader</a> / Daily', '<a href="/en/">CoinRader</a> / Daily')
        en_tag_html = re.sub(r'<link\s+rel="canonical"\s+href="[^"]*"\s*/?>', f'<link rel="canonical" href="{SITE_ORIGIN}/en/daily/tags/{tag_lower}" />', en_tag_html, count=1)
        en_tag_desc_map = {
            "bear": "List of days where the AI judgment is BEAR.",
            "bull": "List of days where the AI judgment is BULL.",
            "wait": "List of days where the AI judgment is WAIT.",
        }
        en_tag_html = re.sub(r"<title>.*?</title>", f"<title>AI {judge_key} Days | CoinRader</title>", en_tag_html, flags=re.DOTALL)
        en_tag_html = re.sub(r'<meta\s+name="description"\s+content="[^"]*"\s*/?>', f'<meta name="description" content="{en_tag_desc_map.get(tag_lower, "Daily AI report list by judgment.")}" />', en_tag_html, count=1)
        en_tag_html = en_tag_html.replace(f'AI {judge_key} の日一覧', f'AI {judge_key} Days')
        en_tag_html = en_tag_html.replace('最新: <a href="/en/daily/latest">latest</a>', 'Latest: <a href="/en/daily/latest">latest</a>')
        en_tag_html = en_tag_html.replace('客観的な暗号資産分析ダッシュボード', 'Objective crypto analytics dashboard')
        en_tag_html = en_tag_html.replace('最新日から過去へ。日付別にAI判定と指標（FGI / RSI / Trend）を確認できます。', 'Browse from latest to oldest. Check AI judgment and indicators (FGI / RSI / Trend) by date.')
        en_tag_html = en_tag_html.replace('毎日のAI判定と主要指標（FGI/RSI/Trend）を一覧で比較できます。気になる日の<strong>要約</strong>を見て、詳細ページへ。', 'Compare daily AI judgments and key indicators (FGI/RSI/Trend) at a glance. Review summaries and open detail pages.')
        en_tag_html = en_tag_html.replace('注目 ', 'Trending ')
        en_tag_html = en_tag_html.replace('上昇 ', 'Gainer ')
        en_tag_html = en_tag_html.replace('注目トレンドは ', 'Trending: ')
        en_tag_html = en_tag_html.replace('BTC RSI が ', 'BTC RSI is ')
        en_tag_html = en_tag_html.replace(' で売られ過ぎ水準。', ', in oversold territory.')
        en_tag_html = en_tag_html.replace('上昇トップは ', 'Top gainer is ')
        en_tag_html = en_tag_html.replace(' で強い動き。', ', showing strong momentum.')
        en_tag_html = en_tag_html.replace('CoinRader ホーム', 'CoinRader Home')
        en_tag_html = en_tag_html.replace('主要リンク', 'Primary links')
        en_tag_html = en_tag_html.replace('活用ガイド', 'Guide')
        en_tag_html = en_tag_html.replace('始め方', 'Getting Started')
        en_tag_html = en_tag_html.replace('データ', 'Data')
        en_tag_html = en_tag_html.replace('運営', 'About')
        en_tag_html = en_tag_html.replace('連絡', 'Contact')
        en_tag_html = en_tag_html.replace('免責', 'Disclaimer')
        en_tag_html = en_tag_html.replace('法務', 'Legal')
        en_tag_html = en_tag_html.replace(' 件', ' results')
        en_tag_html = en_tag_html.replace('一覧', 'All')
        en_tag_html = en_tag_html.replace('検索：日付 / 注目銘柄 / 上昇銘柄 / 要約 など', 'Search: date / hot coins / top gainers / summary ...')
        en_tag_html = en_tag_html.replace('毎日のAI判定と主要指標（FGI/RSI/Trend）を一覧で比較できます。気になる日の<strong>要約</strong>を見て、詳細ページへ。', 'Compare daily AI judgments and key indicators (FGI/RSI/Trend) at a glance. Review summaries and open detail pages.')
        en_tag_html = en_tag_html.replace('毎日のAI判定と主要指標（FGI/RSI/Trend）を一覧で比較できます.気になる日の<strong>要約</strong>を見て、詳細ページへ.', 'Compare daily AI judgments and key indicators (FGI/RSI/Trend) at a glance. Review summaries and open detail pages.')
        en_tag_html = re.sub(r'MA距離が\s*([^\s<]+)\s*で弱含み。', r'MA distance is \1, showing downside pressure.', en_tag_html)
        en_tag_html = re.sub(r'MA距離が\s*([^\s<]+)\s*で弱含み\.', r'MA distance is \1, showing downside pressure.', en_tag_html)
        en_tag_html = normalize_i18n_for_en_html(en_tag_html)
      
        tag_jsonld_en = {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": f"AI {judge_key} Days (CoinRader)",
            "description": en_tag_desc_map.get(tag_lower, "Daily AI report list by judgment."),
            "url": f"{SITE_ORIGIN}/en/daily/tags/{tag_lower}",
            "mainEntity": {"@type": "ItemList", "itemListOrder": "https://schema.org/ItemListOrderDescending", "numberOfItems": len(filtered), "itemListElement": []},
            "publisher": {"@type": "Organization", "name": "CoinRader"},
        }
        en_tag_html = re.sub(r'<script type="application/ld\+json">\s*\{.*?\}\s*</script>', f'<script type="application/ld+json">{json.dumps(tag_jsonld_en, ensure_ascii=False)}</script>', en_tag_html, flags=re.DOTALL, count=1)
        write_text(OUT_DIR_EN / "tags" / f"{tag_lower}.html", en_tag_html)


    update_daily_latest_redirect(latest_ymd)
    latest_target = f"{latest_ymd}.html"
    latest_page_path = OUT_DIR / latest_target
    latest_page_html = read_text(latest_page_path)
    write_text(OUT_DIR / "latest.html", latest_page_html)

    # Also generate extensionless latest page for canonical (/daily/latest)
    write_text(OUT_DIR / "latest", latest_page_html)

    latest_page_html_en = read_text(OUT_DIR_EN / latest_target)
    write_text(OUT_DIR_EN / "latest.html", latest_page_html_en)
    write_text(OUT_DIR_EN / "latest", latest_page_html_en)
  
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
