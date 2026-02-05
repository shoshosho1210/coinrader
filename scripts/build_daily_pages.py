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

2026-02: JSON構造が
  {
    "summary": {
      "date": "YYYY-MM-DD",
      "status": "分析: ...",
      ...
    },
    ...
  }
の形に変更された前提に追従しています。

この差し替え版では:
- sitemap.xml の /daily/ 配下URLを「リッチ形式（lastmod等付き）」で統一して毎回書き換える
  （混在や “1件だけlastmod無し” を防ぐ）
"""

from __future__ import annotations

import os
import re
import json
import glob
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ----------------------------
# Paths / Constants
# ----------------------------
ROOT = Path(__file__).resolve().parents[1]  # scripts/ の1つ上をルートと想定
DATA_DIR = ROOT / "data" / "daily"
OUT_DIR = ROOT / "daily"
TEMPL_DIR = ROOT / "templates"

SITE_ORIGIN = os.environ.get("SITE_ORIGIN", "https://coinrader.net").rstrip("/")


# ----------------------------
# Helpers
# ----------------------------
def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def read_text_optional(paths: List[Path]) -> str:
    for p in paths:
        if p.exists():
            return read_text(p)
    raise FileNotFoundError("None of the optional template files exist: " + ", ".join(str(x) for x in paths))


def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def escape_html(s: str) -> str:
    s = s or ""
    return (s.replace("&", "&amp;")
              .replace("<", "&lt;")
              .replace(">", "&gt;")
              .replace('"', "&quot;")
              .replace("'", "&#39;"))


def escape_xml(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")


def get_path(obj: Any, path: str, default: Any = None) -> Any:
    """dict のネストを 'a.b.c' で安全に取得"""
    cur = obj
    for k in path.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def fmt_pct(v: Any, digits: int = 2) -> str:
    try:
        x = float(v)
        return f"{x:.{digits}f}%"
    except Exception:
        return ""


def fmt_num(v: Any, digits: int = 2) -> str:
    try:
        x = float(v)
        return f"{x:.{digits}f}"
    except Exception:
        return ""


def pick_tag(status: str) -> str:
    """
    summary.status から簡易タグを返す（bear/bull/wait）
    - 例: "分析: 悲観 / 売られすぎ" -> bear
    """
    s = (status or "").lower()
    if any(k in s for k in ["悲観", "売られすぎ", "weak", "bear", "下落", "恐怖"]):
        return "bear"
    if any(k in s for k in ["楽観", "買われすぎ", "strong", "bull", "上昇", "強気"]):
        return "bull"
    return "wait"


def chips_html(dated: List[str]) -> str:
    """
    index.html 用のチップ（リンク）を生成
    """
    parts = []
    for ymd in reversed(sorted(set(dated))):
        mmdd = ymd[4:6] + "/" + ymd[6:8]
        href = f"{ymd}.html"
        inner = f"<small>{mmdd}</small>"
        parts.append(f"<a class='chip' href='{href}'>{inner}</a>")
    return "\n      ".join(parts)


# ----------------------------
# Sitemap (daily block rewrite)
# ----------------------------
def build_daily_sitemap_entries(
    site_origin: str,
    dated: List[str],
    include_root: bool = True,
) -> List[Dict[str, str]]:
    """
    daily系の sitemap エントリを「リッチ形式」で生成する。
    - /daily/ （一覧の導線として入れる場合）
    - /daily/index.html
    - /daily/latest.html
    - /daily/tags/*
    - /daily/YYYYMMDD.html
    """
    entries: List[Dict[str, str]] = []
    dated_u = sorted({d for d in dated if d}, reverse=True)
    latest_ymd = dated_u[0] if dated_u else ""
    latest_iso = ""
    if latest_ymd:
        try:
            latest_iso = datetime.datetime.strptime(latest_ymd, "%Y%m%d").strftime("%Y-%m-%d")
        except Exception:
            latest_iso = ""

    def add(loc: str, lastmod: str = "", changefreq: str = "", priority: str = "") -> None:
        loc = (loc or "").strip()
        if not loc:
            return
        e: Dict[str, str] = {"loc": loc}
        if lastmod:
            e["lastmod"] = lastmod
        if changefreq:
            e["changefreq"] = changefreq
        if priority:
            e["priority"] = priority
        entries.append(e)

    # /daily/（ディレクトリ）も sitemap に入れたい場合
    if include_root and latest_iso:
        add(f"{site_origin}/daily/", lastmod=latest_iso, changefreq="daily", priority="0.9")

    # 固定ページ群（lastmod は最新日に寄せる）
    if latest_iso:
        add(f"{site_origin}/daily/index.html", lastmod=latest_iso, changefreq="daily", priority="0.9")
        add(f"{site_origin}/daily/latest.html", lastmod=latest_iso, changefreq="daily", priority="0.9")

        add(f"{site_origin}/daily/tags/bear.html", lastmod=latest_iso, changefreq="daily", priority="0.7")
        add(f"{site_origin}/daily/tags/bull.html", lastmod=latest_iso, changefreq="daily", priority="0.7")
        add(f"{site_origin}/daily/tags/wait.html", lastmod=latest_iso, changefreq="daily", priority="0.7")

        # 互換用（拡張子なし/末尾スラッシュあり）
        add(f"{site_origin}/daily/tags/bear", lastmod=latest_iso, changefreq="daily", priority="0.6")
        add(f"{site_origin}/daily/tags/bull", lastmod=latest_iso, changefreq="daily", priority="0.6")
        add(f"{site_origin}/daily/tags/wait", lastmod=latest_iso, changefreq="daily", priority="0.6")
        add(f"{site_origin}/daily/tags/bear/", lastmod=latest_iso, changefreq="daily", priority="0.6")
        add(f"{site_origin}/daily/tags/bull/", lastmod=latest_iso, changefreq="daily", priority="0.6")
        add(f"{site_origin}/daily/tags/wait/", lastmod=latest_iso, changefreq="daily", priority="0.6")

    # 日次ページ（lastmod は各日付）
    for ymd in dated_u:
        iso = ""
        try:
            iso = datetime.datetime.strptime(ymd, "%Y%m%d").strftime("%Y-%m-%d")
        except Exception:
            iso = ""
        add(f"{site_origin}/daily/{ymd}.html", lastmod=iso, changefreq="daily", priority="0.8")

    return entries


def rewrite_sitemap_with_daily_block(sitemap_path: Path, daily_entries: List[Dict[str, str]]) -> None:
    """
    既存 sitemap.xml を保ちつつ、/daily/配下のURLはこのスクリプトが生成した
    “リッチ形式”で必ず統一して上書きする。
    """
    if not daily_entries:
        return

    def url_xml(e: Dict[str, str]) -> str:
        loc = escape_xml(str(e.get("loc", "")).strip())
        if not loc:
            return ""
        parts = ["  <url>", f"    <loc>{loc}</loc>"]
        if e.get("lastmod"):
            parts.append(f"    <lastmod>{escape_xml(e['lastmod'])}</lastmod>")
        if e.get("changefreq"):
            parts.append(f"    <changefreq>{escape_xml(e['changefreq'])}</changefreq>")
        if e.get("priority"):
            parts.append(f"    <priority>{escape_xml(e['priority'])}</priority>")
        parts.append("  </url>")
        return "\n".join(parts)

    daily_xml = "\n".join([x for x in (url_xml(e) for e in daily_entries) if x]) + "\n"
    header = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    footer = "</urlset>\n"

    if not sitemap_path.exists():
        write_text(sitemap_path, header + daily_xml + footer)
        return

    xml = read_text(sitemap_path)

    # /daily/ 配下の <url>…</url> を全部除去して、dailyブロックを差し込む
    xml_no_daily = re.sub(
        r"\s*<url>\s*(?:<[^>]+>\s*)*?<loc>\s*https?://[^<]*/daily/[^<]*\s*</loc>[\s\S]*?</url>\s*",
        "\n",
        xml,
        flags=re.IGNORECASE,
    )
    # 連続する空行を潰して整形（見た目とdiff安定化）
    xml_no_daily = re.sub(r"\n{3,}", "\n\n", xml_no_daily)

    if "<urlset" not in xml_no_daily:
        # 壊れている/異形式の場合は、dailyだけでも正しい形式で再生成
        write_text(sitemap_path, header + daily_xml + footer)
        return

    if "</urlset>" in xml_no_daily:
        out = re.sub(r"</urlset>\s*$", daily_xml + "</urlset>\n", xml_no_daily, flags=re.IGNORECASE)
    else:
        out = xml_no_daily.rstrip() + "\n" + daily_xml

    write_text(sitemap_path, out)


