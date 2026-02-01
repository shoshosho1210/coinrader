import os
import re
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 1. 設定とパス
# ==========================================
LOGO_PATH = "logo41.png"
DATA_PATH = "daily_image_overlay.txt"
OUTPUT_PATH = "daily_market_update.png"
# フォント指定（Windows標準の源ノ角ゴシックやメイリオ等。環境に合わせて調整してください）
FONT_PATH = "C:\\Windows\\Fonts\\msgothic.ttc" # 日本語フォント

def parse_data(path):
    """テキストファイルからデータを辞書形式で抽出"""
    data = {}
    if not os.path.exists(path): return None
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    fields = ["MARKET UPDATE", "FGI", "BTC RSI(14)", "STATUS", "TOPIC"]
    for field in fields:
        match = re.search(f"{re.escape(field)}: \\[(.*?)\\]", content)
        data[field] = match.group(1).strip() if match else "-"
    return data

def generate_image():
    data = parse_data(DATA_PATH)
    if not data:
        print("❌ データファイルが見つかりません。")
        return

    # 1. キャンバスの作成（1200x630 / ダークネイビーのグラデーション風背景）
    img = Image.new("RGB", (1200, 630), (10, 16, 28))
    draw = ImageDraw.Draw(img)

    # 2. ロゴの配置（左側）
    if os.path.exists(LOGO_PATH):
        logo = Image.open(LOGO_PATH).convert("RGBA")
        # リサイズ（横幅400px程度に）
        logo.thumbnail((450, 450), Image.LANCZOS)
        img.paste(logo, (50, (630 - logo.height) // 2), logo)

    # 3. テキストの描画
    try:
        font_main = ImageFont.truetype(FONT_PATH, 40)
        font_big = ImageFont.truetype(FONT_PATH, 80)
        font_status = ImageFont.truetype(FONT_PATH, 55)
        font_topic = ImageFont.truetype(FONT_PATH, 35)
    except:
        font_main = font_big = font_status = font_topic = ImageFont.load_default()

    # 右側の描画開始位置
    x_offset = 550
    y_start = 80

    # 日付 (MARKET UPDATE)
    draw.text((x_offset, y_start), f"MARKET UPDATE {data['MARKET UPDATE']}", fill=(56, 189, 248), font=font_main)
    
    # 指標セクション
    draw.text((x_offset, y_start + 80), "心理指数 (FGI):", fill=(148, 163, 184), font=font_main)
    draw.text((x_offset, y_start + 130), data['FGI'], fill=(255, 255, 255), font=font_big)

    draw.text((x_offset, y_start + 250), "BTC RSI(14):", fill=(148, 163, 184), font=font_main)
    draw.text((x_offset, y_start + 300), data['BTC RSI(14)'], fill=(255, 255, 255), font=font_big)

    # 状態判定 (STATUS) - 背景付き
    status_text = data['STATUS']
    draw.rectangle([x_offset, y_start + 410, x_offset + 550, y_start + 490], fill=(30, 41, 59))
    draw.text((x_offset + 20, y_start + 415), status_text, fill=(56, 189, 248), font=font_status)

    # トピック (TOPIC)
    draw.text((x_offset, y_start + 520), f"注目: {data['TOPIC']}", fill=(203, 213, 225), font=font_topic)

    # 4. フッター（サイトドメイン）
    draw.text((1000, 580), "coinrader.net", fill=(51, 65, 85), font=font_topic)

    # 保存
    img.save(OUTPUT_PATH, "PNG")
    print(f"✅ SNS用画像を生成しました: {OUTPUT_PATH}")

if __name__ == "__main__":
    generate_image()