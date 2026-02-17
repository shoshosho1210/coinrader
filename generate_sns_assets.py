import datetime
import os
import json
import sys

# --- 1. RSI計算ロジック (HTML側のJavaScriptと完全一致) ---
def calculate_latest_rsi(prices, period=14):
    """
    CoinGeckoのスパークライン(価格配列)からWilder's RSIを計算し、
    最新(最後)の値を返す関数
    """
    if not prices or len(prices) < period + 1:
        return None

    # 1. 最初のperiod回分の平均ゲイン/ロスを計算 (Simple Average)
    gain_sum = 0
    loss_sum = 0
    for i in range(1, period + 1):
        diff = prices[i] - prices[i-1]
        if diff >= 0:
            gain_sum += diff
        else:
            loss_sum += -diff

    avg_gain = gain_sum / period
    avg_loss = loss_sum / period

    # 2. その後のデータをWilder's Smoothingで計算
    current_rsi = 0
    
    # period地点の初期RSI
    if avg_loss == 0:
        current_rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        current_rsi = 100.0 - (100.0 / (1.0 + rs))

    # period + 1 から最後までループして最新値を導出
    for i in range(period + 1, len(prices)):
        diff = prices[i] - prices[i-1]
        gain = diff if diff > 0 else 0
        loss = -diff if diff < 0 else 0

        # Wilder's Smoothing
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

        if avg_loss == 0:
            current_rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            current_rsi = 100.0 - (100.0 / (1.0 + rs))
            
    return current_rsi

# --- 2. 補助関数 ---
def determine_rsi_status(rsi):
    if rsi is None: return "分析中"
    if rsi <= 30: return "売られすぎ"
    if rsi <= 40: return "やや売られすぎ"
    if rsi >= 70: return "買われすぎ"
    if rsi >= 60: return "やや買われすぎ"
    return "中立圏"

def generate_market_topic(summary, btc_chg=None):
    fgi_value = summary.get('fgi', {}).get('value')
    is_bear = (fgi_value is not None and fgi_value <= 30) or (btc_chg is not None and btc_chg <= -3)
    return "市場局面: リスクオフ（警戒）" if is_bear else "市場局面: リスクオン（選別）"

def determine_ai_status(summary, btc_chg=None):
    fgi_value = summary.get('fgi', {}).get('value')
    if fgi_value is None and btc_chg is None:
        return "分析: 中立", "neutral"
    is_bear = (fgi_value is not None and fgi_value <= 30) or (btc_chg is not None and btc_chg <= -3)
    return ("分析: 弱気 (BEAR)", "bear") if is_bear else ("分析: 強気 (BULL)", "bull")

def format_price(price):
    if price is None: return "-"
    if price >= 1000000: return f"{price/10000:.0f}万"
    return f"{price:,.0f}"

