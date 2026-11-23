# SYNTHETIC 最小示例任务书（非官方赛题）

> 本文件是技能 `corpus-provenance-knowledge-graph` 最小示例的模拟 task.md，
> 语料与全部实体均为 SYNTHETIC（合成），仅用于演示端到端流程。

## 任务

给定一个两论文合成语料（primary=P1，secondary=S1），构建**文献溯源知识图谱**：

1. 以 `material.json` 为聚合索引装载 `primary-material.json` 与
   `secondary-material.json`；`secondary-publisher.xml` 为旁挂文件，仅登记不解析。
2. DOI / title / authors 等根元数据只能归属于 primary（P1）；S1 的元数据仅可
   出现在 S1 自身的 paper 节点上。
3. 每个实质性节点/边必须携带证据三元组：
   `source_id` + JATS `paragraph_id` + 该段落原文的**精确短引文**。
   语料不含 PDF 页码，任何对象不得使用“第 1 页”式地址。
4. 跨论文合并（merge）必须有规范化键与显式理由；同名/同通用术语而物理对象
   不同的节点对，必须留下显式 nonmerge 记录。
5. 不同来源的冲突数值（如 optimal solid loading）原样保留，禁止取平均或择一；
   双方均未报告的信息（如烧结保温时间）进入 unreported。
6. 执行 case.json 中 query_specs 声明的全部查询，结果子图连同证据一并输出。

## 产出

在输出目录生成：`result.json`（动态镜像 output_contract 精确键）、
`graph.json`、`graph.jsonl`、`queries.json`、`verify_report.json`、
`ledger.json`、`preview.dot`、`preview.svg`。

## 运行

从 bundle 根目录执行一条命令即可端到端复现：

```bash
python3 scripts/run_minimal_example.py
```
