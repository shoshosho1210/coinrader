#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CoinRader: 日次ポスト文（X用） + shareページURLを生成するスクリプト。

出力:
  - daily_post_short.txt   (Xにそのまま貼れる短文)
  - daily_post_full.txt    (短文 + 有料(詳細版)向けの下書き)
  - daily_share_url.txt    (shareページURLのみ)
  - share/YYYYMMDD.html    (OGP用の固定HTML)
  - data/daily/YYYYMMDD.json (週次集計用スナップショット)

要件(サイト側に合わせる):
  - Up(24h) は出来高しきい値(既定 5億円)を優先し、不足時は出来高順で補完
  - Vol(アルト) は BTC/ETH を除外し、ステーブル系も除外
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


# -----------------------------
# Config
# -----------------------------
SITE_URL = os.getenv("SITE_URL", "https://coinrader.net/").rstrip("/") + "/"
CG_DEMO_KEY = os.getenv("CG_DEMO_KEY", "")  # CoinGecko Demo Key (optional)
VS = "jpy"

# ランキング抽出のルール（index.html側に合わせる想定）
MIN_VOL_JPY = float(os.getenv("MIN_VOL_JPY", "500000000"))  # 5億円
TOP_N = 3

# ステーブル系（出来高(アルト) から除外・上昇率補完時の除外の参考）
# ※新しいステーブルが増えやすいので、symbol ベースで広めに除外
STABLE_SYMBOLS = {
    "usdt", "usdc", "dai", "busd", "tusd", "usdp", "gusd",
    "fdusd", "usde", "susde", "usds", "usdy",
    "usd1", "usdd", "usdm", "eurt", "eurs", "eurc",
}

MAJOR_EXCLUDE_FOR_ALT_VOL = {"btc", "eth"}  # Vol(アルト)から除外

HEADERS = {
    "User-Agent": "coinrader-bot/1.0",
    "Accept": "application/json",
}


# -----------------------------
# Helpers
# -----------------------------
def cg_headers() -> Dict[str, str]:
    h = dict(HEADERS)
    if CG_DEMO_KEY:
        # CoinGecko Demo API Key header
        h["x-cg-demo-api-key"] = CG_DEMO_KEY
    return h


def safe_num(x: Any) -> Optional[float]:
    try:
        v = float(x)
        if v != v:  # NaN
            return None
        return v
    except Exception:
        return None


def fmt_pct(x: Optional[float], digits: int = 1) -> str:
    if x is None:
        return "—"
    sign = "+" if x >= 0 else ""
    return f"{sign}{x:.{digits}f}%"


def fmt_jpy_yoku(x: Optional[float]) -> str:
    """ざっくり億円表記（例: 2413.5億円）"""
    if x is None:
        return "—"
    oku = x / 1e8
    return f"{oku:.1f}億円"


def today_yyyymmdd_jst() -> str:
    jst = dt.timezone(dt.timedelta(hours=9))
    return dt.datetime.now(jst).strftime("%Y%m%d")


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


# -----------------------------
# Fetchers
# -----------------------------
def fetch_json(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    r = requests.get(url, params=params, headers=cg_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def load_top250() -> List[Dict[str, Any]]:
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": VS,
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h",
    }
    data = fetch_json(url, params)
    return data if isinstance(data, list) else []


def load_trending() -> List[Dict[str, Any]]:
    url = "https://api.coingecko.com/api/v3/search/trending"
    data = fetch_json(url)
    out: List[Dict[str, Any]] = []
    coins = (data or {}).get("coins") if isinstance(data, dict) else None
    if isinstance(coins, list):
        for c in coins:
            item = c.get("item", {}) if isinstance(c, dict) else {}
            if not isinstance(item, dict):
                continue
            out.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "symbol": (item.get("symbol") or "").upper(),
                "market_cap_rank": item.get("market_cap_rank"),
            })
    return out


# -----------------------------
# Ranking logic (align to index)
# -----------------------------
def is_stable_symbol(sym: str) -> bool:
    return sym.lower() in STABLE_SYMBOLS


