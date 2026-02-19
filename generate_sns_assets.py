#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_sns_assets_v6_1.py

Purpose:
- Generate 3 SNS text assets from CoinRader daily JSON (and optionally intraday stable JSON):
  1) daily_post_short.txt       : X main post (NO URL / NO hashtags)
  2) daily_post_self_reply.txt  : Self-reply (URL only here)
  3) daily_post_en.txt          : English material for replying to global influencers

Design goals:
- Backward compatible: try multiple JSON paths, gracefully fallback with "--".
- Minimal assumptions about JSON schema: extract values with heuristics.
- Keep the main post readable within X limits (soft 280 chars target).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

JST = _dt.timezone(_dt.timedelta(hours=9))

# ---------------------------
# Utilities
# ---------------------------

def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def load_json_first(paths: Iterable[Path]) -> Tuple[Optional[Dict[str, Any]], Optional[Path]]:
    for p in paths:
        try:
            if p.exists():
                return _read_json(p), p
        except Exception:
            continue
    return None, None

def _get(d: Dict[str, Any], *keys: str, default=None):
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

def _first_present(*vals):
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        return v
    return None

def _as_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        s = s.replace(",", "")
        # percent like "-1.2%"
        s = s.replace("%", "")
        return float(s)
    except Exception:
        return None

def _as_int(x) -> Optional[int]:
    f = _as_float(x)
    if f is None:
        return None
    return int(round(f))

def _fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "--"
    # keep 1 decimal
    return f"{x:+.1f}%"

def _fmt_price_jpy(x: Optional[float]) -> str:
    if x is None:
        return "--"
    # Japanese style: 万円 if large
    if x >= 1_000_000:
        man = x / 10_000
        return f"¥{man:.1f}万"
    return f"¥{int(round(x)):,}"

def _compact(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s

def _truncate_x(s: str, max_chars: int = 275) -> str:
    """
    Soft truncate for X. Leave a little margin for manual edits.
    """
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1].rstrip() + "…"

def _today_jst() -> _dt.date:
    return _dt.datetime.now(tz=JST).date()

def _format_date_label(date_obj: _dt.date) -> str:
    return date_obj.strftime("%m/%d")

# ---------------------------
# Extraction (schema-agnostic)
# ---------------------------

