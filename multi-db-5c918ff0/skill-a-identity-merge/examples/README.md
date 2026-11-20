# examples/ — 合成示例数据（全部虚构，非真实案例）

本目录全部数据为 **synthetic / illustrative** 的合成示例，仅用于
`scripts/selfcheck` 与 SKILL.md 演示。其中所有 DOI（前缀 `10.99999/synth.*`）
与 PMID（`990000xx` 号段）均为虚构占位，不指向任何真实文献；所有人名、刊名、
题名、摘要均为虚构。selfcheck 断言即建立在下列预埋身份关系之上。

## 文件清单与虚构说明

| 文件 | 内容 | 预埋身份关系 |
|---|---|---|
| `case.json` | 合成案例输入（case_id=`EX-SYN-5C918FF0-A`） | 列出 4 个材料文件 |
| `task.md` | 合成任务说明 | 重申去重/合并/仲裁要求 |
| `raw_crossref.json` | 虚构 Crossref works 响应，5 条 item | P1/P2 与 publisher、EuropePMC 构成 DOI 重复对；P4a 与 P4b 同题名不同年份；P9 无 DOI（Tier2 正例）；P8 无卷期摘要（missing 语义） |
| `raw_europepmc.json` | 虚构 EuropePMC 响应，4 条 result | P2 与 Crossref 同 DOI（重复对 2）；P3 仅 PMID `99000001`（跨标识符对的一半）；P5a 与 P5b 模糊相似；P6 `abstractText` 为空串（unknown 语义） |
| `raw_publisher.json` | 虚构出版商通用 JSON，6 条 record | P3 仅 DOI `10.99999/synth.0003`（另一半）；P1 issue=`3` 与 Crossref `2` 冲突；P5b 模糊对；P7 无摘要卷期（missing 语义） |
| `reference_graph.example.json` | 虚构引用图 | `aliases` 显式给出 `99000001`↔`10.99999/synth.0003`（跨标识符互链的唯一合法依据）；`citations` 边不得触发归并 |
| `expected_merged.example.json` | 全链路期望输出片段（W001、W003 两条 + summary） | 由脚本在合成数据上真实运行生成，共 11 条 canonical 的片段 |

## 预埋断言对应（selfcheck）

- A1：P1、P2 两对 DOI 重复 → `T1_DOI_EXACT` 自动归并；
- A2：P3 跨标识符对（PMID-only × DOI-only）→ 仅凭引用图别名 `T1_ID_CROSSREF` 归并；
- A3：P9 无标识符同题名同年份同首作者 → `T2_TITLE_YEAR_FIRSTAUTHOR` 归并；
- A4：P4a(2019)/P4b(2023) 同题名不同年份 → `NON_DUP_YEAR_MISMATCH`，不并；
- A5：P5a/P5b 模糊相似（Jaccard≈0.89、作者重合 0.5、年份差 1）→
  `T3_FUZZY_ARBITRATE` 进仲裁队列，绝不自动合并。
