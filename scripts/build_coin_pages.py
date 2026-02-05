#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
TEMPL_DIR = ROOT / "templates"
OUT_COINS_DIR = ROOT / "coins"
SITE_ORIGIN = "https://coinrader.net"  # 必要なら env 化してください


# ---- basic file helpers ----
def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def escape_xml(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")


# ---- sitemap helpers (prefix-block rewrite) ----
def build_coin_sitemap_entries(site_origin: str, coins: List[Dict[str, str]]) -> List[Dict[str, str]]:
    # coins/ は一覧の導線として入れる
    entries: List[Dict[str, str]] = [
        {"loc": f"{site_origin}/coins/", "lastmod": "", "changefreq": "daily", "priority": "0.8"}
    ]
    for c in coins:
        entries.append({
            "loc": f"{site_origin}/coins/{c['symbol']}/",
            "lastmod": "",
            "changefreq": "daily",
            "priority": "0.9"
        })
    return entries


def rewrite_sitemap_with_prefix_block(sitemap_path: Path, prefix: str, entries: List[Dict[str, str]]) -> None:
    """
    sitemap.xml 内の「prefix配下の <url>...</url>」を全削除して、
    entries（リッチ形式）を末尾にまとめて追加する。
    prefix 例: "/coins/" or "/daily/"
    """
    if not entries:
        return

    def url_xml(e: Dict[str, str]) -> str:
        loc = escape_xml(str(e.get("loc", "")).strip())
        if not loc:
            return ""
        parts = ["  <url>", f"    <loc>{loc}</loc>"]
        if e.get("lastmod"):
            parts.append(f"    <lastmod>{escape_xml(e['lastmod'])}</lastmod>")
        if e.get("changefreq"):
            parts.append(f"    <changefreq>{escape_xml(e['changefreq'])}</changefreq>")
        if e.get("priority"):
            parts.append(f"    <priority>{escape_xml(e['priority'])}</priority>")
        parts.append("  </url>")
        return "\n".join(parts)

    block_xml = "\n".join([x for x in (url_xml(e) for e in entries) if x]) + "\n"

    header = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    footer = "</urlset>\n"

    if not sitemap_path.exists():
        write_text(sitemap_path, header + block_xml + footer)
        return

    xml = read_text(sitemap_path)
    if "<urlset" not in xml:
        write_text(sitemap_path, header + block_xml + footer)
        return

    # prefix配下のURLを持つ <url>...</url> を除去
    # 例: https://coinrader.net/coins/...
    prefix_esc = re.escape(prefix.strip("/"))
    pattern = rf"\s*<url>\s*(?:<[^>]+>\s*)*?<loc>\s*https?://[^<]*/{prefix_esc}/[^<]*\s*</loc>[\s\S]*?</url>\s*"
    xml_no = re.sub(pattern, "\n", xml, flags=re.IGNORECASE)

    # 連続空行を整理
    xml_no = re.sub(r"\n{3,}", "\n\n", xml_no)

    if "</urlset>" in xml_no:
        out = re.sub(r"</urlset>\s*$", block_xml + "</urlset>\n", xml_no, flags=re.IGNORECASE)
    else:
        out = xml_no.rstrip() + "\n" + block_xml

    write_text(sitemap_path, out)


# ---- page build ----
COINS = [
    {"symbol": "btc", "coin_id": "bitcoin",  "name": "Bitcoin"},
    {"symbol": "eth", "coin_id": "ethereum", "name": "Ethereum"},
    {"symbol": "sol", "coin_id": "solana",   "name": "Solana"},
    {"symbol": "xrp", "coin_id": "ripple",   "name": "XRP"},
]


def render_coin_page(tmpl: str, c: Dict[str, str]) -> str:
    s = tmpl
    s = s.replace("{{SYMBOL}}", c["symbol"])
    s = s.replace("{{SYMBOL_UPPER}}", c["symbol"].upper())
    s = s.replace("{{COIN_ID}}", c["coin_id"])
    s = s.replace("{{NAME}}", c["name"])
    return s


def build_coins_index(site_origin: str, coins: List[Dict[str, str]]) -> str:
    rows = []
    for c in coins:
        rows.append(
            f"<li><a href='/coins/{c['symbol']}/'>{c['name']} ({c['symbol'].upper()})</a></li>"
        )

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Coins | CoinRader</title>
  <meta name="description" content="主要暗号資産の銘柄別ページ一覧。価格・変動・出来高・時価総額などをまとめて確認。" />
  <link rel="canonical" href="{site_origin}/coins/" />
  <style>
    :root {{ color-scheme: dark; }}
    body {{ margin:0; font-family: system-ui,-apple-system,Segoe UI,Roboto,Helvetica Neue,Arial; background:#0f172a; color:#e5e7eb; }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 20px 16px 40px; }}
    a {{ color:#7dd3fc; text-decoration:none; }}
    a:hover {{ text-decoration: underline; }}
    .h1 {{ font-size: 22px; font-weight: 800; margin: 10px 0 6px; }}
    .muted {{ color:#94a3b8; }}
    ul {{ line-height:1.9; }}
    .btn {{ display:inline-flex; padding: 10px 12px; border-radius: 12px; background: rgba(255,255,255,0.06); border:1px solid rgba(148,163,184,0.18); color:#e5e7eb; font-size: 13px; }}
    .btn:hover {{ background: rgba(255,255,255,0.10); text-decoration:none; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="muted"><a href="/">トップ</a> / <span class="muted">Coins</span></div>
    <h1 class="h1">Coins</h1>
    <div class="muted">銘柄別の主要指標と今日の市況メモ。</div>
    <div style="margin-top:12px;">
      <a class="btn" href="/daily/latest.html">全体の最新まとめ</a>
    </div>
    <div style="margin-top:14px;">
      <ul>
        {''.join(rows)}
      </ul>
    </div>
  </div>
</body>
</html>
"""


def main() -> None:
    tmpl = read_text(TEMPL_DIR / "coin_template.html")

    # coins/index.html
    write_text(OUT_COINS_DIR / "index.html", build_coins_index(SITE_ORIGIN, COINS))

    # coins/{symbol}/index.html
    for c in COINS:
        html = render_coin_page(tmpl, c)
        write_text(OUT_COINS_DIR / c["symbol"] / "index.html", html)

    # sitemap: /coins/ ブロックを統一追記
    sitemap_path = ROOT / "sitemap.xml"
    coin_entries = build_coin_sitemap_entries(SITE_ORIGIN, COINS)
    rewrite_sitemap_with_prefix_block(sitemap_path, "/coins", coin_entries)

    print(f"[OK] Generated coins pages into: {OUT_COINS_DIR} (count={len(COINS)})")


if __name__ == "__main__":
    main()
