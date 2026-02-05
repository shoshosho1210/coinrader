#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import os, json
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "coins"
OUT_DIR.mkdir(parents=True, exist_ok=True)

COINS = [
    {"symbol": "btc", "coin_id": "bitcoin",  "name": "Bitcoin"},
    {"symbol": "eth", "coin_id": "ethereum", "name": "Ethereum"},
    {"symbol": "sol", "coin_id": "solana",   "name": "Solana"},
    {"symbol": "xrp", "coin_id": "ripple",   "name": "XRP"},
]

def fetch_markets(coin_ids: list[str], api_key: str | None) -> list[dict]:
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "jpy",
        "ids": ",".join(coin_ids),
        "price_change_percentage": "24h,7d",
    }
    headers = {}
    if api_key:
        # Demoキーの場合のヘッダ名（必要な場合のみ）
        headers["x-cg-demo-api-key"] = api_key

    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    j = r.json()
    if not isinstance(j, list):
        raise RuntimeError("unexpected response")
    return j

def main():
    api_key = os.getenv("CR_COINGECKO_KEY") or os.getenv("CG_DEMO_KEY") or ""
    coin_ids = [c["coin_id"] for c in COINS]
    markets = fetch_markets(coin_ids, api_key if api_key else None)
    by_id = {m.get("id"): m for m in markets}

    for c in COINS:
        m = by_id.get(c["coin_id"])
        if not m:
            raise RuntimeError(f"missing market data for {c['coin_id']}")
        snap = {
            "symbol": c["symbol"],
            "coin_id": c["coin_id"],
            "name": c["name"],
            "market": m,
        }
        out = OUT_DIR / f"{c['symbol']}.json"
        out.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
        print("[OK] wrote", out)

if __name__ == "__main__":
    main()
