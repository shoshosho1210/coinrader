#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "index.html"
OUT_JSON = ROOT / "data" / "top_seed.json"

STABLE_IDS = {
    "tether", "usd-coin", "dai", "true-usd", "first-digital-usd", "ethena-usde",
    "frax", "pax-dollar", "paypal-usd", "gemini-dollar", "paxos-standard", "binance-usd", "liquity-usd",
}
STABLE_SYMBOLS = {"usdt", "usdc", "dai", "tusd", "usde", "fdusd", "pyusd", "gusd", "usdp", "busd", "lusd", "frax"}


def _get_json(url: str, *, params: dict | None = None):
    if params:
        qs = urlencode(params)
        url = f"{url}{'&' if '?' in url else '?'}{qs}"
    req = Request(url, headers={"accept": "application/json"})
    with urlopen(req, timeout=20) as res:
        return json.loads(res.read().decode("utf-8"))


def is_stable(c: dict) -> bool:
    cid = (c.get("id") or "").lower()
    sym = (c.get("symbol") or "").lower()
    name = (c.get("name") or "").lower()
    return cid in STABLE_IDS or sym in STABLE_SYMBOLS or ("stable" in name and "usd" in name)


def yen(n: float | None) -> str:
    if not isinstance(n, (int, float)):
        return "-"
    return f"¥{n:,.0f}"


def pct(n: float | None) -> str:
    if not isinstance(n, (int, float)):
        return "-"
    return f"{n:+.1f}%"


def fallback_img(symbol: str) -> str:
    s = (symbol or "coin").lower()
    return f"https://cryptoicon-api.pages.dev/api/icon/{s}"


COIN_PAGE_MAP = {"bitcoin": "/coins/bitcoin/", "ethereum": "/coins/ethereum/", "solana": "/coins/solana/", "ripple": "/coins/xrp/"}


def coin_href(c: dict) -> str:
    cid = c.get("id") or ""
    return COIN_PAGE_MAP.get(cid, f"https://www.coingecko.com/en/coins/{cid}")


def coin_li(c: dict, *, with_rank: bool = False) -> str:
    rank = c.get("market_cap_rank")
    rank_html = f'<span class="summary-rank">#{rank}</span>' if with_rank and rank else ""
    return (
        "<li class=\"summary-li\">"
        f"<a class=\"summary-coin\" href=\"{coin_href(c)}\" aria-label=\"{c.get('name','')}\">"
        f"<span class=\"name\">{rank_html}{c.get('name','-')}</span>"
        f"<span class=\"val\">{pct(c.get('price_change_percentage_24h'))}</span>"
        "</a></li>"
    )


def card(c: dict, idx: int, mode: str) -> str:
    cls = "up" if (c.get("price_change_percentage_24h") or 0) >= 0 else "down"
    chg_cls = "positive" if (c.get("price_change_percentage_24h") or 0) >= 0 else "negative"
    sym = (c.get("symbol") or "").upper()
    return (
        f'<div class="card {cls}">' 
        f'<div class="rank-badge rank-{idx if idx <=3 else 0}">#{idx}</div>'
        '<div class="card-header">'
        '<div class="coin-header">'
        f'<img class="coin-icon" loading="lazy" src="{c.get("image") or fallback_img(sym)}" alt="{sym}">'
        f'<div><div class="coin-name">{c.get("name","-")}</div><div class="coin-symbol">{sym}</div></div>'
        '</div>'
        f'<div><div class="price">{yen(c.get("current_price"))}</div><div class="change {chg_cls}">{pct(c.get("price_change_percentage_24h"))}</div></div>'
        '</div></div>'
    )


def load_local_markets() -> list[dict]:
    out = []
    for sym in ("btc","eth","sol","xrp"):
        fp = ROOT / "data" / "coins" / f"{sym}.json"
        if not fp.exists():
            continue
        row = json.loads(fp.read_text(encoding="utf-8")).get("market") or {}
        if row:
            out.append(row)
    return out


def fetch_seed() -> dict:
    try:
        markets = _get_json(
        "https://api.coingecko.com/api/v3/coins/markets",
        params={
            "vs_currency": "jpy",
            "order": "market_cap_desc",
            "per_page": 250,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h,7d",
        },
    )

        trend_raw = _get_json("https://api.coingecko.com/api/v3/search/trending")
        trend_items = ((trend_raw or {}).get("coins") or [])[:5]
        trend_ids = [((x.get("item") or {}).get("id")) for x in trend_items]
        trend_ids = [x for x in trend_ids if x]
        by_id = {c.get("id"): c for c in markets}
        trending = [by_id[i] for i in trend_ids if i in by_id][:5]
    except Exception:
        markets = load_local_markets()
        by_id = {c.get("id"): c for c in markets}
        preferred = ["bitcoin", "ethereum", "solana", "ripple"]
        trending = [by_id[x] for x in preferred if x in by_id]

    gainers = [c for c in markets if isinstance(c.get("price_change_percentage_24h"), (int, float)) and not is_stable(c)]
    gainers = sorted(gainers, key=lambda x: x.get("price_change_percentage_24h", -999), reverse=True)[:5]

    by_vol = [c for c in markets if isinstance(c.get("total_volume"), (int, float))]
    volume = sorted(by_vol, key=lambda x: x.get("total_volume", 0), reverse=True)[:5]

    alt_volume = [
        c for c in by_vol
        if (c.get("id") not in {"bitcoin", "ethereum"}) and (c.get("symbol", "").lower() not in {"btc", "eth"})
    ]
    alt_volume = sorted(alt_volume, key=lambda x: x.get("total_volume", 0), reverse=True)[:5]

    mcap_top = markets[:20]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trending": trending,
        "gainers": gainers,
        "volume": volume,
        "alt_volume": alt_volume,
        "mcap_top": mcap_top,
    }


