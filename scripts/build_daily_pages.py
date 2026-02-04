#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CoinRader: data/daily/*.json から daily/ 配下のHTMLを自動生成します。
- daily/YYYYMMDD.html
- daily/index.html (一覧)
- daily/latest.html (最新へのリダイレクト)

前提:
- JSONファイル名: data/daily/20260204.json のように8桁日付
- JSON内に必要キーが無い場合でも、落ちないようにフォールバックします。
"""
from __future__ import annotations
import os, re, json, glob, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # repo root想定: scripts/ の1つ上
DATA_DIR = ROOT / "data" / "daily"
OUT_DIR  = ROOT / "daily"
TEMPL_DIR = ROOT / "templates"

SITE_ORIGIN = os.environ.get("CR_SITE_ORIGIN", "https://coinrader.net").rstrip("/")
TZ_NAME = "JST"

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")

def load_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def yyyymmdd_to_iso(yyyymmdd: str) -> str:
    return f"{yyyymmdd[0:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"

def build_jsonld(date_iso: str, canonical: str, title: str, desc: str) -> str:
    # Article + Breadcrumb (最小)
    obj = [
      {
        "@context":"https://schema.org",
        "@type":"BreadcrumbList",
        "itemListElement":[
          {"@type":"ListItem","position":1,"name":"CoinRader","item":f"{SITE_ORIGIN}/"},
          {"@type":"ListItem","position":2,"name":"Daily","item":f"{SITE_ORIGIN}/daily/"},
          {"@type":"ListItem","position":3,"name":date_iso,"item":canonical},
        ]
      },
      {
        "@context":"https://schema.org",
        "@type":"Article",
        "headline": title,
        "datePublished": date_iso,
        "dateModified": date_iso,
        "mainEntityOfPage": canonical,
        "publisher": {"@type":"Organization","name":"CoinRader"},
        "description": desc
      }
    ]
    return json.dumps(obj, ensure_ascii=False)

def safe_get(d: dict, *keys, default=""):
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur if cur is not None else default

def build_reason_html(payload: dict) -> str:
    # 可能なら JSON内の説明テキストを使い、無ければ数値から簡易生成
    # （キー名は将来変わっても良いように、いくつか探す）
    reasons = []
    for path in [
        ("ai","reasons"),
        ("ai","reason_lines"),
        ("ai","bullets"),
        ("insight","reasons"),
    ]:
        v = safe_get(payload, *path, default=None)
        if isinstance(v, list) and v:
            reasons = [str(x) for x in v if str(x).strip()]
            break

    if not reasons:
        sent = safe_get(payload, "sentiment", default=safe_get(payload,"fear_greed",default=""))
        rsi  = safe_get(payload, "btc_rsi", default=safe_get(payload,"rsi",default=""))
        trend = safe_get(payload, "trend", default="")
        # 最低限の“読める文章”
        if sent != "":
            try:
                s = float(sent)
                if s < 25: reasons.append(f"Fear & Greed が {sent} で極端に低く、市場心理は悲観に傾いています。")
                elif s < 45: reasons.append(f"Fear & Greed が {sent} で弱気寄りです。")
                else: reasons.append(f"Fear & Greed が {sent} で中立〜強気寄りです。")
            except: pass
        if rsi != "":
            try:
                x = float(rsi)
                if x < 30: reasons.append(f"BTC RSI が {rsi} で売られすぎ圏です。")
                elif x > 70: reasons.append(f"BTC RSI が {rsi} で買われすぎ圏です。")
                else: reasons.append(f"BTC RSI は {rsi} で中立圏です。")
            except: pass
        if trend != "":
            reasons.append(f"トレンド指標は「{trend}」です。")
        if not reasons:
            reasons.append("日次データから総合判断を生成しています。")

    return "\n".join([f"<p>{escape_html(line)}</p>" for line in reasons])

def escape_html(s: str) -> str:
    return (s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
             .replace('"',"&quot;").replace("'","&#39;"))

def main():
    tmpl = read_text(TEMPL_DIR / "daily_template.html")
    tmpl_index = read_text(TEMPL_DIR / "daily_index_template.html")
    tmpl_latest = read_text(TEMPL_DIR / "latest_template.html")

    files = sorted(glob.glob(str(DATA_DIR / "*.json")))
    dated = []
    for f in files:
        name = Path(f).stem
        if re.fullmatch(r"\d{8}", name):
            dated.append(name)

    dated = sorted(set(dated))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    latest = dated[-1] if dated else None

    for ymd in reversed(dated):
        p = DATA_DIR / f"{ymd}.json"
        payload = load_json(p)

        date_iso = yyyymmdd_to_iso(ymd)
        canonical = f"{SITE_ORIGIN}/daily/{ymd}.html"

        # 値の取り出し（将来キーが変わっても落ちないように）
        judge = safe_get(payload, "ai_judge", default=safe_get(payload,"ai", "judge", default="WAIT"))
        sent = safe_get(payload, "sentiment", default=safe_get(payload,"fear_greed", default=""))
        rsi  = safe_get(payload, "btc_rsi", default=safe_get(payload,"rsi", default=""))
        trend = safe_get(payload, "trend", default=safe_get(payload,"ai","trend", default=""))

        updated_at = safe_get(payload, "updated_at", default=safe_get(payload,"timestamp", default=""))
        if not updated_at:
            updated_at = f"{date_iso} 09:00"

        title = f"BTC AI分析（{date_iso}） | CoinRader"
        desc = f"{date_iso}のCoinRader日次AIレポート。Fear & Greed={sent}、BTC RSI={rsi}、Trend={trend} をもとに総合判断を提示します。".strip()
        jsonld = build_jsonld(date_iso, canonical, title, desc)
        why_html = build_reason_html(payload)

        html = tmpl
        repl = {
            "{{TITLE}}": title,
            "{{DESCRIPTION}}": desc,
            "{{CANONICAL}}": canonical,
            "{{OG_TITLE}}": title,
            "{{OG_DESCRIPTION}}": desc,
            "{{DATE}}": date_iso,
            "{{H1}}": f"BTC AI分析（{date_iso}）",
            "{{UPDATED_AT}}": str(updated_at),
            "{{JUDGE}}": escape_html(str(judge)),
            "{{SENTIMENT_VALUE}}": escape_html(str(sent)),
            "{{BTC_RSI}}": escape_html(str(rsi)),
            "{{TREND}}": escape_html(str(trend)),
            "{{WHY_HTML}}": why_html,
            "{{JSONLD}}": jsonld,
        }
        for k,v in repl.items():
            html = html.replace(k, v)

        out_path = OUT_DIR / f"{ymd}.html"
        write_text(out_path, html)

        rows.append(
            f'<div class="row"><div><div class="date"><a href="/daily/{ymd}.html">{date_iso}</a></div>'
            f'<div class="meta">AI JUDGE: {escape_html(str(judge))}</div></div>'
            f'<div class="meta">F&G {escape_html(str(sent))} / RSI {escape_html(str(rsi))}</div></div>'
        )

    # index.html
    index_html = tmpl_index.replace("{{ROWS}}", "\n".join(rows) if rows else '<div class="row"><div class="date">まだ日次データがありません</div></div>')
    write_text(OUT_DIR / "index.html", index_html)

    # latest.html
    latest_url = f"/daily/{latest}.html" if latest else "/"
    latest_html = tmpl_latest.replace("{{LATEST_URL}}", latest_url)
    write_text(OUT_DIR / "latest.html", latest_html)

    print(f"[ok] generated: {len(dated)} pages, latest={latest}")

if __name__ == "__main__":
    main()