def build_gainers_24h(markets: List[Dict[str, Any]], n: int = TOP_N, min_vol_jpy: float = MIN_VOL_JPY) -> List[Dict[str, Any]]:
    """
    上昇率TOP: 出来高>=しきい値を優先。
    足りない場合は、出来高が大きい順で補完（ただしステーブル系は除外）。
    """
    rows: List[Dict[str, Any]] = []
    for c in markets:
        sym = (c.get("symbol") or "").upper()
        pc = safe_num(c.get("price_change_percentage_24h"))
        vol = safe_num(c.get("total_volume"))
        if sym == "" or pc is None or vol is None:
            continue
        if is_stable_symbol(sym):
            continue
        rows.append({
            "id": c.get("id"),
            "symbol": sym,
            "name": c.get("name"),
            "pc24": pc,
            "vol_jpy": vol,
            "mc_rank": c.get("market_cap_rank"),
        })

    # 1) vol>=threshold の中で上昇率降順
    pri = [r for r in rows if r["vol_jpy"] >= min_vol_jpy]
    pri.sort(key=lambda r: r["pc24"], reverse=True)

    picked: List[Dict[str, Any]] = pri[:n]

    # 2) 足りない分は（残り）出来高降順で補完
    if len(picked) < n:
        picked_syms = {r["symbol"] for r in picked}
        rest = [r for r in rows if r["symbol"] not in picked_syms]
        rest.sort(key=lambda r: r["vol_jpy"], reverse=True)
        picked.extend(rest[: max(0, n - len(picked))])

    return picked[:n]


def build_alt_volume(markets: List[Dict[str, Any]], n: int = TOP_N) -> List[Dict[str, Any]]:
    """
    出来高(アルト): BTC/ETH + ステーブル系を除外して出来高降順。
    """
    rows: List[Dict[str, Any]] = []
    for c in markets:
        sym = (c.get("symbol") or "").lower()
        if not sym:
            continue
        if sym in MAJOR_EXCLUDE_FOR_ALT_VOL:
            continue
        if sym in STABLE_SYMBOLS:
            continue
        vol = safe_num(c.get("total_volume"))
        if vol is None:
            continue
        rows.append({
            "id": c.get("id"),
            "symbol": sym.upper(),
            "name": c.get("name"),
            "vol_jpy": vol,
            "pc24": safe_num(c.get("price_change_percentage_24h")),
            "mc_rank": c.get("market_cap_rank"),
        })
    rows.sort(key=lambda r: r["vol_jpy"], reverse=True)
    return rows[:n]


