# 任务说明（合成示例）

> 本文件是 source-integrity-audit bundle 的**合成示例**任务书，数据均为编造。

在一切文献追踪/增量逻辑之前，对 `materials/` 下组织方本地固化的上游题录快照
做完整性与真实性审计：

1. 为每个源文件建立 SHA-256 内容哈希台账（含字节数、固化时间——取自材料自身
   字段，不得编造）；
2. 校验每条题录的 Schema：title / authors / 日期字段 / 至少一个标识符；
3. 元数据一致性：DOI 语法 `^10\.\d{4,9}/\S+$`、日期合法且不得晚于窗口终点
   （2026-11-21，作为"现在"）、arXiv 号格式、PMID 纯数字；
4. 异常检测：源内重复、未来日期、缺失日期、空标题、撤稿/更正标记、同源
   v1/v2 快照结构漂移、以及与 `previous_snapshot.json`（本地增量导入状态）
   的差异；
5. 输出 `integrity_report.json`、`quarantine` 清单与 gating 决策
   （proceed / proceed_with_quarantine / block），最终组装
   `output/result.json`，必须包含 `case.json` 中 `output_contract` 列出的
   全部字段以及 sources、uncertainty、change_records。

约束：完全离线，不得发起网络请求；所有字段值必须来自材料并给出
locator（文件 + JSON 路径）供复核。
