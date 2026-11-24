#!/usr/bin/env bash
# run_example.sh — 合成示例：非交互全流程（生成案例→prepare→填 plan→finish）
# 一切产物写入 mktemp 临时目录，绝不写回 bundle。
set -euo pipefail

S="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d /tmp/render-proof-demo.XXXXXX)"
mkdir -p "$T/input" "$T/work" "$T/output"
echo "== 临时目录: $T =="

echo "-- 1/4 生成合成案例 --"
python3 "$S/scripts/make_synthetic_case.py" --out "$T/input"

echo "-- 2/4 prepare（抽取 + partial-first） --"
python3 "$S/scripts/run_case.py" prepare --input "$T/input" --work "$T/work" --output "$T/output"

echo "-- 3/4 自动填 plan（含故意过载页） --"
python3 "$S/scripts/fill_example_plan.py" --work "$T/work"

echo "-- 4/4 finish（构建→渲染→像素QA→自动修复闭环） --"
python3 "$S/scripts/run_case.py" finish --input "$T/input" --work "$T/work" --output "$T/output"

echo
echo "== 产物清单（$T/output） =="
ls -la "$T/output"
echo "-- preview 页数: $(ls "$T/output"/preview/slide-*.png 2>/dev/null | wc -l) --"
echo "-- render_proof.json 摘要 --"
python3 - "$T/output/render_proof.json" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))
print("overall:", p["overall"], "| runs:", p["run"],
      "| page_count:", p["page_count"], "| fonts:", p["fonts"]["status"])
print("fix_log entries:", len(p["fix_log"]))
for f in p["fix_log"]:
    print("  -", f.get("type"), f"it{f.get('iteration')}", f"p{f.get('page')}:",
          f.get("detail", "")[:90])
PY
echo
echo "== 完成。临时目录保留供检查：$T（用完可 rm -rf） =="