# ----------------------------
# Main
# ----------------------------
def main() -> None:
    tmpl = read_text(TEMPL_DIR / "daily_template.html")
    tmpl_index = read_text_optional([
        TEMPL_DIR / "daily_index.html",
        TEMPL_DIR / "daily_index_template.html",
    ])
    tmpl_latest = read_text(TEMPL_DIR / "latest_template.html")

    files = sorted(glob.glob(str(DATA_DIR / "*.json")))
    dated: List[str] = []
    for f in files:
        name = Path(f).stem
        if re.fullmatch(r"\d{8}", name):
            dated.append(name)
    dated = sorted(set(dated))

    if not dated:
        raise RuntimeError("No daily JSON found under data/daily/*.json")

    pages: List[Dict[str, Any]] = []
    for ymd in reversed(dated):
        json_path = DATA_DIR / f"{ymd}.json"
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}

        date_iso = get_path(payload, "summary.date", default="")
        if not date_iso:
            try:
                date_iso = datetime.datetime.strptime(ymd, "%Y%m%d").strftime("%Y-%m-%d")
            except Exception:
                date_iso = ymd

        status = get_path(payload, "summary.status", default="")
        sentiment = get_path(payload, "summary.sentiment", default="")
        btc_rsi = get_path(payload, "summary.btc_rsi", default="")
        focus = get_path(payload, "summary.focus", default="")

        tag = pick_tag(str(status))

        # テンプレ差し込み
        html = tmpl
        html = html.replace("{{DATE_ISO}}", escape_html(str(date_iso)))
        html = html.replace("{{DATE_YMD}}", escape_html(str(ymd)))
        html = html.replace("{{STATUS}}", escape_html(str(status)))
        html = html.replace("{{SENTIMENT}}", escape_html(fmt_num(sentiment, 0) if sentiment != "" else ""))
        html = html.replace("{{BTC_RSI}}", escape_html(fmt_num(btc_rsi, 2) if btc_rsi != "" else ""))
        html = html.replace("{{FOCUS}}", escape_html(str(focus)))
        html = html.replace("{{TAG}}", escape_html(tag))

        # ★ build marker
        html = html.replace("</body>", f"<!-- build:{ymd} -->\n</body>", 1)

        out_path = OUT_DIR / f"{ymd}.html"
        write_text(out_path, html)

        pages.append({
            "ymd": ymd,
            "date_iso": date_iso,
            "tag": tag,
        })

    latest_ymd = pages[0]["ymd"] if pages else dated[-1]

    # index.html（一覧）
    index_html = tmpl_index
    index_html = index_html.replace("{{CHIPS}}", chips_html(dated))
    index_html = index_html.replace("{{LATEST_YMD}}", escape_html(str(latest_ymd)))
    index_html = index_html.replace("{{LATEST_DATE}}", escape_html(str(pages[0]["date_iso"] if pages else "")))

    # ★ build marker
    index_html = index_html.replace("</body>", f"<!-- build:{latest_ymd} -->\n</body>", 1)

    write_text(OUT_DIR / "index.html", index_html)

    # tags
    tags_dir = OUT_DIR / "tags"
    tags_dir.mkdir(parents=True, exist_ok=True)

    tags = ["bear", "bull", "wait"]
    for tag in tags:
        tag_lower = tag.lower()

        # /daily/tags/{tag}.html を作る（テンプレが無い場合は index をベースに簡易生成）
        tag_html = index_html
        tag_html = tag_html.replace("{{TITLE}}", f"Daily - {tag_upper(tag_lower)}", 1) if "{{TITLE}}" in tag_html else tag_html

        # 一覧のチップをフィルタ
        filtered = [p["ymd"] for p in pages if p.get("tag") == tag_lower]
        tag_html = tag_html.replace("{{CHIPS}}", chips_html(filtered))

        # head title を上書き（存在する場合）
        tag_html = tag_html.replace("<title>Daily</title>", f"<title>Daily - {tag_lower}</title>", 1)

        # ★ build marker
        tag_html = tag_html.replace("</body>", f"<!-- build:{latest_ymd} -->\n</body>", 1)

        out_path_html = tags_dir / f"{tag_lower}.html"
        write_text(out_path_html, tag_html)

        # 互換: /daily/tags/{tag} をファイルとして読む環境向け（必要なら）
        write_text(tags_dir / tag_lower, tag_html)

    # latest.html（最新ページへのリンク差し替え）
    latest_target = f"{latest_ymd}.html"
    latest_html = tmpl_latest.replace("{{LATEST_HREF}}", latest_target)
    latest_html = latest_html.replace("{{LATEST_DATE}}", pages[0]["date_iso"] if pages else "")
    write_text(OUT_DIR / "latest.html", latest_html)

    # sitemap.xml（/daily/配下はこのスクリプトで統一上書き）
    daily_entries = build_daily_sitemap_entries(SITE_ORIGIN, dated, include_root=True)
    rewrite_sitemap_with_daily_block(ROOT / "sitemap.xml", daily_entries)

    print(f"[OK] Generated {len(pages)} pages into: {OUT_DIR} (latest={latest_target})")


def tag_upper(tag: str) -> str:
    return (tag or "").upper()


if __name__ == "__main__":
    main()
