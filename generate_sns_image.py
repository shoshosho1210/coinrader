import os, re, sys
from PIL import Image, ImageDraw, ImageFont

def generate_image():
    # 1. ファイルの読み込み
    if not os.path.exists("daily_image_overlay.txt"):
        print("❌ データ不足のため画像生成をスキップします"); return

    with open("daily_image_overlay.txt", "r", encoding="utf-8") as f:
        content = f.read()
    
    # 2. データの抽出 (正規表現のエスケープ処理を追加)
    def get_val(key):
        # re.escapeにより "RSI(14)" の括弧を特殊記号ではなく「文字」として扱います
        pattern = rf"{re.escape(key)}:\s*\[\s*(.*?)\s*\]"
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip()
        else:
            print(f"⚠️ 警告: キー '{key}' が見つかりません。")
            return "-"

    # 必要な項目を辞書に格納
    d = {k: get_val(k) for k in ["MARKET UPDATE", "FGI", "BTC RSI(14)", "STATUS", "TOPIC"]}

    # 3. 画像のベース作成
    img = Image.new("RGB", (1200, 630), (10, 16, 28))
    draw = ImageDraw.Draw(img)

    # 4. ロゴの合成
    if os.path.exists("logo41.png"):
        logo = Image.open("logo41.png").convert("RGBA")
        logo.thumbnail((400, 400), Image.Resampling.LANCZOS)
        img.paste(logo, (60, (630 - logo.height) // 2), logo)

    # 5. フォントの設定 (Linux環境への対応)
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    ]
    f_path = next((fp for fp in font_paths if os.path.exists(fp)), None)
    
    def draw_text_safe(pos, text, size, color):
        try:
            f = ImageFont.truetype(f_path, size) if f_path else ImageFont.load_default()
        except:
            f = ImageFont.load_default()
        draw.text(pos, text, fill=color, font=f)

    # 6. テキスト描画
    x_offset = 550
    draw_text_safe((x_offset, 80), f"MARKET UPDATE {d['MARKET UPDATE']}", 40, (56, 189, 248))
    draw_text_safe((x_offset, 200), f"FGI: {d['FGI']}", 80, (255, 255, 255))
    draw_text_safe((x_offset, 320), f"BTC RSI: {d['BTC RSI(14)']}", 80, (255, 255, 255))
    draw_text_safe((x_offset, 450), d['STATUS'], 50, (56, 189, 248))
    draw_text_safe((x_offset, 530), f"注目: {d['TOPIC']}", 30, (203, 213, 225))

    # 7. 保存
    img.save("daily_market_update.png", "PNG")
    print("✅ 画像生成成功: daily_market_update.png")

if __name__ == "__main__":
    generate_image()
