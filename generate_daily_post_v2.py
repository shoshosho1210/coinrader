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
# 2. データ取得 (APIキー対応)
# ==========================================
def get_coingecko_data(url, params):
    # YAMLで設定した CG_DEMO_KEY を読み込む
    api_key = os.getenv("CG_DEMO_KEY")
    headers = {"x-cg-demo-api-key": api_key} if api_key else {}
    
    try:
        res = requests.get(url, params=params, headers=headers, timeout=30)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"APIエラー: {url} -> {e}")
        return None

def format_price(price):
    if price is None: return "-"
    if price >= 1000000: return f"{price/10000:.0f}万"
    return f"{price:,.0f}"

# ==========================================
# 3. メイン処理
# ==========================================
def generate_post():
    # データ取得
    markets = get_coingecko_data("https://api.coingecko.com/api/v3/coins/markets", 
                                {"vs_currency": "jpy", "order": "market_cap_desc", "per_page": 250})
    
    # トレンド取得 (API構造が違うため個別処理)
    trending_raw = get_coingecko_data("https://api.coingecko.com/api/v3/search/trending", {})
    trending = [item['item'] for item in trending_raw.get('coins', [])] if trending_raw else []

    # 取得失敗時のガード
    if not markets:
        # 失敗しても空のJSONを作らないと後続のActionが止まるため、エラーメッセージを返す
        print("❌ データの取得に失敗しました。レート制限の可能性があります。")
        return False

    # --- データの抽出 ---
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

    # --- 日付計算 (JST) ---
    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    date_str = jst_now.strftime("%m/%d")
    file_date = jst_now.strftime("%Y%m%d")
    display_date = jst_now.strftime("%Y-%m-%d")

    # ==========================================
    # 4. ファイル保存 (data/daily と share/)
    # ==========================================
    
    # 1. JSON保存
    save_dir = "data/daily"
    os.makedirs(save_dir, exist_ok=True)
    with open(f"{save_dir}/{file_date}.json", "w", encoding="utf-8") as f:
        json.dump(markets, f, ensure_ascii=False, indent=2)

    # 2. HTML保存 (削ぎ落としたのは転送専用だからですが、OGPタグはフルセット入れています)
    share_html = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>CoinRader - 今日の注目 {display_date}</title>
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="CoinRader">
  <meta property="og:title" content="CoinRader - 今日の注目 {display_date}">
  <meta property="og:description" content="トレンド/上昇率/出来高をひと目で。">
  <meta property="og:url" content="https://coinrader.net/share/{file_date}.html">
  <meta property="og:image" content="https://coinrader.net/assets/og/ogp.png?v={file_date}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="https://coinrader.net/assets/og/ogp.png?v={file_date}">
  <meta http-equiv="refresh" content="0;url=https://coinrader.net/?v={file_date}">
</head>
<body></body>
</html>"""
    os.makedirs("share", exist_ok=True)
    with open(f"share/{file_date}.html", "w", encoding="utf-8") as f:
        f.write(share_html)

    # 3. テキスト出力
    chg = btc.get('price_change_percentage_24h', 0) if btc else 0
    ai_status = "【分析: 楽観】" if chg > 3 else ("【分析: 悲観】" if chg < -3 else "【分析: 中立】")
    site_url = f"https://coinrader.net/share/{file_date}.html"
    icon = "📈" if chg > 0 else "📉"

    short_post = (
        f"🤖 CoinRader 市場速報 ({date_str})\n"
        f"{ai_status} 多角的な需給解析を更新\n\n"
        f"🔹 Bitcoin {icon}\n"
        f"価格: ¥{format_price(btc['current_price']) if btc else '-'}\n"
        f"前日比: {'+' if chg > 0 else ''}{chg:.1f}%\n\n"
        f"🔥 トレンド: {', '.join(trend_symbols)}\n"
        f"🚀 急上昇: {top_gainers[0]['symbol'].upper() if top_gainers else '-'}\n\n"
        f"📊 詳細分析はサイトでチェック\n{site_url}\n\n"
        f"#Bitcoin #暗号資産 #CoinRader #BTC"
    )

    with open("daily_post_short.txt", "w", encoding="utf-8") as f: f.write(short_post)
    with open("daily_post_full.txt", "w", encoding="utf-8") as f: f.write(short_post)
    with open("daily_share_url.txt", "w", encoding="utf-8") as f: f.write(site_url)
    with open("daily_note_draft.md", "w", encoding="utf-8") as f: f.write(f"# Market Note {display_date}")

    return True

if __name__ == "__main__":
    if generate_post():
        print("✅ 正常終了")
    else:
        print("❌ 失敗")
