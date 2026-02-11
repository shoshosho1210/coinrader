#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CoinRader: 各コイン用のSNSシェア最適化

各コインのJSON市場データを読み込み、以下を生成:
  1. share/coins/<slug>.html — og:description に最新価格・変動率を含むリダイレクトページ
  2. og_descriptions.json — coin_template.html のog:descriptionを上書きするためのデータ

使い方:
  python scripts/generate_coin_ogp.py

※ fetch_coin_snapshots.py → build_coin_pages.py の後に実行する想定
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "coins"
SHARE_DIR = ROOT / "share" / "coins"
SITE_ORIGIN = os.environ.get("CR_SITE_ORIGIN", "https://coinrader.net").rstrip("/")

# build_coin_pages.py の COINS と同じ構成
COINS = [
    {"slug": "bitcoin",    "symbol": "btc",  "coin_id": "bitcoin",      "name": "Bitcoin"},
    {"slug": "ethereum",   "symbol": "eth",  "coin_id": "ethereum",     "name": "Ethereum"},
    {"slug": "tether",     "symbol": "usdt", "coin_id": "tether",       "name": "Tether"},
    {"slug": "xrp",        "symbol": "xrp",  "coin_id": "ripple",       "name": "XRP"},
    {"slug": "bnb",        "symbol": "bnb",  "coin_id": "binancecoin",  "name": "BNB"},
    {"slug": "solana",     "symbol": "sol",  "coin_id": "solana",       "name": "Solana"},
    {"slug": "usdc",       "symbol": "usdc", "coin_id": "usd-coin",     "name": "USDC"},
    {"slug": "dogecoin",   "symbol": "doge", "coin_id": "dogecoin",     "name": "Dogecoin"},
    {"slug": "cardano",    "symbol": "ada",  "coin_id": "cardano",      "name": "Cardano"},
    {"slug": "tron",       "symbol": "trx",  "coin_id": "tron",         "name": "TRON"},
    {"slug": "avalanche",  "symbol": "avax", "coin_id": "avalanche-2",  "name": "Avalanche"},
    {"slug": "chainlink",  "symbol": "link", "coin_id": "chainlink",    "name": "Chainlink"},
    {"slug": "shiba-inu",  "symbol": "shib", "coin_id": "shiba-inu",    "name": "Shiba Inu"},
    {"slug": "sui",        "symbol": "sui",  "coin_id": "sui",          "name": "Sui"},
    {"slug": "stellar",    "symbol": "xlm",  "coin_id": "stellar",      "name": "Stellar"},
    {"slug": "polkadot",   "symbol": "dot",  "coin_id": "polkadot",     "name": "Polkadot"},
    {"slug": "bitcoin-cash","symbol": "bch",  "coin_id": "bitcoin-cash", "name": "Bitcoin Cash"},
    {"slug": "hyperliquid","symbol": "hype", "coin_id": "hyperliquid",  "name": "Hyperliquid"},
    {"slug": "uniswap",    "symbol": "uni",  "coin_id": "uniswap",      "name": "Uniswap"},
    {"slug": "litecoin",   "symbol": "ltc",  "coin_id": "litecoin",     "name": "Litecoin"},
]


def fmt_price(v: float | None) -> str:
    if v is None:
        return "-"
    if v >= 1_000_000:
        return f"{v / 10_000:,.0f}万円"
    return f"¥{v:,.0f}"


def fmt_pct(v: float | None) -> str:
    if v is None:
        return "-"
    return f"{'+' if v >= 0 else ''}{v:.1f}%"


def load_market(symbol: str) -> dict | None:
    p = DATA_DIR / f"{symbol}.json"
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("market")


def build_share_html(coin: dict, m: dict) -> str:
    """SNSシェア用のリダイレクトHTMLを生成"""
    name = coin["name"]
    sym = coin["symbol"].upper()
    slug = coin["slug"]

    price = fmt_price(m.get("current_price"))
    chg24 = fmt_pct(m.get("price_change_percentage_24h"))
    rank = m.get("market_cap_rank", "?")

    desc = f"{name} ({sym}) 最新情報 — 価格: {price}, 24h変動: {chg24}, 時価総額ランク: #{rank}。CoinRaderで詳細分析を確認。"
    url = f"{SITE_ORIGIN}/coins/{slug}/"
    share_url = f"{SITE_ORIGIN}/share/coins/{slug}.html"
    og_image = f"{SITE_ORIGIN}/assets/og/ogp_v2.png"

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{name} ({sym}) — 最新市場データ | CoinRader</title>
  <meta name="description" content="{desc}" />
  <meta name="robots" content="noindex,follow,max-image-preview:large" />
  <link rel="canonical" href="{url}" />

  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="CoinRader" />
  <meta property="og:title" content="{name} ({sym}) — {price} ({chg24})" />
  <meta property="og:description" content="{desc}" />
  <meta property="og:url" content="{share_url}" />
  <meta property="og:image" content="{og_image}" />
  <meta property="og:image:width" content="1200" />
  <meta property="og:image:height" content="630" />

  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{name} ({sym}) — {price}" />
  <meta name="twitter:description" content="{desc}" />
  <meta name="twitter:image" content="{og_image}" />

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "WebPage",
    "name": "{name} ({sym}) 市場データ",
    "description": "{desc}",
    "url": "{url}"
  }}
  </script>

  <meta http-equiv="refresh" content="0;url={url}" />
</head>
<body></body>
</html>"""


def main() -> None:
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    og_data: dict[str, str] = {}
    generated = 0

    for coin in COINS:
        m = load_market(coin["symbol"])
        if not m:
            print(f"  SKIP {coin['slug']} (no data)")
            continue

        # Share HTML
        html = build_share_html(coin, m)
        out = SHARE_DIR / f"{coin['slug']}.html"
        out.write_text(html, encoding="utf-8")

        # OGP description for use by other scripts
        price = fmt_price(m.get("current_price"))
        chg24 = fmt_pct(m.get("price_change_percentage_24h"))
        rank = m.get("market_cap_rank", "?")
        og_data[coin["slug"]] = (
            f"{coin['name']} ({coin['symbol'].upper()}) 最新情報 — "
            f"価格: {price}, 24h変動: {chg24}, 時価総額ランク: #{rank}。"
            f"CoinRaderで詳細分析を確認。"
        )
        generated += 1

    # Save aggregated OGP descriptions
    og_out = ROOT / "data" / "og_descriptions.json"
    og_out.write_text(json.dumps(og_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] Generated {generated} coin share pages in {SHARE_DIR}")
    print(f"[OK] OGP descriptions saved to {og_out}")


if __name__ == "__main__":
    main()
