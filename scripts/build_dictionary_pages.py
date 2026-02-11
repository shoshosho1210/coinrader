#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CoinRader: /dictionary/ (用語集) を静的生成する
- dictionary/index.html   -> /dictionary/
- dictionary/<slug>/index.html -> /dictionary/<slug>

方針:
- canonical は extensionless に統一
- 生成対象は TERMS に定義（20語以上）
"""

from __future__ import annotations

import os
import re
import datetime as dt
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "dictionary"
TEMPL_DIR = ROOT / "templates"

SITE_ORIGIN = os.environ.get("CR_SITE_ORIGIN", "https://coinrader.net").rstrip("/")
LEGACY_ALIAS_DIRS = ["fear-and-greed"]

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
    {
        "slug": "market-cap",
        "ja_title": "時価総額（Market Cap）",
        "ja_desc": "時価総額は、暗号資産プロジェクトの規模感を示す代表指標です。",
        "body_md": """
### ざっくり言うと
時価総額は「現在価格 × 流通枚数」で計算される市場規模です。

### 見方のポイント
- 大きいほど値動きが比較的安定しやすい
- 小さいほど急騰急落しやすい

### CoinRaderでの見方
トップページの **時価総額TOP20** で、規模と値動きを同時に確認できます。
""".strip(),
        "related": ["volume", "dominance", "altcoin-season"],
    },
    {
        "slug": "dominance",
        "ja_title": "ドミナンス（Dominance）",
        "ja_desc": "市場全体の時価総額に占めるBTCやETHの比率。資金の偏りを見る指標です。",
        "body_md": """
### ざっくり言うと
ドミナンスは「市場の主役が誰か」を示します。

### 典型パターン
- BTCドミナンス上昇：資金がBTCに集まりやすい
- BTCドミナンス低下：アルトに資金が回る可能性

### CoinRaderでの見方
市場概況の **Dominance** から、資金の流れを把握できます。
""".strip(),
        "related": ["market-cap", "altcoin-season", "trend"],
    },
    {
        "slug": "support-resistance",
        "ja_title": "サポート/レジスタンス",
        "ja_desc": "価格が反発しやすい下値帯（サポート）と、上値が重くなりやすい帯（レジスタンス）。",
        "body_md": """
### ざっくり言うと
過去に意識された価格帯は、将来も反応しやすい傾向があります。

### 実践のコツ
- 1本の線より「ゾーン」で考える
- 出来高とセットで見る

### CoinRaderでの見方
トレンド指標や出来高ランキングと合わせると、反発/失速の確度が上がります。
""".strip(),
        "related": ["volume", "moving-average", "breakout"],
    },
    {
        "slug": "breakout",
        "ja_title": "ブレイクアウト",
        "ja_desc": "レンジ上限や重要ラインを上抜け/下抜けして、新しい値動きが始まる局面。",
        "body_md": """
### ざっくり言うと
「長く抑えられていた壁」を抜けた瞬間の動きです。

### 判定の目安
- 出来高が伴うか
- だまし（フェイク）で戻されないか

### CoinRaderでの見方
上昇TOPや出来高急増銘柄で、初動の手掛かりを得やすくなります。
""".strip(),
        "related": ["support-resistance", "volume", "trend"],
    },
    {
        "slug": "volatility",
        "ja_title": "ボラティリティ（Volatility）",
        "ja_desc": "価格変動の大きさ。高いほど短期チャンスとリスクの両方が増えます。",
        "body_md": """
### ざっくり言うと
ボラティリティは「どれだけ値が動くか」の指標です。

### 重要ポイント
- 高ボラ：利益機会が増える一方、損失拡大も速い
- 低ボラ：レンジ化しやすい

### CoinRaderでの見方
RSI・Trend・出来高を組み合わせると、過熱相場の見極めに役立ちます。
""".strip(),
        "related": ["rsi", "volume", "atr"],
    },
    {
        "slug": "atr",
        "ja_title": "ATR（Average True Range）",
        "ja_desc": "値幅の平均を使ってボラティリティを測るテクニカル指標です。",
        "body_md": """
### ざっくり言うと
ATRは「最近どれくらい動いたか」を数値化したものです。

### 活用例
- 損切り幅の設計
- 利確目標の目安

### CoinRaderでの見方
出来高やトレンドが強い局面で、リスク管理の基準として使えます。
""".strip(),
        "related": ["volatility", "risk-reward", "stop-loss"],
    },
    {
        "slug": "funding-rate",
        "ja_title": "資金調達率（Funding Rate）",
        "ja_desc": "無期限先物でロング/ショートの偏りを示す指標。過熱感の把握に有効です。",
        "body_md": """
