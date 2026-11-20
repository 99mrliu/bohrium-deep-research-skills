# 跨库字段覆盖与缺口审计报告 — {{CASE_ID}}

> 生成时间（UTC）：{{GENERATED_AT}}　·　全程离线，仅基于本地材料，未执行任何真实联网查询。
> 来源集合：{{SOURCES}}　·　原始记录总数：{{TOTAL_RECORDS}}　·　去重后论文数（最小聚类口径）：{{UNIQUE_PAPERS}}
> 聚类口径：DOI（小写化）精确匹配优先；无 DOI 时按归一题名+年份精确匹配。不做模糊匹配。

## 1. 库 × 字段覆盖矩阵

单元格为计数，四列依次为 present / missing / unknown / not_provided（图例见表末）。

{{MATRIX_TABLE}}

## 2. 单库独有文献（仅一个来源出现的论文）

{{SINGLE_SOURCE_TABLE}}

## 3. 系统性缺口字段（所有来源均无 present 值）

{{SYSTEMATIC_GAP_TABLE}}

## 4. 撤回 / 更正标记记录（单列，需人工确认是否纳入）

{{RETRACTED_TABLE}}

## 5. 库间记录数对账（返回总数 vs 解析成功 vs 丢弃，丢弃逐条留原因）

{{RECONCILIATION_TABLE}}

## 6. 失败降级状态台账摘要

{{LEDGER_SUMMARY}}

---

*本报告由 fieldatlas-coverage-audit 的 coverage_matrix.py 自动渲染；
字段语义与判定规则见 references/field_map_*.md 与 references/gap_taxonomy.md。*
