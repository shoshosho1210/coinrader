#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CoinRader: Top 50 暗号資産のコインページを自動生成

生成物:
  - coins/index.html  (一覧ページ: カードUIグリッド)
  - coins/<slug>/index.html  (各銘柄ページ)

使い方:
  python scripts/build_coin_pages.py
"""

from __future__ import annotations

import os
import json
import html as html_mod
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPL_DIR = ROOT / "templates"
OUT_COINS_DIR = ROOT / "coins"
SITE_ORIGIN = os.environ.get("CR_SITE_ORIGIN", "https://coinrader.net").rstrip("/")

# Top 50 暗号資産（時価総額順ベース 2026-02）
# slug: URL用, symbol: 通貨ティッカー, coin_id: CoinGecko API ID, name: 正式名称
COINS = [
    {"slug": "bitcoin",         "symbol": "btc",   "coin_id": "bitcoin",            "name": "Bitcoin"},
    {"slug": "ethereum",        "symbol": "eth",   "coin_id": "ethereum",           "name": "Ethereum"},
    {"slug": "tether",          "symbol": "usdt",  "coin_id": "tether",             "name": "Tether"},
    {"slug": "xrp",             "symbol": "xrp",   "coin_id": "ripple",             "name": "XRP"},
    {"slug": "bnb",             "symbol": "bnb",   "coin_id": "binancecoin",        "name": "BNB"},
    {"slug": "solana",          "symbol": "sol",   "coin_id": "solana",             "name": "Solana"},
    {"slug": "usdc",            "symbol": "usdc",  "coin_id": "usd-coin",           "name": "USDC"},
    {"slug": "dogecoin",        "symbol": "doge",  "coin_id": "dogecoin",           "name": "Dogecoin"},
    {"slug": "cardano",         "symbol": "ada",   "coin_id": "cardano",            "name": "Cardano"},
    {"slug": "tron",            "symbol": "trx",   "coin_id": "tron",               "name": "TRON"},
    {"slug": "avalanche",       "symbol": "avax",  "coin_id": "avalanche-2",        "name": "Avalanche"},
    {"slug": "chainlink",       "symbol": "link",  "coin_id": "chainlink",          "name": "Chainlink"},
    {"slug": "shiba-inu",       "symbol": "shib",  "coin_id": "shiba-inu",          "name": "Shiba Inu"},
    {"slug": "sui",             "symbol": "sui",   "coin_id": "sui",                "name": "Sui"},
    {"slug": "stellar",         "symbol": "xlm",   "coin_id": "stellar",            "name": "Stellar"},
    {"slug": "polkadot",        "symbol": "dot",   "coin_id": "polkadot",           "name": "Polkadot"},
    {"slug": "bitcoin-cash",    "symbol": "bch",   "coin_id": "bitcoin-cash",       "name": "Bitcoin Cash"},
    {"slug": "hyperliquid",     "symbol": "hype",  "coin_id": "hyperliquid",        "name": "Hyperliquid"},
    {"slug": "uniswap",         "symbol": "uni",   "coin_id": "uniswap",            "name": "Uniswap"},
    {"slug": "litecoin",        "symbol": "ltc",   "coin_id": "litecoin",           "name": "Litecoin"},
    {"slug": "hedera",          "symbol": "hbar",  "coin_id": "hedera-hashgraph",   "name": "Hedera"},
    {"slug": "near",            "symbol": "near",  "coin_id": "near",               "name": "NEAR Protocol"},
    {"slug": "aptos",           "symbol": "apt",   "coin_id": "aptos",              "name": "Aptos"},
    {"slug": "pepe",            "symbol": "pepe",  "coin_id": "pepe",               "name": "Pepe"},
    {"slug": "internet-computer","symbol": "icp",  "coin_id": "internet-computer",  "name": "Internet Computer"},
    {"slug": "dai",             "symbol": "dai",   "coin_id": "dai",                "name": "Dai"},
    {"slug": "aave",            "symbol": "aave",  "coin_id": "aave",               "name": "Aave"},
    {"slug": "ethereum-classic","symbol": "etc",   "coin_id": "ethereum-classic",   "name": "Ethereum Classic"},
    {"slug": "polygon",         "symbol": "pol",   "coin_id": "matic-network",      "name": "Polygon"},
    {"slug": "render",          "symbol": "render","coin_id": "render-token",        "name": "Render"},
    {"slug": "cosmos",          "symbol": "atom",  "coin_id": "cosmos",             "name": "Cosmos"},
    {"slug": "filecoin",        "symbol": "fil",   "coin_id": "filecoin",           "name": "Filecoin"},
    {"slug": "arbitrum",        "symbol": "arb",   "coin_id": "arbitrum",           "name": "Arbitrum"},
    {"slug": "optimism",        "symbol": "op",    "coin_id": "optimism",           "name": "Optimism"},
    {"slug": "vechain",         "symbol": "vet",   "coin_id": "vechain",            "name": "VeChain"},
    {"slug": "injective",       "symbol": "inj",   "coin_id": "injective-protocol", "name": "Injective"},
    {"slug": "the-graph",       "symbol": "grt",   "coin_id": "the-graph",          "name": "The Graph"},
    {"slug": "fantom",          "symbol": "ftm",   "coin_id": "fantom",             "name": "Fantom"},
    {"slug": "algorand",        "symbol": "algo",  "coin_id": "algorand",           "name": "Algorand"},
    {"slug": "theta",           "symbol": "theta", "coin_id": "theta-token",        "name": "Theta Network"},
    {"slug": "maker",           "symbol": "mkr",   "coin_id": "maker",              "name": "Maker"},
    {"slug": "sei",             "symbol": "sei",   "coin_id": "sei-network",        "name": "Sei"},
    {"slug": "flow",            "symbol": "flow",  "coin_id": "flow",               "name": "Flow"},
    {"slug": "ondo",            "symbol": "ondo",  "coin_id": "ondo-finance",       "name": "Ondo Finance"},
    {"slug": "pyth",            "symbol": "pyth",  "coin_id": "pyth-network",       "name": "Pyth Network"},
    {"slug": "jupiter",         "symbol": "jup",   "coin_id": "jupiter-exchange-solana", "name": "Jupiter"},
    {"slug": "floki",           "symbol": "floki", "coin_id": "floki",              "name": "FLOKI"},
    {"slug": "worldcoin",       "symbol": "wld",   "coin_id": "worldcoin-wld",      "name": "Worldcoin"},
    {"slug": "bonk",            "symbol": "bonk",  "coin_id": "bonk",               "name": "Bonk"},
    {"slug": "stacks",          "symbol": "stx",   "coin_id": "blockstack",         "name": "Stacks"},
]


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")

def esc(s: str) -> str:
    """HTML entity escape."""
    return html_mod.escape(s, quote=True)


# --------------- Related Coins ---------------

def build_related_coins_html(current_slug: str, limit: int = 8) -> str:
    """現在のコインを除いた関連銘柄チップ HTML を生成"""
    others = [c for c in COINS if c["slug"] != current_slug]
    # 先頭 limit 件（時価総額上位）
    picked = others[:limit]
    chips = []
    for c in picked:
        chips.append(
            f'<a class="chip" href="/coins/{c["slug"]}/">'
            f'{esc(c["name"])} ({c["symbol"].upper()})</a>'
        )
    return "\n        ".join(chips)


# --------------- Index Page ---------------

def build_coins_index() -> str:
    """カードグリッド UI のコイン一覧ページを生成"""
    cards = []
    for i, c in enumerate(COINS, 1):
        cards.append(f"""      <a href="/coins/{c['slug']}/" class="coin-card">
        <span class="coin-rank">#{i}</span>
        <span class="coin-name">{esc(c['name'])}</span>
        <span class="coin-sym">{c['symbol'].upper()}</span>
      </a>""")
    items_html = "\n".join(cards)

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>暗号資産 銘柄一覧 (Top {len(COINS)}) | CoinRader</title>
  <meta name="description" content="主要暗号資産{len(COINS)}銘柄の価格・変動率・時価総額を一覧で確認。Bitcoin, Ethereum, Solana 等。CoinRader。" />
  <meta name="robots" content="index, follow" />
  <link rel="canonical" href="{SITE_ORIGIN}/coins/" />
  <meta property="og:locale" content="ja_JP" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="CoinRader" />
  <meta property="og:title" content="暗号資産 銘柄一覧 (Top {len(COINS)}) | CoinRader" />
  <meta property="og:description" content="主要暗号資産{len(COINS)}銘柄の価格・変動率を一覧で確認。" />
  <meta property="og:url" content="{SITE_ORIGIN}/coins/" />
  <meta property="og:image" content="{SITE_ORIGIN}/assets/og/ogp_v2.png" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="暗号資産 銘柄一覧 | CoinRader" />
  <meta name="twitter:image" content="{SITE_ORIGIN}/assets/og/ogp_v2.png" />
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
      {{"@type": "ListItem", "position": 2, "name": "Coins"}}
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
      transition: transform .15s, border-color .15s;
      white-space:nowrap;
    }}
    .headerNav a:hover {{ transform:translateY(-1px); border-color:rgba(56,189,248,.35); }}
    .breadcrumb {{ font-size:13px; color:#94a3b8; margin-bottom:8px; }}
    .breadcrumb a {{ color:#7dd3fc; }}
    h1 {{ font-size:22px; font-weight:800; margin:10px 0 6px; }}
    .sub {{ font-size:13px; color:#94a3b8; margin-bottom:18px; }}
    .coin-grid {{
      display:grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap:10px;
    }}
    .coin-card {{
      display:flex; align-items:center; gap:10px;
      background:#111827; border:1px solid rgba(148,163,184,.18);
      border-radius:12px; padding:12px 14px;
      text-decoration:none !important; color:#e5e7eb;
      transition: transform .15s, border-color .2s, box-shadow .2s;
    }}
    .coin-card:hover {{
      transform:translateY(-2px);
      border-color:rgba(56,189,248,.4);
      box-shadow:0 8px 20px rgba(0,0,0,.3);
    }}
    .coin-rank {{
      font-size:12px; font-weight:800; color:#94a3b8;
      min-width:28px; text-align:center;
    }}
    .coin-name {{ font-size:14px; font-weight:700; color:#f9fafb; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .coin-sym {{ font-size:12px; color:#94a3b8; margin-left:auto; white-space:nowrap; }}
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
      .footer-brand {{ flex-direction:column; gap:6px; }}
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
        <a href="/daily/latest"><i class="fa-solid fa-chart-line"></i><span>Daily</span></a>
        <a href="/dictionary/"><i class="fa-solid fa-book"></i><span>用語集</span></a>
      </nav>
    </header>

    <nav class="breadcrumb" aria-label="パンくずリスト">
      <a href="/">トップ</a> / <span>Coins</span>
    </nav>

    <h1><i class="fa-solid fa-coins" style="color:#38bdf8;margin-right:8px;"></i>暗号資産 銘柄一覧</h1>
    <div class="sub">主要{len(COINS)}銘柄の個別ページ。各銘柄のリアルタイム価格・変動率・時価総額を確認できます。</div>

    <div class="coin-grid">
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
        <a href="/">ホーム</a>
        <a href="/coins/">Coins</a>
        <a href="/daily/latest">Daily</a>
        <a href="/about">運営者情報</a>
        <a href="/contact">お問い合わせ</a>
      </div>
    </div>
    <div class="footer-copyright">
      &copy; 2026 CoinRader. All rights reserved. ｜ 本サイトは投資助言ではありません。
    </div>
  </footer>
</body>
</html>
"""


