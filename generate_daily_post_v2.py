import requests
import datetime
import os
import json
import time

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
# 2. データ取得・分析関数
# ==========================================
def get_coingecko_data(url, params):
    api_key = os.getenv("CG_DEMO_KEY")
    headers = {"x-cg-demo-api-key": api_key} if api_key else {}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=30)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"APIエラー: {url} -> {e}")
        return None

def calculate_rsi_from_prices(prices, period=14):
    """
    価格配列（Sparkline）からRSI(14)を計算する
    index.htmlのロジックに合わせるため、単純なAPI取得ではなく計算を行う
    """
    if not prices or len(prices) < period + 1:
        return None
    
    # 価格変動の計算
    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
    
    # 初期平均の計算
    gain = sum([d for d in deltas[:period] if d > 0]) / period
    loss = sum([-d for d in deltas[:period] if d < 0]) / period
    
    avg_gain = gain
    avg_loss = loss
    
    # Wilder's Smoothing
    for i in range(period, len(deltas)):
        d = deltas[i]
        gain = d if d > 0 else 0
        loss = -d if d < 0 else 0
        
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        
    if avg_loss == 0:
        return 100.0
        
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calculate_ma_distance(coin_id):
    """過去250日分の価格を取得して50日/200日MA乖離率を計算する"""
    data = get_coingecko_data(f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart", 
                              {"vs_currency": "jpy", "days": "250", "interval": "daily"})
    if not data or 'prices' not in data:
        return None
    
    prices = [p[1] for p in data['prices']]
    if len(prices) < 200:
        return None

    # SMA50 と SMA200 の計算
    sma50 = sum(prices[-50:]) / 50
    sma200 = sum(prices[-200:]) / 200
    
    # 乖離率 (%)
    ma_distance = ((sma50 - sma200) / sma200) * 100
    return round(ma_distance, 2)
    
def get_fear_and_greed_index():
    try:
        res = requests.get("https://api.alternative.me/fng/", timeout=10)
        data = res.json()
        return {"value": int(data['data'][0]['value']), "label": data['data'][0]['value_classification']}
    except:
        return {"value": 50, "label": "Neutral"}

def format_price(price):
    if price is None: return "-"
    if price >= 1000000: return f"{price/10000:.0f}万"
    return f"{price:,.
