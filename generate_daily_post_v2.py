import requests
import datetime
import os
import json
import sys

# --- 除外ロジック等は維持 ---
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

def get_coingecko_data(url, params):
    api_key = os.getenv("CG_DEMO_KEY")
    headers = {"x-cg-demo-api-key": api_key} if api_key else {}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=30)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"APIエラー: {e}")
        return None

def calculate_rsi(coin_id):
    data = get_coingecko_data(f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart", 
                              {"vs_currency": "jpy", "days": 20, "interval": "daily"})
    if not data or 'prices' not in data: return None
    prices = [p[1] for p in data['prices']]
    if len(prices) < 15: return None
    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
    up = [d if d > 0 else 0 for d in deltas[-14:]]
    down = [-d if d < 0 else 0 for d in deltas[-14:]]
    avg_up, avg_down = sum(up)/14, sum(down)/14
    return round(100 - (100 / (1 + (avg_up / avg_down))), 2) if avg_down != 0 else 100

def calculate_ma_distance(coin_id):
    data = get_coingecko_data(f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart", 
                              {"vs_currency": "jpy", "days": 250, "interval": "daily"})
    if not data or 'prices' not in data: return None
    p = [p[1] for p in data['prices']]
    if len(p) < 200: return None
    return round((( (sum(p[-50:])/50) - (sum(p[-200:])/200) ) / (sum(p[-200:])/200)) * 100, 2)

def get_fear_and_greed_index():
    try:
        res = requests.get("https://api.alternative.me/fng/", timeout=10)
        d = res.json()['data'][0]
        return {"value": int(d['value']), "label": d['value_classification']}
    except:
        return {"value": 50, "label": "Neutral"}

# --- メイン処理（JSON出力のみ） ---
def generate_post():
    markets = get_coingecko_data("https://api.coingecko.com/api/v3/coins/markets", 
                                {"vs_currency": "jpy", "order": "market_cap_desc", "per_page": 250, "sparkline": "true", "price_change_percentage": "24h,7d"})
    if not markets: return False

    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    file_date = jst_now.strftime("%Y%m%d")

    # 分析データの構築
    intelligence_json = {
        "summary": {
            "date": jst_now.strftime("%Y-%m-%d"),
            "fgi": get_fear_and_greed_index(),
            "btc_dominance": round((next(c for c in markets if c['id']=='bitcoin')['market_cap'] / sum(c.get('market_cap',0) or 0 for c in markets) * 100), 2),
            "technical": {
                "btc_rsi": calculate_rsi("bitcoin"),
                "btc_ma_distance": calculate_ma_distance("bitcoin")
            },
            "top_gainer": {
                "symbol": sorted([c for c in markets if (c.get('total_volume') or 0) >= 500_000_000 and not is_stable_coin(c) and not is_wrapped_or_duplicate(c)], 
                                 key=lambda x: x.get('price_change_percentage_24h', 0) or 0, reverse=True)[0]['symbol'].upper(),
                "change": 0 # 詳細数値はSNS側で計算
            },
            "trending": [c['item']['symbol'].upper() for c in (get_coingecko_data("https://api.coingecko.com/api/v3/search/trending", {}) or {}).get('coins', [])[:3]]
        },
        "raw_data": markets 
    }

    # JSON保存のみ実行
    os.makedirs("data/daily", exist_ok=True)
    with open(f"data/daily/{file_date}.json", "w", encoding="utf-8") as f:
        json.dump(intelligence_json, f, ensure_ascii=False, indent=2)
    
    return True

if __name__ == "__main__":
    if generate_post():
        print("✅ JSON更新完了（SNS用テキスト出力はスキップ）")
    else:
        sys.exit(1)