# --------------- Coin Page ---------------

def render_coin_page(tmpl: str, c: dict) -> str:
    s = tmpl
    s = s.replace("{{SYMBOL}}", c["symbol"])
    s = s.replace("{{SYMBOL_UPPER}}", c["symbol"].upper())
    s = s.replace("{{COIN_ID}}", c["coin_id"])
    s = s.replace("{{NAME}}", c["name"])
    s = s.replace("{{SLUG}}", c["slug"])
    s = s.replace("{{COINGECKO_KEY}}", "")
    s = s.replace("{{RELATED_COINS_HTML}}", build_related_coins_html(c["slug"]))
    return s


# --------------- _redirects ---------------

def build_redirects_coins_section() -> str:
    """コイン用の _redirects 追記案を stdout に表示"""
    lines = ["\n# --- Coins: auto-generated ticker aliases ---"]
    for c in COINS:
        sym = c["symbol"]
        slug = c["slug"]
        # ticker → slug redirect (if they differ)
        if sym != slug:
            lines.append(f"/coins/{sym}                       /coins/{slug}/              301")
            lines.append(f"/coins/{sym}/                      /coins/{slug}/              301")
        # .html legacy
        lines.append(f"/coins/{slug}.html              /coins/{slug}/              301")
    return "\n".join(lines)


# --------------- Main ---------------

def main() -> None:
    tmpl_path = TEMPL_DIR / "coin_template.html"
    if not tmpl_path.exists():
        raise SystemExit(f"Missing template: {tmpl_path}")

    tmpl = read_text(tmpl_path)

    # Hub (index)
    write_text(OUT_COINS_DIR / "index.html", build_coins_index())

    # Coin pages
    for c in COINS:
        html = render_coin_page(tmpl, c)
        write_text(OUT_COINS_DIR / c["slug"] / "index.html", html)

    print(f"[OK] Generated coins pages: {OUT_COINS_DIR} (count={len(COINS)})")

    # Print redirect suggestions
    print("\n--- Suggested _redirects additions ---")
    print(build_redirects_coins_section())

if __name__ == "__main__":
    main()
