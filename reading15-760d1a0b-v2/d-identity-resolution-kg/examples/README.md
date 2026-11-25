# 示例说明（examples/）— SYNTHETIC example, not real papers

本目录是一个**完全合成**的最小示例：两篇虚构的钙钛矿太阳能电池小论文
（S1 = primary，S2 = secondary，各 11 段）。所有论文、作者、DOI、数据都是
编造的，仅用于演示管线；`output/` 中的结果是**合成示例产物，不是正式案例答案**。

## 运行

```bash
python3 scripts/run_minimal_example.py        # 或 examples/run_example.sh
```

它只用本 bundle 自己的脚本，模拟 `/input → /app/work → /app/output`：

- `synthetic/input/`：case.json、task.md、material.json、primary-material.json、
  secondary-material.json、corpus-manifest.json（含真实可校验的 sha256）；
- `synthetic/model_artifacts/`：模拟模型要写的两个小 JSON
  （adjudication.json、extractions.json，均标注 SYNTHETIC）；
- `synthetic/work/`：中间产物（每次运行重新生成）；
- `synthetic/output/`：最终交付（已提交，可不运行直接查看）。

## 语料内含的 6 个测试装置

1. 跨篇别名对：`methylammonium lead iodide`（S1）↔ `MAPbI3`（S2）→ 合并；
2. 首提缩写：`power conversion efficiency (PCE)`（S1-p01，共 7 处定义）；
3. 跨篇数值冲突：PCE 21.1%（1-sun 初始）vs 18.7%（500 h 湿热后）→
   两个独立声明 + conflict_registry 保留；
4. 同名异物陷阱：`TiO2` 在 S1 是致密电子传输层、在 S2 是介孔支架 →
   显式 NON-merge（nonmerge_registry，P16）；
5. 未报告项：hysteresis index（S1-p08 明说未测）；
6. case.json 含 output_contract + 恰好 3 个 query_specs
   （neighborhood / edges_by_relation / conflict_check）。

## 期望控制台输出

```
discover: 2 source(s), 22 paragraph(s), 0 warning(s) -> .../work/corpus.json
candidates: 17 pair(s) (2 trap-flagged) from 40 mention(s) -> .../work/candidates.json
adjudicate: 16 merge(s), 1 nonmerge(s), 10 entit(ies), 0 quarantined decision(s)
build_graph: 18 node(s), 13 edge(s), 5 claim(s), 1 conflict(s), 0 warning(s)
verify: 127/127 evidence item(s) OK across 10 file(s); verdict=pass -> .../work/verify_report.json
query: 3 executed, 3 answered -> .../work/query_results.json
assemble: status=success; result.json + 7 artifact(s) -> .../output
run_minimal_example: exit=0 ...
```

## 输出文件清单（synthetic/output/）

| 文件 | 内容 |
|---|---|
| `result.json` | 镜像 output_contract 全部键；status=success |
| `graph.json` | 18 节点（13 实体 + 5 声明）、13 边 |
| `merge_ledger.json` | 16 个被接受的合并（含跨篇 MAPbI3、spiro-OMeTAD） |
| `nonmerge_registry.json` | 1 个被拒绝的合并：TiO2 陷阱（P16） |
| `conflict_registry.json` | 1 条保留式冲突：PCE 21.1% vs 18.7%（K0001） |
| `entity_map.json` | 稳定实体 ID E0001…E0010 及别名、提及证据 |
| `query_results.json` | 3 个真实执行的查询（Q1–Q3 均 answered） |
| `verify_report.json` | 引用完整性审计 |

中间产物（`synthetic/work/`）另含 corpus.json、candidates.json（17 个候选对，
2 个陷阱标记）、adjudication_report.json、extraction_report.json、run_meta.json
（唯一含墙钟时间的文件，不参与确定性比较）。与 output/ 或 model_artifacts/
逐字节相同的暂存副本未重复提交；重新运行 `run_minimal_example.py` 会重建完整
work/ 目录。
