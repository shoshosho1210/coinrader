import requests
import datetime
import math

# ==========================================
# 1. 除外ロジックの定義 (index27-11.html準拠)
# ==========================================

# ステーブルコインの定義 (JS: STABLE_IDS, STABLE_SYMBOLS)
STABLE_IDS = {
    "tether", "usd-coin", "dai", "true-usd", "first-digital-usd", "ethena-usde",
    "frax", "pax-dollar", "paypal-usd", "gemini-dollar", "paxos-standard", 
    "binance-usd", "liquity-usd"
}
STABLE_SYMBOLS = {
    "usdt", "usdc", "dai", "tusd", "usde", "fdusd", "pyusd", "gusd", 
    "usdp", "busd", "lusd", "frax"
}

# Wrapped / 重複トークンの定義 (JS: SKIP_KEYWORDS)
SKIP_KEYWORDS = ["wrapped", "staked", "bridged", "token", "wbtc", "weth", "steth"]

def is_stable_coin(coin):
    """ステーブルコインかどうかを判定"""
    c_id = coin.get('id', '').lower()
    c_sym = coin.get('symbol', '').lower()
    c_name = coin.get('name', '').lower()

    if c_id in STABLE_IDS or c_sym in STABLE_SYMBOLS:
        return True
    
    # フォールバック (名前判定)
    if "stable" in c_name and ("usd" in c_name or "usd" in c_sym):
        return True
    
    return False

def is_wrapped_or_duplicate(coin):
    """Wrappedトークンや重複トークンかどうかを判定"""
    c_id = coin.get('id', '').lower()
    c_name = coin.get('name', '').lower()
    c_sym = coin.get('symbol', '').lower()

    # BTCとETHそのものは除外しない
    if c_id in ['bitcoin', 'ethereum']:
        return False

    # キーワードチェック
    for k in SKIP_KEYWORDS:
        if k in c_name or k in c_sym:
            return True
            
    return False

# ==========================================
# 2. データ取得・整形処理
# ==========================================

def get_market_data():
    """CoinGeckoから市場データを取得"""
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "jpy",
        "order": "market_cap_desc",
        "per_page": 250,  # 上位250位まで取得
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h"
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching data: {e}")
        return []

def get_trending_coins():
    """トレンド検索銘柄を取得"""
    url = "https://api.coingecko.com/api/v3/search/trending"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        # item形式から単純な辞書へ変換
        return [item['item'] for item in data.get('coins', [])]
    except Exception as e:
        print(f"Error fetching trending: {e}")
        return []

def format_price(price):
    """価格を日本円形式に整形"""
    if price is None:
        return "-"
    if price >= 1000000:
        return f"{price/10000:.0f}万"
    elif price >= 1000:
        return f"{price:,.0f}"
    elif price >= 1:
        return f"{price:.1f}"
    else:
        return f"{price:.2f}"

# ==========================================
# 3. 投稿テキスト生成
# ==========================================

def generate_post():
    markets = get_market_data()
    trending = get_trending_coins()
    
    if not markets:
        return "データの取得に失敗しました。"

    # --- BTC情報の取得 ---
    btc = next((item for item in markets if item["id"] == "bitcoin"), None)
    btc_text = ""
    if btc:
        price = format_price(btc['current_price'])
        change = btc.get('price_change_percentage_24h', 0)
        icon = "📈" if change > 0 else ("📉" if change < 0 else "➡️")
        sign = "+" if change > 0 else ""
        btc_text = f"BTC: ¥{price} ({sign}{change:.1f}%) {icon}"

    # --- 上昇率ランキング (Gainers) ---
    # 条件: 
    # 1. 24h出来高が一定以上 (例: 5億円 = 500,000,000) -> マイナーすぎるコインを除外
    # 2. ステーブルコインではない (index27-11.html準拠)
    # 3. Wrapped/重複ではない (index27-11.html準拠)
    MIN_VOL_JPY = 500_000_000 

    valid_markets = [
        c for c in markets 
        if c.get('price_change_percentage_24h') is not None
        and c.get('total_volume', 0) >= MIN_VOL_JPY
        and not is_stable_coin(c)           # ★ここが重要
        and not is_wrapped_or_duplicate(c)  # ★ここが重要
    ]
    
    # 騰落率でソート
    top_gainers = sorted(valid_markets, key=lambda x: x['price_change_percentage_24h'], reverse=True)[:3]
    
    gainer_text = ""
    if top_gainers:
        top = top_gainers[0]
        change = top['price_change_percentage_24h']
        gainer_text = f"\n🚀Top: {top['symbol'].upper()} +{change:.1f}%"
        
        # 2位、3位も入れたい場合は以下のように拡張可能
        # for g in top_gainers[1:]:
        #    gainer_text += f", {g['symbol'].upper()} +{g['price_change_percentage_24h']:.1f}%"

    # --- トレンド ---
    # トレンドからもStable/Wrappedを除外したほうが綺麗な場合があるが、
    # APIの順位そのままの方がトレンド性があるため、ここでは上位をそのまま使うことが多い。
    # ただし、WBTCなどがトレンド入りして邪魔な場合は以下でフィルタ可能。
    trend_symbols = []
    for t in trending:
        # トレンドデータは markets と構造が違うため簡易チェック
        # t['id'], t['symbol'], t['name'] がある
        if is_wrapped_or_duplicate(t) or is_stable_coin(t):
            continue
        trend_symbols.append(t['symbol'].upper())
        if len(trend_symbols) >= 3:
            break
            
    trend_text = f"\n🔥Trend: {', '.join(trend_symbols)}" if trend_symbols else ""

    # --- テキスト結合 ---
    dt_now = datetime.datetime.now()
    date_str = dt_now.strftime("%m/%d %H:%M")
    
    post_text = (
        f"【市場速報 {date_str}】\n"
        f"{btc_text}"
        f"{trend_text}"
        f"{gainer_text}\n\n"
        f"詳細・分析はこちら👇\n"
        f"https://coinrader.net/\n"
        f"#Bitcoin #仮想通貨 #CoinRader"
    )
    
    return post_text

if __name__ == "__main__":
    print(generate_post())
