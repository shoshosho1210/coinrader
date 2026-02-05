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

def read_text_optional(paths: List[Path]) -> str:
    """Return the content of the first existing file in paths."""
    for p in paths:
        if p.exists():
            return read_text(p)
    raise FileNotFoundError("None of the optional template files exist: " + ", ".join(str(x) for x in paths))


def read_text_optional_with_path(paths: List[Path]) -> tuple[Path, str]:
    """Return (path, text) for the first existing file in paths."""
    for p in paths:
        if p.exists():
            return p, read_text(p)
    raise FileNotFoundError("None of the optional template files exist: " + ", ".join(str(x) for x in paths))

def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")

def escape_html(s: str) -> str:
    return (s.replace("&", "&amp;")
              .replace("<", "&lt;")
              .replace(">", "&gt;")
              .replace('"', "&quot;")
              .replace("'", "&#39;"))


def build_seo_meta(date_iso: str, ymd: str, judge: str, sentiment_value, btc_rsi, trend, trending: List[str], top_gainer=None) -> Dict[str, str]:
    # title/description は検索結果でのクリック率を意識して具体的な数値を含める
    try:
        rsi_s = f"{float(btc_rsi):.2f}" if btc_rsi is not None else "-"
    except Exception:
        rsi_s = "-"
    try:
        trend_s = f"{float(trend):.1f}" if trend is not None else "-"
    except Exception:
        trend_s = "-"
    fgi_s = str(sentiment_value) if sentiment_value is not None else "-"
    trend_str = "/".join([t.upper() for t in (trending or [])][:3])
    gain_str = ""
    if isinstance(top_gainer, dict) and top_gainer.get("symbol"):
        ch = top_gainer.get("change")
        try:
            ch_s = f"{float(ch):.2f}" if ch is not None else ""
        except Exception:
            ch_s = str(ch) if ch is not None else ""
        gain_str = f" 上昇トップ:{top_gainer.get('symbol').upper()}(+{ch_s}%)" if ch_s else f" 上昇トップ:{top_gainer.get('symbol').upper()}"

    title = f"BTC AI分析 {date_iso}｜Fear&Greed {fgi_s} / RSI {rsi_s} / Trend {trend_s}（CoinRader）"
    desc = f"{date_iso}のBTCをAIが日次分析。市場心理(Fear&Greed)={fgi_s}、RSI={rsi_s}、Trend={trend_s}。総合判断={judge}。注目トレンド:{trend_str}.{gain_str}".strip()
    og_title = f"BTC AI分析 {date_iso}｜AI判定 {judge}"
    og_desc = f"Fear&Greed={fgi_s} / RSI={rsi_s} / Trend={trend_s}。注目:{trend_str}"
    canonical = f"https://coinrader.net/daily/{ymd}.html"
    return {
        "TITLE": title,
        "DESCRIPTION": desc,
        "OG_TITLE": og_title,
        "OG_DESCRIPTION": og_desc,
        "CANONICAL": canonical,
    }


def build_jsonld(canonical: str, title: str, description: str, date_iso: str, updated_at_jst: str) -> str:
    # 日次ページは Article として扱う
    # updated_at_jst: 'YYYY-MM-DD 09:00' のような文字列を想定
    def to_iso(dt_s: str) -> str:
        try:
            # allow 'YYYY-MM-DD HH:MM' (JST)
            dt = datetime.datetime.strptime(dt_s, "%Y-%m-%d %H:%M")
            # JST +09:00
            return dt.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=9))).isoformat()
        except Exception:
            return date_iso + "T09:00:00+09:00"

    data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": description,
        "datePublished": date_iso + "T09:00:00+09:00",
        "dateModified": to_iso(updated_at_jst),
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
        "publisher": {"@type": "Organization", "name": "CoinRader"},
    }
    return json.dumps(data, ensure_ascii=False)



