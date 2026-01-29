#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime as dt
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SITE_URL = os.getenv("SITE_URL", "https://coinrader.net/").rstrip("/") + "/"
DAYS = int(os.getenv("WEEK_DAYS", "7"))

def load_snapshots(days: int = DAYS) -> List[Dict[str, Any]]:
    p = Path("data/daily")
    if not p.exists(): return []
    # ファイル名が "YYYYMMDD.json" の形式のものだけを対象にする
    files = sorted([x for x in p.glob("*.json") if x.stem.isdigit() and len(x.stem) == 8])
    files = files[-days:]
    out = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
            if not text.strip(): continue
            data = json.loads(text)
            out.append(data)
        except Exception as e: 
            print(f"Warning: Failed to load {f.name}: {e}")
            continue
    return out

def pct(x: Optional[float], digits: int = 1) -> str:
    if x is None: return "—"
    return f"{'+' if x >= 0 else ''}{x:.{digits}f}%"

def mood_label(fgi):
    if fgi is None: return "中立"
    if fgi < 25: return "極度の恐怖"
    if fgi < 45: return "恐怖"
    if fgi > 75: return "強欲"
    return "中立"

def compute_weekly_intelligence(snaps: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not snaps: return {}

    # --- 1. 価格変化 ---
    def get_price(snap, coin_id):
        # raw_data がリストの場合と辞書の場合に対応（念のため）
        raw = snap.get("raw_data", [])
        if isinstance(raw, list):
            coin = next((c for c in raw if c.get("id") == coin_id), None)
            return coin.get("current_price") if coin else None
        return None

    btc_start = get_price(snaps[0], "bitcoin")
    btc_end = get_price(snaps[-1], "bitcoin")
    btc_ret = (btc_end / btc_start - 1) * 100 if btc_start and btc_end else None

    eth_start = get_price(snaps[0], "ethereum")
    eth_end = get_price(snaps[-1], "ethereum")
    eth_ret = (eth_end / eth_start - 1) * 100 if eth_start and eth_end else None

    # --- 2. 指標の推移 ---
    fgi_values = []
    dom_values = []
    btc_rsi_values = []
    btc_ma_values = []

    for s in snaps:
        summary = s.get("summary", {})
        
        # FGI
        fgi_data = summary.get("fgi")
        if isinstance(fgi_data, dict):
            fgi_values.append(fgi_data.get("value"))
        elif isinstance(fgi_data, int): # 古い形式対応
            fgi_values.append(fgi_data)
            
        # Dominance
        if "btc_dominance" in summary:
            dom_values.append(summary["btc_dominance"])
            
        # Technical
        tech = summary.get("technical", {})
        if "btc_rsi" in tech:
            btc_rsi_values.append(tech["btc_rsi"])
        if "btc_ma_distance" in tech:
            btc_ma_values.append(tech["btc_ma_distance"])

    # None除去
    fgi_values = [v for v in fgi_values if v is not None]
    dom_values = [v for v in dom_values if v is not None]
    btc_rsi_values = [v for v in btc_rsi_values if v is not None]
    btc_ma_values = [v for v in btc_ma_values if v is not None]

    # --- 3. 市場の幅 (Breadth) ---
    breadth_ratios = []
    for s in snaps:
        raw = s.get("raw_data", [])
        if not raw or not isinstance(raw, list): continue
        ups = len([c for c in raw if (c.get("price_change_percentage_24h") or 0) > 0])
        total = len(raw)
        if total > 0:
            breadth_ratios.append(ups / total * 100)

    # --- 4. トレンド・上昇銘柄 ---
    trend_counter = Counter()
    gainer_counter = Counter()
    
    for s in snaps:
        sum_data = s.get("summary", {})
        # Trending
        trends = sum_data.get("trending", [])
        if isinstance(trends, list):
            for sym in trends:
                if sym: trend_counter[sym] += 1
        
        # Gainer
        top_g = sum_data.get("top_gainer", {})
        if isinstance(top_g, dict) and top_g.get("symbol"):
            gainer_counter[top_g["symbol"]] += 1

    return {
        "days": len(snaps),
        "btc_ret": btc_ret,
        "eth_ret": eth_ret,
        "fgi_avg": sum(fgi_values) / len(fgi_values) if fgi_values else None,
        "fgi_latest": fgi_values[-1] if fgi_values else None,
        "dom_avg": sum(dom_values) / len(dom_values) if dom_values else None,
        "dom_change": (dom_values[-1] - dom_values[0]) if len(dom_values) > 1 else 0,
        "rsi_latest": btc_rsi_values[-1] if btc_rsi_values else None,
        "ma_latest": btc_ma_values[-1] if btc_ma_values else None,
        "avg_breadth": sum(breadth_ratios) / len(breadth_ratios) if breadth_ratios else None,
        "trend_top": trend_counter.most_common(5),
        "gainer_top": gainer_counter.most_common(5)
    }

def render_markdown(agg: Dict[str, Any], start_date: str, end_date: str) -> str:
    fgi = agg.get("fgi_latest")
    mood = mood_label(fgi)
    
    dom_change = agg.get("dom_change", 0)
    dom_direction = "上昇（資金の集中）" if dom_change > 0.5 else ("低下（アルトへの分散）" if dom_change < -0.5 else "横ばい")

    lines = [
        f"# CoinRader 週次マーケット・インテリジェンス",
        f"集計期間: {start_date} 〜 {end_date} ({agg['days']}日間)",
        "",
        "## 1. 週間エグゼクティブ・サマリー",
        f"- **主要資産騰落率:** BTC {pct(agg.get('btc_ret'))} / ETH {pct(agg.get('eth_ret'))}",
        f"- **市場の心理状態:** 指数 {fgi if fgi is not None else '-'}（{mood}）",
        f"- **資金フロー:** BTCドミナンスは **{dom_direction}** の傾向",
        "",
        "## 2. 需給・テクニカル分析",
        f"- **長期トレンド (MA乖離):** 現在 **{pct(agg.get('ma_latest'))}**",
        f"  - 50日/200日移動平均の距離はトレンドの大局を示します。現在は「{'強気相場' if (agg.get('ma_latest') or 0) > 0 else '弱気相場'}」の範疇にあります。",
        f"- **短期勢い (RSI):** RSI(14)は **{agg.get('rsi_latest', '—')}**",
        f"  - {'売られすぎ（反発警戒）' if (agg.get('rsi_latest') or 50) < 30 else '買われすぎ（調整警戒）' if (agg.get('rsi_latest') or 50) > 70 else '中立圏内'}を示唆しています。",
        f"- **騰落分布:** 週間平均で市場の **{agg.get('avg_breadth', 0):.1f}%** の銘柄が上昇。",
        "",
        "## 3. 今週の注目セクター & 銘柄",
        "### 🔥 トレンド頻出（市場の関心）"
    ]
    
    if agg.get("trend_top"):
        for sym, cnt in agg.get("trend_top", []):
            lines.append(f"- **{sym}**: 週内 {cnt}回ランクイン")
    else:
        lines.append("- 特筆すべきトレンドなし")
    
    lines.append("")
    lines.append("### 🚀 急上昇の常連（強いモメンタム）")
    if agg.get("gainer_top"):
        for sym, cnt in agg.get("gainer_top", []):
            lines.append(f"- **{sym}**: 週内 {cnt}回ランクイン（買い需要継続）")
    else:
        lines.append("- 特筆すべき急騰銘柄なし")

    lines.append("")
    lines.append("## 4. 総評と来週の展望")
    
    # 簡易的なロジックによる総評生成
    btc_ret = agg.get("btc_ret", 0) or 0
    
    if btc_ret > 0 and dom_change < 0:
        lines.append("今週はBTCが堅調な中でドミナンスが低下しており、典型的な「アルトコインへの資金循環」が見られました。リスクオンの姿勢が強まっています。")
    elif btc_ret < 0 and dom_change > 0:
        lines.append("全体的にリスクオフの動きが強く、資金がアルトからBTCへ退避する「クオリティへの逃避」が鮮明です。")
    elif (agg.get("ma_latest") or 0) < 0:
        lines.append("市場は方向感を模索中ですが、長期トレンド（MA乖離）がマイナス圏にあり、本格的な回復にはまだ時間を要する局面です。")
    else:
        lines.append("市場は方向感を模索中ですが、長期トレンドは維持されています。個別銘柄の材料による選別色が強まる一週間でした。")

    lines.append("")
    lines.append("---")
    lines.append(f"📊 詳細分析ダッシュボード: {SITE_URL}")
    lines.append("※ 本レポートはAIによる自動生成であり、投資助言ではありません。")

    return "\n".join(lines)

def main():
    snaps = load_snapshots(DAYS)
    if not snaps:
        print("集計対象のデータが見つかりませんでした。")
        return

    agg = compute_weekly_intelligence(snaps)
    
    # 日付の安全な取得
    try:
        start_date = snaps[0]["summary"]["date"]
        end_date = snaps[-1]["summary"]["date"]
    except KeyError:
        start_date = "Unknown"
        end_date = "Unknown"
    
    md_content = render_markdown(agg, start_date, end_date)
    
    with open("weekly_note_draft.md", "w", encoding="utf-8-sig") as f:
        f.write(md_content)
    
    # X (Twitter) 用のショートメッセージ
    fgi_latest = agg.get('fgi_latest')
    trend_top = agg.get('trend_top', [])
    trend_str = ', '.join([x[0] for x in trend_top[:2]]) if trend_top else "なし"
    
    short_msg = (
        f"【週次マーケット分析レポート】\n"
        f"期間: {start_date}〜{end_date}\n\n"
        f"市場心理: {fgi_latest if fgi_latest is not None else '-'} ({mood_label(fgi_latest)})\n"
        f"長期トレンド: {pct(agg.get('ma_latest'))}\n"
        f"注目銘柄: {trend_str}\n\n"
        f"📝 続きはサイトの週報をチェック\n{SITE_URL}\n"
        f"#暗号資産 #CoinRader"
    )
    with open("weekly_summary.txt", "w", encoding="utf-8-sig") as f:
        f.write(short_msg)

    print("✅ 週次レポートと告知用テキストを生成しました。")

if __name__ == "__main__":
    main()
