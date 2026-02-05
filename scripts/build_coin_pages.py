#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPL_DIR = ROOT / "templates"
OUT_COINS_DIR = ROOT / "coins"
SITE_ORIGIN = "https://coinrader.net"

COINS = [
    {"symbol": "btc", "coin_id": "bitcoin",  "name": "Bitcoin"},
    {"symbol": "eth", "coin_id": "ethereum", "name": "Ethereum"},
    {"symbol": "sol", "coin_id": "solana",   "name": "Solana"},
    {"symbol": "xrp", "coin_id": "ripple",   "name": "XRP"},
]

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")

def build_coins_index() -> str:
    items = "\n".join(
        [f"<li><a href='/coins/{c['symbol']}/'>{c['name']} ({c['symbol'].upper()})</a></li>" for c in COINS]
    )
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Coins | CoinRader</title>
  <meta name="description" content="主要暗号資産の銘柄別ページ一覧。" />
  <link rel="canonical" href="{SITE_ORIGIN}/coins/" />
  <style>
    :root {{ color-scheme: dark; }}
    body {{ margin:0; font-family: system-ui,-apple-system,Segoe UI,Roboto,Helvetica Neue,Arial; background:#0f172a; color:#e5e7eb; }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 20px 16px 40px; }}
    a {{ color:#7dd3fc; text-decoration:none; }}
    a:hover {{ text-decoration: underline; }}
    .h1 {{ font-size: 22px; font-weight: 800; margin: 10px 0 6px; }}
    .muted {{ color:#94a3b8; }}
    ul {{ line-height:1.9; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="muted"><a href="/">トップ</a> / <span class="muted">Coins</span></div>
    <h1 class="h1">Coins</h1>
    <div class="muted">銘柄別ページ一覧。</div>
    <div style="margin-top:14px;">
      <ul>
        {items}
      </ul>
    </div>
  </div>
</body>
</html>
"""

def render_coin_page(tmpl: str, c: dict) -> str:
    s = tmpl
    s = s.replace("{{SYMBOL}}", c["symbol"])
    s = s.replace("{{SYMBOL_UPPER}}", c["symbol"].upper())
    s = s.replace("{{COIN_ID}}", c["coin_id"])
    s = s.replace("{{NAME}}", c["name"])
    return s

def main() -> None:
    tmpl_path = TEMPL_DIR / "coin_template.html"
    if not tmpl_path.exists():
        raise SystemExit(f"Missing template: {tmpl_path}")

    tmpl = read_text(tmpl_path)

    write_text(OUT_COINS_DIR / "index.html", build_coins_index())

    for c in COINS:
        html = render_coin_page(tmpl, c)
        write_text(OUT_COINS_DIR / c["symbol"] / "index.html", html)

    print(f"[OK] Generated coins pages: {OUT_COINS_DIR} (count={len(COINS)})")

if __name__ == "__main__":
    main()
