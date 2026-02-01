import datetime
import os
import json
import sys

def format_price(price):
    if price is None: return "-"
    if price >= 1000000: return f"{price/10000:.0f}万"
    return f"{price:,.0f}"

def generate_sns_assets():
    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    file_date = jst_now.strftime("%Y%m%d")
    display_date = jst_now.strftime("%Y-%m-%d")
    # 💡 強制更新のためのタイムスタンプ (秒まで含める)
    ts = jst_now.strftime("%Y-%m-%d %H:%M:%S")
    ts_tag = f"\n\n(Update: {ts})"

    paths = [f"data/daily/{file_date}.json", "data/daily/latest.json"]
    json_path = next((p for p in paths if os.path.exists(p)), None)

    if not json_path:
        print("❌ エラー: データJSONが見つかりません。")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    try:
        os.makedirs("share", exist_ok=True)
        
        # 1. daily_share_url.txt (URLの末尾に時刻を付けて強制更新)
        share_url = f"https://coinrader.net/share/{file_date}.html?t={jst_now.strftime('%H%M%S')}"
        with open("daily_share_url.txt", "w", encoding="utf-8") as f:
            f.write(share_url)
        
        # 2. その他のテキストファイルにもタイムスタンプを強制挿入
        with open("daily_post_short.txt", "w", encoding="utf-8") as f:
            f.write(f"🤖 CoinRader 市場速報 ({display_date})" + ts_tag)
        
        with open("daily_note_draft.md", "w", encoding="utf-8") as f:
            f.write(f"# Report {display_date}" + ts_tag)

        # 3. HTML
        share_html = f"<!doctype html><html><head><meta charset='utf-8'><meta http-equiv='refresh' content='0;url={share_url}'></head></html>"
        with open(f"share/{file_date}.html", "w", encoding="utf-8") as f:
            f.write(share_html)

        print(f"✅ 全アセット生成完了: daily_share_url.txt -> {share_url}")
    except Exception as e:
        print(f"❌ 書き込み失敗: {e}")
        sys.exit(1)

if __name__ == "__main__":
    generate_sns_assets()
