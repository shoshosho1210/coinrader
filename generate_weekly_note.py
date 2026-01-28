#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime as dt
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SITE_URL = os.getenv("SITE_URL", "https://coinrader.net/").rstrip("/") + "/"
# 直近何日分を集計するか
DAYS = int(os.getenv("WEEK_DAYS", "7"))

def load_snapshots(days: int = DAYS) -> List[Dict[str, Any]]:
    p = Path("data/daily")
    if not p.exists():
        return []

    # 数字8桁.json を取得し、日付順にソート
    files = sorted([x for x in p.glob("*.json") if x.name[:8].isdigit()])
    files = files[-days:]
    
    out = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            out.append(data)
        except Exception:
            continue
    return out

def pct(x: Optional[float], digits: int = 1) -> str:
    if x is None: return "—"
    return f"{'+' if x >= 0 else ''}{x:.{digits}f}%"

def compute_weekly_intelligence(snaps: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not snaps: return {}

    # --- 1. 価格変化とリターン ---
    def get_price(snap, coin_id):
        # raw_dataから特定のコインを探す
        coin = next((c for c in snap.get("raw_data", []) if c["id"] == coin_id), None)
        return coin.get("current_price") if coin else None

    btc_start = get_price(snaps[0], "bitcoin")
    btc_end = get_price(snaps[-1], "bitcoin")
    btc_ret = (btc_end / btc_start - 1) * 100 if btc_start and btc_end else None

    eth_start = get_price(snaps[0], "ethereum")
    eth_end = get_price(snaps[-1], "ethereum")
    eth_ret = (eth_end / eth_start - 1) * 100 if eth_start and eth_end else None

    # --- 2. 指標の推移 (FGI, Dominance, RSI) ---
    fgi_values = [s["summary"]["sentiment"]["fgi"] for s in snaps if "sentiment" in s["summary"]]
    dom_values = [s["summary"]["sentiment"]["btc_dominance"] for s in snaps if "sentiment" in s["summary"]]
    btc_rsi_values = [s["summary"]["technical"]["btc_rsi"] for s in snaps if s["summary"].get("technical") and s["summary"]["technical"]["btc_rsi"]]

    # --- 3. 市場の幅 (Breadth) の計算 ---
    # 全銘柄のうち、何割が上昇したかの週間平均
    breadth_ratios = []
    for s in snaps:
        raw = s.get("raw_data", [])
        if not raw: continue
        ups = len([c for c in raw if (c.get("price_change_percentage_24h") or 0) > 0])
        breadth_ratios.append(ups / len(raw) * 100)

    # --- 4. トレンド・上昇銘柄の頻出調査 ---
    trend_counter = Counter()
    gainer_counter = Counter()
    for s in snaps:
        movers = s["summary"].get("top_movers", {})
        for sym in movers.get("trending", []):
            trend_counter[sym] += 1
        top_g = movers.get("top_gainer")
        if top_g and isinstance(top_g, list) and len(top_g) > 0:
            gainer_counter[top_g[0]["symbol"].upper()] += 1

    return {
        "days": len(snaps),
        "btc_ret": btc_ret,
        "eth_ret": eth_ret,
        "fgi_avg": sum(fgi_values) / len(fgi_values) if fgi_values else None,
        "fgi_latest": fgi_values[-1] if fgi_values else None,
        "dom_avg": sum(dom_values) / len(dom_values) if dom_values else None,
        "dom_change": (dom_values[-1] - dom_values[0]) if len(dom_values) > 1 else 0,
        "rsi_latest": btc_rsi_values[-1] if btc_rsi_values else None,
        "avg_breadth": sum(breadth_ratios) / len(breadth_ratios) if breadth_ratios else None,
        "trend_top": trend_counter.most_common(5),
        "gainer_top": gainer_counter.most_common(5)
    }

def render_markdown(agg: Dict[str, Any], start_date: str, end_date: str) -> str:
    # センチメント判定
    fgi = agg.get("fgi_latest", 50)
    mood = "極度の恐怖（絶好の仕込み時）" if fgi < 25 else ("恐怖" if fgi < 45 else "強欲（過熱注意）" if fgi > 75 else "中立")
    
    dom_direction = "上昇（資金の集中）" if agg.get("dom_change", 0) > 0.5 else ("低下（アルトへの分散）" if agg.get("dom_change", 0) < -0.5 else "横ばい")

    lines = []
    lines.append(f"# CoinRader 週次マーケット・インテリジェンス")
    lines.append(f"集計期間: {start_date} 〜 {end_date} ({agg['days']}日間)")
    lines.append("")
    lines.append("## 1. 週間エグゼクティブ・サマリー")
    lines.append(f"- **主要資産騰落率:** BTC {pct(agg.get('btc_ret'))} / ETH {pct(agg.get('eth_ret'))}")
    lines.append(f"- **市場の心理状態:** 指数 {agg.get('fgi_latest')}（{mood}）")
    lines.append(f"- **資金フロー:** BTCドミナンスは **{dom_direction}** の傾向")
    lines.append("")
    lines.append("## 2. 需給・テクニカル分析")
    lines.append(f"- **BTCドミナンス:** 平均 {agg.get('dom_avg', 0):.2f}%")
    lines.append(f"- **BTCテクニカル:** RSI(14)は **{agg.get('rsi_latest', '—')}**。")
    if agg.get('rsi_latest'):
        status = "売られすぎ（反発警戒）" if agg['rsi_latest'] < 30 else ("買われすぎ（調整警戒）" if agg['rsi_latest'] > 70 else "中立圏内")
        lines.append(f"  - 現在の価格水準はテクニカル的に「{status}」を示唆しています。")
    lines.append(f"- **騰落分布:** 週間平均で市場の **{agg.get('avg_breadth', 0):.1f}%** の銘柄が上昇。")
    lines.append("")
    lines.append("## 3. 今週の注目セクター & 銘柄")
    lines.append("### 🔥 トレンド頻出（市場の関心）")
    for sym, cnt in agg.get("trend_top", []):
        lines.append(f"- **{sym}**: 週内 {cnt}回ランクイン")
    
    lines.append("")
    lines.append("### 🚀 急上昇の常連（強いモメンタム）")
    if agg.get("gainer_top"):
        for sym, cnt in agg.get("gainer_top", []):
            lines.append(f"- **{sym}**: 強い買い需要を確認")
    else:
        lines.append("- 特筆すべき急騰銘柄なし")

    lines.append("")
    lines.append("## 4. 総評と来週の展望")
    if (agg.get("btc_ret") or 0) > 0 and (agg.get("dom_change", 0) < 0):
        lines.append("今週はBTCが堅調な中でドミナンスが低下しており、典型的な「アルトコインへの資金循環」が見られました。")
    elif (agg.get("btc_ret") or 0) < 0 and (agg.get("dom_change", 0) > 0):
        lines.append("全体的にリスクオフの動きが強く、資金がアルトからBTCへ退避する「クオリティへの逃避」が鮮明です。")
    else:
        lines.append("市場は方向感を模索中ですが、RSIとFGIの乖離を注視する必要があります。")

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
    
    # 期間ラベル作成
    start_date = snaps[0]["summary"]["date"]
    end_date = snaps[-1]["summary"]["date"]
    
    md_content = render_markdown(agg, start_date, end_date)
    
    # ファイル書き出し
    with open("weekly_note_draft.md", "w", encoding="utf-8-sig") as f:
        f.write(md_content)
    
    # X告知用
    short_msg = (
        f"【週次マーケット分析レポート】\n"
        f"期間: {start_date}〜{end_date}\n\n"
        f"市場心理: {agg.get('fgi_latest')} ({mood_label(agg.get('fgi_latest'))})\n"
        f"BTCドミナンス: {agg.get('dom_avg',0):.1f}%\n"
        f"注目銘柄: {', '.join([x[0] for x in agg.get('trend_top', [])[:2]])}\n\n"
        f"📝 続きはサイトの週報をチェック\n{SITE_URL}\n"
        f"#暗号資産 #CoinRader"
    )
    with open("weekly_summary.txt", "w", encoding="utf-8-sig") as f:
        f.write(short_msg)

    print("✅ 週次レポート(Markdown)と告知用テキストを生成しました。")

def mood_label(fgi):
    if not fgi: return "中立"
    if fgi < 30: return "恐怖"
    if fgi > 70: return "強欲"
    return "中立"

if __name__ == "__main__":
    main()
