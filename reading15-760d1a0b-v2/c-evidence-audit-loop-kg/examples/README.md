# 合成示例（SYNTHETIC example, not real papers）

> **声明**：`examples/` 下所有内容均为 **SYNTHETIC 合成示例**，两篇"论文"完全虚构，
> 仅用于演示审计-修复闭环；`synthetic/output/` 中的产物**不是正式案例答案**。

## 运行方式

```bash
sh examples/run_example.sh
# 或
python3 scripts/run_minimal_example.py
```

脚本非交互地跑完全部阶段：stage-1 模型草案由 `examples/stage1_extraction_draft.json`
扮演（**故意埋入 3 个缺陷**），stage-3 模型修复由 `examples/stage2_repairs.json`
扮演；其余步骤全部由 `scripts/` 机械完成。

## 故意埋入的缺陷（用于演示闭环）

| 条目 | 缺陷 | 审计理由码 | 修复 |
|---|---|---|---|
| `n-paper-sec` | 把根标题（属于 primary）安在 secondary 证据上 | `ROOT_META_MISATTRIBUTION` | 改为 secondary 自己的标题 + sec-p01 引文 |
| `n-claim-pce-pri` | quote 是改写句，非段落精确子串 | `QUOTE_NOT_SUBSTRING` | 替换为 pri-p06 的逐字片段 |
| `e-uses-tio2-sec` | `paragraph_id: sec-p99` 不存在 | `ADDRESS_UNKNOWN` | 改为 sec-p03 |

## 预期控制台输出（摘要）

```
discover: case_id=synthetic-perovskite-001 sources=2 paragraphs=24 queries=3
audit iter=1: items=30 accept=27 repair=3 reject=0 | quote=93.9% addr=97.0% attr=96.7% coverage=50.0%
apply_repairs: applied=3 dropped=0 refused=0 unknown=0 -> .../extraction.repaired.json
audit iter=2: items=30 accept=30 repair=0 reject=0 | quote=100.0% addr=100.0% attr=100.0% coverage=50.0%
build_graph: nodes=14 edges=12 merges=1 nonmerges=1 unreported=1 dropped_edges=0
query: executed 3/3 query specs
  q1 [neighborhood]: nodes=4 edges=3 evidence=6 undetermined=0
  q2 [edges_by_relation]: nodes=3 edges=2 evidence=4 undetermined=0
  q3 [conflict_check]: nodes=3 edges=3 evidence=4 undetermined=1
assemble: result.json status=success | certificate verdict=pass (quote 93.9% -> 100.0%, addr 97.0% -> 100.0%)
certificate verdict: pass | quarantined: 0
graph: nodes=14 edges=12 merges=1 nonmerges=1 unreported=1
queries executed: 3/3
```

## 输出文件（synthetic/output/，已随包提交）

| 文件 | 内容 |
|---|---|
| `result.json` | 镜像 output_contract 全部键的最终结果（status=success） |
| `audit_certificate.json` | **签名产物**：两轮指标 + baseline_vs_final 增益 |
| `audit_report.iter1.json` / `audit_report.iter2.json` | 两轮逐项裁决与理由码 |
| `repair_queue.iter1.json` / `repair_queue.iter2.json` | 每轮修复队列（只含失败项；iter2 为空） |
| `audit_report.json` / `repair_queue.json` | 最新一轮的副本 |
| `extraction.repaired.json` | 修复后的抽取（含 repair_log） |
| `graph.json` | 14 节点 / 12 边 / 1 合并 / 1 显式不合并 / 1 未报告项 |
| `queries.json` | 3 个真实执行的查询及证据与 undetermined |
| `quarantine.json` | 隔离区（本例为空：全部修复成功） |

## 6 个测试夹具在语料中的位置

1. 跨篇别名对：primary `methylammonium lead iodide` ↔ secondary `MAPbI3`
   （合并条目 `m-mapbi3-alias`，sec-p10 显式等价）。
2. 首提缩写：pri-p01 `power conversion efficiency (PCE)`。
3. 跨篇数值冲突：pri-p06 21.1%（初始 1-sun）vs sec-p04 18.7%（500 h 湿热后）——
   两条独立 claim + `conflicts-with` 边，**未合并**（见 q3 查询结果）。
4. 同名不同对象：两篇的 `TiO2`（致密 ETL vs Dyesol 浆料支架，lot 42）——
   显式 nonmerge `x-tio2-nonmerge`。
5. 未报告项：primary 的 hysteresis index（`u-hysteresis`，附"未报告"原文引文）。
6. `case.json` 含 `output_contract` 与恰好 3 个 `query_specs`
   （neighborhood / edges_by_relation / conflict_check）。