def render(seed: dict) -> dict[str, str]:
    trend_list = "".join(coin_li(c) for c in seed["trending"][:3])
    up_list = "".join(coin_li(c) for c in seed["gainers"][:3])
    mcap_list = "".join(coin_li(c, with_rank=True) for c in seed["mcap_top"][:5])

    trend_grid = "".join(card(c, i + 1, "trend") for i, c in enumerate(seed["trending"][:5]))
    gain_grid = "".join(card(c, i + 1, "gainers") for i, c in enumerate(seed["gainers"][:5]))
    vol_grid = "".join(card(c, i + 1, "volume") for i, c in enumerate(seed["volume"][:5]))
    alt_grid = "".join(card(c, i + 1, "alt") for i, c in enumerate(seed["alt_volume"][:5]))

    mcap_rows = []
    for c in seed["mcap_top"]:
        mcap_rows.append(
            "<tr>"
            f"<td>{c.get('name','-')} <span class='muted'>{(c.get('symbol') or '').upper()}</span></td>"
            f"<td>{yen(c.get('current_price'))}</td>"
            f"<td>{pct(c.get('price_change_percentage_24h'))}</td>"
            f"<td>{pct(c.get('price_change_percentage_7d_in_currency'))}</td>"
            f"<td>{yen(c.get('market_cap'))}</td>"
            "<td class='col-optional'>-</td>"
            "<td style='text-align:center;'>-</td>"
            f"<td>{yen(c.get('total_volume'))}</td>"
            "</tr>"
        )

    generated = (seed.get("generated_at") or datetime.now(timezone.utc).isoformat()).replace("T", " ")[:16] + " UTC"
    note = f'<div class="msg" style="grid-column:1 / -1; font-size:11px;">初期表示は事前生成データ（{generated}）です。表示後に最新化します。</div>'

    return {
        "summaryTrendList": trend_list,
        "summaryUpList": up_list,
        "summaryMcapTopList": mcap_list,
        "grid-trend": trend_grid + note,
        "grid-gainers": gain_grid + note,
        "grid-volume": vol_grid + note,
        "grid-alt-volume": alt_grid + note,
        "mcapTableBody": "".join(mcap_rows),
    }


def _replace_one(text: str, pattern: str, replacement: str) -> str:
    out, n = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
    if n != 1:
        raise RuntimeError(f"target not found for pattern: {pattern}")
    return out


def apply_seed_to_index(html: str, snippets: dict[str, str]) -> str:
    html = _replace_one(
        html,
        r'<ol class="summary-ol" id="summaryTrendList">.*?</ol>',
        f'<ol class="summary-ol" id="summaryTrendList">{snippets["summaryTrendList"]}</ol>',
    )
    html = _replace_one(
        html,
        r'<ol class="summary-ol" id="summaryUpList">.*?</ol>',
        f'<ol class="summary-ol" id="summaryUpList">{snippets["summaryUpList"]}</ol>',
    )
    html = _replace_one(
        html,
        r'<ol class="summary-ol" id="summaryMcapTopList">.*?</ol>',
        f'<ol class="summary-ol" id="summaryMcapTopList">{snippets["summaryMcapTopList"]}</ol>',
    )
    html = _replace_one(
        html,
        r'<div class="grid" id="grid-trend">.*?</div>\s*</section>',
        f'<div class="grid" id="grid-trend">{snippets["grid-trend"]}</div>\n</section>',
    )
    html = _replace_one(
        html,
        r'<div class="grid" id="grid-gainers">.*?</div>\s*</section>',
        f'<div class="grid" id="grid-gainers">{snippets["grid-gainers"]}</div>\n</section>',
    )
    html = _replace_one(
        html,
        r'<div class="grid" id="grid-volume">.*?</div>\s*</section>',
        f'<div class="grid" id="grid-volume">{snippets["grid-volume"]}</div>\n</section>',
    )
    html = _replace_one(
        html,
        r'<div class="grid" id="grid-alt-volume">.*?</div>\s*</section>',
        f'<div class="grid" id="grid-alt-volume">{snippets["grid-alt-volume"]}</div>\n</section>',
    )
    html = _replace_one(
        html,
        r'<tbody id="mcapTableBody">.*?</tbody>',
        f'<tbody id="mcapTableBody">{snippets["mcapTableBody"]}</tbody>',
    )
    return html


def main() -> int:
    seed = fetch_seed()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")

    snippets = render(seed)
    html = INDEX_HTML.read_text(encoding="utf-8")
    html = apply_seed_to_index(html, snippets)
    INDEX_HTML.write_text(html, encoding="utf-8")
    print("[OK] updated index.html and data/top_seed.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