def extract_metrics(daily: Dict[str, Any], stable: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Try to extract:
    - date (JST)
    - btc_change_pct_24h
    - fgi
    - rsi
    - market_mode_label (optional)
    - signal_stable / signal_overall
    - score_overall (optional)
    """
    out: Dict[str, Any] = {}

    # date
    date_str = _first_present(
        _get(daily, "summary", "date"),
        _get(daily, "date"),
        _get(daily, "ts"),
        _get(daily, "generated_at"),
    )
    date_obj = None
    if isinstance(date_str, str):
        try:
            # accept YYYYMMDD
            if re.fullmatch(r"\d{8}", date_str):
                date_obj = _dt.datetime.strptime(date_str, "%Y%m%d").date()
            else:
                # ISO
                date_obj = _dt.datetime.fromisoformat(date_str.replace("Z", "+00:00")).astimezone(JST).date()
        except Exception:
            date_obj = None
    out["date"] = date_obj or _today_jst()

    # signal + score
    out["signal"] = _first_present(
        _get(stable or {}, "signal_stable"),
        _get(daily, "summary", "signal_overall"),
        _get(daily, "signal_overall"),
        _get(daily, "summary", "signal"),
    )
    out["score"] = _first_present(
        _get(stable or {}, "score_overall"),
        _get(daily, "summary", "score_overall"),
        _get(daily, "score_overall"),
    )

    out["market_mode_label"] = _first_present(
        _get(daily, "summary", "market_mode_label"),
        _get(daily, "summary", "market_mode"),
        _get(daily, "market_mode_label"),
        _get(stable or {}, "phase_label"),
    )

    # BTC change / RSI / FGI – many possible schemas
    btc = None
    for key in ("btc", "BTC", "bitcoin", "Bitcoin"):
        if isinstance(daily.get(key), dict):
            btc = daily[key]
            break

    out["btc_change_pct_24h"] = _first_present(
        _get(daily, "btc_change_pct_24h"),
        _get(daily, "summary", "btc_change_pct_24h"),
        _get(daily, "summary", "btc", "change_pct_24h"),
        _get(btc or {}, "change_pct_24h"),
        _get(btc or {}, "change24h"),
        _get(btc or {}, "pct_change_24h"),
    )

    out["btc_price_jpy"] = _first_present(
        _get(daily, "btc_price_jpy"),
        _get(daily, "summary", "btc_price_jpy"),
        _get(daily, "summary", "btc", "price_jpy"),
        _get(btc or {}, "price_jpy"),
        _get(btc or {}, "price"),
    )

    out["rsi"] = _first_present(
        _get(daily, "rsi"),
        _get(daily, "summary", "rsi"),
        _get(daily, "summary", "btc", "rsi"),
        _get(btc or {}, "rsi"),
        _get(btc or {}, "rsi14"),
        _get(daily, "indicators", "rsi"),
    )

    out["fgi"] = _first_present(
        _get(daily, "fear_greed"),
        _get(daily, "summary", "fear_greed"),
        _get(daily, "summary", "fgi"),
        _get(daily, "fgi"),
        _get(daily, "indicators", "fear_greed"),
        _get(daily, "indicators", "fgi"),
    )

    # Change conditions (optional)
    out["change_condition"] = _first_present(
        _get(daily, "summary", "change_condition"),
        _get(daily, "summary", "switch_condition"),
        _get(daily, "change_condition"),
    )

    # Normalization
    out["btc_change_pct_24h"] = _as_float(out["btc_change_pct_24h"])
    out["btc_price_jpy"] = _as_float(out["btc_price_jpy"])
    out["rsi"] = _as_float(out["rsi"])
    out["fgi"] = _as_int(out["fgi"])
    out["score"] = _as_int(out["score"])

    return out

# ---------------------------
# Copywriting
# ---------------------------

def build_main_post(m: Dict[str, Any]) -> str:
    date_label = _format_date_label(m["date"])
    fgi = m.get("fgi")
    rsi = m.get("rsi")
    chg = m.get("btc_change_pct_24h")
    price = m.get("btc_price_jpy")

    fgi_line = f"恐怖指数(FGI) {fgi}" if fgi is not None else "恐怖指数(FGI) --"
    rsi_line = f"RSI {rsi:.0f}" if isinstance(rsi, (int, float)) else "RSI --"
    chg_line = f"24h {_fmt_pct(chg)}" if chg is not None else "24h --"
    price_line = f"BTC { _fmt_price_jpy(price) }" if price is not None else "BTC --"

    # Interpretation (lightweight, not overconfident)
    interp = []
    if fgi is not None:
        if fgi <= 10:
            interp.append("「極度の恐怖」水準。投げ売りが出やすい一方、反転の芽も出やすい。")
        elif fgi <= 25:
            interp.append("恐怖寄り。戻りは重くなりやすい。")
        elif fgi >= 75:
            interp.append("強気寄り。過熱に注意。")
        else:
            interp.append("中立域。材料待ちになりやすい。")

    if isinstance(rsi, (int, float)):
        if rsi < 45:
            interp.append("RSIは弱め。勢いの回復はまだ限定的。")
        elif rsi > 55:
            interp.append("RSIは強め。上方向の勢いが出やすい。")
        else:
            interp.append("RSIは中立。レンジに入りやすい。")

    if chg is not None:
        if abs(chg) < 1.0:
            interp.append("値幅は小さめ。方向感を探る局面。")
        elif chg <= -2.0:
            interp.append("下押しが強い。戻り局面での反落に注意。")
        elif chg >= 2.0:
            interp.append("上振れが強い。過熱と反落に注意。")

    # Default change condition if not present
    cond = m.get("change_condition")
    if not cond:
        cond = "判断が変わる目安：FGIが25を超え、かつRSIが50を回復したら警戒度を一段下げる。"

    lines = [
        f"【今日のBTC / {date_label}】",
        f"{fgi_line} / {rsi_line} / {chg_line}",
        f"{price_line}",
    ]
    # keep only 2 interpretation lines max
    interp = interp[:2]
    lines.extend(interp)
    lines.append(cond)

    return _truncate_x(_compact("\n".join(lines)))

def build_self_reply(base_url: str) -> str:
    # URL is allowed only here
    return _compact(f"毎日の指標まとめ：{base_url}")

def build_english_reply(m: Dict[str, Any]) -> str:
    date_label = _format_date_label(m["date"])
    fgi = m.get("fgi")
    rsi = m.get("rsi")
    chg = m.get("btc_change_pct_24h")

    parts = [f"BTC snapshot ({date_label}, JST):"]
    if fgi is not None:
        parts.append(f"- Fear & Greed: {fgi} (very low = risk-off sentiment)")
    else:
        parts.append("- Fear & Greed: --")
    if isinstance(rsi, (int, float)):
        parts.append(f"- RSI(14): {rsi:.0f} (momentum {'weak' if rsi<45 else 'neutral' if rsi<=55 else 'strong'})")
    else:
        parts.append("- RSI(14): --")
    if chg is not None:
        parts.append(f"- 24h change: {_fmt_pct(chg)}")
    else:
        parts.append("- 24h change: --")

    # A single, cautious takeaway
    takeaway = "Takeaway: sentiment is heavy; wait for RSI>50 and FGI>25 to confirm risk easing."
    parts.append(takeaway)

    return _truncate_x(_compact("\n".join(parts)))

# ---------------------------
# Main
# ---------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="out", help="Output directory")
    ap.add_argument("--base-url", default="https://coinrader.net", help="Site URL (used only in self-reply)")
    ap.add_argument(
        "--daily-json",
        default="data/daily/latest.json",
        help="Primary daily JSON path (fallbacks are tried automatically)",
    )
    ap.add_argument(
        "--stable-json",
        default="data/intraday/stable.json",
        help="Optional stable JSON path (if missing, it's ignored)",
    )
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Prefer new location; keep backward compat with old `data/latest.json`.
    daily_paths = [
        Path(args.daily_json),
        Path("data/daily/latest.json"),
        Path("data/latest.json"),
        Path("data/daily") / (_today_jst().strftime("%Y%m%d") + ".json"),
    ]
    daily, daily_path = load_json_first(daily_paths)
    if daily is None:
        daily = {}
        daily_path = None

    stable, stable_path = load_json_first([Path(args.stable_json), Path("data/intraday/stable.json")])

    m = extract_metrics(daily, stable)

    main_post = build_main_post(m)
    self_reply = build_self_reply(args.base_url)
    en_post = build_english_reply(m)

    (out_dir / "daily_post_short.txt").write_text(main_post + "\n", encoding="utf-8")
    (out_dir / "daily_post_self_reply.txt").write_text(self_reply + "\n", encoding="utf-8")
    (out_dir / "daily_post_en.txt").write_text(en_post + "\n", encoding="utf-8")

    src_info = []
    if daily_path:
        src_info.append(f"daily={daily_path.as_posix()}")
    if stable_path:
        src_info.append(f"stable={stable_path.as_posix()}")
    src = ", ".join(src_info) if src_info else "no-json-found (fallback placeholders used)"

    print("✅ SNS assets generated:", src)
    print(" -", (out_dir / "daily_post_short.txt").as_posix())
    print(" -", (out_dir / "daily_post_self_reply.txt").as_posix())
    print(" -", (out_dir / "daily_post_en.txt").as_posix())


if __name__ == "__main__":
    main()
