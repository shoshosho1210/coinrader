import datetime
import os
import json
import sys

# --- 1. 補助関数 ---
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

# --- 2. メイン処理 ---
def generate_sns_assets():
    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    file_date = jst_now.strftime("%Y%m%d")
    display_date = jst_now.strftime("%Y-%m-%d")
    date_label = jst_now.strftime("%m/%d")
    update_time = jst_now.strftime("%H:%M:%S")
    
    # Git強制更新用タグ
    force_update_tag = f"\n\n(Generated at: {update_time})"
    
    paths = [f"data/daily/{file_date}.json", "data/daily/latest.json"]
    json_path = next((p for p in paths if os.path.exists(p)), None)

    if not json_path:
        print("❌ エラー: データJSONが見つかりません。")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # データ抽出
    summary = data.get("summary", {})
    btc = next((c for c in data.get("raw_data", []) if c["id"] == "bitcoin"), None)
    
    btc_rsi = summary.get("technical", {}).get("btc_rsi")
    fgi = summary.get("fgi", {"value": 50, "label": "Neutral"})
    chg = btc.get('price_change_percentage_24h', 0) if btc else 0
    
    ai_status_msg = "分析: 楽観" if chg > 3 else ("分析: 悲観" if chg < -3 else "分析: 中立")
    icon = "📈" if chg > 0 else "📉"
    trending_str = ", ".join(summary.get("trending", []))
    top_g = summary.get("top_gainer", {"symbol": "-", "change": 0})

    # --- ① SNS投稿用テキスト (short) の復元 ---
    short_post = (
        f"🤖 CoinRader 市場速報 ({date_label})\n"
        f"{ai_status_msg}\n\n"
        f"🔹 Bitcoin {icon}\n"
        f"価格: ¥{format_price(btc['current_price']) if btc else '-'}\n"
        f"前日比: {'+' if chg > 0 else ''}{chg:.1f}%\n"
        f"RSI(14): {btc_rsi if btc_rsi else '-'}\n"
        f"心理指数: {fgi['value']} ({fgi['label']})\n\n"
        f"📈 注目銘柄\n"
        f"トレンド入り: {trending_str}\n"
        f"急上昇銘柄: {top_g['symbol']} ({int(top_g['change'])}%↑)\n\n"
        f"📊 詳細分析\n"
        f"https://coinrader.net/share/{file_date}.html\n\n"
        f"#CoinRader #ビットコイン #暗号資産"
        f"{force_update_tag}"
    )

    # --- ② 画像オーバーレイ用 ---
    image_overlay_text = (
        f"MARKET UPDATE: [ {date_label} ]\n"
        f"FGI: [ {fgi['value']} ({fgi['label']}) ]\n"
        f"BTC RSI(14): [ {btc_rsi if btc_rsi else '-'} ]\n"
        f"STATUS: [ {determine_rsi_status(btc_rsi)} ]\n"
        f"TOPIC: [ {generate_market_topic(summary)} ]"
    )

    # --- ③ daily_note_draft.md ---
    note_content = (
        f"# Market Note {display_date} ({update_time} 更新)\n\n"
        f"## 📊 今日の主要マーケット指標\n"
        f"- **BTC価格:** ¥{format_price(btc['current_price']) if btc else '-'}\n"
        f"- **BTC RSI(14):** {btc_rsi if btc_rsi else '-'}\n"
        f"- **心理指数(FGI):** {fgi['value']} ({fgi['label']})\n"
    )

    # --- ④ HTML出力の完全復元 ---
    share_html = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>CoinRader {display_date}</title>
  <meta property="og:title" content="CoinRader - 今日の注目 {display_date}">
  <meta property="og:url" content="https://coinrader.net/share/{file_date}.html">
  <meta property="og:image" content="https://coinrader.net/assets/og/ogp2.png?v={file_date}">
  <meta name="twitter:card" content="summary_large_image">
  <meta http-equiv="refresh" content="0;url=https://coinrader.net/?v={file_date}">
</head>
<body></body>
</html>"""

    # --- ファイル書き出し ---
    try:
        os.makedirs("share", exist_ok=True)
        with open("daily_post_short.txt", "w", encoding="utf-8") as f: f.write(short_post)
        with open("daily_image_overlay.txt", "w", encoding="utf-8") as f: f.write
