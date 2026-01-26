#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CoinRader: 週次レポート（note下書き）を自動生成する。

入力:
  - data/daily/YYYYMMDD.json (generate_daily_post_v2.py が生成)

出力:
  - weekly_note_draft.md     (note貼り付け用 下書き)
  - weekly_summary.txt       (X等の短文告知用)
  - weekly_share_url.txt     (週次share URL。必要なら別途HTMLも作れる)

※ 週次は「過去7日分（存在する分）」を集計し、数字 + 文章を軽めにまとめる。
"""
from __future__ import annotations

import datetime as dt
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SITE_URL = os.getenv("SITE_URL", "https://coinrader.net/").rstrip("/") + "/"
DAYS = int(os.getenv("WEEK_DAYS", "7"))


def load_snapshots(days: int = DAYS) -> List[Dict[str, Any]]:
    p = Path("data/daily")
    if not p.exists():
        return []

    files = sorted([x for x in p.glob("*.json") if x.name[:8].isdigit()])
    # 新しい順に最大days
    files = files[-days:]
    out = []
    for f in files:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    # 日付順
    out.sort(key=lambda d: d.get("date", ""))
    return out


def pct(x: Optional[float], digits: int = 1) -> str:
    if x is None:
        return "—"
    sign = "+" if x >= 0 else ""
    return f"{sign}{x:.{digits}f}%"


def fmt_oku_jpy(x: Optional[float]) -> str:
    if x is None:
        return "—"
    return f"{x/1e8:.1f}億円"


def date_range_label(snaps: List[Dict[str, Any]]) -> Tuple[str, str, str]:
    if not snaps:
        return ("", "", "")
    s = snaps[0]["date"]
    e = snaps[-1]["date"]
    s2 = f"{s[:4]}-{s[4:6]}-{s[6:]}"
    e2 = f"{e[:4]}-{e[4:6]}-{e[6:]}"
    tag = snaps[-1]["date"]
    return s2, e2, tag


def compute_weekly(snaps: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not snaps:
        return out

    # --- Breadth aggregate ---
    up_ratios = []
    avg_chgs = []
    days_up = 0
    days_down = 0
    for s in snaps:
        b = s.get("breadth", {}) or {}
        up = b.get("up")
        down = b.get("down")
        if isinstance(up, int) and isinstance(down, int):
            if up >= down:
                days_up += 1
            else:
                days_down += 1
        ur = b.get("upRatio")
        ac = b.get("avgChg")
        if isinstance(ur, (int, float)):
            up_ratios.append(float(ur))
        if isinstance(ac, (int, float)):
            avg_chgs.append(float(ac))

    out["breadth"] = {
        "days": len(snaps),
        "days_up": days_up,
        "days_down": days_down,
        "avg_up_ratio": (sum(up_ratios) / len(up_ratios)) if up_ratios else None,
        "avg_avg_chg": (sum(avg_chgs) / len(avg_chgs)) if avg_chgs else None,
    }

    # --- BTC/ETH weekly return (using daily price snapshots) ---
    def weekly_return(sym: str) -> Optional[float]:
        prices = []
        for s in snaps:
            p = (s.get(sym, {}) or {}).get("price_jpy")
            if isinstance(p, (int, float)) and p > 0:
                prices.append(float(p))
        if len(prices) < 2:
            return None
        return (prices[-1] / prices[0] - 1.0) * 100.0

    out["btc_ret"] = weekly_return("btc")
    out["eth_ret"] = weekly_return("eth")

    # --- Trending frequency ---
    trend_counter = Counter()
    for s in snaps:
        for t in (s.get("trend") or [])[:3]:
            sym = (t.get("symbol") or "").strip()
            if sym:
                trend_counter[sym] += 1
    out["trend_top"] = trend_counter.most_common(10)

    # --- Gainers frequency + max gain observed ---
    gain_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "max_pc": None})
    for s in snaps:
        for g in (s.get("gainers") or [])[:3]:
            sym = (g.get("symbol") or "").strip()
            pc = g.get("pc24")
            if not sym:
                continue
            gain_stats[sym]["count"] += 1
            if isinstance(pc, (int, float)):
                cur = gain_stats[sym]["max_pc"]
                if cur is None or pc > cur:
                    gain_stats[sym]["max_pc"] = float(pc)
    # sort by count desc, then max_pc desc
    gain_sorted = sorted(
        [(k, v["count"], v["max_pc"]) for k, v in gain_stats.items()],
        key=lambda x: (x[1], x[2] if x[2] is not None else -1e9),
        reverse=True,
    )
    out["gainers_top"] = gain_sorted[:10]

    # --- Alt volume frequency ---
    vol_counter = Counter()
    for s in snaps:
        for v in (s.get("vol_alt") or [])[:3]:
            sym = (v.get("symbol") or "").strip()
            if sym:
                vol_counter[sym] += 1
    out["vol_top"] = vol_counter.most_common(10)

    return out


def render_note(snaps: List[Dict[str, Any]], agg: Dict[str, Any]) -> str:
    s2, e2, tag = date_range_label(snaps)
    share_url = f"{SITE_URL}share/{tag}.html" if tag else SITE_URL

    b = agg.get("breadth", {})
    mood = "上昇優勢" if (b.get("days_up", 0) >= b.get("days_down", 0)) else "下落優勢"

    # A案 見出し構成
    lines = []
    lines.append(f"# CoinRader 週次レポート（{s2}〜{e2}）")
    lines.append("")
    lines.append("## 1. 今週の結論（3行サマリー）")
    lines.append(f"- 市場ムード：**{mood}**（上昇優勢日 {b.get('days_up',0)} / 下落優勢日 {b.get('days_down',0)}）")
    lines.append(f"- 上位250の平均変化：**{pct(b.get('avg_avg_chg'),2)}**（日次平均）／ 上昇比率：**{(round(b.get('avg_up_ratio')) if isinstance(b.get('avg_up_ratio'), (int,float)) else '—')}%**（日次平均）")
    lines.append(f"- BTC/ETH（週次）：BTC **{pct(agg.get('btc_ret'),1)}** / ETH **{pct(agg.get('eth_ret'),1)}**（日次スナップショットから算出）")
    lines.append("")
    lines.append("## 2. 週間の値動きまとめ（見方）")
    lines.append("- CoinRaderの「今日の注目」は *トレンド / 上昇率(24h) / 出来高(アルト)* の3軸で“いま”を拾います。")
    lines.append("- 週次では、毎日の上位3位を集計して「よく出た銘柄」「急騰の常連」「出来高の主役」を俯瞰します。")
    lines.append("")
    lines.append("## 3. トレンドの継続と入れ替わり")
    tt = agg.get("trend_top", [])[:5]
    if tt:
        lines.append("今週よくトレンド入りした銘柄（出現回数）")
        for sym, cnt in tt:
            lines.append(f"- {sym}：{cnt}日")
    else:
        lines.append("（データ不足）")
    lines.append("")
    lines.append("## 4. 上昇率(24h)の主役")
    gt = agg.get("gainers_top", [])[:5]
    if gt:
        lines.append("今週よく上昇率TOP3に入った銘柄（出現回数 / 最大上昇）")
        for sym, cnt, maxpc in gt:
            lines.append(f"- {sym}：{cnt}日 / 最大 {pct(maxpc,1)}")
    else:
        lines.append("（データ不足）")
    lines.append("")
    lines.append("## 5. 出来高(アルト)の主役")
    vt = agg.get("vol_top", [])[:5]
    if vt:
        lines.append("今週よく出来高TOP3に入った銘柄（出現回数）")
        for sym, cnt in vt:
            lines.append(f"- {sym}：{cnt}日")
    else:
        lines.append("（データ不足）")
    lines.append("")
    lines.append("## 6. 来週の監視リスト（最大5）")
    # シンプルに「トレンド頻出」「上昇頻出」「出来高頻出」を混ぜる
    watch = []
    for sym, _ in (tt or []):
        if sym not in watch:
            watch.append(sym)
        if len(watch) >= 5:
            break
    for sym, _, _ in (gt or []):
        if sym not in watch:
            watch.append(sym)
        if len(watch) >= 5:
            break
    for sym, _ in (vt or []):
        if sym not in watch:
            watch.append(sym)
        if len(watch) >= 5:
            break
    if watch:
        for sym in watch[:5]:
            lines.append(f"- {sym}：出来高の維持／連騰の継続／トレンドの再浮上を確認")
    else:
        lines.append("（データ不足）")
    lines.append("")
    lines.append("## 7. 参考リンク")
    lines.append(f"- 今日の注目（最新）：{share_url}")
    lines.append(f"- ダッシュボード：{SITE_URL}")
    lines.append("")
    lines.append("## 8. 算出ルール（要約）")
    if snaps:
        rules = (snaps[-1].get("rules") or {})
        min_vol = rules.get("min_vol_jpy")
        if isinstance(min_vol, (int, float)):
            lines.append(f"- 上昇率(24h)は出来高 **{min_vol/1e8:.1f}億円以上** を優先（不足時は出来高順で補完）")
        lines.append("- 出来高(アルト)は BTC/ETH とステーブル系を除外")
        lines.append("- 数値は CoinGecko API の日次スナップショットに基づく（厳密な週次ローソクではありません）")
    lines.append("")
    lines.append("----")
    lines.append("免責：本レポートは情報提供であり、投資助言ではありません。最終判断はご自身でお願いします。")

    return "\n".join(lines)


def main() -> None:
    snaps = load_snapshots(DAYS)
    agg = compute_weekly(snaps)

    md = render_note(snaps, agg)

    # Windowsでも開きやすいよう utf-8-sig
    Path("weekly_note_draft.md").write_text(md, encoding="utf-8-sig")

    s2, e2, tag = date_range_label(snaps)
    share_url = f"{SITE_URL}share/{tag}.html" if tag else SITE_URL
    short = (
        f"【週次レポート {s2}〜{e2}】\n"
        f"市場ムード: {('上昇優勢' if agg.get('breadth',{}).get('days_up',0)>=agg.get('breadth',{}).get('days_down',0) else '下落優勢')}\n"
        f"BTC {pct(agg.get('btc_ret'),1)} / ETH {pct(agg.get('eth_ret'),1)}\n"
        f"→ {share_url}\n"
        f"#暗号資産"
    )
    Path("weekly_summary.txt").write_text(short, encoding="utf-8-sig")
    Path("weekly_share_url.txt").write_text(share_url, encoding="utf-8-sig")

    print("wrote: weekly_note_draft.md / weekly_summary.txt / weekly_share_url.txt")


if __name__ == "__main__":
    main()
