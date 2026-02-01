import datetime
import os
import json
import sys # 追加

# ... (判定ロジック関数はそのまま) ...

def generate_sns_assets():
    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    file_date = jst_now.strftime("%Y%m%d")
    date_label = jst_now.strftime("%m/%d")
    json_path = f"data/daily/{file_date}.json"

    if not os.path.exists(json_path):
        # 💡 ここで最新のファイルを使うようにフォールバックを入れるとより堅牢です
        print(f"❌ エラー: {json_path} が見つかりません。")
        sys.exit(1) # GitHub Actionsに失敗を通知

    # ... (データ抽出・テキスト構築ロジックはそのまま) ...

    try:
        with open("daily_post_short.txt", "w", encoding="utf-8") as f: f.write(short_post)
        with open("daily_image_overlay.txt", "w", encoding="utf-8") as f: f.write(image_overlay_text)
        os.makedirs("share", exist_ok=True)
        with open(f"share/{file_date}.html", "w", encoding="utf-8") as f: f.write(share_html)
        print(f"✅ SNSアセット生成成功")
    except Exception as e:
        print(f"❌ ファイル書き込みエラー: {e}")
        sys.exit(1)

if __name__ == "__main__":
    generate_sns_assets()
