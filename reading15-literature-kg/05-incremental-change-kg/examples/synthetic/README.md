# SYNTHETIC 合成示例（仅演示接口，非正式案例结果）

> 本目录全部内容为**合成数据**：两篇"论文"、DOI、作者、哈希均为虚构占位，
> 仅用于演示增量图谱工作流的接口与不变式，不冒充任何正式案例结果或真实文献结论。

## 场景

- **primary**（`input/primary-material.json`）：溶胶凝胶法制备 LiFePO4/C 复合正极，
  0.1 C 下放电容量 158 mAh/g，优于水热参比样品（141 mAh/g）。
- **secondary**（`input/secondary-material.json`）：水热法合成 LFP/C，
  0.1 C 下 149 mAh/g，并声称水热 LFP/C 倍率性能高于溶胶凝胶粉体。

## 演示的不变式

| 设计 | 对应操作 | 结果 |
|-|-|-|
| 真别名合并（LFP/C = LiFePO4/C，p2.001 显式证据） | MERGE | 幸存者 `n_mat_29a6b6b9` 保留原 ID，别名+证据追加 |
| 新方法/新边/新数值 | ADD | `hydrothermal method` 节点、149 mAh/g 边（与 158 分存） |
| 通用样品不合并（两篇都用 "commercial carbon black"） | KEEP_DISTINCT | `n_mat_bbb0bb6d`（baseline 不动）与 `n_mat_bbb0bb6d_2`（确定性后缀）并存 |
| 只追加证据 | UPDATE_EVIDENCE | metric 节点追加 p1.004 结果段短引 |
| 结论冲突不覆盖 | CONFLICT | 两条 outperforms 边结成 `cf_b39462fd`，均标 conflicted |

最终图：**9 节点、9 边**（baseline 6 节点 5 边），满足 ≥8/≥8。

## 真实执行的查询（`queries/query-specs.json`，结果在 `output/queries.json`）

1. `q1_capacity_by_material`（current）：哪些材料报告了放电容量——158 与 149
   两条边分存，数值/条件不合并；
2. `q2_node_change_baseline_vs_current`（both）：LiFePO4/C 节点跨版本
   before/after——**baseline vs current 变化查询**；
3. `q3_conflicts`（current）：冲突组与双方原文证据；
4. `q4` / `q4b`（baseline 与 current）：通用样品 carbon black 的保持区分对照。

## 复现

```bash
bash examples/synthetic/run_synthetic.sh            # 全流程，输出到 output/
bash examples/synthetic/tests/negative_tests.sh     # 负向测试（6 项断言）
```

负向测试实测：T1 重跑幂等（两次输出逐字节一致 + 无重复 ID）、T2 旧 ID 保留、
T3 引文篡改被校验器拒绝并定位、T4 基线封存不被改写 + 冲突双方并存不覆盖。

## 目录

```
input/       合成输入（case/manifest/material/primary/secondary/task）
candidates/  Agent 语义候选与变更集（baseline-candidates.json、changeset.json）
queries/     查询清单 query-specs.json
output/      一键复现后的交付件（result.json、graph-baseline/current(.json/.jsonl)、
             queries.json、changes(.json/.jsonl)、change-ledger.md、
             graph-preview.md、graph.dot、graph.svg、diff.json）
tests/       negative_tests.sh
```
