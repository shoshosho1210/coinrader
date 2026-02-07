#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CoinRader: /dictionary/ (用語集) を静的生成する
- dictionary/index.html   -> /dictionary/
- dictionary/<slug>/index.html -> /dictionary/<slug>

方針:
- canonical は extensionless に統一
- 生成対象は TERMS に定義（まずは5語）
"""

from __future__ import annotations

import os
import re
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "dictionary"
TEMPL_DIR = ROOT / "templates"

SITE_ORIGIN = os.environ.get("CR_SITE_ORIGIN", "https://coinrader.net").rstrip("/")


TERMS = [
    {
        "slug": "rsi",
        "ja_title": "RSI",
        "ja_desc": "RSI（相対力指数）は、買われ過ぎ・売られ過ぎを判断する代表的なオシレーター指標です。",
        "body_md": """
### ざっくり言うと
RSI は「一定期間の上げ下げの勢い」を 0〜100 で表します。

### 目安
- **70以上**：買われ過ぎ（反落リスク）
- **30以下**：売られ過ぎ（反発余地）

### CoinRaderでの見方
Dailyページの **BTC RSI** を見て、過熱/売られ過ぎを一瞬で判断できます。
""".strip(),
        "related": ["fear-greed-index", "moving-average", "volume"],
    },
    {
        "slug": "fear-greed-index",
        "ja_title": "Fear & Greed Index（恐怖指数）",
        "ja_desc": "市場の心理状態（恐怖/強欲）を数値化した指標。極端値は反転のヒントになります。",
        "body_md": """
### ざっくり言うと
市場が「怖がっているか」「楽観しているか」を数値化します。

### 目安（一般的）
- **0〜24**：Extreme Fear（悲観が強い）
- **75〜100**：Extreme Greed（過熱）

### CoinRaderでの見方
Dailyページの **FGI** を、RSIやTrendとセットで確認します。
""".strip(),
        "related": ["rsi", "trend", "moving-average"],
    },
    {
        "slug": "moving-average",
        "ja_title": "移動平均（MA）",
        "ja_desc": "価格の平均を滑らかにして、トレンドの方向や勢いを把握する指標です。",
        "body_md": """
### ざっくり言うと
移動平均は「トレンドの地形図」です。

### よくある見方
- 価格がMAより上：上向き基調
- 価格がMAより下：下向き基調
- 短期MAと長期MAの交差：トレンド転換の合図になりやすい

### CoinRaderでの見方
Dailyの **Trend（MA距離）** を見ると、上/下方向の圧力を定量で把握できます。
""".strip(),
        "related": ["trend", "rsi"],
    },
    {
        "slug": "volume",
        "ja_title": "出来高（Volume）",
        "ja_desc": "取引がどれだけ活発かを示す指標。上昇/下落の“納得感”に関わります。",
        "body_md": """
### ざっくり言うと
出来高は「その値動きにどれだけ参加者がいるか」です。

### よくある考え方
- 上昇＋出来高増：上昇が“本物”になりやすい
- 上昇＋出来高減：上昇が“薄い”可能性
- 急落＋出来高増：投げ売り/強制清算などの可能性

### CoinRaderでの見方
ダッシュボードの出来高系ランキングで、今どこが動いているかを素早く把握できます。
""".strip(),
        "related": ["trend"],
    },
    {
        "slug": "trend",
        "ja_title": "Trend（CoinRaderのトレンド指標）",
        "ja_desc": "CoinRaderのDailyにあるTrendは、MA距離などから“地合い”を把握するための数値です。",
        "body_md": """
### ざっくり言うと
Trendは、相場の“追い風/向かい風”をざっくり掴むための指標です。

### CoinRaderでの見方
FGI（心理）/ RSI（過熱）/ Trend（地合い）をセットで見て、AI判定の背景を理解します。
""".strip(),
        "related": ["moving-average", "fear-greed-index", "rsi"],
    },
]


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def escape_html(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") \
                    .replace('"', "&quot;").replace("'", "&#39;")


def md_to_html(md: str) -> str:
    # 超軽量：見出し/箇条書き/改行のみ最低限
    lines = (md or "").splitlines()
    out = []
    in_ul = False
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            if in_ul:
                out.append("</ul>")
                in_ul = False
            continue
        if line.startswith("### "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h3>{escape_html(line[4:].strip())}</h3>")
            continue
        if line.startswith("- "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{escape_html(line[2:].strip())}</li>")
            continue
        # paragraph
        if in_ul:
            out.append("</ul>")
            in_ul = False
        out.append(f"<p>{escape_html(line.strip())}</p>")
    if in_ul:
        out.append("</ul>")
    return "\n".join(out)


def iso_today() -> str:
    return dt.datetime.utcnow().date().isoformat()


def main() -> None:
    tmpl_term = read_text(TEMPL_DIR / "dictionary_term.html")
    tmpl_index = read_text(TEMPL_DIR / "dictionary_index.html")

    # index rows
    rows = []
    for t in TERMS:
        slug = t["slug"]
        title = t["ja_title"]
        desc = t["ja_desc"]
        rows.append(
            f"<a class='card' href='/dictionary/{escape_html(slug)}'>"
            f"<div class='card-title'>{escape_html(title)}</div>"
            f"<div class='card-desc'>{escape_html(desc)}</div>"
            f"</a>"
        )
    index_html = tmpl_index.replace("{{ROWS}}", "\n".join(rows))
    index_html = index_html.replace("{{LASTMOD}}", iso_today())
    index_html = index_html.replace("{{CANONICAL}}", f"{SITE_ORIGIN}/dictionary/")
    write_text(OUT_DIR / "index.html", index_html)

    # term pages
    for t in TERMS:
        slug = t["slug"]
        title = t["ja_title"]
        desc = t["ja_desc"]
        canonical = f"{SITE_ORIGIN}/dictionary/{slug}"
        body_html = md_to_html(t.get("body_md", ""))

        # related
        rel = []
        for rslug in (t.get("related") or []):
            rt = next((x for x in TERMS if x["slug"] == rslug), None)
            if not rt:
                continue
            rel.append(
                f"<a class='chip' href='/dictionary/{escape_html(rslug)}'>{escape_html(rt['ja_title'])}</a>"
            )
        rel_html = ("".join(rel)) if rel else ""

        html = tmpl_term
        html = html.replace("{{TITLE}}", escape_html(title))
        html = html.replace("{{DESCRIPTION}}", escape_html(desc))
        html = html.replace("{{CANONICAL}}", escape_html(canonical))
        html = html.replace("{{H1}}", escape_html(title))
        html = html.replace("{{BODY}}", body_html)
        html = html.replace("{{RELATED}}", rel_html)
        html = html.replace("{{LASTMOD}}", iso_today())

        out = OUT_DIR / slug / "index.html"
        write_text(out, html)

    print(f"[OK] dictionary pages generated: {OUT_DIR} (count={len(TERMS)})")


if __name__ == "__main__":
    main()
