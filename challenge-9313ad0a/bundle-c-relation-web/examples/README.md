# 合成示例说明（Synthetic Example）

本目录全部内容为**合成（synthetic）示例**：研究对象"催化剂Q"、其制备、表征、性能与失活数据均为虚构，不对应任何真实研究、论文或数据，仅用于演示 relation-web 技能的工具链行为。

## 目录结构

- `synthetic-input/nodes.json`：10 个合成节点，`parent` 指针构成一棵小型主题树（根 n1，下设 n2 制备方法、n5 表征结果、n7 性能评价、n9 失活机理等分支）。
- `synthetic-input/relations.json`：9 条合成关系边：
  - r1–r5：完全合法（r1–r4 为 basis=fact 且引句逐字命中，r5 为 basis=inference 且 note 非空）；
  - r6：basis=fact 但引句**虚构**（材料中不存在）→ 预期判定 fabricated（错误级，退出码 1）；
  - r7：from（n4）是 to（n2）的后代 → 预期判定层级冗余（拒绝）；
  - r8：from == to（n8 → n8）→ 预期判定自环（拒绝）；
  - r9：basis=inference 但 note 为空 → 预期拒绝。
- `synthetic-input/pages.jsonl`：3 行合成材料文本，含 r1–r4、r7、r8 所需的逐字引句；并在第 1 页与第 3 页植入同一指标"产率"的两个冲突取值（87.5% 与 79.2%）。
- `synthetic-output/gate_report.json`、`synthetic-output/rejected.json`：对 synthetic-input 真实运行 `scripts/relation_gate.py` 的输出（退出码 1，因含虚构证据）。
- `synthetic-output/conflict_candidates.json`：真实运行 `scripts/conflict_scan.py` 的输出，其中可检出所植入的"产率"冲突候选。

## 复现命令

在 bundle 根目录下执行：

```
python3 scripts/relation_gate.py \
  --nodes examples/synthetic-input/nodes.json \
  --relations examples/synthetic-input/relations.json \
  --material examples/synthetic-input/pages.jsonl \
  --report gate_report.json --rejected rejected.json
echo $?   # 预期 1

python3 scripts/conflict_scan.py \
  --nodes examples/synthetic-input/nodes.json \
  --material examples/synthetic-input/pages.jsonl \
  --out conflict_candidates.json
echo $?   # 预期 0
```
