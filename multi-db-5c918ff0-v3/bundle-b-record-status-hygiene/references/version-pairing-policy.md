# 版本归并政策（preprint ↔ VoR Pairing Policy）

多数据库联合检索中，同一项研究常以 preprint 与期刊正式版（version of
record, VoR）两个身份同时出现。把它们计作两项独立研究，与漏掉撤回一样，
都是**状态卫生事故**。本政策规定何时可以归并、如何归并、归并后如何计数。

## 证据层级（从高到低）

1. **显式关系链接（唯一可自动归并的依据）**
   - Crossref `relation-type == "is-preprint-of"`（本记录是 X 的 preprint）
     或 `"has-preprint"`（本记录有 preprint X），且目标 DOI 能解析到本次
     材料中的另一条记录 → `basis: "explicit"`，自动配对；
   - 双向链接（preprint 端 `is-preprint-of` + VoR 端 `has-preprint`）互相
     印证时为最强证据，去重后仍为同一对。
2. **显式链接但目标缺席**（`explicit_external`）
   - 关系指向的 DOI 不在任何在场材料中 → **不得折叠**，进入
     `pending_review`，在 uncertainty 中声明"另一半缺席"。
3. **书目学回退（bibliographic fallback）——永不自动归并**
   - 条件：规范化标题完全一致 + 第一作者姓氏一致 + 年份差 ≤ 1，且一方带
     preprint 标记（posted-content/subtype preprint、pubType Preprint、
     source PPR）而另一方不带；
   - 满足条件仅进入 `pending_review`（`basis: "ambiguous"`），必须等模型
     以 `merge_version_pair` 或 `split_not_same` 裁定后才折叠/拆散；
   - 理由：标题+作者+年份合谋撞车在真实语料中确会发生，自动归并的风险
     由候选池错误计数承担，不可接受。

## 归并规则

确认一对之后（显式自动，或回退经模型确认）：

- 候选集按**一项研究**计数（`counts_as_studies: 1`）；
- 引用字段（doi、title、year、authors、journal）**以 VoR 为准**；
- preprint 不删除，作为候选条目的 `alternate_version` 保留
  （record_id / doi / source_db / version_role）；
- 任一端若带 severe 状态信号（如 VoR 被撤回），按状态政策处理该端；
  归并不豁免任何一端的状态审查——折叠只发生在两端均通过状态门控之后。

## import_state 撤回条目的治理

- import_state 中 `status ∈ {withdrawn, removed, retracted, deleted}` 的条目，
  其对应记录**必须**排除出候选池并注明 `IMPORT_STATE_WITHDRAWN`；
- 声称已导入但在所有在场响应中不存在的标识符 → `import_inconsistent`：
  隔离该声明（不隔离任何真实记录），在报告与 uncertainty 中如实披露；
- 响应中存在而 import_state 未知的记录 → `not_yet_imported`，仅信息性，
  不影响状态判定；
- 案例中**没有** import_state 材料时，对账为空操作，但必须显式声明
  "无导入状态可核对"，不得默认视为一致。

## 不可核验原则

查不到状态 ≠ 干净。一条记录若在材料内没有任何状态承载面（Crossref 无
`relation`/`update-to` 键、EuropePMC 无 `pubTypeList`、出版商无
`status`/`notice` 字段、引用图无对应节点），其 `status_class` 判为
`unverifiable` 而非 `clean`：**不进入候选池**，列入报告的待补证清单。
本技能绝不联网查询外部撤回数据库；所有状态证据必须能指回材料内部的
显式字段、关系或图状态属性。
