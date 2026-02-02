import requests
import datetime
import os
import json
import time

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
# 2. データ取得・分析関数
# ==========================================
def get_coingecko_data(url, params):
    api_key = os.getenv("CG_DEMO_KEY")
    headers = {"x-cg-demo-api-key": api_key} if api_key else {}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=30)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"APIエラー: {url} -> {e}")
        return None

# ★修正1: RSI計算ロジックを変更（index.html準拠）
def calculate_rsi_from_sparkline(prices, period=14):
    """Sparklineの価格配列からRSI(14)を計算 (Wilder's Smoothing)"""
    if not prices or len(prices) < period + 1:
        return None
    
    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
    
    gain = sum([d for d in deltas[:period] if d > 0]) / period
    loss = sum([-d for d in deltas[:period] if d < 0]) / period
    
    avg_gain = gain
    avg_loss = loss
    
    for i in range(period, len(deltas)):
        d = deltas[i]
        gain = d if d > 0 else 0
        loss = -d if d < 0 else 0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        
    if avg_loss == 0: return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calculate_ma_distance(coin_id):
    """過去250日分の価格を取得してMA乖離率を計算 (変更なし)"""
    data = get_coingecko_data(f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart", 
                              {"vs_currency": "jpy", "days": "250", "interval": "daily"})
    if not data or 'prices' not in data:
        return None
    
    prices = [p[1] for p in data['prices']]
    if len(prices) < 200:
        return None

    sma50 = sum(prices[-50:]) / 50
    sma200 = sum(prices[-200:]) / 200
    ma_distance = ((sma50 - sma200) / sma200) * 100
    return round(ma_distance, 2)
    
def get_fear_and_greed_index():
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
    # ★修正1: sparkline=true を追加
    markets = get_coingecko_data("https://api.coingecko.com/api/v3/coins/markets", 
                                {"vs_currency": "jpy", "order": "market_cap_desc", "per_page": 250, "sparkline": "true"})
    
    trending_raw = get_coingecko_data("https://api.coingecko.com/api/v3/search/trending", {})
    trending_coins = [item['item'] for item in trending_raw.get('coins', [])] if trending_raw else []
    fgi = get_fear_and_greed_index()

    if not markets:
        print("❌ 市場データの取得に失敗しました。")
        return False

    # 指標抽出
    btc = next((item for item in markets if item["id"] == "bitcoin"), None)
    eth = next((item for item in markets if item["id"] == "ethereum"), None)

    # ★修正1: RSIをSparklineから計算（構造は維持）
    btc_rsi = None
    if btc and 'sparkline_in_7d' in btc:
        btc_rsi = calculate_rsi_from_sparkline(btc['sparkline_in_7d'].get('price', []))

    eth_rsi = None
    if eth and 'sparkline_in_7d' in eth:
        eth_rsi = calculate_rsi_from_sparkline(eth['sparkline_in_7d'].get('price', []))

    # MAは別途取得
    btc_ma_dist = calculate_ma_distance("bitcoin")

    total_mcap = sum(c.get('market_cap', 0) or 0 for c in markets)
    btc_dom = (btc['market_cap'] / total_mcap * 100) if btc and total_mcap > 0 else 0

    # ★修正2: total_volume が None の場合のエラー回避 (or 0)
    valid_gainers = [
        c for c in markets 
        if (c.get('total_volume') or 0) >= 500_000_000 
        and not is_stable_coin(c) 
        and not is_wrapped_or_duplicate(c)
    ]
    top_gainer = sorted(valid_gainers, key=lambda x: x.get('price_change_percentage_24h', 0) or 0, reverse=True)[:1]
    
    # トレンドシンボル
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
    # 4. JSON 生成 (元の構造を完全に維持)
    # ==========================================
    intelligence_json = {
        "summary": {
            "date": display_date,
            "fgi": fgi,
            "btc_dominance": round(btc_dom, 2),
            "technical": {
                "btc_rsi": btc_rsi,
                "eth_rsi": eth_rsi,
                "btc_ma_distance": btc_ma_dist
            },
            "top_gainer": {
                "symbol": top_gainer[0]['symbol'].upper() if top_gainer else "-",
                "change": round(top_gainer[0]['price_change_percentage_24h'], 2) if top_gainer else 0
            },
            "trending": trend_symbols
        },
        "raw_data_count": len(markets),
        "raw_data": markets 
    }

    # JSON保存 (Daily)
    os.makedirs("data/daily", exist_ok=True)
    with open(f"data/daily/{file_date}.json", "w", encoding="utf-8") as f:
        json.dump(intelligence_json, f, ensure_ascii=False, indent=2)

    # ★修正3: latest.json も更新する
    with open("data/latest.json", "w", encoding="utf-8") as f:
        json.dump(intelligence_json, f, ensure_ascii=False, indent=2)

    # シェア用HTML作成
    share_html = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>CoinRader {display_date}</title>
  <meta property="og:title" content="CoinRader - 今日の注目 {display_date}">
  <meta property="og:url" content="https://coinrader.net/share/{file_date}.html">
  <meta property="og:image" content="https://coinrader.net/assets/og/ogp_v2.png?v={file_date}">
  <meta name="twitter:card" content="summary_large_image">
  <meta http-equiv="refresh" content="0;url=https://coinrader.net/?v={file_date}">
