import datetime
import os
import json
import sys

# --- 1. 補助関数（ロジック完全復元） ---
def determine_rsi_status(rsi):
    if rsi is None: return "分析中"
    if rsi <= 30: return "売られすぎ"
    if rsi <= 40: return "やや売られすぎ"
    if rsi >= 70: return "買われすぎ"
    if rsi >= 60: return "やや買われすぎ"
    return "中立圏"

def generate_market_topic(summary):
    btc_rsi = summary.get('technical', {}).get('btc_rsi')
    btc_dom = summary.get('btc_dominance', 0)
    top_gainer = summary.get('top_gainer', {})
    if btc_rsi and btc_rsi <= 25: return "パニック売り一巡、底打ち反転を模索中"
    if btc_dom < 45: return "アルトへの資金循環。セクター別物色の兆候"
    if top_gainer.get('change', 0) > 15:
        return f"特定アルト({top_gainer.get('symbol', '').upper()})への強い買い需要"
    return "主要指標は均衡、次のトレンド待ちの局面"

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
    
    # Git強制更新用の不可視タグ（ファイルの末尾に隠す）
    git_force_tag = f"\n"
    
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
    btc_dom = summary.get("btc_dominance", 0)
    fgi = summary.get("fgi", {"value": 50, "label": "Neutral"})
    chg = btc.get('price_change_percentage_24h', 0) if btc else 0
    
    ai_status_msg = "分析: 楽観" if chg > 3 else ("分析: 悲観" if chg < -3 else "分析: 中立")
    icon = "📈" if chg > 0 else "📉"
    trending_str = ", ".join(summary.get("trending", []))
    top_g = summary.get("top_gainer", {"symbol": "-", "change": 0})
    rsi_note = determine_rsi_status(btc_rsi)

    # --- ① SNS投稿用テキスト (short) ---
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
        f"{git_force_tag}"
    )

    # --- ② 【完全復元】daily_note_draft.md ---
    note_content = (
        f"# Market Note {display_date} ({update_time} 更新)\n\n"
        f"## 📊 今日の主要マーケット指標\n"
        f"- **BTC価格:** ¥{format_price(btc['current_price']) if btc else '-'} ({'+' if chg > 0 else ''}{chg:.1f}%)\n"
        f"- **BTC RSI(14):** {btc_rsi if btc_rsi else '-'}\n"
        f"- **心理指数(FGI):** {fgi['value']} ({fgi['label']})\n"
        f"- **BTCドミナンス:** {btc_dom}%\n\n"
        f"## 📈 注目銘柄の動向\n"
        f"- **トレンド入り:** {trending_str}\n"
        f"- **本日の急上昇銘柄:** {top_g['symbol']} ({int(top_g['change'])}%↑)\n\n"
        f"## ✍️ 市場分析メモ\n"
        f"- 本日の市場センチメントは「{fgi['label']}」となっており、{ai_status_msg}の傾向が見られます。\n"
        f"- テクニカル的にはBTC RSIが {btc_rsi if btc_rsi else '-'} の水準にあり、{rsi_note} を示唆しています。"
        f"{git_force_tag}"
    )

    # --- ③ HTML出力 ---
    share_html = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>CoinRader {display_date}</title>
  <meta property="og:title" content="CoinRader - 今日の注目 {display_date}">
  <meta property="og:url" content="https://coinrader.net/share/{file_date}.html">
  <meta property="og:image" content="https://coinrader.net/assets/og/ogp_v2.png?v={file_date}">
  <meta name="twitter:card" content="summary_large_image">
  <meta http-equiv="refresh" content="0;url=https://coinrader.net/?v={file_date}">
</head>
<body></body>
</html>"""

    # --- 💾 ファイル書き出し ---
    try:
        os.makedirs("share", exist_ok=True)
        with open("daily_post_short.txt", "w", encoding="utf-8") as f: f.write(short_post)
        with open("daily_note_draft.md", "w", encoding="utf-8") as f: f.write(note_content)
        with open("daily_share_url.txt", "w", encoding="utf-8") as f: 
            f.write(f"https://coinrader.net/share/{file_date}.html?t={jst_now.strftime('%H%M')}")
        with open(f"share/{file_date}.html", "w", encoding="utf-8") as f: f.write(share_html)
        
        # ==========================================
        # 💡 [変更箇所] daily_image_overlay.txt 
        # nano banana pro（画像生成AI）用の詳細プロンプト
        # ==========================================
        fgi_val = fgi.get('value', 50)
        # 恐怖指数に応じた発光色の指定
        accent_color = "赤色(Neon Red)" if fgi_val <= 30 else "オレンジ色(Orange)" if fgi_val <= 45 else "シアン(Cyan)"
        
        ai_image_prompt = (
            f"Attached is the base template 'ogp_v2.png'. \n"
            f"Please overlay the following market data onto the right-side highlighted area in a professional cyberpunk HUD style. \n"
            f"Ensure the text has a subtle neon glow and is perfectly integrated into the background theme.\n\n"
            f"--- DATA TO OVERLAY ---\n"
            f"DATE: [ {date_label} ]\n"
            f"SENTIMENT: [ {fgi_val} ({fgi.get('label', 'Neutral')}) ]\n"
            f"BTC RSI: [ {btc_rsi if btc_rsi else '-'} ]\n"
            f"STATUS: [ {ai_status_msg} / {rsi_note} ]\n"
            f"FOCUS: [ {generate_market_topic(summary)} ]\n\n"
            f"--- DESIGN INSTRUCTION ---\n"
            f"Use high-tech digital font. Highlight the SENTIMENT value with a '{accent_color}' glow. \n"
            f"Maintain a clean, sophisticated atmosphere for institutional traders."
        )

        with open("daily_image_overlay.txt", "w", encoding="utf-8") as f:
            f.write(ai_image_prompt.strip())
            
        print(f"✅ 全アセット生成完了。AI画像プロンプトを書き出しました ({update_time})")

    except Exception as e:
        print(f"❌ 書き込み失敗: {e}")
        sys.exit(1)

if __name__ == "__main__":
    generate_sns_assets()
