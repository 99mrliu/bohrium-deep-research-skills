# 真值源与处置策略（references/truth_source_policy.md）

## 真值源等级

| 等级 | 来源 | 可支持的结论 |
|---|---|---|
| T1 | 案例本地留存的 Crossref 响应（`message` 结构） | 标识符解析、题录字段、撤稿 relation |
| T1 | 案例本地留存的 EuropePMC 响应（`resultList` 结构） | 标识符解析、题录字段、pubType 撤稿 |
| T2 | 出版商页面留存快照 / 题录导出文件 | 题录字段佐证（不单独支持撤稿结论） |
| T3 | 综述参考文献列表、专家清单 | 仅支持"该文献被来源引用"，不支持任何元数据真实性结论 |

规则：

1. 核验结论只可由 T1 级来源独立支持；T2/T3 仅作佐证。
2. 本地无任何 T1 响应覆盖的记录 → `verification_status=unverified_no_local_response`，保留在分母中但列入 result.json 的 uncertainty，禁止写成"已核验"。
3. 不发起实时远程请求补核；本任务明确禁止实时覆盖度与"最新发表"声明，远程核验结论与案例快照时间不一致，反而引入不可复算性。
4. 撤稿结论：T1 单渠道标记即可 exclude，但若只有 T2 线索则 `needs_manual_review`，不静默排除。

## 处置（disposition）一览

| disposition | 触发 | 对分母的影响 |
|---|---|---|
| include | 核验通过或无需处置 | 计入 |
| exclude_retracted | T1 撤稿标记 | 不计入分母，写入 exclusions |
| identifier_conflict | 标识符解析到不同文献 | 保留记录、不参与可信命中，列入 uncertainty |
| flag_keep_unverified | 无 T1 覆盖 | 计入分母，列入 uncertainty |
| flag_keep_no_fulltext | 全文不可得 | 计入分母（题录级核验仍有效） |
| merged_into:Rxxx | 重复记录 | 合并入保留记录，台账可查 |

## 冻结与变更

`reference_set.json` 一经写出即冻结（`refset_version` + `content_sha256`）。
运行中任何后续修正（人工裁定、材料补充）必须：

1. 追加 `change_log` 条目（时间戳、事件、原因、影响 ref_id）；
2. 提升版本号（v1.0.0 → v1.1.0）并重新计算内容哈希；
3. 覆盖率报告引用新版本，旧版本产物保留不删。
