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
def get_fear_and_greed_index():
    """市場の恐怖強欲指数(FGI)を取得"""
    try:
        res = requests.get("https://api.alternative.me/fng/", timeout=10)
        data = res.json()
        return {"value": int(data['data'][0]['value']), "label": data['data'][0]['value_classification']}
    except:
        return {"value": 50, "label": "Neutral"}

def generate_post():
    markets = get_market_data()
    trending = get_trending_coins()
    fgi = get_fear_and_greed_index()
    
    if not markets: return False

    # --- データの抽出と高度な指標の計算 ---
    btc = next((item for item in markets if item["id"] == "bitcoin"), None)
    eth = next((item for item in markets if item["id"] == "ethereum"), None)
    
    # 市場全体の時価総額（簡易合算）とBTCドミナンス
    total_mcap = sum(c.get('market_cap', 0) or 0 for c in markets)
    btc_dominance = (btc['market_cap'] / total_mcap * 100) if btc and total_mcap > 0 else 0

    # 日付計算 (JST)
    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    file_date = jst_now.strftime("%Y%m%d")
    display_date = jst_now.strftime("%Y-%m-%d")

    # ==========================================
    # 4. ファイル保存処理 (高度分析用JSON構造)
    # ==========================================
    # 週次レポート作成時に「ここだけ見れば良い」データを作成
    intelligence_summary = {
        "date": display_date,
        "market_sentiment": {
            "fgi_value": fgi["value"],
            "fgi_label": fgi["label"],
            "btc_dominance": round(btc_dominance, 2)
        },
        "key_assets": {
            "btc": {
                "price": btc["current_price"],
                "change_24h": round(btc["price_change_percentage_24h"], 2)
            } if btc else {},
            "eth": {
                "price": eth["current_price"],
                "change_24h": round(eth["price_change_percentage_24h"], 2)
            } if eth else {}
        },
        "weekly_report_hooks": {
            "top_gainers": sorted(markets, key=lambda x: x.get('price_change_percentage_24h', 0) or 0, reverse=True)[:5],
            "trending_symbols": [t['symbol'].upper() for t in trending[:5]]
        }
    }

    # 全データを統合して保存
    final_json = {
        "summary": intelligence_summary, # 週次レポートはこの中身を7日分並べるだけで作れる
        "raw_data": markets             # 250銘柄の詳細（深掘り用）
    }

    save_dir = "data/daily"
    os.makedirs(save_dir, exist_ok=True)
    with open(f"{save_dir}/{file_date}.json", "w", encoding="utf-8") as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)

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
