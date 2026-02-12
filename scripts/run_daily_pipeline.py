#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CoinRader: 日次パイプライン（一括実行スクリプト）

毎日の更新フローを1コマンドで実行する。
  1. CoinGecko API からコインスナップショット取得
  2. Daily AI レポートページ生成
  3. Coin ページ再生成
  4. Compare ページ再生成
  5. Sitemap 更新

使い方:
  python scripts/run_daily_pipeline.py          # 全ステップ実行
  python scripts/run_daily_pipeline.py --skip-fetch  # データ取得をスキップ
"""

from __future__ import annotations

import sys
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run_step(label: str, cmd: list[str]) -> bool:
    """1ステップ実行して成否を返す"""
    print(f"\n{'='*60}")
    print(f"▶ {label}")
    print(f"{'='*60}")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.time() - t0
    ok = result.returncode == 0
    status = "✅ OK" if ok else "❌ FAIL"
    print(f"  {status} ({elapsed:.1f}s)")
    return ok


def main() -> None:
    skip_fetch = "--skip-fetch" in sys.argv

    steps: list[tuple[str, list[str]]] = []

    if not skip_fetch:
        steps.append((
            "Step 1: CoinGecko データ取得",
            [sys.executable, str(SCRIPTS / "fetch_coin_snapshots.py")],
        ))

    steps.extend([
        (
            "Step 2: Daily AI レポート生成",
            [sys.executable, str(SCRIPTS / "build_daily_pages.py")],
        ),
        (
            "Step 3: Coin ページ再生成",
            [sys.executable, str(SCRIPTS / "build_coin_pages.py")],
        ),
        (
            "Step 4: Compare ページ再生成",
            [sys.executable, str(SCRIPTS / "build_compare_pages.py")],
        ),
        (
            "Step 5: Sitemap 更新",
            [sys.executable, str(SCRIPTS / "build_split_sitemaps.py")],
        ),
    ])

    results: list[tuple[str, bool]] = []
    for label, cmd in steps:
        ok = run_step(label, cmd)
        results.append((label, ok))
        if not ok:
            print(f"\n⚠️ {label} failed — stopping pipeline.")
            break

    print(f"\n{'='*60}")
    print("📋 パイプライン結果:")
    print(f"{'='*60}")
    for label, ok in results:
        print(f"  {'✅' if ok else '❌'} {label}")

    failed = sum(1 for _, ok in results if not ok)
    if failed:
        print(f"\n❌ {failed} step(s) failed.")
        sys.exit(1)
    else:
        print(f"\n✅ All {len(results)} steps completed successfully!")


if __name__ == "__main__":
    main()
