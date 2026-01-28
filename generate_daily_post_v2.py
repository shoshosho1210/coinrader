import requests
import datetime
import os

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

def format_price(price):
    if price is None: return "-"
    if price >= 1000000: return f"{price/10000:.0f}万"
    return f"{price:,.0f}"

# ==========================================
# 3. 投稿テキスト生成 & ファイル保存
# ==========================================
def generate_post():
    markets = get_market_data()
    trending = get_trending_coins()
    if not markets: return "データの取得に失敗しました。"

    # --- BTCデータの取得 ---
    btc = next((item for item in markets if item["id"] == "bitcoin"), None)
    
    # --- 上昇率トップ (None対策済み) ---
    MIN_VOL_JPY = 500_000_000 
    valid_gainers = [
        c for c in markets 
        if c.get('price_change_percentage_24h') is not None
        and (c.get('total_volume') or 0) >= MIN_VOL_JPY
        and not is_stable_coin(c)
        and not is_wrapped_or_duplicate(c)
    ]
    top_gainers = sorted(valid_gainers, key=lambda x: x['price_change_percentage_24h'], reverse=True)[:1]
    
    # --- トレンド銘柄 ---
    trend_symbols = []
    for t in trending:
        if not (is_wrapped_or_duplicate(t) or is_stable_coin(t)):
            trend_symbols.append(t['symbol'].upper())
        if len(trend_symbols) >= 3: break

    # --- 日付の取得 ---
    dt_now = datetime.datetime.now()
    date_str = dt_now.strftime("%m/%d") # 時間は削除
    
    # --- メッセージの組み立て ---
    chg = btc.get('price_change_percentage_24h', 0) if btc else 0
    icon = "📈" if chg > 0 else ("📉" if chg < 0 else "➡️")
    sign = "+" if chg > 0 else ""
    
    # AI判定ラベル（短くして独自性をキープ）
    ai_status = "【分析: 楽観】" if chg > 3 else ("【分析: 悲観】" if chg < -3 else "【分析: 中立】")

    # --- 日付の取得 ---
    dt_now = datetime.datetime.now()
    date_str = dt_now.strftime("%m/%d")
    file_date = dt_now.strftime("%Y%m%d") # ファイル名用の 20260127 形式

    # --- サイトURLを日別シェアURLに変更 ---
    # 固定のURLではなく、生成されたHTMLファイルを指すようにします
    site_url = f"https://coinrader.net/share/{file_date}.html"
    
    # X用ショートメッセージ (ハッシュタグ変更済み)
    short_post = (
        f"🤖 CoinRader 市場速報 ({date_str})\n"
        f"{ai_status} 多角的な需給解析を更新\n\n"
        f"🔹 Bitcoin {icon}\n"
        f"価格: ¥{format_price(btc['current_price']) if btc else '-'}\n"
        f"前日比: {sign}{chg:.1f}%\n\n"
        f"🔥 トレンド: {', '.join(trend_symbols)}\n"
        f"🚀 急上昇: {top_gainers[0]['symbol'].upper() if top_gainers else '-'}\n\n"
        f"📊 詳細分析はサイトでチェック\n{site_url}\n\n"
        f"#Bitcoin #暗号資産 #CoinRader #BTC"
    )

    # サイトURL
    site_url = "https://coinrader.net/"

    # ファイル出力
    with open("daily_post_short.txt", "w", encoding="utf-8") as f:
        f.write(short_post)
    with open("daily_post_full.txt", "w", encoding="utf-8") as f:
        f.write(short_post) # 今回は両方同じ内容に集約
    with open("daily_share_url.txt", "w", encoding="utf-8") as f:
        f.write(site_url)

    return "✅ ファイル生成完了"

if __name__ == "__main__":
    print(generate_post())
