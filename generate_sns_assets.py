#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# CoinRader SNS Generator v6.3
# - Reads data/daily/latest.json (summary structure)
# - Outputs:
#   daily_post_short.txt
#   daily_share_url.txt
#   share/daily_post_en.txt
# - No out/ directory used

import json
from pathlib import Path
from datetime import datetime

BASE_URL = "https://coinrader.net"
DAILY_PATH = Path("data/daily/latest.json")

def load_json(path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def main():
    data = load_json(DAILY_PATH)
    summary = data.get("summary", {})

    date = summary.get("date", datetime.now().strftime("%Y-%m-%d"))
    fgi = summary.get("fgi", {}).get("value")
    fgi_label = summary.get("fgi", {}).get("label")
    rsi = summary.get("technical", {}).get("btc_rsi")
    signal = summary.get("signal_overall")
    score = summary.get("score_overall")
    top = summary.get("top_gainer", {})
    trending = summary.get("trending", [])

    date_label = datetime.fromisoformat(date).strftime("%m/%d")

    lines = []
    lines.append(f"【今日のBTC / {date_label}】")
    lines.append(f"判定：{signal}（SCORE {score}）｜FGI {fgi}（{fgi_label}）｜RSI {round(rsi,1) if rsi else '--'}")

    if fgi is not None:
        if fgi <= 10:
            lines.append("市場心理は“極度の恐怖”。投げが出やすい水準。")
        elif fgi <= 25:
            lines.append("市場心理は恐怖寄り。戻りは重くなりやすい。")
        elif fgi >= 75:
            lines.append("市場心理は強気寄り。過熱に注意。")
        else:
            lines.append("市場心理は中立域。方向感待ち。")

    if rsi is not None:
        if rsi < 45:
            lines.append("RSIは弱め。勢いの回復は未確認。")
        elif rsi > 55:
            lines.append("RSIは強め。上方向の勢いあり。")
        else:
            lines.append("RSIは中立。レンジ傾向。")

    if top:
        lines.append(f"注目：{top.get('symbol')} +{round(top.get('change',0),1)}%")

    if trending:
        lines.append("Trending: " + " / ".join(trending[:3]))

    lines.append("判断が変わる目安：FGI>25 かつ RSI>50")

    main_post = "\n".join(lines)

    self_reply = f"毎日の市場フェーズはこちら：{BASE_URL}"

    en_lines = []
    en_lines.append(f"BTC snapshot ({date_label} JST)")
    en_lines.append(f"SCORE {score} ({signal}) | FGI {fgi} | RSI {round(rsi,1) if rsi else '--'}")
    en_lines.append("Sentiment is heavy. Waiting for FGI>25 & RSI>50 for confirmation.")
    en_post = "\n".join(en_lines)

    Path("share").mkdir(exist_ok=True)

    Path("daily_post_short.txt").write_text(main_post + "\n", encoding="utf-8")
    Path("daily_share_url.txt").write_text(self_reply + "\n", encoding="utf-8")
    Path("share/daily_post_en.txt").write_text(en_post + "\n", encoding="utf-8")

    print("SNS assets generated (v6.3)")

if __name__ == "__main__":
    main()
