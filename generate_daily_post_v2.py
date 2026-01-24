# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests


# ====== Settings ======
BASE_URL = os.getenv("BASE_URL", "https://coinrader.net").rstrip("/")
SITE_URL = os.getenv("SITE_URL", f"{BASE_URL}/")  # workflow compatibility
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


# ====== Rank emoji (avoid literal emoji in source) ======
RANK_EMOJI = [
    "\u0031\ufe0f\u20e3",  # 1️⃣
    "\u0032\ufe0f\u20e3",  # 2️⃣
    "\u0033\ufe0f\u20e3",  # 3️⃣
    "\u0034\ufe0f\u20e3",  # 4️⃣
    "\u0035\ufe0f\u20e3",  # 5️⃣
]
RANK_EMOJI = [s.encode("utf-8").decode("unicode_escape") for s in RANK_EMOJI]

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
    out: List[str] = []
    for i, x in enumerate(items):
        rank = RANK_EMOJI[i] if i < len(RANK_EMOJI) else f"{i+1}."
        out.append(f"{rank} {x}")
    return " / ".join(out)


def fmt_ranked_pipes(items: List[str]) -> str:
    out: List[str] = []
    for i, x in enumerate(items):
        rank = RANK_EMOJI[i] if i < len(RANK_EMOJI) else f"{i+1}."
        out.append(f"{rank} {x}")
    return " | ".join(out)


def load_trending_top(n: int) -> List[str]:
    data = fetch_json("https://api.coingecko.com/api/v3/search/trending")
    coins = data.get("coins") or []
    symbols: List[str] = []
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
        # Fill remaining from fallback (still excluding stables), prioritize volume then change
        fallback.sort(key=lambda x: (x[1], x[0]), reverse=True)
        for _, __, label in fallback:
            if label not in out:
                out.append(label)
            if len(out) >= n:
                break

    return out[:n]


def pick_top_volume_alt(markets: List[Dict[str, Any]], n: int) -> List[str]:
    items: List[Tuple[float, str]] = []
    for m in markets:
        sym = (m.get("symbol") or "").upper()
        if not sym:
            continue

        if VOL_ALT_EXCLUDE_STABLE and is_stable(sym):
            continue
        if sym.lower() in VOL_ALT_EXCLUDE_SYMBOLS:
            continue

        vol = m.get("total_volume")
        try:
            vol_f = float(vol)
        except Exception:
            continue

        items.append((vol_f, sym))

    items.sort(key=lambda x: x[0], reverse=True)
    return [sym for _, sym in items[:n]]


def today_ymd() -> str:
    jst = dt.timezone(dt.timedelta(hours=9))
    return dt.datetime.now(jst).strftime("%Y-%m-%d")


def today_ymd_compact() -> str:
    jst = dt.timezone(dt.timedelta(hours=9))
    return dt.datetime.now(jst).strftime("%Y%m%d")


def write_share_html(date_compact: str, date_dash: str) -> str:
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    share_path = SHARE_DIR / f"{date_compact}.html"
    share_url = f"{BASE_URL}/share/{date_compact}.html"
    og_img = f"{BASE_URL}/assets/og/ogp.png?v={date_compact}"

    html = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CoinRader - 今日の注目 {date_dash}</title>

<meta property="og:type" content="website">
<meta property="og:site_name" content="CoinRader">
<meta property="og:title" content="CoinRader - 今日の注目 {date_dash}">
<meta property="og:description" content="トレンド/上昇率/出来高をひと目で。">
<meta property="og:url" content="{share_url}">
<meta property="og:image" content="{og_img}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="CoinRader - 今日の注目 {date_dash}">
<meta name="twitter:description" content="トレンド/上昇率/出来高をひと目で。">
<meta name="twitter:image" content="{og_img}">

<meta http-equiv="refresh" content="0;url={BASE_URL}/?v={date_compact}">
</head>
<body></body>
</html>
"""
    share_path.write_text(html, encoding="utf-8")
    return share_url


def main() -> None:
    date_dash = today_ymd()
    date_compact = today_ymd_compact()

    trend = load_trending_top(TREND_N)
    markets = load_markets_top250()
    up = pick_top_gainers(markets, UP_N)
    vol_alt = pick_top_volume_alt(markets, VOL_ALT_N)

    share_url = write_share_html(date_compact, date_dash)
    link = share_url if USE_SHARE_URL_IN_POST else f"{BASE_URL}/"

    lines = [
        f"【今日の注目 {date_dash}】",
        f"🔥Trend: {fmt_ranked_slash(trend)}",
        f"🚀Up(24h): {fmt_ranked_pipes(up)}",
        f"📊Vol(アルト): {fmt_ranked_slash(vol_alt)}",
        f"→ {link} #暗号資産",
    ]

    text = "\n".join(lines)

    Path("daily_post_full.txt").write_text(text, encoding="utf-8")
    Path("daily_post_short.txt").write_text(text, encoding="utf-8")
    Path("daily_share_url.txt").write_text(share_url, encoding="utf-8")

    print(share_url)


if __name__ == "__main__":
    main()
