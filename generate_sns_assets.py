import datetime
import os
import json
import sys

# ... (determine_rsi_status, generate_market_topic, format_price 関数はそのまま) ...

def generate_sns_assets():
    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    file_date = jst_now.strftime("%Y%m%d")
    display_date = jst_now.strftime("%Y-%m-%d")
    date_label = jst_now.strftime("%m/%d")
    update_time = jst_now.strftime("%H:%M:%S")
    
    # Gitに強制認識させるためのタイムスタンプ
    force_update_tag = f"\n\n(Generated at: {update_time})"
    
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
    fgi = summary.get("fgi", {"value": 50, "label": "Neutral"})
    chg = btc.get('price_change_percentage_24h', 0) if btc else 0
    
    # 各アセットにタイムスタンプを付与
    short_post = f"🤖 CoinRader 市場速報 ({date_label})\n価格: ¥{format_price(btc['current_price']) if btc else '-'}\n前日比: {chg:.1f}%" + force_update_tag
    image_overlay = f"MARKET UPDATE: [ {date_label} ]\nFGI: [ {fgi['value']} ]\nBTC RSI(14): [ {btc_rsi} ]\nSTATUS: [ {determine_rsi_status(btc_rsi)} ]\nTOPIC: [ {generate_market_topic(summary)} ]"
    note_draft = f"# Market Note {display_date}\n\nLast Update: {update_time}\n- BTC RSI: {btc_rsi}"

    try:
        os.makedirs("share", exist_ok=True)
        # 確実に上書き
        with open("daily_post_short.txt", "w", encoding="utf-8") as f: f.write(short_post)
        with open("daily_image_overlay.txt", "w", encoding="utf-8") as f: f.write(image_overlay)
        with open("daily_note_draft.md", "w", encoding="utf-8") as f: f.write(note_draft)
        with open("daily_share_url.txt", "w", encoding="utf-8") as f: 
            f.write(f"https://coinrader.net/share/{file_date}.html?t={jst_now.strftime('%H%M')}")
        
        share_html = f"<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>{display_date}</title><meta http-equiv='refresh' content='0;url=https://coinrader.net/?v={file_date}'></head></html>"
        with open(f"share/{file_date}.html", "w", encoding="utf-8") as f: f.write(share_html)
        
        print(f"✅ 強制更新用タグ付きで全ファイルを書き出しました ({update_time})")
    except Exception as e:
        print(f"❌ 書き込み失敗: {e}")
        sys.exit(1)

if __name__ == "__main__":
    generate_sns_assets()