def build_recent_days_html(dated_all: List[str], current_ymd: str, n: int = 7) -> str:
    """直近n件のチップを生成（前後も含めて回遊しやすくする）
    - 可能なら「当日(=最新)」も同じ列に含める
    - 重複表示を避け、日付は small に、ラベルは必要なときだけ表示
    """
    if not dated_all:
        return ""
    if current_ymd not in dated_all:
        return ""

    latest_ymd = dated_all[-1]
    idx = dated_all.index(current_ymd)

    # 基本は「前3・後3（計7）」を狙う。端は自動で寄せる。
    half = n // 2
    start = max(0, idx - half)
    end = min(len(dated_all), idx + half + 1)
    # 端で足りない分を反対側に寄せる
    while (end - start) < n and start > 0:
        start -= 1
    while (end - start) < n and end < len(dated_all):
        end += 1

    window = dated_all[start:end]

    parts = []
    for ymd in window:
        mmdd = f"{ymd[4:6]}/{ymd[6:8]}"
        if ymd == latest_ymd:
            label = "今日"
        elif ymd == current_ymd:
            label = "現在"
        else:
            label = ""
        href = f"/daily/{ymd}.html"
        inner = f"<small>{mmdd}</small>{escape_html(label)}" if label else f"<small>{mmdd}</small>"
        parts.append(f"<a class='chip' href='{href}'>{inner}</a>")

    parts.append("<a class='chip' href='/daily/'><small>LIST</small>一覧</a>")
    parts.append("<a class='chip' href='/daily/latest.html'><small>NEW</small>最新</a>")
    return "\n      ".join(parts)


def build_same_judge_days_html(judge: str, judge_days_all: List[str], current_ymd: str, n: int = 5) -> str:
    """同じAI判定の日への内部リンク（チップ）を生成。
    - current の前後を含めて最大 n 件
    - judge が空、または対象日が不足なら空を返す
    """
    judge = (judge or "").strip()
    if not judge or not judge_days_all or current_ymd not in judge_days_all:
        return ""
    # judge_days_all は昇順前提（YYYYMMDD）
    idx = judge_days_all.index(current_ymd)
    half = n // 2
    start = max(0, idx - half)
    end = min(len(judge_days_all), idx + half + 1)
    while (end - start) < n and start > 0:
        start -= 1
    while (end - start) < n and end < len(judge_days_all):
        end += 1

    window = judge_days_all[start:end]

    parts = []
    # ラベル（非リンク）
    parts.append(
        f"<a class='chip' href='/daily/tags/{escape_html(judge.lower())}.html' style='opacity:.75'><small>SAME</small>{escape_html(judge)}</a>"
    )
    for ymd in window:
        mmdd = f"{ymd[4:6]}/{ymd[6:8]}"
        label = "" if ymd != current_ymd else "現在"
        href = f"/daily/{ymd}.html"
        inner = f"<small>{mmdd}</small>{escape_html(label)}" if label else f"<small>{mmdd}</small>"
        parts.append(f"<a class='chip' href='{href}'>{inner}</a>")
    return "\n      ".join(parts)



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

def normalize_symbol_list(items: Any) -> List[str]:
    """trending等を「銘柄シンボルの文字列リスト」に正規化する。
    - ["BTC","ETH"] -> ["BTC","ETH"]
    - [{"symbol":"btc","label":"BTC"}, ...] -> ["BTC", ...]
    - None/その他 -> []
    """
    if not isinstance(items, list):
        return []
    out: List[str] = []
    for it in items:
        s = ""
        if isinstance(it, str):
            s = it
        elif isinstance(it, dict):
            # よくあるキーを優先順で拾う
            for k in ("symbol", "label", "name", "id"):
                v = it.get(k)
                if isinstance(v, str) and v.strip():
                    s = v
                    break
        if s:
            out.append(s.strip().upper())
    # 重複除去（順序維持）
    seen = set()
    uniq: List[str] = []
    for s in out:
        if s in seen:
            continue
        seen.add(s)
        uniq.append(s)
    return uniq


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
    ma_dist   = get_path(payload, "summary.technical.btc_ma_distance",
                          default=get_path(payload, "summary.technical.ma_distance",
                              default=get_path(payload, "btc_ma_distance",
                                  default=get_path(payload, "ma_distance", default=""))))
    # 旧フォーマットで trend が配列/辞書の場合があるため除外
    if isinstance(ma_dist, (list, dict)):
        ma_dist = ""
    trending  = get_path(payload, "summary.trending", default=get_path(payload, "trending", default=get_path(payload, "trend", default=[])))
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


