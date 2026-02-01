import datetime
import os
import json
import sys

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

def generate_sns_assets():
    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    file_date = jst_now.strftime("%Y%m%d")
    display_date = jst_now.strftime("%Y-%m-%d")
    date_label = jst_now.strftime("%m/%d")
    update_time = jst_now.strftime("%H:%M:%S")
    
    # データ読み込み
    paths = [f"data/daily/{file_date}.json", "data/daily/latest.json"]
    json_path = next((p for p in paths if os.path.exists(p)), None)

    if not json_path:
        print(f"❌ エラー: 参照JSONが見つかりません。")
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
    top_g = summary.get("top_gainer", {"symbol": "-", "change": 0})
    trending_str = ", ".join(summary.get("trending", []))
    ai_status_msg = "分析: 楽観" if chg > 3 else ("分析: 悲観" if chg < -3 else "分析: 中立")

    # ファイル内容の作成
    short_post = f"🤖 CoinRader 市場速報 ({date_label})\n{ai_status_msg}\n\n🔹 Bitcoin\n価格: ¥{format_price(btc['current_price']) if btc else '-'}\n前日比: {'+' if chg > 0 else ''}{chg:.1f}%\nRSI(14): {btc_rsi if btc_rsi else '-'}\n心理指数: {fgi['value']} ({fgi['label']})\n\n📈 注目銘柄\nトレンド: {trending_str}\n急上昇: {top_g['symbol']} ({int(top_g['change'])}%↑)\n\n📊 詳細分析\nhttps://coinrader.net/share/{file_date}.html"
    image_overlay = f"MARKET UPDATE: [ {date_label} ]\nFGI: [ {fgi['value']} ({fgi['label']}) ]\nBTC RSI(14): [ {btc_rsi if btc_rsi else '-'} ]\nSTATUS: [ {rsi_status} ]\nTOPIC: [ {topic_text} ]"
    note_draft = f"# Market Note {display_date}\n\n## 📊 主要指標\n- BTC RSI: {btc_rsi}\n- FGI: {fgi['value']} ({fgi['label']})\n- BTC Dominance: {btc_dom}%"
    share_html = f"<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>{display_date}</title><meta property='og:image' content='https://coinrader.net/assets/og/ogp2.png?v={file_date}'><meta http-equiv='refresh' content='0;url=https://coinrader.net/?v={file_date}'></head></html>"

    # 保存実行
    try:
        os.makedirs("share", exist_ok=True)
        files = {
            "daily_post_short.txt": short_post,
            "daily_image_overlay.txt": image_overlay,
            "daily_note_draft.md": note_draft,
            "daily_share_url.txt": f"https://coinrader.net/share/{file_date}.html",
            f"share/{file_date}.html": share_html
        }
        for name, content in files.items():
            with open(name, "w", encoding="utf-8") as f: f.write(content)
            print(f"✅ 生成成功: {name}")
    except Exception as e:
        print(f"❌ 書き込み失敗: {e}")
        sys.exit(1)

if __name__ == "__main__":
    generate_sns_assets()
