#!/usr/bin/env python3
# generate_daily_post.py
# CoinRader: X投稿用デイリー集計（index_v42.html のランキングルールに合わせる）
import os
import datetime as dt
import requests
from pathlib import Path
from typing import Any



# --- index.html と同等の出来高(アルト)除外ロジック ---
EXCLUDE_VOLUME_IDS = {
    'tether','usd-coin','dai','true-usd','first-digital-usd','ethena-usde',
    'wrapped-bitcoin','staked-ether',
    # 追加で除外したい銘柄はここにidを足す
}
EXCLUDE_NAME_KEYWORDS = [
    'usd','us dollar','stable','tether','usd coin',
    'wrapped','bridged','wormhole','portal',
    'staked','staking','restaked',
    'wbtc','weth','steth'
]

def is_excluded_for_alt_volume(coin: dict) -> bool:
    cid = (coin.get('id') or '').lower()
    name = (coin.get('name') or '').lower()
    sym  = (coin.get('symbol') or '').lower()
    if cid in EXCLUDE_VOLUME_IDS:
        return True
    for k in EXCLUDE_NAME_KEYWORDS:
        if k in name or k in sym:
            return True
    return False
BASE_URL = "https://api.coingecko.com/api/v3"

CG_DEMO_KEY = os.getenv("CG_DEMO_KEY", "").strip()   # Demo API key
VS = os.getenv("VS_CURRENCY", "jpy")                # indexはjpy想定
SITE_URL = os.getenv("SITE_URL", "https://coinrader.net/").strip()
OGP_IMAGE_URL = os.getenv("OGP_IMAGE_URL", "https://coinrader.net/assets/og/ogp.png").strip()
# shareページ（Xカード展開用）を日付で切って生成する（例: /share/20260124.html）
SHARE_DIR = os.getenv("SHARE_DIR", "share").strip()
USE_SHARE_URL_IN_POST = os.getenv("USE_SHARE_URL_IN_POST", "1").strip() not in ("0","false","False")

TIMEOUT = 20

# index_v42.html と同じ：上昇率のノイズ対策（出来高下限を満たす銘柄を優先）
MIN_GAINERS_24H_VOLUME_JPY = int(os.getenv("MIN_GAINERS_24H_VOLUME_JPY", "500000000"))  # 5億円

# ===== stable / major 判定（index_v42.html と合わせる）=====
STABLE_IDS = {
    "tether","usd-coin","dai","true-usd","first-digital-usd","ethena-usde",
    "frax","pax-dollar","paypal-usd","gemini-dollar","paxos-standard","binance-usd","liquity-usd",
    "usd1",

}
STABLE_SYMBOLS = {"usdt","usdc","dai","tusd","usde","fdusd","pyusd","gusd","usdp","busd","lusd","frax","usd1","bsc-usd"}

def is_stable_coin(c: dict) -> bool:
    cid = (c.get("id") or "").lower()
    sym = (c.get("symbol") or "").lower()
    name = (c.get("name") or "").lower()
    if cid in STABLE_IDS or sym in STABLE_SYMBOLS:
        return True
    # fallback heuristic（軽め）
    if ("stable" in name) and (("usd" in name) or ("usd" in sym)):
        return True
    return False

def is_btc_or_eth(c: dict) -> bool:
    cid = (c.get("id") or "").lower()
    sym = (c.get("symbol") or "").lower()
    return cid in ("bitcoin", "ethereum") or sym in ("btc", "eth")