def shorten_one_line(s: str, max_len: int = 70) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    s = " ".join(s.split())
    return (s[:max_len].rstrip() + "…") if len(s) > max_len else s


def build_reason_1line(payload: Dict[str, Any]) -> str:
    """
    daily/index.html 用の「理由1行要約」。
    単調になりやすいFGI文言だけに寄らないように、指標/トレンド/上昇銘柄も優先して散らす。
    """
    # 1) まずはJSONに明示されている理由を最優先で使う
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
            if reasons:
                return shorten_one_line(reasons[0])
        if isinstance(v, str) and v.strip():
            return shorten_one_line(v.strip())

    # 2) 明示理由がない場合は候補を複数作り、優先度で選ぶ
    candidates: List[str] = []

    judge = str(get_path(payload, "summary.judge", default=get_path(payload, "judge", default="")) or "").upper()

    # 指標値
    fgi_value = get_path(payload, "summary.fgi.value", default=get_path(payload, "fear_greed", default=""))
    fgi_label = get_path(payload, "summary.fgi.label", default="")
    btc_rsi   = get_path(payload, "summary.technical.btc_rsi", default=get_path(payload, "btc_rsi", default=""))
    ma_dist   = get_path(
        payload,
        "summary.technical.btc_ma_distance",
        default=get_path(
            payload,
            "summary.technical.ma_distance",
            default=get_path(
                payload,
                "btc_ma_distance",
                default=get_path(payload, "ma_distance", default=""),
            ),
        ),
    )

    if isinstance(ma_dist, (list, dict)):
        ma_dist = ""

    fgi = to_float(fgi_value)
    rsi = to_float(btc_rsi)
    mad = to_float(ma_dist)

    # トレンド/上昇トップ（あれば短文化）
    trending = normalize_symbol_list(
        get_path(payload, "summary.trending",
            default=get_path(payload, "trending",
                default=get_path(payload, "trend", default=[])))
    )
    top_gainer = get_path(payload, "summary.top_gainer", default=get_path(payload, "top_gainer", default=None))
    tg_text = ""
    if isinstance(top_gainer, dict):
        sym = str(top_gainer.get("symbol", "")).strip().upper()
        ch = top_gainer.get("change", None)
        ch_s = ""
        try:
            if ch is not None and ch != "":
                ch_s = f"{float(ch):.2f}".rstrip("0").rstrip(".")
        except Exception:
            ch_s = str(ch).strip() if ch is not None else ""
        if sym and ch_s:
            tg_text = f"{sym} +{ch_s}%"
        elif sym:
            tg_text = sym

    # ---- 優先順位（散らすためFGIは後ろ） ----
    if rsi is not None:
        if rsi < 30:
            candidates.append(f"BTC RSI が {fmt_num(rsi)} で売られ過ぎ水準。")
        elif rsi >= 70:
            candidates.append(f"BTC RSI が {fmt_num(rsi)} で買われ過ぎ水準。")

    if mad is not None:
        if mad <= -3:
            candidates.append(f"MA距離が {fmt_num(mad)}% で弱含み。")
        elif mad >= 3:
            candidates.append(f"MA距離が {fmt_num(mad)}% で上向き。")

    if tg_text:
        candidates.append(f"上昇トップは {tg_text} で強い動き。")

    if trending:
        top3 = "/".join(trending[:3])
        candidates.append(f"注目トレンドは {top3}。")

    if fgi is not None:
        if fgi < 25:
            label = fgi_label or "Extreme Fear"
            # judge を軽く混ぜて同じ文面になりにくくする
            if judge == "BEAR":
                candidates.append(f"Fear & Greed が {fmt_num(fgi,0)}（{label}）で強い悲観。")
            else:
                candidates.append(f"Fear & Greed が {fmt_num(fgi,0)}（{label}）で警戒ムード。")
        elif fgi >= 75:
            label = fgi_label or "Extreme Greed"
            if judge == "BULL":
                candidates.append(f"Fear & Greed が {fmt_num(fgi,0)}（{label}）で過熱気味。")
            else:
                candidates.append(f"Fear & Greed が {fmt_num(fgi,0)}（{label}）で楽観優勢。")

    if judge:
        # 最終フォールバック（指標欠けの日でも破綻しない）
        if judge == "WAIT":
            candidates.append("材料が揃わず、いったん様子見。")
        elif judge == "BEAR":
            candidates.append("反発弱く、戻り売りに注意。")
        elif judge == "BULL":
            candidates.append("上向き基調だが、急変には注意。")

    return shorten_one_line(candidates[0] if candidates else "")




