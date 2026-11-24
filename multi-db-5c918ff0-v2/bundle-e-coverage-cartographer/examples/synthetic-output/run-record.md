# 运行记录（run-record）

**合成示例声明**：`examples/synthetic-input/` 为 SYNTHETIC teaching data——
全部文献、DOI（伪造前缀 10.99955）、PMID、期刊名均为虚构，仅用于演示覆盖
审计逻辑，不构成任何真实检索结论。本目录下的产物是对该合成输入
**真实运行脚本** 得到的结果，未做任何手工修饰。

## 运行命令

```bash
python3 scripts/coverage_cartographer.py \
  --case examples/synthetic-input/case.json \
  --task examples/synthetic-input/task.md \
  --work /tmp/cc-work-1 \
  --out examples/synthetic-output
```

退出码：`0`（审计正常完成；分析性缺口如实反映在 `status="partial"`）。

## 埋设异常 vs 检出结果

| # | 埋设异常（位置） | 期望台账类型 | 检出 |
|---|---|---|---|
| 1 | crossref `message.total-results=3` 但 `items` 仅 2 条且无 cursor（crossref_response.json） | `hitcount_mismatch` | ✅ gap-0010 |
| 2 | europepmc 记录 PMID 38000002 无 DOI；europepmc 全库无 volume/issue/pages/reference_list；crossref 无 pmid/pmcid；publisher 无 abstract/pmid/pmcid | `field_systematic_gap` | ✅ gap-0001…0009（9 条） |
| 3 | "Synthetic Provenance Tracking in Multi-Database Search" 仅出现于 europepmc | `single_source_only` | ✅ gap-0016（pmid:38000002） |
| 4 | 引用图节点 n3（doi 10.99955/syn.2020.0999）无任何来源检索到（reference_graph.json） | `referenced_not_retrieved` | ✅ gap-0015 |
| 5 | import_state.json 声明幻影 id `doi:10.99955/syn.2021.0777` 不存在于任何响应 | `import_state_gap` | ✅ gap-0012 |
| 6 | publisher 记录与 crossref 记录同 DOI（10.99955/syn.2021.0002）但年份冲突 2022 vs 2021 | `identifier_conflict` | ✅ gap-0011（列待仲裁，未静默合并） |
| 7 | task.md 记录同一检索式被逐字同时发送至 crossref 与 europepmc | `mechanical_copy` | ✅ gap-0013 |
| 8 | publisher 库无任何检索式证据（task.md 自述"未附任何检索式"） | `query_evidence_missing` | ✅ gap-0014（仅 publisher） |

台账合计 16 条（warning 14、info 2），无一条埋设异常被遗漏，也无误报的
多余条目；`status="partial"` 与台账非空一致。

## 产物清单

- `result.json`：case_id + 全部 5 个 output_contract 字段（candidate_set /
  coverage_summary / gap_summary / uncertainty_statement / change_records）
  + status / sources / uncertainty / gap_counts / unresolved_contract_fields（空）；
- `gap_ledger.json`：16 条台账条目，含 type / severity / db / evidence / impact；
- `coverage_matrix.json` / `coverage_matrix.md`：12 规范字段 × 3 数据库覆盖矩阵；
- `omission_report.md`：逐条目的证据定位与影响陈述。

## 重跑与确定性验证

1. 同输入连续两次运行到两个独立临时目录（`/tmp/cc-o1`、`/tmp/cc-o2`）：
   `diff -r` 结果 **字节一致**（OUT_IDENTICAL）；中间产物
   `normalized_records.json` 亦字节一致。
2. 覆盖重跑本目录：与首次产物 **字节一致**（EXAMPLE_MATCHES_RERUN），幂等。
3. `--help` 退出码 0；缺失/畸形 case.json 退出码 3 且 result.json 诚实标记
   `status="failed"`；含无法填充契约字段的降级场景退出码 2 且字段为 null
   并登记 `unresolved_contract_fields`。
4. 确定性保障：纯 Python 3 标准库、无网络、无随机性、产出物不含墙钟时间，
   全部 JSON 排序键写出。
