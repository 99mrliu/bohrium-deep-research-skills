# examples — 合成示例（全部数据为虚构，非真实案例）

**声明**：本目录所有文献题名、作者、DOI（`10.55555/synth.*`）、PMID（`9000000x`）、
期刊名、查询参数、导入状态均为**合成示例数据**，仅用于 selfcheck 与演示脚本行为，
不对应任何真实文献、真实数据库响应或真实案例答案。skill 不预置、不硬编码真实
DOI/PMID。

## 文件说明

| 文件 | 内容 | 设计意图 |
|---|---|---|
| `case.json` | 合成案例输入（case_id=EX-SYN-C01，含 output_contract 扩展字段） | 演示动态脚手架 |
| `task.md` | 合成任务说明 | 演示研究问题提取 |
| `raw_crossref_page1.json` | Crossref 第 1 页（items=2，total-results=5） | 分页截断场景的一半 |
| `raw_crossref_page2.json` | Crossref 第 2 页（items=2，total-results=5） | 2 页合计 4 < 5 → suspected_truncation |
| `raw_europepmc.json` | EuropePMC 响应（hitCount=3） | 字段语法差异、内嵌 request |
| `raw_publisher.json` | 出版商 JSON（items=3，第 3 条为不可解析字符串） | query_unrecorded + unparsed 丢弃 |
| `query_ledger.example.jsonl` | 组织方记录的查询台账（crossref×2 + europepmc×1） | publisher 未记录 → query_unrecorded |
| `import_state.json` | 组织方本地导入状态（5 条） | already_imported / updated / conflicting 三类 |
| `lineage_report.example.md` | 全链路渲染报告（示例输出，非真实案例结果） | 展示最终交付形态 |

## 合成数据的关键构造（≥8 条记录跨三来源）

- 共 10 条原始 item：crossref×4、EuropePMC×3、publisher×3。
- **两对标识符/题名重复**：
  - Tier1：crossref page1 item[1]（doi `10.55555/synth.002`）与 publisher item[0]
    （doi `10.55555/SYNTH.002`，大写变体）→ 同一 canonical；
  - Tier1：crossref page2 item[1]（doi `10.55555/synth.004`）与 EuropePMC item[0]
    （同 DOI）→ 同一 canonical；
  - Tier2：crossref page1 item[0] 与 EuropePMC item[2]（归一题名精确一致、无共同
    标识符）→ 同一 canonical。
- **1 条被丢弃的重复项**：publisher item[0] → duplicate_of。
- **1 条 relevance_excluded**：EuropePMC item[1]（由模型 exclusions 文件声明）。
- **1 条 unparsed**：publisher item[2]（字符串条目）。
- **1 条 query_unrecorded**：publisher 库。
- **import diff 四类**：new×2（synth.001/006）、already_imported×1（synth.003）、
  updated×1（synth.004 页码 300-311 vs 导入 300-315）、conflicting×1
  （synth.002 导入状态内两个矛盾版本）。

`selfcheck` 使用的 relevance_excluded 排除项在运行时以临时文件注入（键为
`europepmc:raw_europepmc.json:item[1]`），不预置在 examples 中。
