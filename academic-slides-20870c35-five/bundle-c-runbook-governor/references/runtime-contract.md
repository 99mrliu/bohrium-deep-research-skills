# 运行时契约：输入布局、result.json 语义与诚实规则

本文件是 deck-runbook-governor 对运行时契约的规范化解读，供 Agent 在六个阶段中随时对照。

## 1. 输入布局（只读）

| 路径 | 内容 | 处置 |
|---|---|---|
| `/input/case.json` | 案例契约：`case_id`、`output_contract`、可能的 work_order / slide_workorder | 由 `contract_init.py` 防御性解析，模型只读其产物 `contract.json` |
| `/input/task.md` | 任务说明（听众、时长、场合等自然语言要求） | Phase 1/2 通读，与 work-order 交叉印证 |
| `/input/` 下材料 | 真实 PDF / PPTX / 文本 / 图，**无预提取答案层** | 必须读真实文件，不得从文件名推断内容；材料 SHA-256 已入 contract.json |
| 模板 / 起始 deck | 真实 PPTX（可能有） | Phase 3 在其内构建；缺失按异常处置降级 |

## 2. 输出布局

| 路径 | 内容 |
|---|---|
| `/app/work` | 中间产物：逐页文本、mainline.json、storyboard.json、toolchain.txt、checkpoints/ |
| `/app/output` | 最终交付：`result.json`、`contract.json`、`budget_ledger.json`、可编辑 deck、导出预览（PDF/PNG）、content map |

运行时的 deck/PDF 等二进制产物由平台独立留存，不受 Skill 资源"纯文本"约束；但 Skill 仓库本身不得含二进制。

## 3. result.json 字段语义

### 3.1 动态契约字段（禁止硬编码）

`output_contract` 的全部根字段必须出现在 result.json 顶层，字段名由 `contract_init.py` 从实际 case.json 动态读出并写入 `contract.json` 的 `output_contract.top_level_fields`——Agent 不得凭记忆书写任何字段名。骨架阶段全部以 `"PENDING"` 占位，各阶段用真实值替换。

### 3.2 固定区块

| 字段 | 语义 |
|---|---|
| `case_id` | 与 case.json 完全一致（D1） |
| `status` | 受控词表 `completed` / `partial` / `blocked`（D5） |
| `sources` | 实际使用的材料数组，每条含 `id` / `title` / `locator` |
| `uncertainty` | 不确定性与假设数组（work-order 缺字段时的假设必须在此声明） |
| `limitations` | 限制数组；`partial` 下非空（D4），空契约字段须逐项在此点名（D2） |
| `blocked_reason` | 仅 `blocked` 时必须非空（D4）：缺什么、停在哪 |
| `change_log` | 变更记录数组，每条恰含 `file` / `what` / `why` / `rollback` 四个非空字符串键（D6）；`rollback` 写可回滚到的 checkpoint 名或"重新生成该文件" |
| `exceptions`（若契约要求） | 异常与降级记录：类型、识别方式、处置、影响 |

### 3.3 产物路径

契约中的产物字段（editable deck / export preview(s) / content map）取**相对 `/app/output` 的相对路径**：字符串、字符串数组、`{"path": ...}` 或 `{"paths": [...]}` 均可被 D3 解析。绝对路径与越出 `/app/output` 的路径直接判负。产物文件必须真实存在且非空（D3）。

## 4. 诚实状态三条铁律

1. `completed`：全部契约字段非空非占位、产物真实落盘、`sources` 非空。
2. `partial`：允许契约字段留空数组/空串，但 `limitations` 必须**逐字段**写明原因，`uncertainty` 不得为空。
3. `blocked`：仅当材料/环境根本性不可用时使用；`blocked_reason` 写清缺什么、停在哪；D2/D3 豁免，D1/D4/D5/D6 仍检查。

任何情况下不得为通过门控而填充无依据内容；宁可 `partial` 也不伪造 `completed`。删除 `limitations` 凑 completed、编造 `sources` 凑 D4、把 PENDING 改成空串绕 D2，都是直接摧毁可核验性的行为。

## 5. 退出码约定（全部脚本一致）

| 退出码 | 含义 | 处置 |
|---|---|---|
| 0 | 通过 / 成功 | 进入下一步 |
| 1 | 门控违例 / 操作失败 | 读 stdout 逐项清单（D 编号 / 篡改文件名），修复后重跑 |
| 2 | 用法 / IO / 模式错误 | 检查参数、路径、JSON 合法性；contract_init 此时已写出 blocked 骨架 |

## 6. 确定性

`contract_init.py` 与 `delivery_gate.py` 无随机数、无时间戳，同一输入重复运行字节一致、判定一致；可反复复核。`checkpoint.py` 仅 manifest 的 `saved_at_*` 为人读时间戳，不参与判定。
