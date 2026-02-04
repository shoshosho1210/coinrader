#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CoinRader: data/daily/*.json から daily/ 配下のHTMLを自動生成します。
- daily/YYYYMMDD.html
- daily/index.html (一覧)
- daily/latest.html (最新へのリダイレクト)

前提:
- JSONファイル名: data/daily/20260204.json のように8桁日付
- JSON内に必要キーが無い場合でも、落ちないようにフォールバックします。

2026-02: JSON構造が
  {
    "summary": {
      "date": "YYYY-MM-DD",
      "fgi": {"value": 14, "label": "Extreme Fear"},
      "technical": {"btc_rsi": 46.63, "btc_ma_distance": -11.6},
      "trending": ["HYPE","TRIA","BTC"],
      ...
    },
    ...
  }
のようなネストになったため、summary.* から値を抽出するように対応。
"""
from __future__ import annotations

import os
import re
import json
import glob
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# scripts/ の1つ上を repo root として想定
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "daily"
OUT_DIR  = ROOT / "daily"
TEMPL_DIR = ROOT / "templates"

SITE_ORIGIN = os.environ.get("CR_SITE_ORIGIN", "https://coinrader.net").rstrip("/")
TZ_NAME = "JST"


# ---------- utils ----------
def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")

def escape_html(s: str) -> str:
    return (s.replace("&", "&amp;")
              .replace("<", "&lt;")
              .replace(">", "&gt;")
              .replace('"', "&quot;")
              .replace("'", "&#39;"))

def get_path(obj: Any, path: str, default: Any = "") -> Any:
    """
    dict のネストを "summary.technical.btc_rsi" のようなドット区切りで取得。
    """
    cur = obj
    for key in path.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur if cur is not None else default

def to_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        if s == "":
            return None
        return float(s)
    except Exception:
        return None

def fmt_num(x: Any, ndigits: int = 2) -> str:
    v = to_float(x)
    if v is None:
        return ""
    return f"{v:.{ndigits}f}".rstrip("0").rstrip(".")

def compute_judge(fgi_value: Any, btc_rsi: Any, ma_dist: Any) -> str:
    """
    JSONに明示的な ai_judge が無い場合の簡易判定。
    - BULL / BEAR / WAIT を返す（テンプレ側のスタイル判定に使いやすい）
    """
    fgi = to_float(fgi_value)
    rsi = to_float(btc_rsi)
    mad = to_float(ma_dist)
    if fgi is None or rsi is None or mad is None:
        return "WAIT"

    # 恐怖＋トレンド弱い -> 弱気寄り（ただし売られ過ぎならWAIT寄り）
    if fgi <= 25 and mad <= -5:
        if rsi <= 30:
            return "WAIT"  # 売られ過ぎで即断を避ける
        return "BEAR"

    # 強欲＋トレンド強い -> 強気寄り
    if fgi >= 75 and mad >= 5:
        if rsi >= 70:
            return "WAIT"  # 過熱で即断を避ける
        return "BULL"

    # RSIで補助
    if rsi <= 30:
        return "WAIT"
    if rsi >= 70:
        return "WAIT"

    # トレンドで緩く
    if mad >= 3:
        return "BULL"
    if mad <= -3:
        return "BEAR"
    return "WAIT"


# ---------- reason builder ----------
def build_reason_html(payload: Dict[str, Any]) -> str:
    """
    可能なら JSON内の説明テキストを使い、無ければ数値から簡易生成。
    """
    reasons: List[str] = []

    # 将来、理由の配列/テキストが追加された時に拾えるように候補を複数
    for path in [
        "ai.reasons",
        "ai.reason_lines",
        "ai.reason",
        "reasons",
        "reason_lines",
        "reason",
        "summary.reason_lines",
        "summary.reason",
    ]:
        v = get_path(payload, path, default=None)
        if isinstance(v, list) and v:
            reasons = [str(x).strip() for x in v if str(x).strip()]
            break
        if isinstance(v, str) and v.strip():
            # 1文を1行に
            reasons = [v.strip()]
            break

    # summary.* から指標を取得
    fgi_value = get_path(payload, "summary.fgi.value", default=get_path(payload, "fear_greed", default=""))
    fgi_label = get_path(payload, "summary.fgi.label", default="")
    btc_rsi   = get_path(payload, "summary.technical.btc_rsi", default=get_path(payload, "btc_rsi", default=""))
    ma_dist   = get_path(payload, "summary.technical.btc_ma_distance", default=get_path(payload, "trend", default=""))
    trending  = get_path(payload, "summary.trending", default=[])
    top_gainer_symbol = get_path(payload, "summary.top_gainer.symbol", default="")
    top_gainer_change = get_path(payload, "summary.top_gainer.change", default="")

    if not reasons:
        # Fear & Greed
        fgi = to_float(fgi_value)
        if fgi is not None:
            if fgi < 25:
                label = fgi_label or "Extreme Fear"
                reasons.append(f"Fear & Greed が {fmt_num(fgi,0)}（{label}）で、市場心理は強い悲観に寄っています。")
            elif fgi < 45:
                reasons.append(f"Fear & Greed が {fmt_num(fgi,0)} で弱気寄りです。")
            elif fgi < 55:
                reasons.append(f"Fear & Greed が {fmt_num(fgi,0)} で中立付近です。")
            elif fgi < 75:
                reasons.append(f"Fear & Greed が {fmt_num(fgi,0)} で強気寄りです。")
            else:
                label = fgi_label or "Extreme Greed"
                reasons.append(f"Fear & Greed が {fmt_num(fgi,0)}（{label}）で過熱感があります。")

        # RSI
        rsi = to_float(btc_rsi)
        if rsi is not None:
            if rsi < 30:
                reasons.append(f"BTC RSI が {fmt_num(rsi)} で売られ過ぎ水準です。")
            elif rsi < 45:
                reasons.append(f"BTC RSI が {fmt_num(rsi)} で弱めです。")
            elif rsi < 55:
                reasons.append(f"BTC RSI が {fmt_num(rsi)} で中立付近です。")
            elif rsi < 70:
                reasons.append(f"BTC RSI が {fmt_num(rsi)} で堅調です。")
            else:
                reasons.append(f"BTC RSI が {fmt_num(rsi)} で買われ過ぎ水準です。")

        # MA distance (trend proxy)
        mad = to_float(ma_dist)
        if mad is not None:
            if mad <= -8:
                reasons.append(f"MA距離が {fmt_num(mad)}% と大きくマイナスで、下方向の圧力が強い状態です。")
            elif mad <= -3:
                reasons.append(f"MA距離が {fmt_num(mad)}% で、弱含みです。")
            elif mad < 3:
                reasons.append(f"MA距離が {fmt_num(mad)}% で、方向感は限定的です。")
            elif mad < 8:
                reasons.append(f"MA距離が {fmt_num(mad)}% で、上向きの勢いがあります。")
            else:
                reasons.append(f"MA距離が {fmt_num(mad)}% と大きくプラスで、上昇が加速しています。")

        # Trending
        if isinstance(trending, list) and trending:
            top3 = [str(x).strip().upper() for x in trending[:3] if str(x).strip()]
            if top3:
                reasons.append(f"注目トレンド: {' / '.join(top3)}")

        # Top gainer
        if str(top_gainer_symbol).strip():
            ch = to_float(top_gainer_change)
            if ch is not None:
                reasons.append(f"上昇トップ: {str(top_gainer_symbol).upper()}（+{fmt_num(ch)}%）")

    # HTML
    li = "\n".join([f"<li>{escape_html(x)}</li>" for x in reasons[:6]])
    return f"<ul class='why-list'>{li}</ul>" if li else ""


# ---------- main ----------
def main() -> None:
    tmpl = read_text(TEMPL_DIR / "daily_template.html")
    tmpl_index = read_text(TEMPL_DIR / "daily_index_template.html")
    tmpl_latest = read_text(TEMPL_DIR / "latest_template.html")

    files = sorted(glob.glob(str(DATA_DIR / "*.json")))
    dated: List[str] = []
    for f in files:
        name = Path(f).stem
        if re.fullmatch(r"\d{8}", name):
            dated.append(name)
    dated = sorted(set(dated))
    if not dated:
        raise SystemExit(f"No daily json files found in: {DATA_DIR}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 最新日付
    latest_ymd = dated[-1]

    # 各日付ページ生成
    pages: List[Dict[str, str]] = []
    for ymd in reversed(dated):
        json_path = DATA_DIR / f"{ymd}.json"
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}

        # YYYYMMDD -> YYYY-MM-DD
        date_iso = get_path(payload, "summary.date", default="")
        if not date_iso:
            try:
                date_iso = datetime.datetime.strptime(ymd, "%Y%m%d").strftime("%Y-%m-%d")
            except Exception:
                date_iso = ymd

        # 指標抽出（summary.* を優先）
        fgi_value = get_path(payload, "summary.fgi.value", default=get_path(payload, "fear_greed", default=""))
        btc_rsi   = get_path(payload, "summary.technical.btc_rsi", default=get_path(payload, "btc_rsi", default=""))
        ma_dist   = get_path(payload, "summary.technical.btc_ma_distance", default=get_path(payload, "trend", default=""))

        # judge
        judge = get_path(payload, "ai_judge", default=get_path(payload, "ai.judge", default=""))
        if not str(judge).strip():
            judge = compute_judge(fgi_value, btc_rsi, ma_dist)

        # 更新時刻（無ければ毎朝9時）
        updated_at = get_path(payload, "updated_at", default=get_path(payload, "timestamp", default=""))
        if not str(updated_at).strip():
            updated_at = f"{date_iso} 09:00"

        # 表示用
        sent = fmt_num(fgi_value, 0) if fmt_num(fgi_value, 0) != "" else str(fgi_value)
        rsi  = fmt_num(btc_rsi, 2) if fmt_num(btc_rsi, 2) != "" else str(btc_rsi)
        trend = fmt_num(ma_dist, 1) if fmt_num(ma_dist, 1) != "" else str(ma_dist)

        # メタ情報
        title = f"BTC AI分析（{date_iso}）"
        desc  = f"CoinRaderの日次AI分析レポート（{date_iso}）。Fear&Greed={sent}, RSI={rsi}, Trend={trend}。"
        canonical = f"{SITE_ORIGIN}/daily/{ymd}.html"

        why_html = build_reason_html(payload)

        html = tmpl
        repl = {
            "{{TITLE}}": title,
            "{{DESCRIPTION}}": desc,
            "{{CANONICAL}}": canonical,
            "{{OG_TITLE}}": title,
            "{{OG_DESCRIPTION}}": desc,
            "{{DATE}}": date_iso,
            "{{H1}}": f"BTC AI分析（{date_iso}）",
            "{{UPDATED_AT}}": str(updated_at),
            "{{JUDGE}}": escape_html(str(judge)),
            "{{SENTIMENT_VALUE}}": escape_html(str(sent)),
            "{{BTC_RSI}}": escape_html(str(rsi)),
            "{{TREND}}": escape_html(str(trend)),
            "{{WHY_HTML}}": why_html,
        }
        for k, v in repl.items():
            html = html.replace(k, v)

        out_file = OUT_DIR / f"{ymd}.html"
        write_text(out_file, html)

        pages.append({
            "ymd": ymd,
            "date_iso": date_iso,
            "title": title,
            "href": f"{ymd}.html",
        })

    # 一覧 index.html
    # テンプレ側で {{ITEMS}} を期待している想定（既存実装に合わせる）
    items_html = "\n".join([
        f"<li><a href='{escape_html(p['href'])}'>{escape_html(p['title'])}</a></li>"
        for p in pages
    ])
    index_html = tmpl_index.replace("{{ITEMS}}", items_html)
    # 最新ページへの導線が必要ならテンプレ側で {{LATEST_HREF}} を利用可能に
    index_html = index_html.replace("{{LATEST_HREF}}", f"{latest_ymd}.html")
    write_text(OUT_DIR / "index.html", index_html)

    # latest.html（最新ページへリダイレクト/案内）
    latest_target = f"{latest_ymd}.html"
    latest_html = tmpl_latest.replace("{{LATEST_HREF}}", latest_target)
    latest_html = latest_html.replace("{{LATEST_DATE}}", pages[0]["date_iso"] if pages else "")
    write_text(OUT_DIR / "latest.html", latest_html)

    print(f"[OK] Generated {len(pages)} pages into: {OUT_DIR} (latest={latest_target})")


if __name__ == "__main__":
    main()
