#!/bin/bash
# run_example.sh — 【合成示例】端到端演示（非正式案例结果）。
# 用法：bash examples/run_example.sh [临时根目录]
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
ROOT="${1:-$(mktemp -d /tmp/kbqa-ingest-demo.XXXXXX)}"
echo "== 合成示例根目录: $ROOT"
python3 "$HERE/make_fixture.py" "$ROOT"
mkdir -p "$ROOT/work" "$ROOT/output"

echo "== 1) forensic_scan"
python3 "$SKILL/scripts/forensic_scan.py" --input "$ROOT/input" --work "$ROOT/work" --out "$ROOT/output"

echo "== 2) lineage"
python3 "$SKILL/scripts/lineage.py" --work "$ROOT/work" --out "$ROOT/output"

echo "== 3) catalog_check"
python3 "$SKILL/scripts/catalog_check.py" --input "$ROOT/input" --work "$ROOT/work" --out "$ROOT/output"

echo "== 产物清单"
ls "$ROOT/output"
echo "== catalog_report.md"
cat "$ROOT/output/catalog_report.md"
echo "== DONE (合成示例，输出为虚构数据)"
