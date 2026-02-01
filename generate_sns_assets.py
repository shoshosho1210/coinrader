import datetime
import os
import json
import sys

# ==========================================
# 1. 判定ロジック
# ==========================================
def determine_rsi_status(rsi):
    if rsi is None: return "ANALYZING..."
    if rsi <= 30: return "🚨 EXTREME OVERSOLD"
    if rsi <= 40: return "📉 OVERSOLD"
    if rsi >= 70: return "🚨 EXTREME OVERBOUGHT"
    if rsi >= 60: return "📈 OVERBOUGHT"
    return "⚖️ NEUTRAL"

def generate_market_topic(summary):
    btc_rsi = summary.get('technical', {}).get('btc_rsi')
    btc_dom = summary.get('btc_dominance', 0)
    top_gainer = summary.get('top_gainer', {})
    if btc_rsi and btc_rsi <= 25: return "底値圏での歴史的買い場を模索中"
    if btc_dom < 45: return "アルトコインへの資金循環が鮮明"
    if top_gainer.get('change', 0) > 15:
        return f"{top_gainer.get('symbol', '').upper()}等の特定アルトに強い買い需要"
    return "主要指標は均衡、次なるトレンド待ち"

def format_price(price):
    if price is None: return "-"
    if price >= 1000000: return f"{price/10000:.0f}万"
    return f"{price:,.0f}"

# ==========================================
# 2. メイン処理
# ==========================================
def generate_sns_assets():
    # 日本時間 (JST)
    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    file_date = jst_now.strftime("%Y%m%d")
    display_date = jst_now.strftime("%Y-%m-%d")
    date_label = jst_now.strftime("%m/%d")
    update_time = jst_now.strftime("%H:%M:%S")
    
    # データ読み込みパス
    paths = [f"data/daily/{file_date}.json", "data/daily/latest.json"]
    json_path = next((p for p in paths if os.path.exists(p)), None)

    if not json_path:
        print("❌ エラー: データJSONが見つかりません。")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    summary = data.get("summary", {})
    btc = next((c for c in data.get("raw_data", []) if c["id"] == "bitcoin"), None)
    
    btc_rsi = summary.get("technical", {}).get("btc_rsi")
    btc_dom = summary.get("btc_dominance", 0)
    fgi = summary.get("fgi", {"value": 50, "label": "Neutral"})
    chg = btc.get('price_change_percentage_24h', 0) if btc else 0
    
    rsi_status = determine_rsi_status(btc_rsi)
    topic_text = generate_market_topic(summary)

    ai_status_msg = "分析: 楽観" if chg > 3 else ("分析: 悲観" if chg < -3 else "分析: 中立")
    icon = "📈" if chg > 0 else "📉"
    trending_str = ", ".join(summary.get("trending", []))
    top_g = summary.get("top_gainer", {"symbol": "-", "change": 0})

    # --- ① SNS投稿用短文 (Twitter/X用) ---
    short_post = (
        f"🤖 CoinRader 市場速報 ({date_label})\n{ai_status_msg}\n\n"
        f"🔹 Bitcoin {icon}\n価格: ¥{format_price(btc['current_price']) if btc else '-'}\n"
        f"前日比: {'+' if chg > 0 else ''}{chg:.1f}%\nRSI(14): {btc_rsi if btc_rsi else '-'}\n"
        f"心理指数: {fgi['value']} ({fgi['label']})\n\n"
        f"📈 注目銘柄\nトレンド入り: {trending_str}\n急上昇銘柄: {top_g['symbol']} ({int(top_g['change'])}%↑)\n\n"
        f"📊 詳細分析\nhttps://coinrader.net/share/{file_date}.html\n\n#CoinRader #ビットコイン #暗号資産"
    )

    # --- ② 画像オーバーレイ用テキスト ---
    image_overlay_text = (
        f"MARKET UPDATE: [ {date_label} ]\n"
        f"FGI: [ {fgi['value']} ({fgi['label']}) ]\n"
        f"BTC RSI(14): [ {btc_rsi if btc_rsi else '-'} ]\n"
        f"STATUS: [ {rsi_status} ]\n"
        f"TOPIC: [ {topic_text} ]"
    )

    # --- ③ daily_note_draft.md (詳細レポート案) ---
    note_content = f"""# Market Note {display_date} ({update_time} 更新)

## 📊 今日の主要マーケット指標
- **BTC価格:** ¥{format_price(btc['current_price']) if btc else '-'} ({'+' if chg > 0 else ''}{chg:.1f}%)
- **BTC RSI(14):** {btc_rsi if btc_rsi else 'データ収集中'}
- **心理指数(FGI):** {fgi['value']} ({fgi['label']})
- **BTCドミナンス:** {btc_dom}%

## 📈 注目銘柄の動向
- **トレンド入り:** {trending_str}
- **本日の急上昇銘柄:** {top_g['symbol']} ({int(top_g['change'])}%↑)

## ✍️ 市場分析メモ
- 本日の市場センチメントは「{fgi['label']}」となっており、{ai_status_msg}の傾向が見られます。
- テクニカル的にはBTC RSIが {btc_rsi if btc_rsi else '-'} の水準にあり、{'買われすぎ' if (btc_rsi or 0) > 70 else '売られすぎ' if (btc_rsi or 0) < 30 else '中立圏'} を示唆しています。
"""

    # --- ④ シェア用HTML ---
    share_html = f"<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>CoinRader {display_date}</title><meta property='og:image' content='https://coinrader.net/assets/og/ogp2.png?v={file_date}'><meta http-equiv='refresh' content='0;url=https://coinrader.net/?v={file_date}'></head></html>"

    # --- 💾 ファイル書き出しセクション ---
    try:
        os.makedirs("share", exist_ok=True)
        # 短文
        with open("daily_post_short.txt", "w", encoding="utf-8") as f: f.write(short_
