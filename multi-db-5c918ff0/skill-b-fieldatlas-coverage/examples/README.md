# examples/ — 合成示例数据（声明：全部虚构）

**本目录下所有数据均为程序合成的虚构示例（synthetic fixtures），不是真实案例、
不是真实文献，所有 DOI、PMID、PMCID、期刊名、人名、机构名均为虚构占位
（`10.55123/synth.*`、`99001xxx` 等），与任何真实出版物无关。**

这些文件唯一用途是供 `scripts/selfcheck` 在离线环境跑通全链路并断言关键行为：

- `case.json` / `task.md`：合成案例壳（含 output_contract）；
- `raw_crossref.json` / `raw_europepmc.json` / `raw_publisher.json`：三个来源的
  合成原始响应，共 19 条记录、对应 9 篇虚构论文。其中刻意构造：
  - 1 条仅 Crossref 收录（`10.55123/synth.0008`）→ 单库独有；
  - 1 条仅 EuropePMC 收录且 `authorString` 为空字符串（pmid 99001234）→
    authors 字段 unknown 案例；
  - 1 条 EuropePMC 记录 `pubTypeList` 含 `Retracted Publication` → 撤回标记案例；
  - 同一条记录（pmid 99001234）`journalInfo.journal` 嵌套缺失 → schema 漂移案例；
  - `license` 字段在三个来源的全部记录中均不存在 → 系统性缺口案例；
  - Crossref 响应整体不含 `abstract` 键 → not_provided（响应载荷层面）案例；
  - publisher 侧 DOI 大写、题名带句点 → 小写化与归一题名聚类案例；
  - Crossref `published-print` 与 `published-online` 不一致 → 语义告警案例。
- `import_state.json`：合成本地导入状态，2 条已导入；其中 `L-0002` 的
  issue=1 与新材料 issue=2 冲突 → conflicting_updates 案例。
- `coverage_matrix.example.json`：`selfcheck` 的回归基线（由本 bundle 脚本
  在合成数据上真实运行所得的输出快照）。

预期汇总：unique papers = 9；crossref=7 条、europepmc=7 条、publisher=5 条；
单库独有 = 2（crossref 1 + europepmc 1）；系统性缺口字段 = [license]。
