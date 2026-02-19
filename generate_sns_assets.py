#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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


def classify_phase(score, fgi, rsi):

    if score <= -3 and fgi <= 10 and rsi < 45:
        return (
            "恐怖の底探り局面",
            "市場心理は崩壊水準だが、価格はまだ決定的に壊れていない。",
            "反転確認までは戻り売り優位。"
        )

    if score <= -2 and fgi <= 25 and rsi >= 45:
        return (
            "売り圧力鈍化フェーズ",
            "恐怖は強いが、テクニカルは下げ止まりを示唆。",
            "短期反発の可能性を警戒。"
        )

    if -1 <= score <= 1:
        return (
            "エネルギー圧縮局面",
            "センチメントとモメンタムが拮抗。",
            "ブレイク方向に注意。"
        )

    if score >= 3 and fgi >= 75 and rsi > 60:
        return (
            "過熱警戒ゾーン",
            "強気は過度に傾いている。",
            "追いかけ買いはリスク高。"
        )

    return (
        "方向感模索フェーズ",
        "明確な優位性はまだ形成されていない。",
        "指標改善を待つ局面。"
    )


def main():
    data = load_json(DAILY_PATH)
    summary = data.get("summary", {})

    date = summary.get("date", datetime.now().strftime("%Y-%m-%d"))
    fgi = summary.get("fgi", {}).get("value", 0)
    fgi_label = summary.get("fgi", {}).get("label", "")
    rsi = summary.get("technical", {}).get("btc_rsi", 0)
    signal = summary.get("signal_overall", "N/A")
    score = summary.get("score_overall", 0)
    top = summary.get("top_gainer", {})
    trending = summary.get("trending", [])

    date_label = datetime.fromisoformat(date).strftime("%m/%d")

    phase, insight, action = classify_phase(score, fgi, rsi)

    lines = []
    lines.append(f"【今日のBTC / {date_label}】")
    lines.append(f"判定：{signal}（SCORE {score}）｜FGI {fgi}（{fgi_label}）｜RSI {round(rsi,1)}")
    lines.append("")
    lines.append(f"▼ 局面：{phase}")
    lines.append(insight)
    lines.append("")
    lines.append(action)

    if top:
        lines.append("")
        lines.append(f"注目：{top.get('symbol')} +{round(top.get('change',0),1)}%")

    if trending:
        lines.append(f"Trending: {' / '.join(trending[:3])}")

    lines.append("")
    lines.append("判断が変わる目安：FGI>25 かつ RSI>50")

    main_post = "\n".join(lines)

    self_reply = f"毎日の市場フェーズ分析：{BASE_URL}"

    en_post = (
        f"BTC Phase Report ({date_label} JST)\n"
        f"SCORE {score} ({signal}) | FGI {fgi} | RSI {round(rsi,1)}\n"
        f"Phase: {phase}\n"
        "Waiting for confirmation above FGI 25 & RSI 50."
    )

    Path("share").mkdir(exist_ok=True)

    Path("daily_post_short.txt").write_text(main_post + "\n", encoding="utf-8")
    Path("daily_share_url.txt").write_text(self_reply + "\n", encoding="utf-8")
    Path("share/daily_post_en.txt").write_text(en_post + "\n", encoding="utf-8")

    print("SNS assets generated (v6.4 Pro)")


if __name__ == "__main__":
    main()
