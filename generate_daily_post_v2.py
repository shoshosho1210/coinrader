import requests
import datetime
import os
import json
from typing import Any, Dict, Optional, Tuple

# ==========================================
# 1. 除外ロジック (ステーブル・Wrapped除外)
# ==========================================
STABLE_IDS = {"tether", "usd-coin", "dai", "true-usd", "first-digital-usd", "ethena-usde", "frax", "pax-dollar", "paypal-usd", "gemini-dollar", "paxos-standard", "binance-usd", "liquity-usd"}
STABLE_SYMBOLS = {"usdt", "usdc", "dai", "tusd", "usde", "fdusd", "pyusd", "gusd", "usdp", "busd", "lusd", "frax"}
SKIP_KEYWORDS = ["wrapped", "staked", "bridged", "token", "wbtc", "weth", "steth"]

# ==========================================
# 2. データ取得・分析関数　
# ==========================================
def is_stable_coin(coin):
    c_id = (coin.get('id') or '').lower()
    c_sym = (coin.get('symbol') or '').lower()
    return c_id in STABLE_IDS or c_sym in STABLE_SYMBOLS

def is_wrapped_or_duplicate(coin):
    c_id = (coin.get('id') or '').lower()
    if c_id in ['bitcoin', 'ethereum']: 
        return False
    c_name = (coin.get('name') or '').lower()
    c_sym = (coin.get('symbol') or '').lower()
    for k in SKIP_KEYWORDS:
        if k in c_name or k in c_sym: 
            return True
    return False

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

def calculate_rsi_from_prices(prices, period=14):
    """
    価格配列（Sparkline）からRSI(14)を計算する
    index.htmlのロジックに合わせるため、単純なAPI取得ではなく計算を行う
    """
    if not prices or len(prices) < period + 1:
        return None

    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]

    gain = sum([d for d in deltas[:period] if d > 0]) / period
    loss = sum([-d for d in deltas[:period] if d < 0]) / period

    avg_gain = gain
    avg_loss = loss

    # Wilder's Smoothing
    for i in range(period, len(deltas)):
        d = deltas[i]
        g = d if d > 0 else 0
        l = -d if d < 0 else 0

        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calculate_ma_distance(coin_id):
    """過去250日分の価格を取得して50日/200日MA乖離率を計算する"""
    data = get_coingecko_data(
        f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
        {"vs_currency": "jpy", "days": "250", "interval": "daily"}
    )
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

# ==========================================
# 3. BTC RAW判定（最小：安定化前提の初期値）
# ==========================================
def calc_btc_score_signal(btc_rsi: Optional[float], btc_ma_distance: Optional[float], fgi_value: Optional[int]) -> Tuple[Optional[int], Optional[str], str]:
    """
    BTCの raw score/signal を生成する（まずは安定化目的の初期ロジック）
    returns: (score_overall, signal_raw, reason_text)
    """
    if btc_ma_distance is None and btc_rsi is None and fgi_value is None:
        return None, None, "missing inputs"

    score = 0
    reasons = []

    # MA距離（主役）
    if btc_ma_distance is not None:
        if btc_ma_distance > 0:
            score += 2
            reasons.append("MA:bull")
        elif btc_ma_distance < 0:
            score -= 2
            reasons.append("MA:bear")
        else:
            reasons.append("MA:flat")

    # RSI（補助・境界は広め）
    if btc_rsi is not None:
        if btc_rsi >= 58:
            score += 1
            reasons.append("RSI:high")
        elif btc_rsi <= 42:
            score -= 1
            reasons.append("RSI:low")
        else:
            reasons.append("RSI:mid")

    # FGI（微調整・弱め）
    if fgi_value is not None:
        if fgi_value >= 65:
            score += 1
            reasons.append("FGI:greed")
        elif fgi_value <= 35:
            score -= 1
            reasons.append("FGI:fear")
        else:
            reasons.append("FGI:neutral")

    # raw判定
    if score >= 2:
        sig = "BUY"
    elif score <= -2:
        sig = "SELL"
    else:
        sig = "WAIT"

    return int(score), sig, ",".join(reasons)[:200]

# ==========================================
# 4. intraday保存 + 状態機械(stable)
# ==========================================
INTRADAY_DIR = "data/intraday"
RAW_DIR = os.path.join(INTRADAY_DIR, "raw")
STATE_PATH = os.path.join(INTRADAY_DIR, "state.json")
STABLE_PATH = os.path.join(INTRADAY_DIR, "stable.json")