### ざっくり言うと
Funding Rate は、ポジションの偏りによるコストです。

### 典型解釈
- 大きくプラス：ロング過多
- 大きくマイナス：ショート過多

### CoinRaderでの見方
Fear & Greed や RSI と合わせると、逆張り判断の補助になります。
""".strip(),
        "related": ["open-interest", "fear-greed-index", "rsi"],
    },
    {
        "slug": "open-interest",
        "ja_title": "建玉（Open Interest）",
        "ja_desc": "未決済の先物ポジション総量。市場参加の熱量や偏りを表します。",
        "body_md": """
### ざっくり言うと
Open Interest は「現在積み上がっているポジション量」です。

### 見方の例
- 価格上昇＋OI増：トレンド継続の可能性
- 急落＋OI減：ロスカット連鎖の可能性

### CoinRaderでの見方
出来高ランキングと合わせると、急変動の背景理解に役立ちます。
""".strip(),
        "related": ["funding-rate", "volume", "liquidation"],
    },
    {
        "slug": "liquidation",
        "ja_title": "清算（Liquidation）",
        "ja_desc": "証拠金不足でポジションが強制決済されること。急騰急落の引き金になりやすい。",
        "body_md": """
### ざっくり言うと
レバレッジ取引で損失が限度を超えると、強制的にポジションが閉じられます。

### なぜ重要？
- 連鎖清算が起きると値動きが加速する
- 短時間で相場の地合いが反転しやすい

### CoinRaderでの見方
高ボラ・高出来高のタイミングで、急変の背景として意識します。
""".strip(),
        "related": ["open-interest", "volatility", "risk-reward"],
    },
    {
        "slug": "altcoin-season",
        "ja_title": "アルトシーズン",
        "ja_desc": "BTCよりアルトコインが相対的に強くなりやすい局面を指します。",
        "body_md": """
### ざっくり言うと
市場の主役がBTCからアルトへ移るフェーズです。

### 観察ポイント
- BTCドミナンス低下
- 中小型アルトの出来高増

### CoinRaderでの見方
上昇TOPや出来高TOPで、資金循環の変化を追えます。
""".strip(),
        "related": ["dominance", "market-cap", "volume"],
    },
    {
        "slug": "on-chain-data",
        "ja_title": "オンチェーンデータ",
        "ja_desc": "ブロックチェーン上のトランザクションやアクティブアドレスなどの実需指標。",
        "body_md": """
### ざっくり言うと
オンチェーンは「実際の利用状況」を示す生データです。

### 代表指標
- 送金量
- アクティブアドレス
- 手数料推移

### CoinRaderでの見方
テクニカルだけでなく、需給の裏付けを確認する視点として有効です。
""".strip(),
        "related": ["hash-rate", "market-cap", "trend"],
    },
    {
        "slug": "hash-rate",
        "ja_title": "ハッシュレート",
        "ja_desc": "マイニングネットワークの計算力。PoWチェーンの安全性や競争状況を示します。",
        "body_md": """
### ざっくり言うと
ハッシュレートが高いほど、ネットワーク防御力が高い傾向があります。

### 見方
- 長期上昇：マイナー参加が強い
- 急落：採算悪化や設備停止の可能性

### CoinRaderでの見方
長期の市場信頼感を測る補助指標として使えます。
""".strip(),
        "related": ["on-chain-data", "trend"],
    },
    {
        "slug": "staking",
        "ja_title": "ステーキング",
        "ja_desc": "トークンを預けてネットワーク維持に参加し、報酬を得る仕組みです。",
        "body_md": """
### ざっくり言うと
ステーキングは、保有資産をロックして利回りを得る運用方法です。

### 注意点
- ロック期間と解除待ち
- スラッシングなどのリスク

### CoinRaderでの見方
価格変動だけでなく、保有戦略の比較視点として重要です。
""".strip(),
        "related": ["apy", "risk-reward", "market-cap"],
    },
    {
        "slug": "apy",
        "ja_title": "APY（年換算利回り）",
        "ja_desc": "複利を考慮した年換算利回り。ステーキングやDeFiで頻出する指標です。",
        "body_md": """
### ざっくり言うと
APYは「1年でどれだけ増える見込みか」を示します。

### 見るべき点
- 表示利回りの変動性
- 手数料・ロック条件

### CoinRaderでの見方
価格上昇だけに頼らない収益設計を考える際の基礎になります。
""".strip(),
        "related": ["staking", "risk-reward"],
    },
    {
        "slug": "defi",
        "ja_title": "DeFi（分散型金融）",
        "ja_desc": "中央管理者なしで金融サービスを提供するエコシステムの総称。",
        "body_md": """
