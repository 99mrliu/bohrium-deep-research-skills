#!/usr/bin/env bash
# gated-pipeline-deck 端到端示例（合成示例）。全部产物写入 $(mktemp -d)，绝不写回 bundle。
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
IN="$TMP/input"; WK="$TMP/work"; OUT="$TMP/output"
mkdir -p "$IN" "$WK" "$OUT"
echo "== tmpdir: $TMP"

echo; echo "== [0] 生成合成案例（synthetic demo）"
python3 "$SKILL_DIR/scripts/make_synthetic_case.py" --out "$IN"

echo; echo "== [1] prepare: S0-S4（读输入/抽取/解剖模板/预填 plan；立即写 partial result.json）"
python3 "$SKILL_DIR/scripts/run_case.py" prepare --input "$IN" --work "$WK" --output "$OUT"

echo; echo "== [1b] 校验 partial result.json（模拟 prepare 后被杀：output 必须是合法 partial）"
python3 - "$OUT/result.json" <<'PYEOF'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
need = ["case_id", "status", "summary", "artifacts", "evidence_map",
        "sources", "uncertainty", "change_log"]
missing = [f for f in need if f not in r]
assert not missing, f"缺字段: {missing}"
assert r["status"] == "partial", f"status 应为 partial，实际 {r['status']}"
assert r["case_id"] == "synthetic-demo-04"
print("PARTIAL-OK: result.json 可解析，contract 字段齐全，status=partial")
PYEOF

echo; echo "== [2] 自动填 plan（真实运行中此步由 Agent 编辑 slide_plan.json）"
python3 "$SKILL_DIR/scripts/fill_example_plan.py" --work "$WK"

echo; echo "== [3] finish: S5-S9（plan-gate / build / export / qa-gate / finalize）"
python3 "$SKILL_DIR/scripts/run_case.py" finish --input "$IN" --work "$WK" --output "$OUT"

echo; echo "== [4] 断点续跑演示: 删除 S6-S9 检查点后重跑 finish"
echo "    预期: S0-S5 打印 'skip Sn (checkpoint valid)'，S6-S9 重新执行"
rm -f "$WK/checkpoints/S6.json" "$WK/checkpoints/S7.json" \
      "$WK/checkpoints/S8.json" "$WK/checkpoints/S9.json"
python3 "$SKILL_DIR/scripts/run_case.py" finish --input "$IN" --work "$WK" --output "$OUT"

echo; echo "== [5] status 汇总"
python3 "$SKILL_DIR/scripts/run_case.py" status --input "$IN" --work "$WK" --output "$OUT"

echo; echo "== [6] 产物清单（$OUT）"
find "$OUT" -type f | sort | sed "s|^$OUT/|  |"

echo; echo "== [7] qa_gates.json"
cat "$OUT/qa_gates.json"

echo; echo "EXAMPLE-DONE tmpdir=$TMP"
