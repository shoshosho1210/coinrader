#!/usr/bin/env python3
# generate_daily_post_v2.py
# CoinRader: X投稿用デイリー集計（index系のランキングルールに合わせる）
from __future__ import annotations

import os
import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

BASE_URL = "https://api.coingecko.com/api/v3"

CG_DEMO_KEY = os.getenv("CG_DEMO_KEY", "").strip()   # Demo API key
VS = os.getenv("VS_CURRENCY", "jpy")                # indexはjpy想定
SITE_URL = os.getenv("SITE_URL", "https://coinrader.net/").strip().rstrip("/") + "/"
OGP_IMAGE_URL = os.getenv("OGP_IMAGE_URL", "https://coinrader.net/assets/og/ogp.png").strip()

# shareページ（Xカード展開用）を日付で切って生成する（例: /share/20260124.html）
SHARE_DIR = os.getenv("SHARE_DIR", "share").strip()
USE_SHARE_URL_IN_POST = os.getenv("USE_SHARE_URL_IN_POST", "1").strip() not in ("0", "false", "False")

TIMEOUT = 20

# 上昇率のノイズ対策（出来高下限を満たす銘柄を優先）
MIN_GAINERS_24H_VOLUME_JPY = int(os.getenv("MIN_GAINERS_24H_VOLUME_JPY", "500000000"))  # 5億円

RANK_EMOJI = ["1️⃣", "2️⃣", "3️⃣"]

# ===== stable / major 判定 =====
STABLE_IDS = {
    "tether", "usd-coin", "dai", "true-usd", "first-digital-usd", "ethena-usde",
    "frax", "pax-dollar", "paypal-usd", "gemini-dollar", "paxos-standard", "binance-usd", "liquity-usd",
}
STABLE_SYMBOLS = {"usdt", "usdc", "dai", "tusd", "usde", "fdusd", "pyusd", "gusd", "usdp", "busd", "lusd", "frax"}


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
    if sym and len(sym) <= 12:
        return sym
    # まれに symbol が長い/空のとき
    n = (name or "").strip()
    return (n[:12].upper() or "UNKNOWN")


def fmt_rank(items: List[str]) -> str:
    return " ".join([f"{i+1}.{s}" for i, s in enumerate(items)])


def vol_oku_jpy(v: float) -> float:
    # 1億円 = 1e8 JPY
    return v / 1e8


def fmt_oku_jpy(v: float) -> str:
    return f"{vol_oku_jpy(v):.1f}億円"


def build_share_page(date_str: str, site_base: str) -> Tuple[str, str]:
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


