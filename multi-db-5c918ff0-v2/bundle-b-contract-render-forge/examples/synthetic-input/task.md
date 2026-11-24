# Synthetic Task(合成教学任务)

研究问题:在虚构的模型反应(model reactions)中,哪些合成催化剂(synthetic
catalysts)能够提高选择性(selectivity)?

## 检索范围与口径(scope)

- 纳入(include):2022–2025 年发表、标题或期刊名含 synthetic 的英文论文。
- 排除(exclude):预印本、会议摘要、无 DOI 且无 PMID 的记录。
- 范围(scope):仅覆盖 source_dbs 声明的三个离线数据库快照,不做外推。

## 交付要求(deliverables)

必须交付以下 output_contract 字段,全部写入 `/app/output/result.json`:
`candidate_set`、`ranking_basis`、`evidence_records`、`status_notes`、
`coverage_statement`。

同时交付可复核的渲染工件:`candidate_table.md`、`provenance_chain.md`、
`coverage_matrix.md`、`render_gate_report.md`。所有结论必须可溯源到具体
材料文件的 JSON 路径;任何无法从材料支撑的契约字段一律置 null 并写入
`unresolved_contract_fields`,严禁编造。