def cg_get(path: str, params: dict | None = None) -> Any:
    url = f"{BASE_URL}{path}"
    headers = {}
    if CG_DEMO_KEY:
        headers["x-cg-demo-api-key"] = CG_DEMO_KEY
    r = requests.get(url, params=params or {}, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def safe_sym(name: str, symbol: str) -> str:
    sym = (symbol or "").upper()
    if sym and len(sym) <= 10:
        return sym
    # まれに symbol が長い/空のとき
    return (name or "")[:10].upper()

def fmt_rank(items: list[str]) -> str:
    return " ".join([f"{i+1}.{s}" for i, s in enumerate(items)])

def build_share_page(date_str: str, site_base: str) -> tuple[str, str]:
    """share/YYYYMMDD.html を生成し、そのURLとローカルパスを返す。
    - Xのカードキャッシュ対策として、日付ごとに別URLにする
    - 画面表示ではトップへリダイレクト（meta refresh）
    """
    yyyymmdd = date_str.replace("-", "")
    site_base = site_base.rstrip("/")
    share_url = f"{site_base}/{SHARE_DIR}/{yyyymmdd}.html"

    # 画像キャッシュ回避用クエリ（ogp.png自体は同じでOK）
    ogp_image = OGP_IMAGE_URL
    if "?" in ogp_image:
        ogp_image_q = ogp_image + f"&v={yyyymmdd}"
    else:
        ogp_image_q = ogp_image + f"?v={yyyymmdd}"

    html = f'''<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>CoinRader - 今日の注目 {date_str}</title>

  <meta property="og:type" content="website">
  <meta property="og:site_name" content="CoinRader">
  <meta property="og:title" content="CoinRader - 今日の注目 {date_str}">
  <meta property="og:description" content="トレンド/上昇率/出来高をひと目で。">
  <meta property="og:url" content="{share_url}">
  <meta property="og:image" content="{ogp_image_q}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="CoinRader - 今日の注目 {date_str}">
  <meta name="twitter:description" content="トレンド/上昇率/出来高をひと目で。">
  <meta name="twitter:image" content="{ogp_image_q}">

  <meta http-equiv="refresh" content="0;url={site_base}/?v={yyyymmdd}">
</head>
<body></body>
</html>
'''
    share_dir = Path(SHARE_DIR)
    share_dir.mkdir(parents=True, exist_ok=True)
    out_path = share_dir / f"{yyyymmdd}.html"
    out_path.write_text(html, encoding="utf-8")
    return share_url, str(out_path)

def build_gainers_top5(markets_top: list[dict]) -> list[dict]:
    base = [
        c for c in markets_top
        if isinstance(c.get("price_change_percentage_24h"), (int, float))
        and is_stable_coin(c) is False
    ]

    primary = [
        c for c in base
        if isinstance(c.get("total_volume"), (int, float))
        and c["total_volume"] >= MIN_GAINERS_24H_VOLUME_JPY
    ]
    primary.sort(key=lambda x: x.get("price_change_percentage_24h", 0), reverse=True)

    if len(primary) >= 5:
        return primary[:5]

    picked = {c.get("id") for c in primary}
    fallback = [c for c in base if isinstance(c.get("total_volume"), (int, float))]
    fallback.sort(key=lambda x: x.get("total_volume") or 0, reverse=True)

    for c in fallback:
        if len(primary) >= 5:
            break
        cid = c.get("id")
        if cid and cid not in picked:
            primary.append(c)
            picked.add(cid)
    return primary[:5]

def build_post():
    # --- Trending TOP5（indexと同じ /search/trending） ---
    trending = cg_get("/search/trending")
    trend_items: list[str] = []
    for c in (trending.get("coins") or [])[:10]:
        item = c.get("item") or {}
        name = item.get("name", "")
        sym = item.get("symbol", "")
        if name or sym:
            trend_items.append(safe_sym(name, sym))
        if len(trend_items) >= 5:
            break

    # --- indexの marketsTop（時価総額上位250 / vs=jpy） ---
    markets_top: list[dict] = cg_get("/coins/markets", {
        "vs_currency": VS,
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": "false",                 # 投稿用は不要
        "price_change_percentage": "24h",
    }) or []

    # --- 上昇率TOP5（indexの buildGainersTop5 と一致） ---
    gain_top = build_gainers_top5(markets_top)
    gain_top5_full = [
        f"{safe_sym(x.get('name',''), x.get('symbol',''))}({x.get('price_change_percentage_24h', 0):+.1f}%)"
        for x in gain_top
    ]

    # --- 出来高TOP5（全体 / アルト）---
    volume_all = sorted(
        [c for c in markets_top if isinstance(c.get("total_volume"), (int, float))],
        key=lambda x: x.get("total_volume") or 0,
        reverse=True
    )[:5]

    volume_alt = sorted(
        [c for c in markets_top
         if isinstance(c.get("total_volume"), (int, float))
         and (not is_stable_coin(c))
         and (not is_btc_or_eth(c))
         and (not is_excluded_for_alt_volume(c))
        ],
        key=lambda x: x.get("total_volume") or 0,
        reverse=True
    )[:5]


    vol_all_syms = [safe_sym(c.get("name",""), c.get("symbol","")) for c in volume_all]
    vol_alt_syms = [safe_sym(c.get("name",""), c.get("symbol","")) for c in volume_alt]

    # --- Compose ---
    jst = dt.timezone(dt.timedelta(hours=9))
    today = dt.datetime.now(jst).strftime("%Y-%m-%d")
    share_url, share_path = build_share_page(today, SITE_URL)
    post_url = share_url if USE_SHARE_URL_IN_POST else SITE_URL

    full = (
        f"【今日の注目 {today}】\n"
        f"トレンド: {fmt_rank(trend_items)}\n"
        f"上昇率(24h): {fmt_rank(gain_top5_full)}\n"
        f"出来高(全体): {fmt_rank(vol_all_syms)}\n"
        f"出来高(アルト): {fmt_rank(vol_alt_syms)}\n"
        f"→ {post_url}\n"
        f"#暗号資産"
    )

    # X向け（見やすさ優先：改行＋絵文字。出来高はアルトを表示）
    def build_short(n_trend=3, n_up=3, n_vol=3) -> str:
        up_parts = []
        for x in gain_top[:n_up]:
            sym = safe_sym(x.get("name",""), x.get("symbol",""))
            pct = x.get("price_change_percentage_24h", 0)
            up_parts.append(f"{sym} {pct:+.1f}%")
        short = (
            f"【今日の注目 {today}】\n"
            f"🔥Trend: {' / '.join(trend_items[:n_trend])}\n"
            f"🚀Up(24h,出来高≥5億円優先): {' | '.join(up_parts)}\n"
            f"📊Vol(アルト): {' / '.join(vol_alt_syms[:n_vol])}\n"
            f"→ {post_url} #暗号資産"
        )
        return short

    short = build_short()

    # 280字超なら段階的に短縮
    if len(short) > 280:
        short = build_short(n_trend=2, n_up=2, n_vol=2)
    if len(short) > 280:
        # 最終手段：1行圧縮
        up2 = " / ".join([
            f"{safe_sym(x.get('name',''), x.get('symbol',''))}{x.get('price_change_percentage_24h',0):+.1f}%"
            for x in gain_top[:2]
        ])
        short = (
            f"【今日の注目 {today}】"
            f" Trend:{'/'.join(trend_items[:2])}"
            f" | Up:{up2}"
            f" | Vol:{'/'.join(vol_alt_syms[:2])}"
            f" → {post_url} #暗号資産"
        )
        if len(short) > 280:
            short = short[:277] + "…"

    return full, short, share_url, share_path

if __name__ == "__main__":
    full, short, share_url, share_path = build_post()

    with open("daily_post_full.txt", "w", encoding="utf-8") as f:
        f.write(full)

    with open("daily_post_short.txt", "w", encoding="utf-8") as f:
        f.write(short)

    with open("daily_share_url.txt", "w", encoding="utf-8") as f:
        f.write(share_url)

    print(full)
    print("\n--- short ---\n")
    print(short)
    print("\n--- share ---\n")
    print(share_url)
    print(f"(generated: {share_path})")