def _load_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _write_json(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def _phase_label(sig: Optional[str]) -> str:
    if sig == "BUY":
        return "Uptrend"
    if sig == "SELL":
        return "Downtrend"
    return "Range"

def update_stable_state(symbol: str, now_iso: str, now_epoch: int, raw_sig: Optional[str], raw_score: Optional[int]) -> Dict[str, Any]:
    """
    方式A（2回一致）＋方式B（ヒステリシス）のBTC-only実装
    - 2回一致は「stableと異なる方向に切替するときのみ」
    - ヒステリシス:
        BUY維持: score > 0
        SELL維持: score < 0
      （境界は後から調整しやすいよう、ここに集約）
    """
    os.makedirs(INTRADAY_DIR, exist_ok=True)
    state = _load_json(STATE_PATH) or {}

    stable_sig = state.get("stable_signal") or "WAIT"
    changed_at = state.get("changed_at") or now_iso  # 初回は今
    pending_sig = state.get("pending_signal")
    pending_count = int(state.get("pending_count") or 0)
    last_raw_sig = state.get("last_raw_signal")

    # raw欠損なら何もしない（stable維持）
    if raw_sig not in ("BUY", "SELL", "WAIT") or raw_score is None:
        new_state = {
            "version": 1,
            "symbol": symbol,
            "stable_signal": stable_sig,
            "changed_at": changed_at,
            "pending_signal": None,
            "pending_count": 0,
            "last_raw_signal": raw_sig,
            "last_raw_ts": now_iso,
        }
        _write_json(STATE_PATH, new_state)
        return new_state

    # ヒステリシス：維持条件を満たすなら、安易にWAITへ落とさない
    def hysteresis_hold(sig: str, score: int) -> bool:
        if sig == "BUY":
            return score > 0
        if sig == "SELL":
            return score < 0
        return True  # WAITはそのままでもOK

    # まず維持を判定（BUY/SELL中に、明確に維持なら即固定）
    if stable_sig in ("BUY", "SELL") and hysteresis_hold(stable_sig, raw_score):
        pending_sig = None
        pending_count = 0
        new_stable = stable_sig
    else:
        # 維持できない場合、rawがstableと同じならpending解除してそのまま
        if raw_sig == stable_sig:
            pending_sig = None
            pending_count = 0
            new_stable = stable_sig
        else:
            # 切替候補：stableと異なる方向へ行くときだけ2回一致を要求
            # （WAIT -> BUY/SELL も含む）
            candidate = raw_sig

            if pending_sig == candidate:
                pending_count += 1
            else:
                pending_sig = candidate
                pending_count = 1

            # 2回一致 + しきい値で確定（堅め）
            commit = False
            if pending_count >= 2:
                if candidate == "BUY" and raw_score >= 2:
                    commit = True
                elif candidate == "SELL" and raw_score <= -2:
                    commit = True
                elif candidate == "WAIT":
                    # WAITへの落とし込みは軽めに（ここは好みで2回一致のまま）
                    commit = True

            if commit:
                new_stable = candidate
                pending_sig = None
                pending_count = 0
            else:
                new_stable = stable_sig

    # stableが変わったら changed_at を更新
    if new_stable != stable_sig:
        changed_at = now_iso

    new_state = {
        "version": 1,
        "symbol": symbol,
        "stable_signal": new_stable,
        "changed_at": changed_at,
        "pending_signal": pending_sig,
        "pending_count": pending_count,
        "last_raw_signal": raw_sig,
        "last_raw_ts": now_iso,
    }
    _write_json(STATE_PATH, new_state)
    return new_state

def write_intraday_raw(symbol: str, file_date: str, hhmm: str, now_iso: str, raw_sig: Optional[str], raw_score: Optional[int], reason_text: str) -> str:
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, f"{file_date}_{hhmm}.json")
    payload = {
        "ts": now_iso,
        "symbol": symbol,
        "score_overall": raw_score,
        "signal_raw": raw_sig,
        "reason_hint": reason_text,
        "reason_top3": [],
    }
    _write_json(path, payload)
    return path

def write_stable(symbol: str, now_iso: str, now_epoch: int, raw_sig: Optional[str], raw_score: Optional[int], state: Dict[str, Any]) -> None:
    stable_sig = state.get("stable_signal") or "WAIT"
    changed_at = state.get("changed_at") or now_iso

    # duration_hours（UI側で計算しても良いが、ここで入れておく）
    try:
        dt_changed = datetime.datetime.fromisoformat(changed_at.replace("Z", "+00:00"))
        dt_now = datetime.datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        duration_hours = round((dt_now - dt_changed).total_seconds() / 3600.0, 2)
        if duration_hours < 0:
            duration_hours = 0.0
    except Exception:
        duration_hours = None

    payload = {
        "ts": now_iso,
        "symbol": symbol,
        "signal_stable": stable_sig,
        "phase_label": _phase_label(stable_sig),
        "changed_at": changed_at,
        "duration_hours": duration_hours,
        # 参考情報（UIが必要なら使える）
        "signal_raw": raw_sig,
        "score_overall": raw_score,
    }
    _write_json(STABLE_PATH, payload)

