import requests
import json
import time
from datetime import datetime
import os

# --- 設定 ---
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"
FGI_API_URL = "https://api.alternative.me/fng/?limit=1"

# 保存先ディレクトリの定義
DATA_DIR = "data"
DAILY_DIR = os.path.join(DATA_DIR, "daily")

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
    
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    # 平滑化
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
    data = fetch_json(f"{COINGECKO_API_URL}/coins/{coin_id}/market_chart", params={"vs_currency": "jpy", "days": days + 5})
    if not data or "prices" not in data:
        return None
    
    prices = [p[1] for p in data["prices"]]
    if len(prices) < days:
        return None
    
    current_price = prices[-1]
    sma = sum(prices[-days:]) / days
    
    distance = ((current_price - sma) / sma) * 100
    return round(distance, 2)

def main():
    print("Fetching Market Data...")

    # 1. 市場全体データ (Top 250)
    market_params = {
        "vs_currency": "jpy",
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": "true",
        "price_change_percentage": "24h,7d"