def build_gainers_top5(markets_top: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    base = [
        c for c in markets_top
        if isinstance(c.get("price_change_percentage_24h"), (int, float))
        and (not is_stable_coin(c))
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


def build_note_draft(
    today: str,
    post_url: str,
    share_url: str,
    trend_syms: List[str],
    gain_top: List[Dict[str, Any]],
    vol_alt_syms: List[str],
    markets_top: List[Dict[str, Any]],
) -> str:
    """noteに貼り付ける下書き（Markdown）を生成（短い解説も自動で埋める）。"""

    # symbol->market mapping (top250 only)
    by_sym: Dict[str, Dict[str, Any]] = {}
    for m in markets_top:
        s = (m.get("symbol") or "").upper()
        if s and s not in by_sym:
            by_sym[s] = m

    def get_m(sym: str) -> Dict[str, Any] | None:
        return by_sym.get(sym.upper())

    def pct24(m: Dict[str, Any] | None) -> float | None:
        if not m:
            return None
        v = m.get("price_change_percentage_24h_in_currency")
        if v is None:
            v = m.get("price_change_percentage_24h")
        try:
            return float(v)
        except Exception:
            return None

    def voljpy(m: Dict[str, Any] | None) -> float | None:
        if not m:
            return None
        try:
            return float(m.get("total_volume"))
        except Exception:
            return None

    def mcap_rank(m: Dict[str, Any] | None) -> int | None:
        if not m:
            return None
        v = m.get("market_cap_rank")
        try:
            return int(v)
        except Exception:
            return None

    def explain_line(sym: str, kind: str) -> str:
        m = get_m(sym)
        p = pct24(m)
        v = voljpy(m)
        r = mcap_rank(m)
        parts: List[str] = []
        if p is not None:
            parts.append(f"24h {p:+.1f}%")
        if v is not None:
            parts.append(f"出来高 {fmt_oku_jpy(v)}")
        if r is not None:
            parts.append(f"時価総額#{r}")
        if not parts:
            return f"{sym}：top250外/データ未取得の可能性"
        # kind-specific tail
        if kind == "trend":
            parts.append("（CoinGeckoトレンド）")
        elif kind == "up":
            if v is not None:
                ok = "✓" if v >= MIN_GAINERS_24H_VOLUME_JPY else "×"
                parts.append(f"出来高しきい値({fmt_oku_jpy(float(MIN_GAINERS_24H_VOLUME_JPY))}) {ok}")
        return f"{sym}：" + " / ".join(parts)

    # Market mood (top250, non-stables)
    changes: List[float] = []
    up_cnt = 0
    dn_cnt = 0
    for m in markets_top:
        if is_stable_coin(m):
            continue
        p = pct24(m)
        if p is None:
            continue
        changes.append(p)
        if p >= 0:
            up_cnt += 1
        else:
            dn_cnt += 1
    mood_line = ""
    if changes:
        avg = sum(changes) / len(changes)
        ratio = (up_cnt / max(1, (up_cnt + dn_cnt))) * 100.0
        mood = "上昇優勢" if up_cnt >= dn_cnt else "下落優勢"
        mood_line = f"- 市場ムード：{mood}（上昇 {up_cnt} / 下落 {dn_cnt}、平均 {avg:+.2f}%、上昇比率 {ratio:.0f}%）"
    else:
        mood_line = "- 市場ムード：算出できませんでした（データ不足）"

    # Up top3 symbols
    up_syms = [safe_sym(x.get("name", ""), x.get("symbol", "")) for x in gain_top[:3]]

    # Overlaps for watch memo
    tset = set([s.upper() for s in trend_syms[:3]])
    uset = set([s.upper() for s in up_syms])
    vset = set([s.upper() for s in vol_alt_syms[:3]])

    watch: List[str] = []
    for s in [*trend_syms[:3], *up_syms, *vol_alt_syms[:3]]:
        su = s.upper()
        if su in tset and su in vset:
            watch.append(f"{s}：トレンド×出来高で注目度高め（過熱には注意）")
        elif su in uset and su in vset:
            watch.append(f"{s}：上昇×出来高（急騰/急落の反動に注意）")
    # fill if empty
    if not watch:
        if up_syms:
            watch.append(f"{up_syms[0]}：上昇トップ。出来高と継続性を確認")
        if trend_syms:
            watch.append(f"{trend_syms[0]}：トレンド上位。話題性の継続を確認")
        if vol_alt_syms:
            watch.append(f"{vol_alt_syms[0]}：出来高上位。価格変動との連動を確認")
    watch = watch[:3]

    # Build the free blocks (same as X post)
    free_lines = [
        f"【今日の注目 {today}】",
        "",
        "🔥トレンド",
        f"{RANK_EMOJI[0]} {trend_syms[0]}" if len(trend_syms) > 0 else f"{RANK_EMOJI[0]} -",
        f"{RANK_EMOJI[1]} {trend_syms[1]}" if len(trend_syms) > 1 else f"{RANK_EMOJI[1]} -",
        f"{RANK_EMOJI[2]} {trend_syms[2]}" if len(trend_syms) > 2 else f"{RANK_EMOJI[2]} -",
        "",
        "🚀上昇率(24h)",
        f"{RANK_EMOJI[0]} {up_syms[0]} {pct24(get_m(up_syms[0])):+.1f}%" if len(up_syms) > 0 and pct24(get_m(up_syms[0])) is not None else f"{RANK_EMOJI[0]} {up_syms[0]}" if len(up_syms)>0 else f"{RANK_EMOJI[0]} -",
        f"{RANK_EMOJI[1]} {up_syms[1]} {pct24(get_m(up_syms[1])):+.1f}%" if len(up_syms) > 1 and pct24(get_m(up_syms[1])) is not None else f"{RANK_EMOJI[1]} {up_syms[1]}" if len(up_syms)>1 else f"{RANK_EMOJI[1]} -",
        f"{RANK_EMOJI[2]} {up_syms[2]} {pct24(get_m(up_syms[2])):+.1f}%" if len(up_syms) > 2 and pct24(get_m(up_syms[2])) is not None else f"{RANK_EMOJI[2]} {up_syms[2]}" if len(up_syms)>2 else f"{RANK_EMOJI[2]} -",
        "",
        "📊出来高(アルト)",
        f"{RANK_EMOJI[0]} {vol_alt_syms[0]}" if len(vol_alt_syms) > 0 else f"{RANK_EMOJI[0]} -",
        f"{RANK_EMOJI[1]} {vol_alt_syms[1]}" if len(vol_alt_syms) > 1 else f"{RANK_EMOJI[1]} -",
        f"{RANK_EMOJI[2]} {vol_alt_syms[2]}" if len(vol_alt_syms) > 2 else f"{RANK_EMOJI[2]} -",
        "",
        f"→ {post_url}",
    ]

    paid_lines = [
        "----",
        "ここから有料（詳細版）",
        "",
        "## 今日のサマリー",
        mood_line,
        "",
        "## トレンド解説（上位3）",
        f"- {explain_line(trend_syms[0], 'trend')}" if len(trend_syms) > 0 else "- -",
        f"- {explain_line(trend_syms[1], 'trend')}" if len(trend_syms) > 1 else "- -",
        f"- {explain_line(trend_syms[2], 'trend')}" if len(trend_syms) > 2 else "- -",
        "",
        "## 上昇率解説（上位3）",
        f"- {explain_line(up_syms[0], 'up')}" if len(up_syms) > 0 else "- -",
        f"- {explain_line(up_syms[1], 'up')}" if len(up_syms) > 1 else "- -",
        f"- {explain_line(up_syms[2], 'up')}" if len(up_syms) > 2 else "- -",
        "",
        "## 出来高解説（アルト上位3）",
        f"- {explain_line(vol_alt_syms[0], 'vol')}" if len(vol_alt_syms) > 0 else "- -",
        f"- {explain_line(vol_alt_syms[1], 'vol')}" if len(vol_alt_syms) > 1 else "- -",
        f"- {explain_line(vol_alt_syms[2], 'vol')}" if len(vol_alt_syms) > 2 else "- -",
        "",
        "## 監視メモ（最大3）",
        *[f"- {w}" for w in watch],
        "",
        "## 算出ルール（要約）",
        f"- 上昇率は出来高 {fmt_oku_jpy(float(MIN_GAINERS_24H_VOLUME_JPY))} 以上を優先（不足時は出来高順で補完）",
        "- ステーブル系は上昇率・出来高(アルト)から除外",
        "- BTC/ETHは出来高(アルト)から除外",
        "",
        f"（リンク）{share_url}",
    ]

    # note貼り付け用Markdown
    return "\n".join([*free_lines, "", *paid_lines]).strip() + "\n"


def build_post() -> Tuple[str, str, str, str, str]:
    # --- Trending TOP（/search/trending） ---
    trending = cg_get("/search/trending")
    trend_items: List[str] = []
    for c in (trending.get("coins") or [])[:10]:
        item = c.get("item") or {}
        name = item.get("name", "")
        sym = item.get("symbol", "")
        if name or sym:
            trend_items.append(safe_sym(name, sym))
        if len(trend_items) >= 5:
            break

    # --- markets（時価総額上位250 / vs=jpy） ---
    markets_top: List[Dict[str, Any]] = cg_get("/coins/markets", {
        "vs_currency": VS,
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h",
    }) or []

    # --- 上昇率TOP5（出来高しきい値を優先） ---
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
         and (not is_btc_or_eth(c))],
        key=lambda x: x.get("total_volume") or 0,
        reverse=True
    )[:5]

    vol_all_syms = [safe_sym(c.get("name", ""), c.get("symbol", "")) for c in volume_all]
    vol_alt_syms = [safe_sym(c.get("name", ""), c.get("symbol", "")) for c in volume_alt]

    # --- Date (JST) ---
    jst = dt.timezone(dt.timedelta(hours=9))
    today = dt.datetime.now(jst).strftime("%Y-%m-%d")
    share_url, share_path = build_share_page(today, SITE_URL)
    post_url = share_url if USE_SHARE_URL_IN_POST else SITE_URL

    # Full (plain)
    full = (
        f"【今日の注目 {today}】\n"
        f"トレンド: {fmt_rank(trend_items)}\n"
        f"上昇率(24h): {fmt_rank(gain_top5_full)}\n"
        f"出来高(全体): {fmt_rank(vol_all_syms)}\n"
        f"出来高(アルト): {fmt_rank(vol_alt_syms)}\n"
        f"→ {post_url}\n"
        f"#暗号資産"
    )

    # Short (ranked, no extra note line)
    def build_short(n_trend: int = 3, n_up: int = 3, n_vol: int = 3) -> str:
        up_parts: List[str] = []
        for x in gain_top[:n_up]:
            sym = safe_sym(x.get("name", ""), x.get("symbol", ""))
            pct = float(x.get("price_change_percentage_24h", 0) or 0)
            up_parts.append(f"{sym} {pct:+.1f}%")

        # align: rank emojis appear on their own line entries
        short_lines = [
            f"【今日の注目 {today}】",
            "🔥トレンド",
            *( [f"{RANK_EMOJI[i]} {trend_items[i]}" for i in range(min(n_trend, len(trend_items)))] ),
            "",
            "🚀上昇率(24h)",
            *( [f"{RANK_EMOJI[i]} {up_parts[i]}" for i in range(min(n_up, len(up_parts)))] ),
            "",
            "📊出来高(アルト)",
            *( [f"{RANK_EMOJI[i]} {vol_alt_syms[i]}" for i in range(min(n_vol, len(vol_alt_syms)))] ),
            f"→ {post_url} #暗号資産",
        ]
        return "\n".join(short_lines)

    short = build_short()

    # 280字超なら段階的に短縮
    if len(short) > 280:
        short = build_short(n_trend=2, n_up=2, n_vol=2)
    if len(short) > 280:
        # 最終手段：1行圧縮
        up2 = " / ".join([
            f"{safe_sym(x.get('name',''), x.get('symbol',''))}{float(x.get('price_change_percentage_24h',0) or 0):+.1f}%"
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

    # note draft
    note_md = build_note_draft(
        today=today,
        post_url=post_url,
        share_url=share_url,
        trend_syms=trend_items,
        gain_top=gain_top,
        vol_alt_syms=vol_alt_syms,
        markets_top=markets_top,
    )

    return full, short, note_md, share_url, share_path


if __name__ == "__main__":
    full, short, note_md, share_url, share_path = build_post()

    # Windowsのメモ帳対策：UTF-8(BOM)で保存
    Path("daily_post_full.txt").write_text(full, encoding="utf-8-sig")
    Path("daily_post_short.txt").write_text(short, encoding="utf-8-sig")
    Path("daily_share_url.txt").write_text(share_url, encoding="utf-8-sig")
    Path("daily_note_draft.md").write_text(note_md, encoding="utf-8-sig")

    print(full)
    print("\n--- short ---\n")
    print(short)
    print("\n--- note draft ---\n")
    print(note_md)
    print("\n--- share ---\n")
    print(share_url)
    print(f"(generated: {share_path})")
