import os, re, sys
from PIL import Image, ImageDraw, ImageFont

def generate_image():
    # 1. パスの設定
    TEMPLATE_PATH = "assets/og/ogp_v2.png"
    DATA_PATH = "daily_image_overlay.txt"
    OUTPUT_PATH = "daily_market_update.png"

    # 2. データの読み込み
    if not os.path.exists(DATA_PATH):
        print(f"❌ {DATA_PATH} が見つかりません。生成を中断します。")
        return

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    
    # データの抽出ロジック (特殊文字エスケープ済み)
    def get_val(key):
        pattern = rf"{re.escape(key)}:\s*\[\s*(.*?)\s*\]"
        match = re.search(pattern, content)
        return match.group(1).strip() if match else "-"

    d = {k: get_val(k) for k in ["MARKET UPDATE", "FGI", "BTC RSI(14)", "STATUS", "TOPIC"]}

    # 3. 背景画像の読み込み
    if not os.path.exists(TEMPLATE_PATH):
        print(f"❌ テンプレート画像 {TEMPLATE_PATH} が見つかりません。")
        # テンプレートがない場合は紺色の背景を新規作成して代用
        img = Image.new("RGB", (1200, 630), (10, 16, 28))
        print("⚠️ 代替の背景色で画像を作成します。")
    else:
        img = Image.open(TEMPLATE_PATH).convert("RGB")
        print(f"✅ テンプレートを読み込みました: {TEMPLATE_PATH}")

    draw = ImageDraw.Draw(img)

    # 4. フォント設定 (GitHub Actions / Linux 環境対応)
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:\\Windows\\Fonts\\msgothic.ttc" # Windows用
    ]
    f_path = next((fp for fp in font_paths if os.path.exists(fp)), None)
    
    def draw_text(pos, text, size, color):
        try:
            f = ImageFont.truetype(f_path, size) if f_path else ImageFont.load_default()
        except:
            f = ImageFont.load_default()
        draw.text(pos, text, fill=color, font=f)

    # 5. データの描画 (テンプレートの右側エリアに配置)
    # 座標は ogp_v2.png のレイアウトに合わせて微調整してください
    x_base = 580 
    
    # 日付ラベル
    draw_text((x_base, 90), f"UPDATE: {d['MARKET UPDATE']}", 35, (56, 189, 248))
    
    # FGI & RSI (メイン指標)
    draw_text((x_base, 190), f"FGI: {d['FGI']}", 75, (255, 255, 255))
    draw_text((x_base, 300), f"RSI: {d['BTC RSI(14)']}", 75, (255, 255, 255))
    
    # 状態ステータス
    draw_text((x_base, 430), d['STATUS'], 55, (56, 189, 248))
    
    # 注目トピック (小さめ)
    draw_text((x_base, 520), f"FOCUS: {d['TOPIC']}", 28, (203, 213, 225))

    # 6. 保存
    img.save(OUTPUT_PATH, "PNG")
    print(f"✅ 画像生成に成功しました: {OUTPUT_PATH}")

if __name__ == "__main__":
    generate_image()
