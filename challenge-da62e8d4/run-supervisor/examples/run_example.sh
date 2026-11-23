#!/usr/bin/env bash
# 合成示例（synthetic），非正式案例结果。
# 完整演示 run-supervisor 全周期：init -> phase 登记 -> run 两候选（一成功一崩溃）
# -> status -> 填写 result.json 合约字段 -> finalize（预期判定 partial 且 lint PASS）。
#
# 用法：bash run_example.sh [输出根目录]
#   输出根目录默认 <本脚本目录>/output；测试时应指向 bundle 之外，例如：
#   bash run_example.sh /path/to/selftest/run-supervisor/example
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUPERVISOR="$HERE/../scripts/supervisor.py"
INPUT="$HERE/input"
ROOT="${1:-$HERE/output}"          # 输出根目录
WORK="$ROOT/work"                  # 模拟 /app/work
OUT="$ROOT/output"                 # 模拟 /app/output

echo "== [0] 清理并准备：$ROOT"
rm -rf "$ROOT"
mkdir -p "$WORK/notes" "$OUT"

echo "== [1] init：建立状态机与合法 result.json 骨架"
python3 "$SUPERVISOR" init --case "$INPUT/case.json" --work "$WORK" --output "$OUT"

echo "== [2] inventory 阶段：盘点材料（写证据笔记并登记）"
cat > "$WORK/notes/inventory.md" <<'EOF'
# inventory（合成示例）
- case.json 已解析：case_id=synthetic-demo-001，合约字段 5 个。
- 候选代码：method_ok.py（预期成功）、method_fail.py（预期崩溃）。
- 原始数据/作者仓库：缺失（预期情况，显式登记为 data_gaps）。
EOF
python3 "$SUPERVISOR" phase --work "$WORK" --name inventory --status done \
  --evidence "$WORK/notes/inventory.md"

echo "== [3] targets 阶段：登记验算目标指标"
cat > "$WORK/notes/targets.md" <<'EOF'
# targets（合成示例）
- 目标指标：accuracy=0.901、rmse=0.124（来自题目材料中的合成目标值）。
EOF
python3 "$SUPERVISOR" phase --work "$WORK" --name targets --status done \
  --evidence "$WORK/notes/targets.md"

echo "== [4] tolerances 阶段：登记容差判据"
cat > "$WORK/notes/tolerances.md" <<'EOF'
# tolerances（合成示例）
- accuracy 绝对容差 ±0.01；rmse 绝对容差 ±0.02（agent 的科学判断，监督器不裁决）。
EOF
python3 "$SUPERVISOR" phase --work "$WORK" --name tolerances --status done \
  --evidence "$WORK/notes/tolerances.md"

echo "== [5] run 阶段：受控运行两个候选（method_fail 会崩溃，流程必须继续）"
python3 "$SUPERVISOR" run --work "$WORK" --name method_ok   --timeout 60 -- \
  python3 "$INPUT/method_ok.py"
python3 "$SUPERVISOR" run --work "$WORK" --name method_fail --timeout 60 -- \
  python3 "$INPUT/method_fail.py"

echo "== [5b] 中间时刻自检：result.json 此刻就必须可解析且含全部合约字段"
python3 - "$OUT/result.json" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
fields = ["metric_table", "chosen_candidate", "discrepancy_cause",
          "reproducibility_verdict", "data_gaps"]
missing = [f for f in fields if f not in r]
assert not missing, "合约字段缺失: %s" % missing
assert r["status"] in ("success", "partial", "unable", "refused")
print("中间时刻 result.json 合法：status=%s，合约字段齐全。" % r["status"])
EOF

python3 "$SUPERVISOR" phase --work "$WORK" --name run --status done \
  --evidence "runs/method_ok/meta.json" --evidence "runs/method_fail/meta.json" \
  --note "method_ok 成功；method_fail 崩溃（exit 1），已记为证据"

echo "== [6] status：预算台账与下一建议动作"
python3 "$SUPERVISOR" status --work "$WORK"

echo "== [7] compare/conclude 阶段：agent 写分析证据并登记"
cat > "$WORK/notes/compare.md" <<'EOF'
# compare（合成示例）
- method_ok 指标与目标一致（accuracy 0.901 在 ±0.01 内）。
- method_fail 无指标产出（exit 1），差异归因：候选代码自身崩溃，非数据问题。
EOF
python3 "$SUPERVISOR" phase --work "$WORK" --name compare --status done \
  --evidence "$WORK/notes/compare.md"

echo "== [8] 填写 result.json 合约字段（agent 的诚实结论）"
python3 - "$OUT/result.json" <<'EOF'
import json, sys
p = sys.argv[1]
r = json.load(open(p, encoding="utf-8"))
r["metric_table"] = [
    {"candidate": "method_ok", "accuracy": 0.901, "rmse": 0.124,
     "source": "runs/method_ok/stdout.txt（合成示例）"}
]
r["chosen_candidate"] = "method_ok"
r["discrepancy_cause"] = ("method_fail 以 exit 1 崩溃，无指标产出；"
                          "归因于候选代码自身错误（见 runs/method_fail/stderr.txt），"
                          "与论文数值无关——合成代码不等于作者原代码。")
r["reproducibility_verdict"] = ("partial：仅 method_ok 在合成数据上通过指标核对；"
                                "这不构成论文数值复现。")
r["data_gaps"] = ["原始数据缺失（预期情况）", "作者官方仓库缺失（预期情况）"]
r["sources"] = {"method_ok 指标": "runs/method_ok/stdout.txt",
                "method_fail 崩溃": "runs/method_fail/stderr.txt"}
json.dump(r, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("合约字段已填写。")
EOF

python3 "$SUPERVISOR" phase --work "$WORK" --name conclude --status done \
  --evidence "$OUT/result.json" --note "结论已写入 result.json 合约字段"

echo "== [9] finalize：从证据重算总状态并做合约 lint（预期 partial + PASS）"
python3 "$SUPERVISOR" finalize --case "$INPUT/case.json" --work "$WORK" --output "$OUT"

echo "== 完成。产物：$OUT/result.json ；过程证据：$WORK （合成示例，非正式案例结果）"