def prune_intraday_raw(keep_days: int = 14) -> None:
    """
    intraday/raw を keep_days 日分だけ残す（Git肥大防止）
    """
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now - datetime.timedelta(days=keep_days)
        if not os.path.isdir(RAW_DIR):
            return
        for fn in os.listdir(RAW_DIR):
            if not fn.endswith(".json"):
                continue
            path = os.path.join(RAW_DIR, fn)
            try:
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path), tz=datetime.timezone.utc)
                if mtime < cutoff:
                    os.remove(path)
            except Exception:
                continue
    except Exception:
        pass

# ==========================================
# 5. メイン処理
# ==========================================
def generate_post():
    print("Fetching Market Data...")

    markets = get_coingecko_data(
        "https://api.coingecko.com/api/v3/coins/markets",
        {"vs_currency": "jpy", "order": "market_cap_desc", "per_page": 250, "sparkline": "true"}
    )
    trending_raw = get_coingecko_data("https://api.coingecko.com/api/v3/search/trending", {})
    trending_coins = [item['item'] for item in trending_raw.get('coins', [])] if trending_raw else []
    fgi = get_fear_and_greed_index()

    if not markets:
        print("❌ 市場データの取得に失敗しました。")
        return False

    btc = next((item for item in markets if item["id"] == "bitcoin"), None)
    eth = next((item for item in markets if item["id"] == "ethereum"), None)

    btc_rsi = None
    if btc and 'sparkline_in_7d' in btc and 'price' in btc['sparkline_in_7d']:
        btc_rsi = calculate_rsi_from_prices(btc['sparkline_in_7d']['price'])

    eth_rsi = None
    if eth and 'sparkline_in_7d' in eth and 'price' in eth['sparkline_in_7d']:
        eth_rsi = calculate_rsi_from_prices(eth['sparkline_in_7d']['price'])

    btc_ma_dist = calculate_ma_distance("bitcoin")

    total_mcap = sum(c.get('market_cap', 0) or 0 for c in markets)
    btc_dom = (btc['market_cap'] / total_mcap * 100) if btc and total_mcap > 0 else 0

    valid_gainers = [
        c for c in markets
        if c.get('total_volume') and c.get('total_volume') >= 500_000_000
        and not is_stable_coin(c)
        and not is_wrapped_or_duplicate(c)
    ]
    top_gainer = sorted(valid_gainers, key=lambda x: x.get('price_change_percentage_24h', 0) or 0, reverse=True)[:1]

    trend_symbols = []
    for t in trending_coins:
        if not (is_wrapped_or_duplicate(t) or is_stable_coin(t)):
            trend_symbols.append(t['symbol'].upper())
        if len(trend_symbols) >= 3:
            break

    # 日付計算 (JST)
    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    file_date = jst_now.strftime("%Y%m%d")
    display_date = jst_now.strftime("%Y-%m-%d")
    hhmm = jst_now.strftime("%H%M")

    # ISO8601（Zではなく+09:00）
    now_iso = jst_now.isoformat()
    now_epoch = int(jst_now.timestamp())

    # BTC raw判定
    raw_score, raw_sig, reason_hint = calc_btc_score_signal(
        btc_rsi=btc_rsi,
        btc_ma_distance=btc_ma_dist,
        fgi_value=int(fgi.get("value")) if isinstance(fgi, dict) else None
    )

    # “tradeable”はまず最小：BUY/SELLならOK、それ以外WAIT
    tradeable = "OK" if raw_sig in ("BUY", "SELL") else "WAIT"

    # ==========================================
    # 6. 日次JSON（後方互換維持）
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
            "trending": trend_symbols,

            # 追加（後方互換：無くてもOKなキーだけ）
            "signal_overall": raw_sig,
            "score_overall": raw_score,
            "tradeable": tradeable,
            "market_mode_label": None,
            "reason_top3": []
        },
        "raw_data_count": len(markets),
        "raw_data": markets
    }

    os.makedirs("data/daily", exist_ok=True)
    with open(f"data/daily/{file_date}.json", "w", encoding="utf-8") as f:
        json.dump(intelligence_json, f, ensure_ascii=False, indent=2)

    # latest.json は data/daily に統一（data/latest.json は廃止方針）
    with open("data/daily/latest.json", "w", encoding="utf-8") as f:
        json.dump(intelligence_json, f, ensure_ascii=False, indent=2)

    # ==========================================
    # 7. intraday raw 保存 + stable 更新
    # ==========================================
    write_intraday_raw("BTC", file_date, hhmm, now_iso, raw_sig, raw_score, reason_hint)

    state = update_stable_state("BTC", now_iso, now_epoch, raw_sig, raw_score)
    write_stable("BTC", now_iso, now_epoch, raw_sig, raw_score, state)

    prune_intraday_raw(keep_days=14)

    return True

if __name__ == "__main__":
    if generate_post():
        print("✅ 日次JSON + intraday raw + stable の生成に成功しました")
    else:
        print("❌ プロセス中にエラーが発生しました")
