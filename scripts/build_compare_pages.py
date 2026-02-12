#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CoinRader: 銘柄比較ページの自動生成

上位銘柄同士の比較ページを自動的に生成する。
SEOのロングテールキーワード「Bitcoin vs Ethereum 比較」等を狙う。

生成物:
  - compare/index.html  (比較一覧ページ)
  - compare/<slug-a>-vs-<slug-b>/index.html  (各比較ページ)

使い方:
  python scripts/build_compare_pages.py
"""

from __future__ import annotations

import os
import html as html_mod
from pathlib import Path
from itertools import combinations

ROOT = Path(__file__).resolve().parents[1]
TEMPL_DIR = ROOT / "templates"
OUT_COMPARE_DIR = ROOT / "compare"
SITE_ORIGIN = os.environ.get("CR_SITE_ORIGIN", "https://coinrader.net").rstrip("/")

# 比較ページを生成する対象銘柄（上位の注目度が高い銘柄のみ）
# 全50の組合せは 50C2=1225 になり多すぎるため、上位20銘柄に絞る (20C2=190)
TOP_COINS_FOR_COMPARE = [
    {"slug": "bitcoin",      "symbol": "btc",  "coin_id": "bitcoin",            "name": "Bitcoin"},
    {"slug": "ethereum",     "symbol": "eth",  "coin_id": "ethereum",           "name": "Ethereum"},
    {"slug": "xrp",          "symbol": "xrp",  "coin_id": "ripple",             "name": "XRP"},
    {"slug": "bnb",          "symbol": "bnb",  "coin_id": "binancecoin",        "name": "BNB"},
    {"slug": "solana",       "symbol": "sol",  "coin_id": "solana",             "name": "Solana"},
    {"slug": "dogecoin",     "symbol": "doge", "coin_id": "dogecoin",           "name": "Dogecoin"},
    {"slug": "cardano",      "symbol": "ada",  "coin_id": "cardano",            "name": "Cardano"},
    {"slug": "tron",         "symbol": "trx",  "coin_id": "tron",               "name": "TRON"},
    {"slug": "avalanche",    "symbol": "avax", "coin_id": "avalanche-2",        "name": "Avalanche"},
    {"slug": "chainlink",    "symbol": "link", "coin_id": "chainlink",          "name": "Chainlink"},
    {"slug": "polkadot",     "symbol": "dot",  "coin_id": "polkadot",           "name": "Polkadot"},
    {"slug": "bitcoin-cash", "symbol": "bch",  "coin_id": "bitcoin-cash",       "name": "Bitcoin Cash"},
    {"slug": "litecoin",     "symbol": "ltc",  "coin_id": "litecoin",           "name": "Litecoin"},
    {"slug": "near",         "symbol": "near", "coin_id": "near",               "name": "NEAR Protocol"},
    {"slug": "shiba-inu",    "symbol": "shib", "coin_id": "shiba-inu",          "name": "Shiba Inu"},
    {"slug": "uniswap",      "symbol": "uni",  "coin_id": "uniswap",            "name": "Uniswap"},
    {"slug": "sui",          "symbol": "sui",  "coin_id": "sui",                "name": "Sui"},
    {"slug": "stellar",      "symbol": "xlm",  "coin_id": "stellar",            "name": "Stellar"},
    {"slug": "hedera",       "symbol": "hbar", "coin_id": "hedera-hashgraph",   "name": "Hedera"},
    {"slug": "aptos",        "symbol": "apt",  "coin_id": "aptos",              "name": "Aptos"},
]



def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")

def esc(s: str) -> str:
    return html_mod.escape(s, quote=True)


# --------------- Generate Pairs ---------------

def generate_pairs() -> list[tuple[dict, dict]]:
    """上位銘柄の全ペア（順序固定: 時価総額順が先）"""
    return list(combinations(TOP_COINS_FOR_COMPARE, 2))


def pair_slug(a: dict, b: dict) -> str:
    return f"{a['slug']}-vs-{b['slug']}"


# --------------- Other Compares ---------------

def build_other_compares_html(current_pair_slug: str, all_pairs: list[tuple[dict, dict]], limit: int = 6) -> str:
    """現在のペア以外の比較リンクを生成"""
    chips = []
    for a, b in all_pairs:
        ps = pair_slug(a, b)
        if ps == current_pair_slug:
            continue
        chips.append(
            f'<a class="chip" href="/compare/{ps}/">'
            f'{esc(a["name"])} vs {esc(b["name"])}</a>'
        )
        if len(chips) >= limit:
            break
    return "\n    ".join(chips)


# --------------- Compare Page ---------------

def render_compare_page(tmpl: str, a: dict, b: dict, all_pairs: list[tuple[dict, dict]]) -> str:
    ps = pair_slug(a, b)
    s = tmpl
    s = s.replace("{{NAME_A}}", a["name"])
    s = s.replace("{{NAME_B}}", b["name"])
    s = s.replace("{{SYM_A}}", a["symbol"].upper())
    s = s.replace("{{SYM_B}}", b["symbol"].upper())
    s = s.replace("{{SLUG_A}}", a["slug"])
    s = s.replace("{{SLUG_B}}", b["slug"])
    s = s.replace("{{SYMBOL_A}}", a["symbol"])
    s = s.replace("{{SYMBOL_B}}", b["symbol"])
    s = s.replace("{{OTHER_COMPARES_HTML}}", build_other_compares_html(ps, all_pairs))
    return s


# --------------- Index Page ---------------

def build_compare_index(all_pairs: list[tuple[dict, dict]]) -> str:
    cards = []
    for a, b in all_pairs:
        ps = pair_slug(a, b)
        cards.append(
            f'      <a href="/compare/{ps}/" class="cmp-card">'
            f'<span class="cmp-a">{esc(a["name"])}</span>'
            f'<span class="cmp-vs">VS</span>'
            f'<span class="cmp-b">{esc(b["name"])}</span></a>'
        )
    items_html = "\n".join(cards)
    count = len(all_pairs)

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>暗号資産 比較ページ一覧 ({count}ペア) | CoinRader</title>
  <meta name="description" content="主要暗号資産の比較ページ一覧。Bitcoin vs Ethereum、Solana vs Cardano など{count}ペアの価格・時価総額を比較。CoinRader。" />
  <meta name="robots" content="index, follow" />
  <link rel="canonical" href="{SITE_ORIGIN}/compare/" />
  <meta property="og:locale" content="ja_JP" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="CoinRader" />
  <meta property="og:title" content="暗号資産 比較一覧 | CoinRader" />
  <meta property="og:description" content="主要暗号資産{count}ペアの比較。価格・時価総額・変動率を並べて確認。" />
  <meta property="og:url" content="{SITE_ORIGIN}/compare/" />
  <meta property="og:image" content="{SITE_ORIGIN}/assets/og/ogp_v2.png" />
  <meta name="twitter:card" content="summary_large_image" />
  <link href="/assets/icons/favicon.ico" rel="icon" />
  <link href="/assets/icons/apple-touch-icon.png" rel="apple-touch-icon" sizes="180x180" />
  <meta name="theme-color" content="#0f172a" />
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-TDEBXC7DH6"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', 'G-TDEBXC7DH6');
  </script>
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
      {{"@type": "ListItem", "position": 1, "name": "CoinRader", "item": "{SITE_ORIGIN}/"}},
      {{"@type": "ListItem", "position": 2, "name": "Compare"}}
    ]
  }}
  </script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" referrerpolicy="no-referrer" />
  <style>
    :root {{ color-scheme: dark; --accent: #38bdf8; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica Neue,Arial,sans-serif; background:#0f172a; color:#e5e7eb; }}
    a {{ color:#7dd3fc; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .container {{ max-width:1100px; margin:0 auto; padding:18px; }}
    .pageHeader {{
      display:flex; align-items:center; justify-content:space-between;
      padding:12px 16px; border:1px solid rgba(255,255,255,.1);
      border-radius:14px; background:rgba(255,255,255,.02);
      margin:0 0 18px; gap:12px;
    }}
    .brandLogo {{ height:36px; width:auto; }}
    .headerNav {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }}
    .headerNav a {{
      display:inline-flex; align-items:center; gap:8px;
      color:#cbd5e1; text-decoration:none !important;
      font-size:12px; font-weight:700;
      padding:8px 10px; border-radius:10px;
      border:1px solid rgba(255,255,255,.08); background:rgba(255,255,255,.02);
      transition: transform .15s, border-color .15s; white-space:nowrap;
    }}
    .headerNav a:hover {{ transform:translateY(-1px); border-color:rgba(56,189,248,.35); }}
    .breadcrumb {{ font-size:13px; color:#94a3b8; margin-bottom:8px; }}
    .breadcrumb a {{ color:#7dd3fc; }}
    h1 {{ font-size:22px; font-weight:800; margin:10px 0 6px; }}
    .sub {{ font-size:13px; color:#94a3b8; margin-bottom:18px; }}
    .cmp-grid {{
      display:grid; grid-template-columns:repeat(auto-fill, minmax(260px, 1fr)); gap:10px;
    }}
    .cmp-card {{
      display:flex; align-items:center; justify-content:center; gap:10px;
      background:#111827; border:1px solid rgba(148,163,184,.18);
      border-radius:12px; padding:14px 16px;
      text-decoration:none !important; color:#e5e7eb;
      transition: transform .15s, border-color .2s, box-shadow .2s;
    }}
    .cmp-card:hover {{
      transform:translateY(-2px); border-color:rgba(56,189,248,.4);
      box-shadow:0 8px 20px rgba(0,0,0,.3);
    }}
    .cmp-a, .cmp-b {{ font-size:14px; font-weight:700; }}
    .cmp-vs {{ font-size:11px; font-weight:800; color:#38bdf8; letter-spacing:1px; }}
    .site-footer {{
      background:rgba(10,16,28,0.4); border-top:1px solid rgba(255,255,255,0.05);
      padding:16px 12px; margin-top:40px; width:100%;
    }}
    .footer-inner {{
      max-width:1100px; margin:0 auto;
      display:flex; justify-content:space-between; align-items:center;
      flex-wrap:wrap; gap:15px;
    }}
    .footer-brand {{ display:flex; align-items:center; gap:10px; }}
    .footer-logo {{ height:36px !important; width:auto; opacity:.8; }}
    .footer-tagline {{ font-size:11px; color:#64748b; }}
    .footer-nav {{ display:flex; gap:12px; flex-wrap:wrap; }}
    .footer-nav a {{ color:#94a3b8; font-size:11.5px; text-decoration:none !important; }}
    .footer-nav a:hover {{ color:#38bdf8; }}
    .footer-copyright {{
      max-width:1100px; margin:10px auto 0; padding-top:8px;
      border-top:1px solid rgba(255,255,255,0.02);
      text-align:center; font-size:10px; color:#475569;
    }}
    @media (max-width:768px) {{
      .footer-inner {{ flex-direction:column; text-align:center; }}
      .footer-nav {{ justify-content:center; gap:8px 12px; }}
      .headerNav {{ justify-content:flex-end; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header class="pageHeader" role="banner">
      <a href="/" aria-label="CoinRader ホーム">
        <img class="brandLogo" src="/assets/icons/logo_horizontal_v4.png" alt="CoinRader" />
      </a>
      <nav class="headerNav" aria-label="ページメニュー">
        <a href="/"><i class="fa-solid fa-house"></i><span>ホーム</span></a>
        <a href="/coins/"><i class="fa-solid fa-coins"></i><span>Coins</span></a>
        <a href="/daily/latest"><i class="fa-solid fa-chart-line"></i><span>Daily</span></a>
      </nav>
    </header>

    <nav class="breadcrumb" aria-label="パンくずリスト">
      <a href="/">トップ</a> / <span>比較</span>
    </nav>

    <h1><i class="fa-solid fa-scale-balanced" style="color:#38bdf8;margin-right:8px;"></i>暗号資産 比較</h1>
    <div class="sub">主要{count}ペアの暗号資産を並べて比較。価格・時価総額・変動率を一目で確認できます。</div>

    <div class="cmp-grid">
{items_html}
    </div>
  </div>

  <footer class="site-footer">
    <div class="footer-inner">
      <div class="footer-brand">
        <img alt="CoinRader" class="footer-logo" src="/assets/icons/logo_horizontal_v4.png" />
        <span class="footer-tagline">客観的な暗号資産分析ダッシュボード</span>
      </div>
      <div class="footer-nav">
        <a href="/">ホーム</a><a href="/coins/">Coins</a><a href="/compare/">比較</a>
        <a href="/daily/latest">Daily</a><a href="/about">運営者情報</a>
      </div>
    </div>
    <div class="footer-copyright">&copy; 2026 CoinRader. All rights reserved. ｜ 本サイトは投資助言ではありません。</div>
  </footer>
</body>
</html>
"""


# --------------- Main ---------------

def main() -> None:
    tmpl_path = TEMPL_DIR / "compare_template.html"
    if not tmpl_path.exists():
        raise SystemExit(f"Missing template: {tmpl_path}")

    tmpl = read_text(tmpl_path)
    all_pairs = generate_pairs()

    # Index page
    write_text(OUT_COMPARE_DIR / "index.html", build_compare_index(all_pairs))

    # Compare pages
    for a, b in all_pairs:
        ps = pair_slug(a, b)
        html = render_compare_page(tmpl, a, b, all_pairs)
        write_text(OUT_COMPARE_DIR / ps / "index.html", html)

    print(f"[OK] Generated compare pages: {OUT_COMPARE_DIR} (pairs={len(all_pairs)})")

if __name__ == "__main__":
    main()
