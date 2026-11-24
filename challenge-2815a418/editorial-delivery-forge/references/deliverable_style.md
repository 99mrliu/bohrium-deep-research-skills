# 交付件排版规范（editorial-delivery-forge）

本规范由 `scripts/forge_pack.py` 自动执行；Agent 只需按其结构准备 decisions.json / edits.json，
禁止手工另写交付件（保证同源、编号不漂移）。

## 1. 编号体系（全局唯一）

| 编号 | 格式 | 含义 | 定义处 |
|---|---|---|---|
| 意见子要求 | `R#.#`（如 R1.2） | 审稿意见的最小可回复单元；意见本身记 `R#` | decisions.json `reviewer_decisions[].rid` |
| 修改 | `CHG-##`（如 CHG-03，两位数字） | 一处落在基线正文中的实质性修改 | edits.json `edits[].chg_id` |
| 证据 | `EV-##`（如 EV-01，两位数字） | 一项支撑材料/数据/无法提供的说明 | decisions.json `evidence[].eid` |

交叉引用规则：每个 CHG 必须 `linked_rids` 至少一个子要求；每个 EV 由 CHG 的
`evidence_ids` 引用并在 decisions.json `evidence` 中登记；回复信声称的每处修改
必须能在修订稿中找到同名 CHG 标记（review_pack.html 覆盖矩阵即核查此对应）。

## 2. 修订稿 revised-manuscript.md

- 文首说明块（引用块）：案例号、稿件标题、标记约定、诚实声明、生成时间。
- 正文 = 基线全文 + 内嵌标记：
  - 新增/替换：`⟦CHG-##-BEGIN⟧新文本⟦CHG-##-END⟧`；
  - 删除：`⟦CHG-##-BEGIN⟧【已删除】⟦CHG-##-END⟧`；
  - 无法补做的占位：`【待补数据 EV-##】`（提交前须替换为真实数据）。
- 文末附录「修改摘要表」：`| CHG 编号 | 关联意见 | 位置 | 修改类型 | 修改摘要 |`。

## 3. 回复信 response-letter.md

1. **信头（占位待填）**：稿件编号、稿件标题、通讯作者、日期、责任编辑——留 `＿＿＿＿（待填）`，
   严禁编造真实编号/人名。
2. **称呼与前置声明**：尊敬的编辑与审稿专家；声明基于意见摘要、以原文为准。
3. **一、总述**：只用统计数字（意见数、子要求数、四种裁决各几、落实修改几处、失败几处）。
4. **二、逐条回复**：按意见分节（`### 意见 R1（审稿人 1）`），每个子要求一块，固定五行：
   - 意见要点 / 裁决（接受｜部分接受｜婉拒（附说明）｜无法完成（附说明））/
     回应说明 / 关联修改 / 关联证据。
5. **三、收口表**：表 A 裁决汇总（子要求×裁决×CHG×EV）；表 B 修改—证据对照
   （CHG×子要求×EV×证据状态×位置）。
6. 落款前注明「草案，待通讯作者审定」。

## 4. 修改定位 change-locations.json

每条：`chg_id, action, status, fail_reason, section（最近 markdown 标题）,
line（标记所在行）, anchor_excerpt（锚点前 80 字）, linked_rids, evidence_ids`。

## 5. 证据清单 evidence-checklist.json

每条：`eid, description, status(provided|pending|impossible), status_label, note,
linked_rids, linked_chgs`；附 summary 统计。**pending/impossible 必须如实标注，这是
「未到位证据清单」的核心。**

## 6. 修改记录 change_record.md

落稿状态行 → 一致性警告（如「接受但无 CHG 落实」）→ 逐条 CHG 的
before/after 代码块对照 → 不确定性列表。

## 7. 语言

回复信、批注、表格语言**随审稿意见**（中文意见用中文回复）；专业术语与稿件原文保持一致。