</head>
<body></body>
</html>"""
    os.makedirs("share", exist_ok=True)
    with open(f"share/{file_date}.html", "w", encoding="utf-8") as f:
        f.write(share_html)

  # ==========================================
    # 5. SNS投稿テキスト & 各種レポート出力
    # ==========================================
    chg = btc.get('price_change_percentage_24h', 0) if btc else 0
    ai_status_msg = "分析: 楽観" if chg > 3 else ("分析: 悲観" if chg < -3 else "分析: 中立")
    icon = "📈" if chg > 0 else "📉"
    
    trending_str = ", ".join(trend_symbols) if trend_symbols else "-"
    top_g_sym = intelligence_json['summary']['top_gainer']['symbol']
    top_g_chg = int(intelligence_json['summary']['top_gainer']['change'])
    
    short_post = (
        f"🤖 CoinRader 市場速報 ({date_label})\n"
        f"{ai_status_msg}\n\n"
        f"🔹 Bitcoin {icon}\n"
        f"価格: ¥{format_price(btc['current_price']) if btc else '-'}\n"
        f"前日比: {'+' if chg > 0 else ''}{chg:.1f}%\n"
        f"RSI(14): {btc_rsi if btc_rsi else '-'}\n"
        f"心理指数: {fgi['value']} ({fgi['label']})\n\n"
        f"📈 注目銘柄\n"
        f"トレンド入り: {trending_str}\n"
        f"急上昇銘柄: {top_g_sym} ({top_g_chg}%↑)\n\n"
        f"📊 詳細分析\n"
        f"https://coinrader.net/share/{file_date}.html\n\n"
        f"#CoinRader #ビットコイン #暗号資産"
    )

    update_time = jst_now.strftime("%H:%M:%S")

    note_content = f"""# Market Note {display_date} ({update_time} 更新)

## 📊 今日の主要マーケット指標
- **BTC価格:** ¥{format_price(btc['current_price']) if btc else '-'} ({'+' if chg > 0 else ''}{chg:.1f}%)
- **BTC RSI(14):** {btc_rsi if btc_rsi else 'データ収集中'}
- **心理指数(FGI):** {fgi['value']} ({fgi['label']})
- **BTCドミナンス:** {round(btc_dom, 2)}%

## 📈 注目銘柄の動向
- **トレンド入り:** {trending_str}
- **本日の急上昇銘柄:** {top_g_sym} ({top_g_chg}%↑)

## ✍️ 市場分析メモ
- 本日の市場センチメントは「{fgi['label']}」となっており、{ai_status_msg}の傾向が見られます。
- テクニカル的にはBTC RSIが {btc_rsi if btc_rsi else '-'} の水準にあり、{'買われすぎ' if (btc_rsi or 0) > 70 else '売られすぎ' if (btc_rsi or 0) < 30 else '中立圏'} を示唆しています。
"""

    with open("daily_post_short.txt", "w", encoding="utf-8") as f:
        f.write(short_post)
    
    with open("daily_post_full.txt", "w", encoding="utf-8") as f:
        f.write(short_post)
    
    with open("daily_share_url.txt", "w", encoding="utf-8") as f:
        f.write(f"https://coinrader.net/share/{file_date}.html")
    
    with open("daily_note_draft.md", "w", encoding="utf-8") as f:
        f.write(note_content)

    return True

if __name__ == "__main__":
    if generate_post():
        print("✅ RSI・詳細レポートを含む全ファイルの生成に成功しました")
    else:
        print("❌ プロセス中にエラーが発生しました")
