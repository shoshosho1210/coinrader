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
# 2. データ取得関数 (APIキー対応版)
# ==========================================
def get_coingecko_data(url, params):
    # YAMLで設定した CG_DEMO_KEY を読み込む（GitHub Actions環境用）
    api_key = os.getenv("CG_DEMO_KEY")
    headers = {"x-cg-demo-api-key": api_key} if api_key else {}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=30)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"APIエラー: {url} -> {e}")
        return None

def get_fear_and_greed_index():
    """市場の恐怖強欲指数(FGI)を取得"""
    try:
        res = requests.get("https://api.alternative.me/fng/", timeout=10)
        data = res.json()
        return {"value": int(data['data'][0]['value']), "label": data['data'][0]['value_classification']}
    except:
        return {"value": 50, "label": "Neutral"}

def format_price(price):
    if price is None: return "-"
    if price >= 1000000: return f"{price/10000:.0f}万"
    return f"{price:,.0f}"

# ==========================================
# 3. メイン処理
# ==========================================
def generate_post():
    # A. 市場データ取得 (上位250銘柄)
    markets = get_coingecko_data("https://api.coingecko.com/api/v3/coins/markets", 
                                {"vs_currency": "jpy", "order": "market_cap_desc", "per_page": 250})
    
    # B. トレンド取得
    trending_raw = get_coingecko_data("https://api.coingecko.com/api/v3/search/trending", {})
    trending_coins = [item['item'] for item in trending_raw.get('coins', [])] if trending_raw else []

    # C. 恐怖強欲指数取得
    fgi = get_fear_and_greed_index()

    if not markets:
        print("❌ 市場データの取得に失敗しました。")
        return False

    # --- 分析ロジック ---
    btc = next((item for item in markets if item["id"] == "bitcoin"), None)
    eth = next((item for item in markets if item["id"] == "ethereum"), None)
    
    # ドミナンス計算
    total_mcap = sum(c.get('market_cap', 0) or 0 for c in markets)
    btc_dom = (btc['market_cap'] / total_mcap * 100) if btc and total_mcap > 0 else 0

    # 急上昇 (出来高5億以上から選定)
    MIN_VOL = 500_000_000
    valid_gainers = [c for c in markets if (c.get('total_volume') or 0) >= MIN_VOL and not is_stable_coin(c) and not is_wrapped_or_duplicate(c)]
    top_gainer = sorted(valid_gainers, key=lambda x: x.get('price_change_percentage_24h', 0) or 0, reverse=True)[:1]
    
    # トレンドシンボル抽出
    trend_symbols = []
    for t in trending_coins:
        if not (is_wrapped_or_duplicate(t) or is_stable_coin(t)):
            trend_symbols.append(t['symbol'].upper())
        if len(trend_symbols) >= 3: break

    # 日付計算 (JST)
    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    file_date = jst_now.strftime("%Y%m%d")
    display_date = jst_now.strftime("%Y-%m-%d")
    date_label = jst_now.strftime("%m/%d")

    # ==========================================
    # 4. ファイル保存 (JSON / HTML)
    # ==========================================
    
    # 高度分析用サマリー構造
    intelligence_json = {
        "summary": {
            "date": display_date,
            "fgi": fgi,
            "btc_dominance": round(btc_dom, 2),
            "top_gainer": {
                "symbol": top_gainer[0]['symbol'].upper() if top_gainer else "-",
                "change": round(top_gainer[0]['price_change_percentage_24h'], 2) if top_gainer else 0
            },
            "trending": trend_symbols
        },
        "raw_data_count": len(markets),
        "raw_data": markets # 週次レポートの深掘り用に保持
    }

    # JSON保存
    os.makedirs("data/daily", exist_ok=True)
    with open(f"data/daily/{file_date}.json", "w", encoding="utf-8") as f:
        json.dump(intelligence_json, f, ensure_ascii=False, indent=2)

    # シェア用HTML作成
    share_html = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>CoinRader {display_date}</title>
  <meta property="og:title" content="CoinRader - 今日の注目 {display_date}">
  <meta property="og:url" content="https://coinrader.net/share/{file_date}.html">
  <meta property="og:image" content="https://coinrader.net/assets/og/ogp.png?v={file_date}">
  <meta name="twitter:card" content="summary_large_image">
  <meta http-equiv="refresh" content="0;url=https://coinrader.net/?v={file_date}">
</head>
<body></body>
</html>"""
    os.makedirs("share", exist_ok=True)
    with open(f"share/{file_date}.html", "w", encoding="utf-8") as f:
        f.write(share_html)

    # ==========================================
    # 5. SNS投稿テキスト作成
    # ==========================================
    chg = btc.get('price_change_percentage_24h', 0) if btc else 0
    ai_status = "【分析: 楽観】" if chg > 3 else ("【分析: 悲観】" if chg < -3 else "【分析: 中立】")
    icon = "📈" if chg > 0 else "📉"
    
    short_post = (
        f"🤖 CoinRader 市場速報 ({date_label})\n"
        f"{ai_status} 市場の需給をAI解析\n\n"
        f"🔹 Bitcoin {icon}\n"
        f"価格: ¥{format_price(btc['current_price']) if btc else '-'}\n"
        f"前日比: {'+' if chg > 0 else ''}{chg:.1f}%\n"
        f"心理指数: {fgi['value']} ({fgi['label']})\n\n"
        f"🔥 トレンド: {', '.join(trend_symbols)}\n"
        f"🚀 急上昇: {intelligence_json['summary']['top_gainer']['symbol']}\n\n"
        f"📊 詳細分析\nhttps://coinrader.net/share/{file_date}.html\n\n"
        f"#CoinRader #暗号資産"
    )

    with open("daily_post_short.txt", "w", encoding="utf-8") as f: f.write(short_post)
    with open("daily_post_full.txt", "w", encoding="utf-8") as f: f.write(short_post)
    with open("daily_share_url.txt", "w", encoding="utf-8") as f: f.write(f"https://coinrader.net/share/{file_date}.html")
    with open("daily_note_draft.md", "w", encoding="utf-8") as f: f.write(f"# Market Note {display_date}")

    return True

if __name__ == "__main__":
    if generate_post():
        print("✅ 全ファイルの生成に成功しました")
    else:
        print("❌ プロセス中にエラーが発生しました")
