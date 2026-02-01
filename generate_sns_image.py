import os, re, sys
from PIL import Image, ImageDraw, ImageFont

def generate_image():
    # 1. ファイルの存在確認
    if not os.path.exists("daily_image_overlay.txt"):
        print("❌ データ不足のため画像生成をスキップします"); return

    # 2. ファイル読み込み
    with open("daily_image_overlay.txt", "r", encoding="utf-8") as f:
        content = f.read()
    
    # 3. データの抽出 (特殊文字をエスケープして検索を堅牢化)
    def get_val(key):
        # re.escape(key) を使うことで "RSI(14)" の括弧を正しく認識させます
        pattern = rf"{re.escape(key)}:\s*\[\s*(.*?)\s*\]"
        match = re.search(pattern, content)
        if match:
            return match.group(1)
        else:
            print(f"⚠️ 警告: キー '{key}' が見つかりません。デフォルト値を使います。")
            return "-"

    # 必要な項目を辞書に格納
    d = {k: get_val(k) for k in ["MARKET UPDATE", "FGI", "BTC RSI(14)", "STATUS", "TOPIC"]}

    # 4. 画像作成 (1200x630 / CoinRader ブランドカラー)
    img = Image.new("RGB", (1200, 630), (10, 16, 28))
    draw = ImageDraw.Draw(img)

    # 5. ロゴ合成 (左側)
    if os.path.exists("logo41.png"):
        logo = Image.open("logo41.png").convert("RGBA")
        # 縦横比を維持してリサイズ
        logo.thumbnail((420, 420), Image.Resampling.LANCZOS)
        # 垂直中央に配置
        img.paste(logo, (60, (630 - logo.height) // 2), logo)

    # 6. フォント設定 (GitHub Actions / Linux 環境対応)
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:\\Windows\\Fonts\\msgothic.ttc"
    ]
    f_path = next((fp for fp in font_paths if os.path.exists(fp)), None)
    
    def draw_text_robust(pos, text, size, color):
        try:
            f = ImageFont.truetype(f_path, size) if f_path else ImageFont.load_default()
        except:
            f = ImageFont.load_default()
        draw.text(pos, text, fill=color, font=f)

    # 7. 描画実行 (右側セクション)
    x_pos = 550
    draw_text_robust((x_pos, 80), f"MARKET UPDATE {d['MARKET UPDATE']}", 40, (56, 189, 248))
    draw_text_robust((x_pos, 200), f"FGI: {d['FGI']}", 80, (255, 255, 255))
    draw_text_robust((x_pos, 320), f"RSI: {d['BTC RSI(14)']}", 80, (255, 255, 255))
    
    # 状態判定セクション
    draw_text_robust((x_pos, 450), d['STATUS'], 50, (56, 189, 248))
    # トピック
    draw_text_robust((x_pos, 530), f"注目: {d['TOPIC']}", 30, (203, 213, 225))

    # 8. 保存
    img.save("daily_market_update.png", "PNG")
    print("✅ 画像生成成功: daily_market_update.png")

if __name__ == "__main__":
    generate_image()
