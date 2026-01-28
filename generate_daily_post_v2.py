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
    except: return []

def get_trending_coins():
    url = "https://api.coingecko.com/api/v3/search/trending"
    try:
        res = requests.get(url, timeout=30)
        return [item['item'] for item in res.json().get('coins', [])]
    except: return []

def get_fear_and_greed_index():
    """市場の恐怖強欲指数(FGI)を取得する"""
    try:
        url = "https://api.alternative.me/fng/"
        response = requests.get(url, timeout=10)
        data = response.json()
        fgi_value = int(data['data'][0]['value'])
        fgi_class = data['data'][0]['value_classification']
        return {"value": fgi_value, "label": fgi_class}
    except Exception as e:
        print(f"FGI取得エラー: {e}")
        return {"value": 50, "label": "Neutral"}

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
    fgi_data = get_fear_and_greed_index()
    
    if not markets: return "データの取得に失敗しました。"

    # --- A. 市場の柱 (BTC & ETH) ---
    btc = next((item for item in markets if item["id"] == "bitcoin"), None)
    eth = next((item for item in markets if item["id"] == "ethereum"), None)
    
    # --- B. 市場の体温 (騰落数) ---
    up_count = len([c for c in markets if (c.get('price_change_percentage_24h') or 0) > 0])
    down_count = len([c for c in markets if (c.get('price_change_percentage_24h') or 0) < 0])
    
    # --- C. 急上昇銘柄 (上位5位) ---
    MIN_VOL_JPY = 500_000_000 
    valid_gainers = [
        c for c in markets 
        if c.get('price_change_percentage_24h') is not None
        and (c.get('total_volume') or 0) >= MIN_VOL_JPY
        and not is_stable_coin(c)
        and not is_wrapped_or_duplicate(c)
    ]
    top_5_gainers = sorted(valid_gainers, key=lambda x: x['price_change_percentage_24h'], reverse=True)[:5]
    
    trend_symbols = []
    for t in trending:
        if not (is_wrapped_or_duplicate(t) or is_stable_coin(t)):
            trend_symbols.append(t['symbol'].upper())
        if len(trend_symbols) >= 3: break

    # --- 日付設定 ---
    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    date_str = jst_now.strftime("%m/%d")
    file_date = jst_now.strftime("%Y%m%d")
    display_date = jst_now.strftime("%Y-%m-%d")

    # --- 4. 週次レポート用の黄金比JSONを保存 ---
    daily_json = {
        "date": display_date,
        "btc": {
            "price": btc['current_price'] if btc else 0,
            "change": btc['price_change_percentage_24h'] if btc else 0
        },
        "eth": {
            "price": eth['current_price'] if eth else 0,
            "change": eth['price_change_percentage_24h'] if eth else 0
        },
        "sentiment": fgi_data,
        "breadth": {
            "up": up_count,
            "down": down_count,
            "up_ratio": (up_count / len(markets) * 100) if markets else 0
        },
        "top_gainers": [
            {"symbol": c['symbol'].upper(), "change": c['price_change_percentage_24h']}
            for c in top_5_gainers
        ],
        "trending": trend_symbols
    }

    os.makedirs("assets/data/daily", exist_ok=True)
    with open(f"assets/data/daily/{file_date}.json", "w", encoding="utf-8") as f:
        json.dump(daily_json, f, ensure_ascii=False, indent=4)

    # --- 5. メッセージの組み立て (速報用) ---
    btc_chg = daily_json["btc"]["change"]
    icon = "📈" if btc_chg > 0 else ("📉" if btc_chg < 0 else "➡️")
    sign = "+" if btc_chg > 0 else ""
    ai_status = "【分析: 楽観】" if btc_chg > 3 else ("【分析: 悲観】" if btc_chg < -3 else "【分析: 中立】")
    site_url = f"https://coinrader.net/share/{file_date}.html"

    short_post = (
        f"🤖 CoinRader 市場速報 ({date_str})\n"
        f"{ai_status} 多角的な需給解析を更新\n\n"
        f"🔹 Bitcoin {icon}\n"
        f"価格: ¥{format_price(daily_json['btc']['price'])}\n"
        f"前日比: {sign}{btc_chg:.1f}%\n\n"
        f"🔥 トレンド: {', '.join(trend_symbols)}\n"
        f"🚀 急上昇: {daily_json['top_gainers'][0]['symbol'] if daily_json['top_gainers'] else '-'}\n\n"
        f"📊 詳細分析はサイトでチェック\n{site_url}\n\n"
        f"#Bitcoin #暗号資産 #CoinRader #BTC"
    )

    # テキスト出力
    with open("daily_post_short.txt", "w", encoding="utf-8") as f: f.write(short_post)
    with open("daily_post_full.txt", "w", encoding="utf-8") as f: f.write(short_post)
    
    # HTML生成 (OGP等)
    share_html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>CoinRader {display_date}</title><meta http-equiv="refresh" content="0;url=https://coinrader.net/?v={file_date}"></head><body></body></html>"""
    os.makedirs("share", exist_ok=True)
    with open(f"share/{file_date}.html", "w", encoding="utf-8") as f: f.write(share_html)

    return f"✅ {file_date}.json (黄金比形式) 生成完了"

if __name__ == "__main__":
    print(generate_post())
