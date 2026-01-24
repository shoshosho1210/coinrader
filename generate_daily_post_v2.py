# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests


# ====== Settings ======
BASE_URL = os.getenv("BASE_URL", "https://coinrader.net").rstrip("/")
SITE_URL = os.getenv("SITE_URL", f"{BASE_URL}/")  # workflow互換
CG_DEMO_KEY = os.getenv("CG_DEMO_KEY", "").strip()

# CoinGecko
VS_CURRENCY = "jpy"
MARKETS_TOP = 250
MIN_GAINERS_24H_VOLUME_JPY = int(os.getenv("MIN_GAINERS_24H_VOLUME_JPY", "500000000"))

# Output
SHARE_DIR = Path(os.getenv("SHARE_DIR", "share"))
USE_SHARE_URL_IN_POST = os.getenv("USE_SHARE_URL_IN_POST", "1") != "0"

# Keep list sizes
TREND_N = 3
UP_N = 3
VOL_ALT_N = 3


# ====== Emoji rank digits (no literal emoji in source) ======
# 1️⃣ = "1" + VS16 + keycap
RANK_EMOJI = [
    "\u0031\ufe0f\u20e3",  # 1️⃣
    "\u0032\ufe0f\u20e3",  # 2️⃣
    "\u0033\ufe0f\u20e3",  # 3️⃣
    "\u0034\ufe0f\u20e3",  # 4️⃣
    "\u0035\ufe0f\u20e3",  # 5️⃣
]

STABLE_KEYWORDS = {
    "usdt", "usdc", "dai", "tusd", "busd", "fdusd", "usde", "susde",
    "usdp", "pyusd", "gusd", "eurc", "usdd", "lusd", "frax",
}

# Alt volume excludes these big ones to avoid always showing USDT/BTC/ETH
VOL_ALT_EXCLUDE_SYMBOLS = {"btc", "eth"}
VOL_ALT_EXCLUDE_STABLE = True


def cg_headers() -> Dict[str, str]:
    h = {"accept": "application/json"}
    if CG_DEMO_KEY:
        # CoinGecko demo key header (works for both pro/demo setup)
        h["x-cg-demo-api-key"] = CG_DEMO_KEY
    return h


def fetch_json(url: str) -> Any:
    r = requests.get(url, headers=cg_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def is_stable(symbol: str) -> bool:
    s = (symbol or "").lower()
    return s in STABLE_KEYWORDS or any(k in s for k in STABLE_KEYWORDS)


def fmt_ranked_slash(items: List[str]) -> str:
    # "1️⃣ AAA / 2️⃣ BBB / 3️⃣ CCC"
    out = []
    for i, x in enumerate(items):
        rank = RANK_EMOJI[i] if i < len(RANK_EMOJI) else f"{i+1}."
        out.append(f"{rank} {x}")
    return " / ".join(out)


def fmt_ranked_pipes(items: List[str]) -> str:
    # "1️⃣ AAA | 2️⃣ BBB | 3️⃣ CCC"
    out = []
    for i, x in enumerate(items):
        rank = RANK_EMOJI[i] if i < len(RANK_EMOJI) else f"{i+1}."
        out.append(f"{rank} {x}")
    return " | ".join(out)


def load_trending_top(n: int) -> List[str]:
    data = fetch_json("https://api.coingecko.com/api/v3/search/trending")
    coins = data.get("coins") or []
    symbols = []
    for c in coins:
        item = (c.get("item") or {})
        sym = item.get("symbol") or ""
        if sym:
            symbols.append(sym.upper())
        if len(symbols) >= n:
            break
    return symbols


def load_markets_top250() -> List[Dict[str, Any]]:
    url = (
        "https://api.coingecko.com/api/v3/coins/markets"
        f"?vs_currency={VS_CURRENCY}"
        "&order=market_cap_desc"
        f"&per_page={MARKETS_TOP}&page=1"
        "&sparkline=false"
        "&price_change_percentage=24h"
    )
    data = fetch_json(url)
    return data if isinstance(data, list) else []


def pick_top_gainers(markets: List[Dict[str, Any]], n: int) -> List[str]:
    # Prefer volume >= threshold, exclude stables
    cand: List[Tuple[float, float, str]] = []
    fallback: List[Tuple[float, float, str]] = []

    for m in markets:
        sym = (m.get("symbol") or "").upper()
        if not sym:
            continue
        if is_stable(sym):
            continue

        chg = m.get("price_change_percentage_24h_in_currency")
        if chg is None:
            chg = m.get("price_change_percentage_24h")
        try:
            chg_f = float(chg)
        except Exception:
            continue

        vol = m.get("total_volume")
        try:
            vol_f = float(vol)
        except Exception:
            vol_f = 0.0

        label = f"{sym} {chg_f:+.1f}%"
        tup = (chg_f, vol_f, label)

        if vol_f >= MIN_GAINERS_24H_VOLUME_JPY:
            cand.append(tup)
        fallback.append(tup)

    # Sort by change desc, then volume desc
    cand.sort(key=lambda x: (x[0], x[1]), reverse=True)
    out = [x[2] for x in cand[:n]]

    if len(out) < n:
        # Fill remaining from fallback (still excludi
