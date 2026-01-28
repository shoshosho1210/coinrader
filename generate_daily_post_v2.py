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

def format_price(price):
    if price is None: return "-"
    if price >= 1000000: return f"{price/10000:.0f}万"
    return f"{price:,.0f}"

# ==========================================
# 3. 投稿テキスト & シェアHTML生成
# ==========================================
def generate_post():
    markets = get_market_data()
    trending = get_trending_coins()
    if not markets: return "データの取得に失敗しました。"

    btc = next((item for item in markets if item["id"] == "bitcoin"), None)
    
    MIN_VOL_JPY = 500_000_000 
    valid_gainers = [
        c for c in markets 
        if c.get('price_change_percentage_24h') is not None
        and (c.get('total_volume') or 0) >= MIN_VOL_JPY
        and not is_stable_coin(c)
        and not is_wrapped_or_duplicate(c)
    ]
    top_gainers = sorted(valid_gainers, key=lambda x: x['price_change_percentage_24h'], reverse=True)[:1]
    
    trend_symbols = []
    for t in trending:
        if not (is_wrapped_or_duplicate(t) or is_stable_coin(t)):
            trend_symbols.append(t['symbol'].upper())
        if len(trend_symbols) >= 3: break

    # --- 重要：日本時間(JST)での日付取得 ---
    # GitHub ActionsはUTCなため、9時間加算してJSTにする
    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    date_str = jst_now.strftime("%m/%d")
    file_date = jst_now.strftime("%Y%m%d")   # 20260128 形式
    display_date = jst_now.strftime("%Y-%m-%d") # 2026-01-28 形式

    # --- 4. シェア用HTMLの作成 ---
    share_html = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>CoinRader - 今日の注目 {display_date}</title>
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="CoinRader">
  <meta property="og:title" content="CoinRader - 今日の注目 {display_date}">
  <meta property="og:description" content="トレンド/上昇率/出来高をひと目で。">
  <meta property="og:url" content="https://coinrader.net/share/{file_date}.html">
  <meta property="og:image" content="https://coinrader.net/assets/og/ogp.png?v={file_date}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="CoinRader - 今日の注目 {display_date}">
  <meta name="twitter:description" content="トレンド/上昇率/出来高をひと目で。">
  <meta name="twitter:image" content="https://coinrader.net/assets/og/ogp.png?v={file_date}">
  <meta http-equiv="refresh" content="0;url=https://coinrader.net/?v={file_date}">
</head>
<body></body>
</html>"""

    # shareフォルダを作成して保存
    os.makedirs("share", exist_ok=True)
    with open(f"share/{file_date}.html", "w", encoding="utf-8") as f:
        f.write(share_html)

    # --- 5. メッセージの組み立て ---
    chg = btc.get('price_change_percentage_24h', 0) if btc else 0
    icon = "📈" if chg > 0 else ("📉" if chg < 0 else "➡️")
    sign = "+" if chg > 0 else ""
    ai_status = "【分析: 楽観】" if chg > 3 else ("【分析: 悲観】" if chg < -3 else "【分析: 中立】")
    
    # リンクを日別HTMLに設定
    site_url = f"https://coinrader.net/share/{file_date}.html"

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
    
    # 追加：市場の感情データを取得
    fgi_data = get_fear_and_greed_index()

    # --- ここがポイント！週次レポート用のデータまとめ ---
    daily_json = {
        "date": display_date,
        "btc_price": btc['current_price'] if btc else 0,
        "btc_change": chg,
        "sentiment": fgi_data,  # ← ここに入れます！
        "top_gainer": {
            "symbol": top_gainers[0]['symbol'].upper(),
            "change": top_gainers[0]['price_change_percentage_24h']
        } if top_gainers else None,
        "trending": trend_symbols
    }

    # データの保存（dataフォルダを作成して保存）
    os.makedirs("assets/data/daily", exist_ok=True) 
    with open(f"assets/data/daily/{file_date}.json", "w", encoding="utf-8") as f:
        json.dump(daily_json, f, ensure_ascii=False, indent=4)
    # 各種テキストファイル出力
    with open("daily_post_short.txt", "w", encoding="utf-8") as f:
        f.write(short_post)
    with open("daily_post_full.txt", "w", encoding="utf-8") as f:
        f.write(short_post)
    with open("daily_share_url.txt", "w", encoding="utf-8") as f:
        f.write(site_url)
    
    # GitHub Actionsのテスト用ダミーファイル
    with open("daily_note_draft.md", "w", encoding="utf-8") as f:
        f.write(f"# Market Note {display_date}")

    return f"✅ {file_date}.html 生成完了"

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
        
if __name__ == "__main__":
    print(generate_post())
