# Candidate Table(候选排序表)

- case_id: `synthetic-render-forge-001`
- canonical records: 4
<!-- canonical_records:4 -->
- generated_by: render_forge.py v1.0.0 (deterministic, no wall-clock)
- 排序公式: score = 3×标题命中 + 1×上下文命中 + 2×引用图入度;同分按 record_id 字典序。

## Scope notes(来自 task.md 的纳入/排除口径)

- 检索范围与口径(scope)
- 纳入(include):2022–2025 年发表、标题或期刊名含 synthetic 的英文论文。
- 排除(exclude):预印本、会议摘要、无 DOI 且无 PMID 的记录。
- 范围(scope):仅覆盖 source_dbs 声明的三个离线数据库快照,不做外推。

## Ranked candidates

| rank | record_id | DOI | PMID | year | title | matched query terms | score | source dbs |
|---|---|---|---|---|---|---|---|---|
| 1 | rec-0001 | 10.99988/synforge.2024.001 | 39998801 | 2024 | Synthetic Cobalt Porphyrin Catalysts for Selective Oxidation in Model Reactions | catalysts, model, reactions, synthetic | 18 | CR+EP+PU |
| 2 | rec-0002 | 10.99988/synforge.2023.014 | 39998814 | 2023 | Synthetic Metal-Organic Framework Membranes for Gas Selectivity | selectivity, synthetic | 8 | CR+EP |
| 3 | rec-0003 | 10.99988/synforge.2022.031 | — | 2022 | Synthetic Enzyme Mimics with Tailored Selectivity | selectivity, synthetic, fictional | 7 | CR |
| 4 | rec-0004 | 10.99988/synforge.2025.007 | 39998877 | 2025 | Synthetic Photoredox Methods in Fictional Batch Chemistry | fictional, synthetic | 6 | EP+PU |

> source db badges: CR=crossref, EP=europepmc, PU=publisher, MR=merged_records(上游)。
