# 运行记录（run-record.md）— 合成示例

> **合成示例声明**：`examples/synthetic-input/` 全部为虚构教学数据（伪造 DOI
> `10.99966/...`、`"Synthetic ..."` 标题、虚构作者与期刊），不含任何真实文献实体。
> 本目录 `examples/synthetic-output/` 是脚本**实际运行**的产物，非手工编写。

## 确切命令

在 `examples/` 目录下执行（相对路径，因此 `result.json` 中的 artifacts 路径可移植）：

```bash
cd examples/
python3 ../scripts/identity_arbiter.py \
  --case synthetic-input/case.json \
  --task synthetic-input/task.md \
  --work synthetic-output/work \
  --out synthetic-output
echo $?   # -> 2（诚实降级，见下）
```

产物：`synthetic-output/result.json` 与 `synthetic-output/work/` 下的
`merged_records.json`、`dedup_decisions.jsonl`、`arbitration_queue.json`、
`conflict_log.json`、`identity_report.md`。

## 结果概要

- 9 条输入记录（crossref 3 / europepmc 3 / publisher 3），36 个候选对全部落决策行。
- 合并 3 对：`rec-0001~rec-0007`（T1_SHARED_DOI，出版方 DOI 带 `https://doi.org/` 前缀
  与尾点，规范化后命中）、`rec-0004~rec-0008`（T1_ALIAS_LINK，仅靠 reference_graph
  显式别名 pmid 38900001 ↔ doi 10.99966/synth.2024.020）、`rec-0002~rec-0005`
  （T2_BIBLIOGRAPHIC_EXACT，作者格式变体 `Na Li/John Smith` vs `Li N, Smith J.`）。
- 规范记录 6 条 = 9 − 3；冲突日志 7 条（如 pages `45–58` vs `45-58`、刊名全称 vs 缩写）。

## 为什么 status=partial 是诚实且正确的结果

`rec-0006`（EuropePMC："…Property **Prediction**", 2023）与 `rec-0009`（出版方：
"…Property **Predictions**", 2024）满足 T3 阈值（title_sim=0.75 ≥ 0.6、
surname_overlap=1.0 ≥ 0.5、year_diff=1 ≤ 1），但标题差一个语义词、年份不同、摘要
描述的基准规模不同——这正是"模糊匹配绝不自动合并"纪律要拦截的情形。该对进入
`arbitration_queue.json` 且**未被合并**，`uncertainty` 显式列出。因此本次运行
（未提供 `--adjudications`）以 `status="partial"`、退出码 2 结束：降级被如实报告，
而非静默吞掉。若模型一次性批量裁决后写入裁决文件并加 `--adjudications` 重跑
（格式见 `synthetic-input/adjudications.example.json`），该对将按裁定以
`T3_ADJUDICATED_MERGE` / `T3_ADJUDICATED_SEPARATE` 落账，status 方可转为 `ok`。

## 重跑与确定性

- 重复执行同一命令（含幂等原地重跑）产物**字节级一致**：材料扫描排序、记录 id 按
  扫描序赋号、候选对按 id 序遍历、规范记录按 (规范化 DOI 否则规范化标题) 排序、
  JSON 键排序、无时间戳/随机量/墙钟。
- 换到其他 `--work` / `--out` 目录重跑，除 `result.json.artifacts` 中的路径前缀随
  参数变化外，全部内容产物字节一致。
- 自查要点：`--help` 退出 0；36 条决策行覆盖全部候选对且 reason_code 属于枚举；
  T3 对在仲裁队列且不在任何 `member_records` 中；`conflict_log.json` 非空；
  每个规范字段都有 `provenance`。