def build_breadth_stats(markets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    index.html の「上位250の24h上昇/下落銘柄数」相当:
      - up/down/flat: price_change_percentage_24h の符号
      - avgChg: 平均（%）
      - medianChg: 中央値（%）
    """
    chgs: List[float] = []
    up = down = flat = 0
    for c in markets:
        pc = safe_num(c.get("price_change_percentage_24h"))
        if pc is None:
            continue
        chgs.append(pc)
        if pc > 0:
            up += 1
        elif pc < 0:
            down += 1
        else:
            flat += 1
    avg = sum(chgs) / len(chgs) if chgs else None
    # median
    med = None
    if chgs:
        chgs_sorted = sorted(chgs)
        mid = len(chgs_sorted) // 2
        if len(chgs_sorted) % 2 == 1:
            med = chgs_sorted[mid]
        else:
            med = (chgs_sorted[mid - 1] + chgs_sorted[mid]) / 2
    total = up + down + flat
    up_ratio = (up / (up + down) * 100) if (up + down) > 0 else None
    return {
        "up": up, "down": down, "flat": flat,
        "avgChg": avg, "medianChg": med,
        "total": total,
        "upRatio": up_ratio,
    }


def find_coin_by_symbol(markets: List[Dict[str, Any]], symbol_upper: str) -> Optional[Dict[str, Any]]:
    for c in markets:
        if (c.get("symbol") or "").upper() == symbol_upper.upper():
            return c
    return None


# -----------------------------
# Share HTML (OGP)
# -----------------------------
def build_share_html(date_yyyymmdd: str) -> str:
    # OGPは share 固定ページにし、画像は ogp.png を参照
    title = f"CoinRader - 今日の注目 {date_yyyymmdd[:4]}-{date_yyyymmdd[4:6]}-{date_yyyymmdd[6:]}"
    og_img = f"{SITE_URL}assets/og/ogp.png?v={date_yyyymmdd}"

    # NOTE: Twitterカードは `summary_large_image` が基本
    html = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta property="og:title" content="{title}">
<meta property="og:type" content="website">
<meta property="og:url" content="{SITE_URL}share/{date_yyyymmdd}.html">
<meta property="og:image" content="{og_img}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:image" content="{og_img}">
<meta http-equiv="refresh" content="0; url={SITE_URL}?v={date_yyyymmdd}">
</head>
<body>
<p>Redirecting… <a href="{SITE_URL}?v={date_yyyymmdd}">{SITE_URL}?v={date_yyyymmdd}</a></p>
</body>
</html>
"""
    return html


# -----------------------------
# Daily post text
# -----------------------------
def build_short_post(date_yyyymmdd: str, trend: List[Dict[str, Any]], gainers: List[Dict[str, Any]], vol_alt: List[Dict[str, Any]], share_url: str) -> str:
    d = f"{date_yyyymmdd[:4]}-{date_yyyymmdd[4:6]}-{date_yyyymmdd[6:]}"
    # 1️⃣2️⃣3️⃣（環境差異が出やすいので「絵文字そのもの」で入れる）
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

    trend_s = " ".join([f'{nums[i]} {trend[i]["symbol"]}' for i in range(min(len(trend), TOP_N))])
    up_s = " | ".join([f'{nums[i]} {gainers[i]["symbol"]} {fmt_pct(gainers[i]["pc24"], 1)}' for i in range(min(len(gainers), TOP_N))])
    vol_s = " ".join([f'{nums[i]} {vol_alt[i]["symbol"]}' for i in range(min(len(vol_alt), TOP_N))])

    # A案：3ブロックとも「横方向の位置を揃える」ため、改行 + 空行で視認性を優先
    return (
        f"【今日の注目 {d}】\n\n"
        f"🔥トレンド  {trend_s}\n\n"
        f"🚀上昇率(24h)  {up_s}\n\n"
        f"📊出来高(アルト)  {vol_s}\n\n"
        f"→ {share_url}\n"
        f"#暗号資産"
    )


def build_full_post_with_note(
    short_post: str,
    breadth: Dict[str, Any],
    trend: List[Dict[str, Any]],
    gainers: List[Dict[str, Any]],
    vol_alt: List[Dict[str, Any]],
    markets: List[Dict[str, Any]],
) -> str:
    # NOTE 下書き（有料詳細版用）
    up = breadth.get("up")
    down = breadth.get("down")
    avg = breadth.get("avgChg")
    up_ratio = breadth.get("upRatio")
    mood = "上昇優勢" if (up is not None and down is not None and up >= down) else "下落優勢"
    up_ratio_s = f"{round(up_ratio)}%" if isinstance(up_ratio, (int, float)) else "—"

    def coin_line(r: Dict[str, Any], kind: str) -> str:
        sym = r.get("symbol")
        c = find_coin_by_symbol(markets, sym) if sym else None
        if not c:
            # トレンドで top250外のケース
            return f"{sym}：top250外/データ未取得の可能性"
        pc = safe_num(c.get("price_change_percentage_24h"))
        vol = safe_num(c.get("total_volume"))
        mcr = c.get("market_cap_rank")
        vol_ok = (vol is not None and vol >= MIN_VOL_JPY)
        vol_ok_s = "✓" if vol_ok else "×"
        if kind == "trend":
            return f"{sym}：24h {fmt_pct(pc,1)} / 出来高 {fmt_jpy_yoku(vol)} / 時価総額#{mcr} / （CoinGeckoトレンド）"
        if kind == "up":
            return f"{sym}：24h {fmt_pct(pc,1)} / 出来高 {fmt_jpy_yoku(vol)} / 時価総額#{mcr} / 出来高しきい値({MIN_VOL_JPY/1e8:.1f}億円) {vol_ok_s}"
        if kind == "vol":
            return f"{sym}：24h {fmt_pct(pc,1)} / 出来高 {fmt_jpy_yoku(vol)} / 時価総額#{mcr}"
        return f"{sym}"

    trend_lines = "\n".join([f"{t['symbol']}：{coin_line(t,'trend')}" if t.get("symbol") else "—" for t in trend[:TOP_N]])
    up_lines = "\n".join([coin_line(g, "up") for g in gainers[:TOP_N]])
    vol_lines = "\n".join([coin_line(v, "vol") for v in vol_alt[:TOP_N]])

    memo = []
    if gainers:
        memo.append(f"{gainers[0]['symbol']}：上昇トップ。出来高と継続性を確認")
    if trend:
        memo.append(f"{trend[0]['symbol']}：トレンド上位。話題性の継続を確認")
    if vol_alt:
        memo.append(f"{vol_alt[0]['symbol']}：出来高上位。価格変動との連動を確認")
    memo = memo[:3]
    memo_lines = "\n".join(memo) if memo else "—"

    rules = (
        f"上昇率は出来高 {MIN_VOL_JPY/1e8:.1f}億円 以上を優先（不足時は出来高順で補完）\n"
        "ステーブル系は上昇率・出来高(アルト)から除外\n"
        "BTC/ETHは出来高(アルト)から除外"
    )

    return (
        f"{short_post}\n\n"
        "ここから有料（詳細版）\n\n"
        "今日のサマリー\n"
        f"市場ムード：{mood}（上昇 {up} / 下落 {down}、平均 {fmt_pct(avg,2)}、上昇比率 {up_ratio_s}）\n"
        "トレンド解説（上位3）\n"
        f"{trend_lines}\n"
        "上昇率解説（上位3）\n"
        f"{up_lines}\n"
        "出来高解説（アルト上位3）\n"
        f"{vol_lines}\n"
        "監視メモ（最大3）\n"
        f"{memo_lines}\n"
        "算出ルール（要約）\n"
        f"{rules}\n"
    )


# -----------------------------
# Snapshot for weekly
# -----------------------------
def write_snapshot(date_yyyymmdd: str, payload: Dict[str, Any]) -> None:
    out_dir = Path("data/daily")
    ensure_dir(out_dir)
    p = out_dir / f"{date_yyyymmdd}.json"
    # UTF-8（BOMなし）でOK。週次生成はPythonで読むため。
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    date_yyyymmdd = os.getenv("DATE_YYYYMMDD") or today_yyyymmdd_jst()
    share_url = f"{SITE_URL}share/{date_yyyymmdd}.html"

    markets = load_top250()
    trending = load_trending()

    # Trend: まず trending 上位から TOP_N
    trend = trending[:TOP_N]

    gainers = build_gainers_24h(markets, n=TOP_N, min_vol_jpy=MIN_VOL_JPY)
    vol_alt = build_alt_volume(markets, n=TOP_N)
    breadth = build_breadth_stats(markets)

    # Daily files
    short_post = build_short_post(date_yyyymmdd, trend, gainers, vol_alt, share_url)
    full_post = build_full_post_with_note(short_post, breadth, trend, gainers, vol_alt, markets)

    # Windows側での文字化け対策：utf-8-sig で書く
    Path("daily_post_short.txt").write_text(short_post, encoding="utf-8-sig")
    Path("daily_post_full.txt").write_text(full_post, encoding="utf-8-sig")
    Path("daily_share_url.txt").write_text(share_url, encoding="utf-8-sig")

    # Share page
    ensure_dir(Path("share"))
    share_html = build_share_html(date_yyyymmdd)
    Path("share") .joinpath(f"{date_yyyymmdd}.html").write_text(share_html, encoding="utf-8")

    # Snapshot（週次用）
    # BTC/ETH（価格系列は週次で使う）
    btc = find_coin_by_symbol(markets, "BTC")
    eth = find_coin_by_symbol(markets, "ETH")
    snapshot = {
        "date": date_yyyymmdd,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "site_url": SITE_URL,
        "rules": {
            "min_vol_jpy": MIN_VOL_JPY,
            "stable_symbols": sorted(STABLE_SYMBOLS),
            "exclude_alt_vol": sorted(MAJOR_EXCLUDE_FOR_ALT_VOL),
        },
        "breadth": breadth,
        "trend": trend,
        "gainers": gainers,
        "vol_alt": vol_alt,
        "btc": {
            "price_jpy": safe_num(btc.get("current_price")) if btc else None,
            "pc24": safe_num(btc.get("price_change_percentage_24h")) if btc else None,
        },
        "eth": {
            "price_jpy": safe_num(eth.get("current_price")) if eth else None,
            "pc24": safe_num(eth.get("price_change_percentage_24h")) if eth else None,
        },
    }
    write_snapshot(date_yyyymmdd, snapshot)

    print(short_post)
    print("\n---\n")
    print("wrote: daily_post_short.txt / daily_post_full.txt / daily_share_url.txt / share/*.html / data/daily/*.json")


if __name__ == "__main__":
    main()
