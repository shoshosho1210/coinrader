import requests
import datetime
import math
import os

# ==========================================
# 1. 除外ロジック (ステーブル・Wrapped除外)
# ==========================================
STABLE_IDS = {"tether", "usd-coin", "dai", "true-usd", "first-digital-usd", "ethena-usde", "frax", "pax-dollar", "paypal-usd", "gemini-dollar", "paxos-standard", "binance-usd", "liquity-usd"}
STABLE_SYMBOLS = {"usdt", "usdc", "dai", "tusd", "usde", "fdusd", "pyusd", "gusd", "usdp", "busd", "lusd", "frax"}
SKIP_KEYWORDS = ["wrapped", "staked", "bridged", "token", "wbtc", "weth", "steth"]

def is_stable_coin(coin):
    c_id = coin.get('id', '').lower()
    c_sym = coin.get('symbol', '').lower()
    return c_id in STABLE_IDS or c_sym in STABLE_SYMBOLS

def is_wrapped_or_duplicate(coin):
    c_id = coin.get('id', '').lower()
    if c_id in ['bitcoin', 'ethereum']: return False
    c_name = coin.get('name', '').lower()
    c_sym = coin.get('symbol', '').lower()
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
def run_main():
    markets = get_market_data()
    trending = get_trending_coins()
    if not markets: return

    # --- データの抽出 ---
    btc = next((item for item in markets if item["id"] == "bitcoin"), None)
    
    # エラー修正: Noneチェックと 0 へのフォールバック
    MIN_VOL_JPY = 500_000_000 
    valid_gainers = [
        c for c in markets 
        if c.get('price_change_percentage_24h') is not None
        and (c.get('total_volume') or 0) >= MIN_VOL_JPY # ★None対策
        and not is_stable_coin(c)
        and not is_wrapped_or_duplicate(c)
    ]
    top_gainers = sorted(valid_gainers, key=lambda x: x['price_change_percentage_24h'], reverse=True)[:1]
    
    trend_symbols = []
    for t in trending:
        if not (is_wrapped_or_duplicate(t) or is_stable_coin(t)):
            trend_symbols.append(t['symbol'].upper())
        if len(trend_symbols) >= 3: break

    # --- SNS向けテキスト整形 ---
    dt_now = datetime.datetime.now()
    date_str = dt_now.strftime("%m/%d %H:%M")
    
    chg = btc.get('price_change_percentage_24h', 0) if btc else 0
    icon = "📈" if chg > 0 else ("📉" if chg < 0 else "➡️")
    sign = "+" if chg > 0 else ""
    
    # 1. サイトへのリンク
    site_url = "https://coinrader.net/"
    
    # 2. X用：情報を絞ってインパクト重視 (short)
    short_text = (
        f"🤖 CoinRader 市場速報 ({date_str})\n"
        f"最新のAI市場分析を更新しました！\n\n"
        f"🔹 Bitcoin {icon}\n"
        f"価格: ¥{format_price(btc['current_price']) if btc else '-'}\n"
        f"前日比: {sign}{chg:.1f}%\n\n"
        f"🔥 トレンド: {', '.join(trend_symbols)}\n"
        f"🚀 急上昇: {top_gainers[0]['symbol'].upper() if top_gainers else '-'}\n\n"
        f"📊 詳細な分析はサイトでチェック\n{site_url}\n"
        f"#Bitcoin #暗号資産 #CoinRader"
    )

    # 3. Discord/記録用：全情報網羅 (full)
    full_text = (
        f"【CoinRader 市場分析レポート {date_str}】\n"
        f"AIが需給構造を解析。現在は「中立〜楽観」の境界。平均回帰性が意識される局面です。\n\n"
        f"■ ビットコイン相場\n"
        f"価格: ¥{btc['current_price'] if btc else 0:,.0f}\n"
        f"騰落: {sign}{chg:.2f}%\n\n"
        f"■ トレンド・注目銘柄\n"
        f"Trend: {', '.join(trend_symbols)}\n"
        f"Gain: {top_gainers[0]['name']} (+{top_gainers[0]['price_change_percentage_24h']:.1f}%)\n\n"
        f"▼ 詳細はこちら\n{site_url}"
    )

    # ==========================================
    # 4. ファイルへの書き出し処理
    # ==========================================
    with open("daily_post_short.txt", "w", encoding="utf-8") as f:
        f.write(short_text)
    
    with open("daily_post_full.txt", "w", encoding="utf-8") as f:
        f.write(full_text)
        
    with open("daily_share_url.txt", "w", encoding="utf-8") as f:
        f.write(site_url)

    print("✅ Files generated successfully:")
    print("- daily_post_short.txt")
    print("- daily_post_full.txt")
    print("- daily_share_url.txt")

if __name__ == "__main__":
    run_main()