# --- 3. メイン処理 ---
def generate_sns_assets():
    print("🚀 処理を開始します...")
    
    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    file_date = jst_now.strftime("%Y%m%d")
    display_date = jst_now.strftime("%Y-%m-%d")
    date_label = jst_now.strftime("%m/%d")
    update_time = jst_now.strftime("%H:%M:%S")
    git_force_tag = "\n"
    
    # JSON読み込み
    target_files = [f"data/daily/{file_date}.json", "data/latest.json"]
    json_path = next((p for p in target_files if os.path.exists(p)), None)

    if not json_path:
        print("❌ エラー: データJSONが見つかりません。")
        sys.exit(1)

    print(f"📂 Reading data from: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    summary = data.get("summary", {})
    raw_data = data.get("raw_data", [])
    
    # BTCデータの探索
    btc = next((c for c in raw_data if c.get("id") == "bitcoin"), None)
    
    # --- ★強化ポイント: データの徹底探索とRSI再計算 ---
    spark_prices = []
    
    # 1. ロードしたファイルから探す
    if btc:
        raw_spark = btc.get("sparkline_in_7d")
        if raw_spark:
            # { "price": [...] } の形式か、直接 [...] の形式か両方対応
            if isinstance(raw_spark, dict):
                spark_prices = raw_spark.get("price", [])
            elif isinstance(raw_spark, list):
                spark_prices = raw_spark
    
    # 2. なければ latest.json を強制的に見に行く
    fallback_path = "data/latest.json"
    if not spark_prices and json_path != fallback_path:
        if os.path.exists(fallback_path):
            print(f"⚠️ {os.path.basename(json_path)} にデータがないため、{fallback_path} を確認します...")
            try:
                with open(fallback_path, "r", encoding="utf-8") as f2:
                    data2 = json.load(f2)
                    btc2 = next((c for c in data2.get("raw_data", []) if c.get("id") == "bitcoin"), None)
                    if btc2:
                        raw_spark2 = btc2.get("sparkline_in_7d")
                        if isinstance(raw_spark2, dict):
                            spark_prices = raw_spark2.get("price", [])
                        elif isinstance(raw_spark2, list):
                            spark_prices = raw_spark2
                        
                        if spark_prices:
                            print(f"✅ latest.json から {len(spark_prices)} 件の価格データを取得しました。")
            except Exception as e:
                print(f"⚠️ フォールバック読み込みエラー: {e}")

    # 3. 計算実行
    btc_rsi_calculated = None
    if spark_prices and len(spark_prices) > 14:
        btc_rsi_calculated = calculate_latest_rsi(spark_prices)
    
    if btc_rsi_calculated is not None:
        btc_rsi = round(btc_rsi_calculated, 1) # 小数点1桁
        # サマリーを上書きして後続処理に反映させる
        if "technical" not in summary: summary["technical"] = {}
        summary["technical"]["btc_rsi"] = btc_rsi
        print(f"✅ RSI再計算成功: {btc_rsi} (HTMLと同等の値)")
    else:
        # 計算失敗時は古い保存値を使用
        btc_rsi = summary.get("technical", {}).get("btc_rsi")
        print(f"⚠️ RSI再計算不可 (データ件数: {len(spark_prices)})。保存値を使用: {btc_rsi}")
    # ----------------------------------------------------

    btc_dom = summary.get("btc_dominance", 0)
    fgi = summary.get("fgi", {"value": 50, "label": "Neutral"})
    chg = btc.get('price_change_percentage_24h', 0) if btc else 0
    
    ai_status_msg, _ = determine_ai_status(summary, chg)
    icon = "📈" if chg > 0 else "📉"
    trending_str = ", ".join(summary.get("trending", []))
    top_g = summary.get("top_gainer", {"symbol": "-", "change": 0})
    
    rsi_note = determine_rsi_status(btc_rsi)
    market_topic = generate_market_topic(summary, chg)

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

    # --- ② Note用テキスト ---
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

    # --- ③ HTMLコンテンツ ---
    # ★変更: 時刻を入れて毎回内容を変える
    share_desc = (
        f"{display_date}の暗号資産サマリー。"
        f"FGI {fgi.get('value', '-')}, RSI {btc_rsi if btc_rsi else '-'}。"
        f"注目: {trending_str}"
    )
    share_url = f"https://coinrader.net/share/{file_date}.html"
    share_image = f"https://coinrader.net/assets/og/ogp_v2.png?v={file_date}"

    share_html = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>CoinRader {display_date}</title>
  <meta name="description" content="{share_desc}">
  <meta name="robots" content="noindex,follow,max-image-preview:large">
  <link rel="canonical" href="{share_url}">

  <meta property="og:type" content="website">
  <meta property="og:site_name" content="CoinRader">
  <meta property="og:title" content="CoinRader - 今日の注目 {display_date}">
  <meta property="og:description" content="{share_desc}">
  <meta property="og:url" content="{share_url}">
  <meta property="og:image" content="{share_image}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="CoinRader - 今日の注目 {display_date}">
  <meta name="twitter:description" content="{share_desc}">
  <meta name="twitter:image" content="{share_image}">

  <script type="application/ld+json">{{"@context":"https://schema.org","@type":"WebPage","name":"CoinRader Share {display_date}","description":"{share_desc}","url":"{share_url}"}}</script>
  <meta http-equiv="refresh" content="0;url=https://coinrader.net/">
</head>
<body></body>
</html>"""

    # --- ④ 画像生成プロンプト ---
    fgi_val = fgi.get('value', 50)
    accent_color = "赤色(Neon Red)" if fgi_val <= 30 else "オレンジ色(Orange)" if fgi_val <= 45 else "シアン(Cyan)"
    
    # ★変更: 末尾にタイムスタンプを追加し、Gitが変更を検知するようにする
    ai_image_prompt = (
        f"Attached is the base template 'ogp_v2.png'. \n"
        f"Please overlay the following market data onto the right-side highlighted area in a professional cyberpunk HUD style. \n"
        f"Ensure the text has a subtle neon glow and is perfectly integrated into the background theme.\n\n"
        f"--- DATA TO OVERLAY ---\n"
        f"DATE: [ {date_label} ]\n"
        f"SENTIMENT: [ {fgi_val} ({fgi.get('label', 'Neutral')}) ]\n"
        f"BTC RSI: [ {btc_rsi if btc_rsi else '-'} ]\n"
        f"STATUS: [ {ai_status_msg} / {rsi_note} ]\n"
        f"FOCUS: [ {market_topic} ]\n\n"
        f"--- DESIGN INSTRUCTION ---\n"
        f"Use high-tech digital font. Highlight the SENTIMENT value with a '{accent_color}' glow. \n"
        f"Maintain a clean, sophisticated atmosphere for institutional traders.\n"
        f"GENERATED: [ {update_time} ]"
    )

    # --- 💾 ファイル書き出し ---
    try:
        os.makedirs("share", exist_ok=True)
        
        print("💾 writing: daily_post_short.txt")
        with open("daily_post_short.txt", "w", encoding="utf-8") as f: f.write(short_post)
        
        print("💾 writing: daily_note_draft.md")
        with open("daily_note_draft.md", "w", encoding="utf-8") as f: f.write(note_content)
        
        print("💾 writing: daily_share_url.txt")
        with open("daily_share_url.txt", "w", encoding="utf-8") as f: 
            f.write(f"https://coinrader.net/share/{file_date}.html")
        
        print(f"💾 writing: share/{file_date}.html")
        with open(f"share/{file_date}.html", "w", encoding="utf-8") as f: f.write(share_html)
        
        print("💾 writing: daily_image_overlay.txt")
        with open("daily_image_overlay.txt", "w", encoding="utf-8") as f: f.write(ai_image_prompt.strip())
            
        print(f"✅ 全アセット生成完了 ({update_time})")

    except Exception as e:
        print(f"❌ 書き込み失敗: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    generate_sns_assets()
