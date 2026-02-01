import datetime
import os
import json
import sys

# --- 1. 補助関数（Webダッシュボードのロジックを完全再現） ---

def get_fgi_label(val):
    if val is None: return "分析中"
    if val <= 25: return "極度の恐怖"
    if val <= 45: return "恐怖"
    if val <= 55: return "中立"
    if val <= 75: return "強欲"
    return "極度の強欲"

def get_rsi_tag(rsi):
    if rsi is None: return ""
    if rsi <= 20: return " (⚠️歴史的底値圏)"
    if rsi <= 30: return " (⚠️売られすぎ圏)"
    if rsi >= 80: return " (⚠️歴史的高値圏)"
    if rsi >= 70: return " (⚠️買われすぎ圏)"
    return ""

def get_ai_analysis(fgi, rsi, chg):
    """HTML内のAI分析判定ロジックを再現"""
    if chg <= -5 or (fgi is not None and fgi <= 15):
        return "短期的な急落局面 - 警戒が必要"
    if fgi is not None and fgi <= 30 and rsi is not None and rsi <= 30:
        return "極度の悲観 - 逆張りの検討局面"
    if fgi is not None and fgi >= 70 and rsi is not None and rsi >= 70:
        return "過熱状態 - 自律調整の警戒局面"
    if chg > 3: return "楽観的な地合い - 上昇トレンド"
    if chg < -3: return "悲観的な地合い - 下落トレンド"
    return "需給の均衡状態 - 方向感の模索"

def generate_market_topic_jp(summary):
    """注目トピックを日本人向けに自然な日本語へ変換"""
    btc_rsi = summary.get('technical', {}).get('btc_rsi')
    btc_dom = summary.get('btc_dominance', 0)
    top_gainer = summary.get('top_gainer', {})
    
    if btc_rsi and btc_rsi <= 25: 
        return "パニック売りが一巡し、底打ちを模索する動きが見られます。"
    if btc_dom < 48: 
        return "資金がアルトコインへ分散中。セクターローテーションの兆候があります。"
    if top_gainer.get('change', 0) > 15:
        return f"特定アルト（{top_gainer.get('symbol', '').upper()}等）に強い買い需要が集中しています。"
    return "主要指標は均衡しており、次なる材料待ちの展開が続いています。"

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
    
    paths = [f"data/daily/{file_date}.json", "data/daily/latest.json"]
    json_path = next((p for p in paths if os.path.exists(p)), None)

    if not json_path:
        print("❌ エラー: データJSONが見つかりません。")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # データの抽出
    summary = data.get("summary", {})
    raw_data = data.get("raw_data", [])
    btc = next((c for c in raw_data if c["id"] == "bitcoin"), None)
    
    btc_rsi = summary.get("technical", {}).get("btc_rsi")
    btc_dom = summary.get("btc_dominance", 0)
    fgi_val = summary.get("fgi", {}).get("value")
    chg = btc.get('price_change_percentage_24h', 0) if btc else 0
    
    # 状態判定の確定
    fgi_label = get_fgi_label(fgi_val)
    rsi_tag = get_rsi_tag(btc_rsi)
    ai_status_header = get_ai_analysis(fgi_val, btc_rsi, chg)
    topic_text = generate_market_topic_jp(summary)
    
    icon = "📈" if chg > 0 else "📉"
    trending_str = ", ".join(summary.get("trending", [])[:3])

    # --- ① 【SNS投稿用】フォーマットの反映 ---
    short_post = (
        f"🤖 CoinRader 市場速報 ({date_label})\n"
        f"【分析結果：{ai_status_header}】\n\n"
        f"🔹 Bitcoin現状 {icon}\n"
        f"・価格: ¥{format_price(btc['current_price']) if btc else '-'} ({'+' if chg > 0 else ''}{chg:.1f}%)\n"
        f"・RSI: {btc_rsi if btc_rsi else '-'}{rsi_tag}\n"
        f"・心理指数: {fgi_val if fgi_val else '-'} ({fgi_label})\n\n"
        f"📈 注目トピック\n"
        f"{topic_text}\n\n"
        f"📊 詳細分析\n"
        f"https://coinrader.net/share/{file_date}.html\n\n"
        f"#CoinRader #ビットコイン #暗号資産"
    )

    # --- ② 【詳細レポート用】 ---
    note_content = (
        f"# Market Note {display_date} ({update_time} 更新)\n\n"
        f"## 📊 今日の主要マーケット指標\n"
        f"- **BTC価格:** ¥{format_price(btc['current_price'])} ({'+' if chg > 0 else ''}{chg:.1f}%)\n"
        f"- **BTC RSI(14):** {btc_rsi}{rsi_tag}\n"
        f"- **心理指数(FGI):** {fgi_val} ({fgi_label})\n"
        f"- **BTCドミナンス:** {btc_dom}%\n\n"
        f"## ✍️ AI市場分析\n"
        f"{ai_status_header}。{topic_text}\n"
    )

    # --- ③ HTML（OGP完全対応） ---
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
<body style="background:#0f172a; color:white; font-family:sans-serif; text-align:center; padding-top:20%;">
  <p>分析レポートへ移動中...</p>
</body>
</html>"""

    # --- 💾 ファイル書き出し ---
    try:
        os.makedirs("share", exist_ok=True)
        # SNS短文
        with open("daily_post_short.txt", "w", encoding="utf-8") as f:
            f.write(short_post)
        # レポート
        with open("daily_note_draft.md", "w", encoding="utf-8") as f:
            f.write(note_content)
        # シェア用URL
        with open("daily_share_url.txt", "w", encoding="utf-8") as f:
            f.write(f"https://coinrader.net/share/{file_date}.html")
        # HTML
        with open(f"share/{file_date}.html", "w", encoding="utf-8") as f:
            f.write(share_html)
        # 画像プロンプト用テキスト
        with open("daily_image_overlay.txt", "w", encoding="utf-8") as f:
            f.write(f"DATE: {date_label}\nFGI: {fgi_val}\nRSI: {btc_rsi}\nANALYSIS: {ai_status_header}\nTOPIC: {topic_text}")
            
        print(f"✅ Web同期版アセットを正常に書き出しました ({update_time})")
    except Exception as e:
        print(f"❌ 書き込み失敗: {e}")
        sys.exit(1)

if __name__ == "__main__":
    generate_sns_assets()