# ---------- main ----------
def main() -> None:
    tmpl = read_text(TEMPL_DIR / "daily_template.html")
    # Index template: prefer daily_index.html (new), fallback to daily_index_template.html (old)
    tmpl_index = read_text_optional([
        TEMPL_DIR / "daily_index.html",
        TEMPL_DIR / "daily_index_template.html",
    ])
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


    # 各日付ページ生成（2パス）
    # 1) 先に全JSONを読み込み、judge→日付リストを作る（同じ判定の日リンク用）
    items: List[Dict[str, Any]] = []
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
        ma_dist   = get_path(payload, "summary.technical.btc_ma_distance",
                          default=get_path(payload, "summary.technical.ma_distance",
                              default=get_path(payload, "btc_ma_distance",
                                  default=get_path(payload, "ma_distance", default=""))))
        # 旧フォーマットで trend が配列/辞書の場合があるため除外
        if isinstance(ma_dist, (list, dict)):
            ma_dist = ""

        # trending は新: summary.trending / 旧: trending / さらに旧: trend(配列) の可能性がある
        trending_raw = get_path(payload, "summary.trending",
                                default=get_path(payload, "trending",
                                                default=get_path(payload, "trend", default=[])))
        trending = normalize_symbol_list(trending_raw)

        top_gainer = get_path(payload, "summary.top_gainer", default=get_path(payload, "top_gainer", default={}))
        if not isinstance(top_gainer, dict):
            top_gainer = {}

        # judge
        judge = get_path(payload, "ai_judge", default=get_path(payload, "ai.judge", default=""))
        if not str(judge).strip():
            judge = compute_judge(fgi_value, btc_rsi, ma_dist)

        # 更新時刻（無ければ毎朝9時）
        updated_at = get_path(payload, "updated_at", default=get_path(payload, "timestamp", default=""))
        if not str(updated_at).strip():
            updated_at = f"{date_iso} 09:00"

        # SEO meta（title/description/canonical）
        seo_meta = build_seo_meta(date_iso, ymd, judge, fgi_value, btc_rsi, ma_dist, trending, top_gainer=top_gainer)
        jsonld = build_jsonld(
            seo_meta.get("CANONICAL",""),
            seo_meta.get("TITLE",""),
            seo_meta.get("DESCRIPTION",""),
            date_iso,
            str(updated_at),
        )

        # 表示用
        sent = fmt_num(fgi_value, 0) if fmt_num(fgi_value, 0) != "" else str(fgi_value)
        rsi  = fmt_num(btc_rsi, 2) if fmt_num(btc_rsi, 2) != "" else str(btc_rsi)
        trend_num = fmt_num(ma_dist, 1)
        trend = trend_num if trend_num != "" else "—"

        # メタ情報
        title = seo_meta.get("TITLE") or f"BTC AI分析（{date_iso}）"
        desc  = seo_meta.get("DESCRIPTION") or f"CoinRaderの日次AI分析レポート（{date_iso}）。Fear&Greed={sent}, RSI={rsi}, Trend={trend}。"
        canonical = seo_meta.get("CANONICAL") or f"{SITE_ORIGIN}/daily/{ymd}.html"

        items.append({
            "ymd": ymd,
            "date_iso": date_iso,
            "payload": payload,
            "judge": str(judge),
            "fgi_value": fgi_value,
            "btc_rsi": btc_rsi,
            "ma_dist": ma_dist,
            "trending": trending,
            "top_gainer": top_gainer,
            "updated_at": updated_at,
            "seo_meta": seo_meta,
            "jsonld": jsonld,
            "title": title,
            "desc": desc,
            "canonical": canonical,
            "sent": sent,
            "rsi": rsi,
            "trend": trend,
        })

    # judge -> 日付（昇順）
    judge_days: Dict[str, List[str]] = {}
    for it in items:
        j = (it.get("judge") or "").strip()
        y = it.get("ymd") or ""
        if j and y:
            judge_days.setdefault(j, []).append(y)
    for j in list(judge_days.keys()):
        judge_days[j] = sorted(set(judge_days[j]))

    # 2) ページ生成（同じ判定の日リンクを {{RECENT_DAYS}} に追加）
    pages: List[Dict[str, str]] = []
    for it in items:
        ymd = it["ymd"]
        date_iso = it["date_iso"]
        payload = it["payload"]
        judge = it["judge"]
        sent = it["sent"]
        rsi = it["rsi"]
        trend = it["trend"]
        updated_at = it["updated_at"]
        title = it["title"]
        desc = it["desc"]
        canonical = it["canonical"]
        jsonld = it["jsonld"]
        trending = it["trending"]
        top_gainer = it["top_gainer"]
        fgi_value = it["fgi_value"]
        btc_rsi = it["btc_rsi"]
        ma_dist = it["ma_dist"]

        recent_days_html = build_recent_days_html(dated, ymd, n=7)
        same_judge_html = build_same_judge_days_html(judge, judge_days.get(judge, []), ymd, n=5)
        if same_judge_html:
            recent_days_html = recent_days_html + "\n      " + same_judge_html

        why_html = build_reason_html(payload)

        html = tmpl
        repl = {
            "{{TITLE}}": title,
            "{{DESCRIPTION}}": desc,
            "{{CANONICAL}}": canonical,
            "{{JSONLD}}": jsonld,
            "{{OG_TITLE}}": title,
            "{{OG_DESCRIPTION}}": desc,
            "{{DATE}}": date_iso,
            "{{H1}}": f"BTC AI分析（{date_iso}）",
            "{{UPDATED_AT}}": str(updated_at),
            "{{JUDGE}}": escape_html(str(judge)),
            "{{SENTIMENT_VALUE}}": escape_html(str(sent)),
            "{{SENTIMENT}}": escape_html(str(sent)),
            "{{BTC_RSI}}": escape_html(str(rsi)),
            "{{TREND}}": escape_html(str(trend)),
            "{{WHY_HTML}}": why_html,
            "{{WHY}}": why_html,
            "{{RECENT_DAYS_HTML}}": recent_days_html,
            "{{RECENT_DAYS}}": recent_days_html,
        }
        for k, v in repl.items():
            html = html.replace(k, v)

        out_file = OUT_DIR / f"{ymd}.html"
        write_text(out_file, html)

        # 一覧で使う短い表示用（無い日は空にしておく）
        trend_top3 = "/".join(trending[:3]) if trending else ""

        top_gainer_label = ""
        if isinstance(top_gainer, dict) and str(top_gainer.get("symbol","")).strip():
            sym = str(top_gainer.get("symbol","")).strip().upper()
            ch = top_gainer.get("change")
            ch_s = ""
            try:
                ch_s = f"{float(ch):.2f}".rstrip("0").rstrip(".") if ch is not None else ""
            except Exception:
                ch_s = str(ch).strip() if ch is not None else ""
            top_gainer_label = f"{sym} +{ch_s}%" if ch_s else sym

        reason_1line = build_reason_1line(payload)

        pages.append({
            "ymd": ymd,
            "date_iso": date_iso,
            "title": title,
            "href": f"{ymd}.html",
            "judge": str(judge),
            "fgi": sent,
            "btc_rsi": rsi,
            "trend": trend,
            "trend_top3": trend_top3,
            "top_gainer": top_gainer_label,
            "reason_1line": reason_1line,
        })
    # 一覧 index.html
    # - 新テンプレ: {{ROWS}} を想定（daily_index.html）
    # - 旧テンプレ: {{ITEMS}} を想定（daily_index_template.html）
    pages_desc = sorted(pages, key=lambda p: p.get("ymd",""), reverse=True)  # 最新→過去


    def _pill(text: str, cls: str = "") -> str:
        if not text:
            return ""
        cls_attr = ("pill " + cls).strip()
        return f"<span class='{cls_attr}'>{escape_html(text)}</span>"

    def _fmt_meta_html(p: dict) -> str:
        parts = []

        # AI判定（強調）
        j = (p.get("judge") or "").upper()
        if j:
            cls = "pill-ai"
            if j == "BULL":
                cls += " bull"
            elif j == "BEAR":
                cls += " bear"
            elif j == "WAIT":
                cls += " wait"
            parts.append(_pill(f"AI {j}", cls))

        # 指標
        if p.get("fgi") is not None:
            parts.append(_pill(f"FGI {p['fgi']}", "pill-kpi"))
        if p.get("btc_rsi") is not None:
            parts.append(_pill(f"RSI {p['btc_rsi']}", "pill-kpi"))
        if p.get("trend") is not None:
            parts.append(_pill(f"Trend {p['trend']}", "pill-kpi"))

        # クリック誘導（PV用）
        if p.get("trend_top3"):
            parts.append(_pill(f"注目 {p['trend_top3']}", "pill-hot"))
        if p.get("top_gainer"):
            parts.append(_pill(f"上昇 {p['top_gainer']}", "pill-up"))

        # 要約は短く（長いと一覧が単調＆読みにくい）
        r = (p.get("reason_1line") or "").strip()
        if r:
            r = shorten_one_line(r, max_len=55)
            parts.append(_pill(f"要約 {r}", "pill-reason"))

        return "".join([x for x in parts if x])

    rows_html = "\n".join([
            "<div class='row'>"
            f"<a class='rowlink' href='{escape_html(p['href'])}'>"
            f"<div class='date'>{escape_html(p['date_iso'])}</div>"
            f"<div class='meta'>{_fmt_meta_html(p)}</div>"
            "</a>"
            "</div>"
            for p in pages_desc
        ])

    # 旧テンプレ用の簡易liも残す（互換）
    items_html = "\n".join([
        f"<li><a href='{escape_html(p['href'])}'>{escape_html(p['title'])}</a></li>"
        for p in pages_desc
    ])

    index_html = tmpl_index

    # {{ROWS}} / {{ITEMS}} など表記ゆれ（空白あり）でも置換できるようにする
    #   - {{ROWS}}   or {{ ROWS }}
    #   - {{ITEMS}}  or {{ ITEMS }}
    rows_pat = re.compile(r"\{\{\s*ROWS\s*\}\}")
    items_pat = re.compile(r"\{\{\s*ITEMS\s*\}\}")
    latest_pat = re.compile(r"\{\{\s*LATEST_HREF\s*\}\}")

    before = index_html
    index_html, n_rows = rows_pat.subn(rows_html, index_html)
    index_html, n_items = items_pat.subn(items_html, index_html)
    index_html, n_latest = latest_pat.subn(f"{latest_ymd}.html", index_html)

    # 置換漏れ検知（CIで気づけるように）
    if re.search(r"\{\{\s*(ROWS|ITEMS|LATEST_HREF)\s*\}\}", index_html):
        raise RuntimeError("daily_index.html: placeholder が残っています（ROWS/ITEMS/LATEST_HREF）")

    # 何も置換されなかった場合はテンプレ側のプレースホルダーが違う可能性が高い
    if (n_rows + n_items + n_latest) == 0:
        raise RuntimeError("daily_index.html: placeholder が見つからず置換できませんでした（テンプレの {{ROWS}}/{{ITEMS}}/{{LATEST_HREF}} を確認してください）")
    write_text(OUT_DIR / "index.html", index_html)

    # tag pages（同じAI判定の日をまとめた一覧）
    #   - /daily/tags/bear.html, bull.html, wait.html
    # 目的: 回遊・内部リンク強化（一覧→タグ→各日）
    tags_dir = OUT_DIR / "tags"
    tags_dir.mkdir(parents=True, exist_ok=True)

    rows_pat = re.compile(r"\{\{\s*ROWS\s*\}\}")
    items_pat = re.compile(r"\{\{\s*ITEMS\s*\}\}")
    latest_pat = re.compile(r"\{\{\s*LATEST_HREF\s*\}\}")

    for judge_key in ["BEAR", "BULL", "WAIT"]:
        filtered = [p for p in pages_desc if str(p.get("judge","")).upper() == judge_key]

        # 該当が0件でもタグページは必ず生成する（SEO/回遊の入口を確保）
        if not filtered:
            rows_html_tag = (
                f"<div class='taghead'>"
                f"<div class='tagtitle'>AI {escape_html(judge_key)} の日</div>"
                f"<div class='tagsub'>全0件</div>"
                f"</div>\n"
                + "<div class='empty' style='margin:10px 0 18px;opacity:.8'>"
                + "まだ該当する日がありません。"
                + " <a href='../index.html'>一覧に戻る</a>"
                + "</div>"
            )
            items_html_tag = ""

            tag_html = tmpl_index
            tag_html, _ = rows_pat.subn(rows_html_tag, tag_html)
            tag_html, _ = items_pat.subn(items_html_tag, tag_html)
            tag_html, _ = latest_pat.subn(f"../{latest_ymd}.html", tag_html)

            # タブの current を該当判定へ移す（テンプレがALLをcurrentにしている想定）
            tag_html = tag_html.replace('class="tab current" href="/daily/"', 'class="tab" href="/daily/"')
            tag_html = tag_html.replace(f'class="tab tab-{judge_key.lower()}"', f'class="tab tab-{judge_key.lower()} current"')

            if re.search(r"\{\{\s*(ROWS|ITEMS|LATEST_HREF)\s*\}\}", tag_html):
                raise RuntimeError("tag page: placeholder が残っています（ROWS/ITEMS/LATEST_HREF）")

            out_path = tags_dir / f"{judge_key.lower()}.html"
            write_text(out_path, tag_html)
            continue

        # タグページは /daily/tags/ 配下なので、リンクは ../YYYYMMDD.html で辿れるようにする
        rows_html_tag = (
            f"<div class='taghead'>"
            f"<div class='tagtitle'>AI {escape_html(judge_key)} の日</div>"
            f"<div class='tagsub'>全{len(filtered)}件</div>"
            f"</div>\n"
            + "\n".join([
                "<div class='row'>"
                f"<a class='rowlink' href='../{escape_html(p['ymd'])}.html'>"
                f"<div class='date'>{escape_html(p['date_iso'])}</div>"
                f"<div class='meta'>{_fmt_meta_html(p)}</div>"
                "</a>"
                "</div>"
                for p in filtered
            ])
        )

        items_html_tag = "\n".join([
            f"<li><a href='../{escape_html(p['ymd'])}.html'>{escape_html(p['title'])}</a></li>"
            for p in filtered
        ])

        tag_html = tmpl_index
        tag_html, _ = rows_pat.subn(rows_html_tag, tag_html)
        tag_html, _ = items_pat.subn(items_html_tag, tag_html)
        tag_html, _ = latest_pat.subn(f"../{latest_ymd}.html", tag_html)

        # タブの current を該当判定へ移す（テンプレがALLをcurrentにしている想定）
        tag_html = tag_html.replace('class="tab current" href="/daily/"', 'class="tab" href="/daily/"')
        tag_html = tag_html.replace(f'class="tab tab-{judge_key.lower()}"', f'class="tab tab-{judge_key.lower()} current"')

        # placeholder 残り検知（タグページも同様）
        if re.search(r"\{\{\s*(ROWS|ITEMS|LATEST_HREF)\s*\}\}", tag_html):
            raise RuntimeError("tag page: placeholder が残っています（ROWS/ITEMS/LATEST_HREF）")

        out_path = tags_dir / f"{judge_key.lower()}.html"
        write_text(out_path, tag_html)

    # latest.html（最新ページへリダイレクト/案内）
    latest_target = f"{latest_ymd}.html"
    latest_html = tmpl_latest.replace("{{LATEST_HREF}}", latest_target)
    latest_html = latest_html.replace("{{LATEST_DATE}}", pages[0]["date_iso"] if pages else "")
    write_text(OUT_DIR / "latest.html", latest_html)

    print(f"[OK] Generated {len(pages)} pages into: {OUT_DIR} (latest={latest_target})")


if __name__ == "__main__":
    main()
