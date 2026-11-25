# 示例说明（SYNTHETIC example, not real papers）

> **本示例中的两篇"论文"、抽取草稿、修复文件与全部输出均为人工编造的合成数据**，
> 仅用于演示 b-ontology-guard-kg 的流程与工件形态；它们**不是**正式案例答案。
> 每个输入文本文件都带有 "SYNTHETIC example, not real papers" 声明。

## 运行方式

```bash
bash examples/run_example.sh
# 或
python3 scripts/run_minimal_example.py
```

脚本只使用本技能包自带的脚本，模拟运行时契约：
`examples/synthetic/input/`（= /input）→ `examples/synthetic/output/work/`（= /app/work）
→ `examples/synthetic/output/`（= /app/output）。输出已提交，审阅者无需运行即可查看。

## 合成语料与测试夹具（fixtures）

两篇关于 MAPbI3 钙钛矿太阳能电池的 mini 论文（primary 12 段 / secondary 11 段），覆盖：

1. **跨篇别名对**：primary 的 "MAPbI3" ↔ secondary 的 "methylammonium lead iodide"
   （merge: n12 → n01，带理由与证据）；
2. **首现缩写**："power conversion efficiency (PCE)"（primary p1）；
3. **跨篇数值冲突（不同条件）**：PCE 21.1%（1-sun 初始，primary p7）vs 18.7%
   （500 h 湿热老化后，secondary p7）——保留为两个独立 claim（n06、n13），用
   `compares` 边 e09 连接，**不合并、不判矛盾**；
4. **同名不同物陷阱**：两篇都有的 "TiO2 electron-transport layer"，实为不同样品
   （n04 介孔/device A vs n11 致密/device B）——显式 `nonmerge`（x01）；
5. **未报告项**：hysteresis index（secondary p8 明确未测）→ `unreported`（u01）；
6. **case.json** 含 `output_contract` 与恰好 3 个 `query_specs`
   （q1 邻域、q2 按关系+限定词过滤、q3 矛盾检查）。

**故意的本体违规**：`work/extractions_draft.jsonl` 中埋了 4 条违规（e-bad1..4），
触发 `UNKNOWN_RELATION`、`MISSING_QUALIFIER` + `NUMERIC_REQUIRES_METRIC_CONDITION`、
`DOMAIN_MISMATCH`、`QUOTE_NOT_SUBSTRING`。`work/extractions_repair.jsonl` 是唯一的
一轮修复：修复 e-bad1..3；e-bad4（quote 无法核实）故意不修，永久隔离（final=true）。

## 预期控制台输出

```
discover: 2 sources, 23 paragraphs, 0 warnings -> .../examples/synthetic/output/work
validate pass 1 (draft): 33 accepted, 4 quarantined; violations={"DOMAIN_MISMATCH": 1, "MISSING_QUALIFIER": 1, "NUMERIC_REQUIRES_METRIC_CONDITION": 1, "QUOTE_NOT_SUBSTRING": 1, "UNKNOWN_RELATION": 1}
validate pass 2 (repair): 3 accepted, 0 quarantined; violations={}
build: 17 nodes, 12 edges, 2 merges, 1 nonmerges
query q1 (neighborhood): ok, 3 nodes, 2 edges, 0 undetermined
query q2 (edges_of_relation): ok, 4 nodes, 3 edges, 0 undetermined
query q3 (contradiction_check): ok, 2 nodes, 1 edges, 1 undetermined
assemble: status=success, contract keys=9, notes=0 -> .../examples/synthetic/output
SYNTHETIC example pipeline finished OK -> .../examples/synthetic/output
```

退出码 0。（`notes=0` 表示所有 contract 键均已产出；若显示 notes=N，请查看
result.json 的 `contract_notes`。）

## 输出文件清单（examples/synthetic/output/）

| 文件 | 内容 |
|---|---|
| `result.json` | 最终交付：镜像 output_contract 全部 9 个键 + graph/queries/quarantine/validation_report 等 |
| `graph.json` | 类型化图谱：17 节点 / 12 边（合并后），每边带极性/限定词/证据 |
| `query_results.json` | 3 个真实执行的查询：子图 + 证据 quote + undetermined 列表 |
| `validation_report.json` | 签名工件：两轮校验、逐错误码违规计数、修复预算用量 |
| `quarantine.json` | 签名工件：1 条永久隔离项（e-bad4, QUOTE_NOT_SUBSTRING, final=true） |
| `merge_ledger.json` | 2 条跨篇合并（MAPbI3 别名对；研究者 L. Chen） |
| `nonmerge_registry.json` | 1 条显式不合并（两个 TiO2 样品） |
| `work/` | 中间产物（corpus/discovery/validation_state/validated.jsonl 等），供审阅者追溯 |

## 关键检查点

- `validation_report.json` → `cumulative_violations` 有 5 个错误码的计数，
  `repair_budget` 显示 1/1 已用；
- `quarantine.json` → `count: 1`，条目带 typed error code 与 `final: true`；
- q3 → `verdict: compared_no_contradiction`，并提示条件不同、数值不得合并；
- 所有 quote 均已被校验器机械验证为所引段落的精确子串（未被隔离的条目）。
