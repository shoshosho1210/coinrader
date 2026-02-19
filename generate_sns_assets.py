#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# CoinRader SNS Generator v7.0
# Phase history tracking + transition detection + engagement hook

import json
from pathlib import Path
from datetime import datetime

BASE_URL = "https://coinrader.net"
DAILY_PATH = Path("data/daily/latest.json")
HISTORY_PATH = Path("data/daily/phase_history.json")


def load_json(path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def classify_phase(score, fgi, rsi):

    if score <= -3 and fgi <= 10 and rsi < 45:
        return "恐怖の底探り局面"

    if score <= -2 and fgi <= 25 and rsi >= 45:
        return "売り圧力鈍化フェーズ"

    if -1 <= score <= 1:
        return "エネルギー圧縮局面"

    if score >= 3 and fgi >= 75 and rsi > 60:
        return "過熱警戒ゾーン"

    return "方向感模索フェーズ"


def detect_transition(prev, current):

    messages = []

    if not prev:
        return ""

    if prev["score"] < 0 and current["score"] > prev["score"]:
        messages.append("リスクは緩和方向。")

    if prev["fgi"] < 20 and current["fgi"] > prev["fgi"]:
        messages.append("恐怖は後退中。")

    if prev["rsi"] < 45 and current["rsi"] > 50:
        messages.append("モメンタム改善を確認。")

    if messages:
        return "▼ 転換兆候
" + " ".join(messages)

    return ""


def build_hook(score, fgi):
    if score <= -3:
        return "恐怖は最大だが、崩壊とは限らない。"
    if score >= 3:
        return "熱狂は頂点で生まれる。"
    return "市場は次の方向を探している。"


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

    phase = classify_phase(score, fgi, rsi)

    current_entry = {
        "date": date,
        "score": score,
        "fgi": fgi,
        "rsi": rsi,
        "phase": phase
    }

    history = load_json(HISTORY_PATH) or []
    prev_entry = history[-1] if history else None

    transition_text = detect_transition(prev_entry, current_entry)

    history.append(current_entry)
    history = history[-30:]  # keep last 30 days
    save_json(HISTORY_PATH, history)

    date_label = datetime.fromisoformat(date).strftime("%m/%d")

    hook = build_hook(score, fgi)

    lines = []
    lines.append(f"【今日のBTC / {date_label}】")
    lines.append(f"判定：{signal}（SCORE {score}）｜FGI {fgi}（{fgi_label}）｜RSI {round(rsi,1)}")
    lines.append("")
    lines.append(f"▼ 局面：{phase}")
    lines.append(hook)
    lines.append("")

    if transition_text:
        lines.append(transition_text)
        lines.append("")

    lines.append("判断が変わる目安：FGI>25 かつ RSI>50")

    if top:
        lines.append("")
        lines.append(f"注目：{top.get('symbol')} +{round(top.get('change',0),1)}%")

    if trending:
        lines.append(f"Trending: {' / '.join(trending[:3])}")

    main_post = "\n".join(lines)

    self_reply = f"毎日の市場フェーズ分析：{BASE_URL}"

    en_post = (
        f"BTC Phase Report ({date_label} JST)\n"
        f"SCORE {score} ({signal}) | FGI {fgi} | RSI {round(rsi,1)}\n"
        f"Phase: {phase}\n"
        f"{hook}"
    )

    Path("share").mkdir(exist_ok=True)

    Path("daily_post_short.txt").write_text(main_post + "\n", encoding="utf-8")
    Path("daily_share_url.txt").write_text(self_reply + "\n", encoding="utf-8")
    Path("share/daily_post_en.txt").write_text(en_post + "\n", encoding="utf-8")

    print("SNS assets generated (v7.0 Full System)")


if __name__ == "__main__":
    main()
