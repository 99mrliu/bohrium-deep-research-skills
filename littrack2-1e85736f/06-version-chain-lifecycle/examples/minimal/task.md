# 任务说明（synthetic 演示案例）

> 本文件与 materials/ 下全部快照均为**合成数据**（synthetic），仅为演示
> version-chain-lifecycle Skill 的行为而编造，不对应任何真实文献。

对 `materials/` 下的三个题录快照执行版本链生命周期管理：

1. 抽取全部题录记录（兼容 Crossref `message.items`、Europe PMC
   `resultList.result`、顶层 list 三种布局）。
2. 把同一研究成果的预印本、正式版、修订版、撤稿声明合并为版本链：
   - `2401.00001v1`（arXiv 预印本）与 `10.1234/jcat.2024.0001`（Crossref
     正式版，经 `relation: has-preprint` 相连）必须合并为**一条链**，
     预警分类为 `version_update`，**不得**再产出 `new_work`。
   - `2402.00002v1` 与 `2402.00002v2` 合并为一条修订链（`version_update`）。
   - `10.1234/jmat.2023.0999` 与其撤稿声明 `10.1234/jmat.2024.1000`
     （经 `relation: is-retraction-of` 与 `update-to: retraction` 相连）
     合并为一条链，生命周期状态 `retracted`，预警 `retraction_notice`，
     优先级 `critical`，必须排在 alerts 首位。
   - `10.5678/neur.2024.0777` 为窗口内全新成果（`new_work`）。
   - `PPR999001` 无 DOI、无 arXiv id、无版本关系，无法验证成链，
     按单记录链处理并进入 `unresolved`，整体 `status` 降级为 `partial`。
3. 每条裁决与每条链接决策都要带 locator（材料文件名 + JSON 指针）。
4. 最终按 `case.json` 的 `output_contract` 装配 `output/result.json`。
