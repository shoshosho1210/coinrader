import requests
import datetime
import os
import json

# ==========================================
# 1. 除外ロジック (ステーブル・Wrapped除外)
# ==========================================
STABLE_IDS = {"tether", "usd-coin", "dai", "true-usd", "first-digital-usd", "ethena-usde", "frax", "pax-dollar", "paypal-usd", "gemini-dollar", "paxos-standard", "binance-usd", "liquity-usd"}
STABLE_SYMBOLS = {"usdt", "usdc", "dai", "tusd", "usde", "fdusd", "pyusd", "gusd", "usdp", "busd", "lusd", "frax"}
SKIP_KEYWORDS = ["wrapped", "staked", "bridged", "token", "wbtc", "weth", "steth"]

def is_stable_coin(coin):
    c_id = (coin.get('id') or '').lower()
    c_sym = (coin.get('symbol') or '').lower()
    return c_id in STABLE_IDS or c_sym in STABLE_SYMBOLS

def is_wrapped_or_duplicate(coin):
    c_id = (coin.get('id') or '').lower()
    if c_id in ['bitcoin', 'ethereum']: return False
    c_name = (coin.get('name') or '').lower()
    c_sym = (coin.get('symbol') or '').lower()
    for k in SKIP_KEYWORDS:
        if k in c_name or k in c_sym: return True
    return False

# ==========================================
# 2. データ取得・整形
# ==========================================
def get_market_data():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "jpy", "order": "market_cap_desc", "per_page": 250, "sparkline": "false"}
    try:
        res = requests.get(url, params=params, timeout=30)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"Market Data取得エラー: {e}")
        return []

def get_trending_coins():
    url = "https://api.coingecko.com/api/v3/search/trending"
    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        return [item['item'] for item in res.json().get('coins', [])]
    except Exception as e:
        print(f"Trending取得エラー: {e}")
        return []

def format_price(price):
    if price is None: return "-"
    if price >= 1000000: return f"{price/10000:.0f}万"
    return f"{price:,.0f}"

# ==========================================
# 3. メイン処理：投稿テキスト & JSONデータ生成
# ==========================================
def generate_post():
    markets = get_market_data()
    trending = get_trending_coins()
    if not markets: return "データの取得に失敗しました。"

    btc = next((item for item in markets if item["id"] == "bitcoin"), None)
    
    # --- 日付計算 (JST) ---
    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    file_date = jst_now.strftime("%Y%m%d")
    display_date = jst_now.strftime("%Y-%m-%d")

    # ==========================================
    # 4. ファイル保存処理 (assets/ フォルダに統一)
    # ==========================================
    
    # --- 1. JSONデータの保存 (重要：YAMLとパスを合わせる) ---
    # YAML側の git add assets/ に対応させるため assets/ を追加
    save_dir = "assets/data/daily"
    os.makedirs(save_dir, exist_ok=True)
    json_path = os.path.join(save_dir, f"{file_date}.json")
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(markets, f, ensure_ascii=False, indent=2)

    # --- 2. シェア用HTMLの作成 (既存通り) ---
    share_html = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>CoinRader - 今日の注目 {display_date}</title>
  <meta property="og:url" content="https://coinrader.net/share/{file_date}.html">
  <meta property="og:image" content="https://coinrader.net/assets/og/ogp.png?v={file_date}">
  <meta http-equiv="refresh" content="0;url=https://coinrader.net/?v={file_date}">
</head>
<body></body>
</html>"""

    os.makedirs("share", exist_ok=True)
    with open(f"share/{file_date}.html", "w", encoding="utf-8") as f:
        f.write(share_html)

    # ==========================================
    # (5. メッセージ組み立て & テキスト出力)
    # ==========================================
    # ... [これまでのメッセージ作成ロジック] ...
    
    # 最後に成功メッセージ
    return f"✅ 保存完了: {json_path}"

if __name__ == "__main__":
    print(generate_post())
