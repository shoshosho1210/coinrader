#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CoinRader: CoinGecko API から各コインのスナップショットを取得し data/coins/ に保存

使い方:
  python scripts/fetch_coin_snapshots.py

環境変数:
  CR_COINGECKO_KEY or CG_DEMO_KEY  -- CoinGecko Demo API key（任意）
"""

from __future__ import annotations
import os, json, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "coins"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# build_coin_pages.py と同じリストを維持
# NOTE: 変更時は build_coin_pages.py の COINS と同期すること
COINS = [
    {"symbol": "btc",    "coin_id": "bitcoin",            "name": "Bitcoin"},
    {"symbol": "eth",    "coin_id": "ethereum",           "name": "Ethereum"},
    {"symbol": "usdt",   "coin_id": "tether",             "name": "Tether"},
    {"symbol": "xrp",    "coin_id": "ripple",             "name": "XRP"},
    {"symbol": "bnb",    "coin_id": "binancecoin",        "name": "BNB"},
    {"symbol": "sol",    "coin_id": "solana",             "name": "Solana"},
    {"symbol": "usdc",   "coin_id": "usd-coin",           "name": "USDC"},
    {"symbol": "doge",   "coin_id": "dogecoin",           "name": "Dogecoin"},
    {"symbol": "ada",    "coin_id": "cardano",            "name": "Cardano"},
    {"symbol": "trx",    "coin_id": "tron",               "name": "TRON"},
    {"symbol": "avax",   "coin_id": "avalanche-2",        "name": "Avalanche"},
    {"symbol": "link",   "coin_id": "chainlink",          "name": "Chainlink"},
    {"symbol": "shib",   "coin_id": "shiba-inu",          "name": "Shiba Inu"},
    {"symbol": "sui",    "coin_id": "sui",                "name": "Sui"},
    {"symbol": "xlm",    "coin_id": "stellar",            "name": "Stellar"},
    {"symbol": "dot",    "coin_id": "polkadot",           "name": "Polkadot"},
    {"symbol": "bch",    "coin_id": "bitcoin-cash",       "name": "Bitcoin Cash"},
    {"symbol": "hype",   "coin_id": "hyperliquid",        "name": "Hyperliquid"},
    {"symbol": "uni",    "coin_id": "uniswap",            "name": "Uniswap"},
    {"symbol": "ltc",    "coin_id": "litecoin",           "name": "Litecoin"},
    {"symbol": "hbar",   "coin_id": "hedera-hashgraph",   "name": "Hedera"},
    {"symbol": "near",   "coin_id": "near",               "name": "NEAR Protocol"},
    {"symbol": "apt",    "coin_id": "aptos",              "name": "Aptos"},
    {"symbol": "pepe",   "coin_id": "pepe",               "name": "Pepe"},
    {"symbol": "icp",    "coin_id": "internet-computer",  "name": "Internet Computer"},
    {"symbol": "dai",    "coin_id": "dai",                "name": "Dai"},
    {"symbol": "aave",   "coin_id": "aave",               "name": "Aave"},
    {"symbol": "etc",    "coin_id": "ethereum-classic",   "name": "Ethereum Classic"},
    {"symbol": "pol",    "coin_id": "matic-network",      "name": "Polygon"},
    {"symbol": "render", "coin_id": "render-token",       "name": "Render"},
    {"symbol": "atom",   "coin_id": "cosmos",             "name": "Cosmos"},
    {"symbol": "fil",    "coin_id": "filecoin",           "name": "Filecoin"},
    {"symbol": "arb",    "coin_id": "arbitrum",           "name": "Arbitrum"},
    {"symbol": "op",     "coin_id": "optimism",           "name": "Optimism"},
    {"symbol": "vet",    "coin_id": "vechain",            "name": "VeChain"},
    {"symbol": "inj",    "coin_id": "injective-protocol", "name": "Injective"},
    {"symbol": "grt",    "coin_id": "the-graph",          "name": "The Graph"},
    {"symbol": "ftm",    "coin_id": "fantom",             "name": "Fantom"},
    {"symbol": "algo",   "coin_id": "algorand",           "name": "Algorand"},
    {"symbol": "theta",  "coin_id": "theta-token",        "name": "Theta Network"},
    {"symbol": "mkr",    "coin_id": "maker",              "name": "Maker"},
    {"symbol": "sei",    "coin_id": "sei-network",        "name": "Sei"},
    {"symbol": "flow",   "coin_id": "flow",               "name": "Flow"},
    {"symbol": "ondo",   "coin_id": "ondo-finance",       "name": "Ondo Finance"},
    {"symbol": "pyth",   "coin_id": "pyth-network",       "name": "Pyth Network"},
    {"symbol": "jup",    "coin_id": "jupiter-exchange-solana", "name": "Jupiter"},
    {"symbol": "floki",  "coin_id": "floki",              "name": "FLOKI"},
    {"symbol": "wld",    "coin_id": "worldcoin-wld",      "name": "Worldcoin"},
    {"symbol": "bonk",   "coin_id": "bonk",               "name": "Bonk"},
    {"symbol": "stx",    "coin_id": "blockstack",         "name": "Stacks"},
]


def fetch_markets(coin_ids: list[str], api_key: str | None) -> list[dict]:
    """CoinGecko /coins/markets を呼び出し（最大250件/1回）"""
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "jpy",
        "ids": ",".join(coin_ids),
        "price_change_percentage": "24h,7d",
        "sparkline": "true",
        "per_page": 250,
    }
    headers = {}
    if api_key:
        headers["x-cg-demo-api-key"] = api_key

    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    j = r.json()
    if not isinstance(j, list):
        raise RuntimeError("unexpected response")
    return j


def main():
    api_key = os.getenv("CR_COINGECKO_KEY") or os.getenv("CG_DEMO_KEY") or ""

    # CoinGecko 無料枠は1リクエスト250件まで。50件ならバッチ不要。
    coin_ids = [c["coin_id"] for c in COINS]

    print(f"[INFO] Fetching {len(coin_ids)} coins from CoinGecko...")
    markets = fetch_markets(coin_ids, api_key if api_key else None)
    by_id = {m.get("id"): m for m in markets}

    ok_count = 0
    miss_count = 0
    for c in COINS:
        m = by_id.get(c["coin_id"])
        if not m:
            print(f"[WARN] missing market data for {c['coin_id']} — skipping")
            miss_count += 1
            continue
        snap = {
            "symbol": c["symbol"],
            "coin_id": c["coin_id"],
            "name": c["name"],
            "market": m,
        }
        out = OUT_DIR / f"{c['symbol']}.json"
        out.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
        ok_count += 1

    print(f"[OK] wrote {ok_count} snapshots to {OUT_DIR} (skipped={miss_count})")

if __name__ == "__main__":
    main()
