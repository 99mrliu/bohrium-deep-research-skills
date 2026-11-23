# 最小可复现示例（合成示例 / 非正式案例结果）

> **声明**：本示例全部数据为人工合成的虚构段落（虚构的钙钛矿/光催化“论文”），仅用于演示与回归测试，**不是**任何正式案例的翻译或审计结果。

`data/pairs_bad.jsonl`：6 段（S001–S006），其中 4 处人为缺陷：
- S002：源文 `92%` 在译文中被丢弃 → 预期 `number-dropped`
- S003：源文 `did not show degradation` 的否定在译文中丢失 → 预期 `negation-lost`
- S004：源文引文 `[14]` 在译文中丢失 → 预期 `citation-lost`
- S005：源文 `Fig. 2` 引用在译文中丢失 → 预期 `ref-lost`
- S001、S006 为干净对照段。

`data/pairs_fixed.jsonl`：与 bad 版唯一区别是 S002–S005 的缺陷已全部修复。

## 运行命令

```bash
cd skill
WORK=$(mktemp -d)

# 1) 抽取不变量（仅从 source 侧）
python3 scripts/extract_invariants.py --pairs examples/data/pairs_bad.jsonl --out "$WORK/invariants.json"

# 2) 忠实度门禁：bad 版
python3 scripts/check_fidelity.py --invariants "$WORK/invariants.json" \
    --pairs examples/data/pairs_bad.jsonl \
    --out "$WORK/report_bad.json" --md "$WORK/report_bad.md"
echo "exit=$?"   # 预期 exit=1

# 3) fixed 版（先重新抽取或直接复用 invariants，source 相同）
python3 scripts/check_fidelity.py --invariants "$WORK/invariants.json" \
    --pairs examples/data/pairs_fixed.jsonl \
    --out "$WORK/report_fixed.json"
echo "exit=$?"   # 预期 exit=0

# 4) 人工确认队列
python3 scripts/review_queue.py --report "$WORK/report_bad.json" --out "$WORK/human_review_queue.md"

# 5) 保底 result.json（合成 case）
printf '{"case_id":"demo-001","output_contract":{"fidelity_report":"","human_queue":""}}' > "$WORK/case.json"
python3 scripts/finalize_result.py --case "$WORK/case.json" --out "$WORK/result.json" --status partial \
    --field fidelity_report=report_bad.json
```

## 预期结果

- 第 1 步：`stats` 约为 `numbers=7, citations=1, refs=1, negations=1, hedges=2`（`segments=6`）。
- 第 2 步：退出码 **1**，`report_bad.json` 恰好 **4 个 blocker**，代码分别为
  `number-dropped`(S002)、`negation-lost`(S003)、`citation-lost`(S004)、`ref-lost`(S005)，无 warning。
- 第 3 步：退出码 **0**，`blockers=0, warnings=0`，且 `checks > 0`。
- 第 4 步：`human_review_queue.md` 含 4 个未勾选的 blocker 条目（`- [ ] [S002] number-dropped` 等），每条带源文/译文片段与建议动作。
- 第 5 步：`result.json` 含 `case_id="demo-001"`、`output_contract` 两个字段（`fidelity_report` 已填、`human_queue` 为空字符串）、`status="partial"` 与一条 `change_record`。

## 反向测试（数字被篡改）

将任一段译文中的 `21.3%` 改为 `23.1%` 后重跑第 2 步，预期出现
`number-dropped`（21.3 消失）和/或 `number-changed`（23.1 为外来值）BLOCKER，退出码 1。
