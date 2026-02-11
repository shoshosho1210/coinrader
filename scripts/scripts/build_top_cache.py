#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "top_cache.json"


def _get_json(url: str, *, params: dict | None = None, headers: dict | None = None, timeout: int = 20):
    if params:
        qs = urlencode(params)
        sep = '&' if '?' in url else '?'
        url = f"{url}{sep}{qs}"
    req = Request(url, headers=headers or {})
    with urlopen(req, timeout=timeout) as r:
        raw = r.read().decode('utf-8')
    return json.loads(raw)


def build_payload() -> dict:
    api_key = os.getenv("CR_COINGECKO_KEY") or os.getenv("CG_DEMO_KEY") or ""
    headers = {"x-cg-demo-api-key": api_key} if api_key else None

    prices = _get_json(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": "bitcoin,ethereum", "vs_currencies": "jpy"},
        headers=headers,
    )
    global_data = _get_json("https://api.coingecko.com/api/v3/global", headers=headers)
    fng = _get_json("https://api.alternative.me/fng/", params={"limit": 1, "format": "json"})
    fx = _get_json("https://open.er-api.com/v6/latest/USD")

    fg_row = (fng.get("data") or [{}])[0]

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "ttl_seconds": 300,
        "btc_jpy": prices.get("bitcoin", {}).get("jpy"),
        "eth_jpy": prices.get("ethereum", {}).get("jpy"),
        "btc_dom": ((global_data.get("data") or {}).get("market_cap_percentage") or {}).get("btc"),
        "fear_greed": {
            "value": fg_row.get("value"),
            "label": fg_row.get("value_classification") or "",
        },
        "usd_jpy": (fx.get("rates") or {}).get("JPY"),
    }


def main() -> int:
    prev = None
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            prev = None

    try:
        payload = build_payload()
        status = "fresh"
    except Exception as e:
        if prev is None:
            payload = {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "ttl_seconds": 300,
                "btc_jpy": None,
                "eth_jpy": None,
                "btc_dom": None,
                "fear_greed": {"value": None, "label": ""},
                "usd_jpy": None,
                "stale": True,
                "stale_reason": str(e),
            }
            status = "empty-stale"
        else:
            payload = dict(prev)
            payload["stale"] = True
            payload["stale_reason"] = str(e)
            payload["stale_at"] = datetime.now(timezone.utc).isoformat()
            status = "stale"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote {OUT} ({status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
