import requests
import json
import time
from datetime import datetime
import os

# --- 設定 ---
# CoinGeckoはデモキーなしでも動きますが、あれば設定してください
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"
FGI_API_URL = "https://api.alternative.me/fng/?limit=1"

# 保存先
OUTPUT_FILE = "data/latest_market_data.json"

def fetch_json(url, params=None):
    """安全なリクエスト送信"""
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def calculate_rsi(prices, period=14):
    """価格配列からRSIを計算"""
    if not prices or len(prices) < period + 1:
        return None
    
    # 価格変動の計算
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    # Wilderの平滑化を使用する場合（オプション）
    # ここではシンプルに直近データで計算
    for i in range(period, len(prices) - 1):
        gain = gains[i]
        loss = losses[i]
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
    return round(rsi, 2)

def calculate_ma_distance(coin_id, days=200):
    """移動平均線乖離率を計算"""
    # 過去データ取得 (daily)
    data = fetch_json(f"{COINGECKO_API_URL}/coins/{coin_id}/market_chart", params={"vs_currency": "jpy", "days": days + 5})
    if not data or "prices" not in data:
        return None
    
    prices = [p[1] for p in data["prices"]]
    if len(prices) < days:
        return None
    
    current_price = prices[-1]
    # 直近N日の平均
    sma = sum(prices[-days:]) / days
    
    # 乖離率 (%)
    distance = ((current_price - sma) / sma) * 100
    return round(distance, 2)

def main():
    print("Fetching Market Data...")

    # 1. 市場全体データの取得 (Top 250)
    # sparkline=true で7日間の価格データを取得しRSI計算に使用
    market_params = {
        "vs_currency": "jpy",
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": "true",
        "price_change_percentage": "24h,7d"
    }
    raw_data = fetch_json(f"{COINGECKO_API_URL}/coins/markets", params=market_params)
    
    if not raw_data:
        print("Failed to fetch market data.")
        return

    # 2. Fear & Greed Index
    fgi_data = fetch_json(FGI_API_URL)
    fgi_val = 0
    fgi_label = "Neutral"
    if fgi_data and "data" in fgi_data:
        fgi_val = int(fgi_data["data"][0]["value"])
        fgi_label = fgi_data["data"][0]["value_classification"]

    # 3. Global Data (BTC Dominance)
    global_data = fetch_json(f"{COINGECKO_API_URL}/global")
    btc_dom = 0
    if global_data and "data" in global_data:
        btc_dom = round(global_data["data"]["market_cap_percentage"].get("btc", 0), 2)

    # 4. Trending
    trending_data = fetch_json(f"{COINGECKO_API_URL}/search/trending")
    trending_coins = []
    if trending_data and "coins" in trending_data:
        # 上位3つを取得
        for item in trending_data["coins"][:3]:
            trending_coins.append(item["item"]["symbol"])

    # 5. Technicals Calculation
    btc_coin = next((c for c in raw_data if c["id"] == "bitcoin"), None)
    eth_coin = next((c for c in raw_data if c["id"] == "ethereum"), None)

    btc_rsi = 50.0
    eth_rsi = 50.0
    
    # RSI計算 (7日分のSparklineデータを使用)
    if btc_coin and "sparkline_in_7d" in btc_coin:
        prices = btc_coin["sparkline_in_7d"].get("price", [])
        btc_rsi = calculate_rsi(prices) or 50.0

    if eth_coin and "sparkline_in_7d" in eth_coin:
        prices = eth_coin["sparkline_in_7d"].get("price", [])
        eth_rsi = calculate_rsi(prices) or 50.0

    # MA乖離率 (別途ヒストリカルデータを取得)
    # ここではBTCの200日移動平均乖離率を取得
    btc_ma_dist = calculate_ma_distance("bitcoin", 200) or 0.0

    # 6. Top Gainer (24h)
    # raw_dataの中からステーブルコインを除外し、出来高がある程度あるものから選定
    valid_gainers = [
        c for c in raw_data 
        if c["price_change_percentage_24h"] is not None 
        and "usd" not in c["symbol"].lower() # 簡易的なステーブル除外
        and c["total_volume"] > 100000000 # ノイズ除外
    ]
    # 上昇率でソート
    valid_gainers.sort(key=lambda x: x["price_change_percentage_24h"], reverse=True)
    
    top_gainer = {"symbol": "N/A", "change": 0.0}
    if valid_gainers:
        top = valid_gainers[0]
        top_gainer = {
            "symbol": top["symbol"].upper(),
            "change": round(top["price_change_percentage_24h"], 2)
        }

    # --- 7. 最終JSON構築 (指定フォーマットに厳格準拠) ---
    today_str = datetime.now().strftime("%Y-%m-%d")

    output_data = {
        "summary": {
            "date": today_str,
            # ネストされたFGIオブジェクト
            "fgi": {
                "value": fgi_val,
                "label": fgi_label
            },
            "btc_dominance": btc_dom,
            # ネストされたテクニカルオブジェクト
            "technical": {
                "btc_rsi": btc_rsi,
                "eth_rsi": eth_rsi,
                "btc_ma_distance": btc_ma_dist
            },
            # ネストされたTop Gainerオブジェクト
            "top_gainer": {
                "symbol": top_gainer["symbol"],
                "change": top_gainer["change"]
            },
            # 配列のTrending
            "trending": [t.upper() for t in trending_coins]
        },
        "raw_data_count": len(raw_data),
        "raw_data": raw_data
    }

    # 保存
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"Successfully generated {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
