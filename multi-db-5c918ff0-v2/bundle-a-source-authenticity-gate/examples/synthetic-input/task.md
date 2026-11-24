# 任务说明（合成教学示例）

> 本文件属于 `synthetic-source-gate-001`，全部为**合成教学数据**，非官方赛题答案。

围绕研究问题“虚拟配体 XQ-7 对虚构激酶 SynthKinase-2 的选择性抑制是否已有文献报道”，
组织方（虚构地）提供了三个数据库的离线检索响应、一份保留的引用图，以及组织方本地的
增量导入状态。

你的任务：

1. 在**任何**归一化、去重、合并之前，先对每一份材料工件做真实性门控
   （本 bundle 的 `scripts/source_gate.py` 即执行此步骤）。
2. 输出每件工件的判定（trusted / trusted_with_warnings / quarantined）与机器可读原因码。
3. 仅允许来自可信（含带警告可信）工件的记录进入 `gated_records.json`。
4. 对引用图悬挂边、导入状态不可核验/不一致条目给出声明而非沉默丢弃。
5. 交付 `/app/output/result.json`，包含 `case_id` 与全部 `output_contract` 字段；
   无法诚实填写的字段置 `null` 并列入 `unresolved_contract_fields`。

已知材料中埋有刻意缺陷（hitCount 与结果数不符、导入状态引用了源响应中不存在的标识符、
引用图存在悬挂边），门控应当捕获并如实报告它们。
