#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "coins"

COINS = [
    {"symbol": "btc", "coin_id": "bitcoin"},
    {"symbol": "eth", "coin_id": "ethereum"},
    {"symbol": "sol", "coin_id": "solana"},
    {"symbol": "xrp", "coin_id": "ripple"},
]

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    key = os.getenv("CR_COINGECKO_KEY", "").strip()
    headers = {}
    if key:
        # ブラウザじゃなく Actions(Python) なので CORS は関係ない
        headers["x-cg-demo-api-key"] = key

    ts = int(time.time())

    for c in COINS:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "jpy",
            "ids": c["coin_id"],
            "price_change_percentage": "24h,7d",
        }

        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()

        j = r.json()
        m = j[0] if isinstance(j, list) and j else None
        if not m:
            raise RuntimeError(f"CoinGecko empty: {c['symbol']}")

        payload = {
            "ts": ts,
            "coin_id": c["coin_id"],
            "symbol": c["symbol"],
            "market": m,
        }

        (OUT / f"{c['symbol']}.json").write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    (OUT / "latest.json").write_text(
        json.dumps({"ts": ts, "symbols": [c["symbol"] for c in COINS]}, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"[OK] Wrote coin snapshots into: {OUT}")

if __name__ == "__main__":
    main()
