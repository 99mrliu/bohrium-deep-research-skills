# 输出契约指南（output_contract guide）

本指南说明如何把 case 的 `output_contract` 当作**编译输入**而非记忆负担，以及
PENDING 哨兵约定、诚实 status 语义与预算内的增量交付纪律。

## 1. 如何阅读 case.json 中的 output_contract

- 契约可能位于顶层 `output_contract` / `outputContract` / `contract`，也可能在
  一层嵌套（如 `task.output_contract`）之内。`contract_scaffold.py` 会自动搜索
  这些位置并打印实际来源（stderr 中 `契约来源: ...`），**先核对来源再信任骨架**。
- 契约条目可能是 dict-of-fields（`{"字段": {"type": ..., "required": ..., ...}}`），
  也可能是 list-of-entries（`[{"name": ..., "type": ...}, ...]`），或简写
  `{"字段": "string"}`。脚手架把三种写法归一化为同一份 `contract_schema.json`。
- 契约里声明的 **每一个 required 字段都是交付义务**。契约没写但显然需要的
  `sources` / `uncertainty`，骨架会自动补上——补上不等于可省略。
- 找不到契约时脚手架生成 **fallback 通用契约**（case_id / audit_report /
  evidence / status / sources / uncertainty），并在 schema 中写入
  `"fallback": true` 与警示 note。fallback 是兜底不是免责：必须人工重读
  task.md 确认真实交付要求，必要时手工增补 schema 字段。

## 2. PENDING 哨兵约定

- 骨架中每个契约字段的初值是字符串 `"PENDING::<字段名>"`。它是**机器可检测的
  欠账标记**：`contract_validate.py` 会拒绝任何残留哨兵，除非满足第 3 节的
  partial/failed 例外。
- 填写字段时**整体替换**哨兵值，不要把哨兵拼进正文。
- `pending_reasons` 是一个 `{字段名: 人工理由}` 对象，理由必须是非空、可读、
  具体的句子（例如 `"原文未报告置信区间，无法重算，已标注待复核"`），
  不接受 `"无"` / `"todo"` 这类占位。

## 3. 诚实 status 语义

- **complete**：每一个契约字段都被**真实填好**且通过校验——零 PENDING、
  `pending_reasons` 为空。状态为 complete 而仍有 pending 字段是校验违例。
- **partial**：部分字段未完成，但每个未完成字段都在 `pending_reasons` 中登记了
  人工理由。partial 不是失败，是如实申报进度。
- **failed**：材料不足以支撑契约要求（如论文文本缺失关键章节）。此时**保留已
  确认的部分**（已核实的发现、已读来源），未完成字段走 `pending_reasons`，
  **绝不伪造**其余内容。failed 交付的真实部分必须仍然自洽、可校验。
- 判断不了就先标 `partial`；宁降不升。夸大完成度是本 skill 要消灭的头号
  静默失败。

## 4. 早骨架 / 增量更新纪律（64 次请求 / 900 秒预算）

1. **第一分钟内**运行 `contract_scaffold.py` 生成 schema + 骨架——这是保底
   交付物，此后任何时刻中断都有一份合法的 `result.json`。
2. 每完成一个审查面或填好一个字段，**立即写回** result.json 并存盘；不要
   攒到最后一次请求再写。写文件不占模型请求，拖延才占。
3. findings 有新增就重跑 `render_audit_sheet.py`——三件套（md/html/json）
   同源再渲染，成本一次 bash，漂移代价一次失败。
4. 预算剩余约 1/4 时停止扩展新发现，转入收尾：填 `sources`/`uncertainty`、
   跑 `contract_validate.py`、按 delivery_checklist 终检。
5. 校验违例修复后**必须重跑**校验直到 exit 0（或对仍 pending 的字段如实
   降级 status）。最后一次校验报告 `validation_report.json` 一并留在输出目录。
