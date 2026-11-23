# 最小示例（SYNTHETIC）

本目录是技能 `corpus-provenance-knowledge-graph` 的端到端最小示例。
**全部内容为合成（SYNTHETIC）演示数据，不涉及任何真实文献，也不构成官方赛题答案。**

## 内容

| 文件 | 角色 |
| --- | --- |
| corpus-manifest.json | 来源清单（P1=primary，S1=secondary） |
| material.json | 聚合索引（包装形态 `{"materials":[...]}`） |
| primary-material.json | SYNTHETIC P1：冷冻铸造氧化铝支架（3 段 JATS-like 段落） |
| secondary-material.json | SYNTHETIC S1：冷冻铸造氧化铝膜（3 段，含与 P1 冲突的 30 vol% 主张） |
| secondary-publisher.xml | 旁挂文件（归一化器只登记不解析） |
| case.json | 模拟用例：output_contract + 4 条 query_specs |
| task.md | 模拟任务书 |
| candidate_extraction.json | 模拟模型抽取：13 节点 / 10 边 / 1 merge / 3 nonmerge / 1 conflict / 2 unreported |
| output/ | 运行产物（由脚本生成） |

## 运行（端到端一条命令）

从 bundle 根目录：

```bash
python3 scripts/run_minimal_example.py
```

生成 `output/`：`normalized_corpus.json`、`verify_report.json`、`graph.json`、
`graph.jsonl`、`queries.json`、`result.json`、`ledger.json`、`preview.dot`、`preview.svg`。

关键看点：

- merge `m1`：freeze-casting 作为**通用方法概念**跨 P1/S1 合并；
- nonmerge `nm1`：AL-P1 与 AL-S1 共享通用术语但为不同物理样品，显式不合并；
- conflict `c1`：optimal solid loading 20 vs 30 vol%，`resolution=preserved` 原样保留；
- unreported：烧结保温时间、力学强度两来源均未报告，如实登记；
- q1–q4 为真实执行的查询，结果子图携带完整证据三元组。