### ざっくり言うと
DeFiはブロックチェーン上で動く金融アプリ群です。

### 主な領域
- DEX（分散型取引所）
- レンディング
- 流動性提供

### CoinRaderでの見方
市場テーマの一つとして、資金の流入先を把握するのに役立ちます。
""".strip(),
        "related": ["staking", "apy", "gas-fee"],
    },
    {
        "slug": "gas-fee",
        "ja_title": "ガス代（Gas Fee）",
        "ja_desc": "ブロックチェーン取引時に必要な手数料。ネットワーク混雑で変動します。",
        "body_md": """
### ざっくり言うと
ガス代は「取引を通すための実行コスト」です。

### 見方
- 混雑時は高騰しやすい
- 小口取引では利益を圧迫しやすい

### CoinRaderでの見方
短期売買だけでなく、実際の損益を計算するうえで不可欠です。
""".strip(),
        "related": ["defi", "on-chain-data", "risk-reward"],
    },
    {
        "slug": "slippage",
        "ja_title": "スリッページ",
        "ja_desc": "注文価格と約定価格のズレ。流動性が薄いほど発生しやすい。",
        "body_md": """
### ざっくり言うと
思っていた価格で約定できない現象です。

### 発生しやすい場面
- 板が薄い銘柄
- 大口注文
- 急変動時

### CoinRaderでの見方
出来高TOPや流動性の高い銘柄を優先する判断材料になります。
""".strip(),
        "related": ["volume", "gas-fee", "risk-reward"],
    },
    {
        "slug": "stop-loss",
        "ja_title": "損切り（Stop Loss）",
        "ja_desc": "損失拡大を防ぐため、あらかじめ決めた価格で撤退するルール。",
        "body_md": """
### ざっくり言うと
損切りは「生き残るための保険」です。

### 実践ポイント
- エントリー前に撤退ラインを決める
- 感情で動かさない

### CoinRaderでの見方
高ボラ局面では特に、指標より先に損失管理ルールが重要です。
""".strip(),
        "related": ["risk-reward", "atr", "volatility"],
    },
    {
        "slug": "risk-reward",
        "ja_title": "リスクリワード比",
        "ja_desc": "想定利益と想定損失の比率。トレード設計の基本となる考え方です。",
        "body_md": """
### ざっくり言うと
1回の勝ち負けで、どちらが大きい設計かを示します。

### 例
- 期待利益 6%、許容損失 3% → 2:1

### CoinRaderでの見方
AI示唆を鵜呑みにせず、自分の損益設計に落とし込むことが重要です。
""".strip(),
        "related": ["stop-loss", "atr", "trend"],
    },
    {
        "slug": "dca",
        "ja_title": "DCA（ドルコスト平均法）",
        "ja_desc": "価格に関係なく定期的に同額を積み立てる投資法。長期向けの代表戦略。",
        "body_md": """
### ざっくり言うと
DCAは「時間分散」で高値掴みリスクを和らげる手法です。

### 向いている人
- 短期売買に時間を割けない
- 長期で資産形成したい

### CoinRaderでの見方
日々のノイズに振り回されず、トレンド把握の補助として使えます。
""".strip(),
        "related": ["market-cap", "trend", "risk-reward"],
    },
    {
        "slug": "halving",
        "ja_title": "半減期（Halving）",
        "ja_desc": "ビットコインの新規発行量が一定周期で半減するイベント。供給面で注目されます。",
        "body_md": """
### ざっくり言うと
Halvingは、BTCの供給増加ペースが減る仕組みです。

### 注目される理由
- 需給バランスへの影響
- 長期サイクルとの関連

### CoinRaderでの見方
短期指標に加えて、長期テーマの背景として把握しておくと有効です。
""".strip(),
        "related": ["bitcoin-etf", "hash-rate", "market-cap"],
    },
    {
        "slug": "bitcoin-etf",
        "ja_title": "ビットコインETF",
        "ja_desc": "証券口座からビットコイン価格へアクセスできる金融商品。機関資金流入の観点で重要。",
        "body_md": """
### ざっくり言うと
ETFは、現物を直接扱わずにBTC価格へ投資できる仕組みです。

### 注目ポイント
- 資金流入/流出の規模
- 既存金融市場との連動

### CoinRaderでの見方
短期の値動きだけでなく、中長期の需給変化を見る視点として使えます。
""".strip(),
        "related": ["halving", "market-cap", "dominance"],
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
    for alias in LEGACY_ALIAS_DIRS:
        alias_dir = OUT_DIR / alias
        if alias_dir.exists():
            shutil.rmtree(alias_dir)

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
