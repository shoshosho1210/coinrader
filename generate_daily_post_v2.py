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

    # --- 1. BTC情報の整形 (専門性をアピール) ---
    btc = next((item for item in markets if item["id"] == "bitcoin"), None)
    btc_text = ""
    if btc:
        price = format_price(btc['current_price'])
        change = btc.get('price_change_percentage_24h', 0)
        icon = "📈" if change > 0 else ("📉" if change < 0 else "➡️")
        sign = "+" if change > 0 else ""
        btc_text = f"🔹 Bitcoin {icon}\n価格: ¥{price}\n前日比: {sign}{change:.1f}%"

    # --- 2. 市場センチメント (サイトの個性を出す) ---
    # 数値に基づいて一言添えることで、Botっぽさを消します
    sent_label = "【中立】"
    if btc and btc.get('price_change_percentage_24h', 0) > 3: sent_label = "【楽観】"
    elif btc and btc.get('price_change_percentage_24h', 0) < -3: sent_label = "【悲観】"
    
    ai_insight = f"🤖 AI Market Insight\n{sent_label} 市場構造を多角的に解析。最新インサイトを更新しました。"

    # --- 3. 上昇率ランキング (エラー修正箇所含む) ---
    MIN_VOL_JPY = 500_000_000 
    
    valid_markets = [
        c for c in markets 
        if c.get('price_change_percentage_24h') is not None
        # ↓↓↓ エラー修正点: .get('total_volume') or 0 とすることで None を 0 に変換
        and (c.get('total_volume') or 0) >= MIN_VOL_JPY
        and not is_stable_coin(c)
        and not is_wrapped_or_duplicate(c)
    ]
    
    top_gainers = sorted(valid_markets, key=lambda x: x['price_change_percentage_24h'], reverse=True)[:1]
    
    gainer_text = ""
    if top_gainers:
        top = top_gainers[0]
        gainer_text = f"🚀 本日のリード銘柄\n{top['symbol'].upper()} (+{top['price_change_percentage_24h']:.1f}%)"

    # --- 4. トレンド銘柄 (「今」の空気を伝える) ---
    trend_symbols = []
    for t in trending:
        if is_wrapped_or_duplicate(t) or is_stable_coin(t):
            continue
        trend_symbols.append(t['symbol'].upper())
        if len(trend_symbols) >= 3:
            break
            
    trend_text = f"🔥 今の注目トレンド\n{', '.join(trend_symbols)}" if trend_symbols else ""

    # --- 5. SNS(X)最適化テキスト組み立て ---
    dt_now = datetime.datetime.now()
    date_str = dt_now.strftime("%m/%d %H:%M")
    
    # 情報を「ブロック」で分け、スマホで一瞬で読めるようにします
    post_text = (
        f"🤖 CoinRader 市場速報 ({date_str})\n"
        f"{ai_insight}\n\n"
        f"{btc_text}\n\n"
        f"{trend_text}\n"
        f"{gainer_text}\n\n"
        f"📊 詳細な多角的分析はサイトでチェック\n"
        f"https://coinrader.net/\n\n"
        f"#Bitcoin #仮想通貨 #CoinRader #BTC"
    )
    
    return post_text

if __name__ == "__main__":
    print(generate_post())
