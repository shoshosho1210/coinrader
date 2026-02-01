import os, re, sys
from PIL import Image, ImageDraw, ImageFont

def generate_image():
    if not os.path.exists("daily_image_overlay.txt"):
        print("❌ データ不足のため画像生成をスキップします"); return

    with open("daily_image_overlay.txt", "r", encoding="utf-8") as f:
        content = f.read()
    
    # データ抽出
    get_val = lambda k: re.search(f"{k}: \\[(.*?)\\]", content).group(1)
    d = {k: get_val(k) for k in ["MARKET UPDATE", "FGI", "BTC RSI(14)", "STATUS", "TOPIC"]}

    # 画像作成 (1200x630)
    img = Image.new("RGB", (1200, 630), (10, 16, 28))
    draw = ImageDraw.Draw(img)

    # ロゴ合成
    if os.path.exists("logo41.png"):
        logo = Image.open("logo41.png").convert("RGBA")
        logo.thumbnail((400, 400), Image.Resampling.LANCZOS)
        img.paste(logo, (60, (630 - logo.height) // 2), logo)

    # フォント設定 (Linux標準フォントへのフォールバックを強化)
    font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "C:\\Windows\\Fonts\\msgothic.ttc"]
    f_path = next((fp for fp in font_paths if os.path.exists(fp)), None)
    
    def draw_t(pos, text, size, color):
        f = ImageFont.truetype(f_path, size) if f_path else ImageFont.load_default()
        draw.text(pos, text, fill=color, font=f)

    draw_t((550, 80), f"MARKET UPDATE {d['MARKET UPDATE']}", 40, (56, 189, 248))
    draw_t((550, 200), f"FGI: {d['FGI']}", 80, (255, 255, 255))
    draw_t((550, 320), f"BTC RSI: {d['BTC RSI(14)']}", 80, (255, 255, 255))
    draw_t((550, 450), d['STATUS'], 50, (56, 189, 248))
    draw_t((550, 530), f"注目: {d['TOPIC']}", 30, (203, 213, 225))

    img.save("daily_market_update.png", "PNG")
    print("✅ 画像生成成功: daily_market_update.png")

if __name__ == "__main__":
    generate_image()
