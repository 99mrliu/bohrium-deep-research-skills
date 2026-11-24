#!/usr/bin/env bash
# runbook-governor 合成示例驱动脚本（非正式测试案例）。
# 模拟一次受治理运行：intake→question→…→closeout，并故意把预算打满
# 触发 L2 → triage → finalize partial。所有产物写入 examples/output/。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
RB="$HERE/../scripts/runbook.py"
WORK="$HERE/output/work"
OUT="$HERE/output/app_output"
S="$WORK/run_state.json"
rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"

python3 "$RB" --state "$S" init \
    --case "$HERE/input/case.json" --output "$OUT" \
    --requests 10 --seconds 900
# 说明：示例用 --requests 10 的小预算，便于演示降级；真实评测默认 64。

python3 "$RB" --state "$S" enter --phase intake
ls -laR "$HERE/input" > "$WORK/inventory.md"
python3 "$RB" --state "$S" exit --phase intake \
    --note "登记 4 个输入文件；骨架 result.json 已由 init 落盘"
python3 "$RB" --state "$S" tick --n 2
python3 "$RB" --state "$S" checkpoint

python3 "$RB" --state "$S" enter --phase question
printf '%s\n' '# 合成示例：问题五要素' \
  '- 研究对象：方法 M（虚构）' \
  '- 关键变量：指标 X、数据集 D' \
  '- 比较基线：基线方法 B（Alpha 2024）' \
  '- 预期结论方向：M 能否在 D 上把 X 提升 5 个百分点' \
  '- 可证伪条件：在 D 的固定划分上 X(M) - X(B) < 0.05' \
  > "$WORK/question_frame.md"
python3 "$RB" --state "$S" exit --phase question \
    --note "五要素成稿；未指定项：D 的划分细节（材料未给）"
python3 "$RB" --state "$S" tick --n 2

python3 "$RB" --state "$S" enter --phase retrieve
printf '%s\n' '# 合成示例：筛选日志' \
  '- paper_alpha.txt：纳入（同数据集 D 的基线证据）' \
  '- paper_beta.txt：纳入（方法 M 的证据，但数据集不同）' \
  > "$WORK/screening_log.md"
printf '%s\n' '# 覆盖边界声明（合成示例）' \
  '本结论仅在输入文献集 {paper_alpha.txt, paper_beta.txt} 内成立；' \
  '"未见覆盖"指在该边界内未见，不做全局新颖性断言。' \
  > "$WORK/coverage_boundary.md"
python3 "$RB" --state "$S" exit --phase retrieve \
    --note "2/2 纳入；覆盖边界=输入文献集"
python3 "$RB" --state "$S" tick --n 2
python3 "$RB" --state "$S" checkpoint

python3 "$RB" --state "$S" enter --phase extract
printf '%s\n' '# 合成示例：证据表' \
  '| 来源 | 任务 | 方法 | 数据 | 指标X | 局限 |' \
  '|-|-|-|-|-|-|' \
  '| paper_alpha.txt | D 上提升 X | 改进流程 | 合成数据集 D | 0.71→0.74 | 单数据集、无显著性 |' \
  '| paper_beta.txt | 基准 P 上评估 M | 方法 M | 公开基准 P | 0.80 | 未在 D 上实验；约 200 GPU 时 |' \
  > "$WORK/evidence_table.md"
python3 "$RB" --state "$S" exit --phase extract --note "2 篇文献字段提取完毕"
python3 "$RB" --state "$S" tick --n 2

# 故意把剩余预算打满，演示 L2 降级
python3 "$RB" --state "$S" tick --n 2 || true
echo "--- status（应为 L2，因 10/10 请求用尽）---"
python3 "$RB" --state "$S" status

echo "--- triage：强制合法 partial ---"
python3 "$RB" --state "$S" triage

python3 "$RB" --state "$S" finalize --status partial \
    --reason "示例故意耗尽 10 次请求预算，synthesize/closeout 未执行；已交付骨架与过程产物"

cp "$S" "$OUT/run_state.json"
echo "--- 产物清单 ---"
find "$HERE/output" -type f | sort
