# 阶段协议（stage protocol）

## 阶段定义

| 阶段 | 目标 | required_artifacts（相对 /app/work） | deadline（秒） |
|---|---|---|---|
| intake | 材料清点：列出全部输入材料、可用性、初步判断 | `notes/material_inventory.md` | 120 |
| outline | 章节骨架 + 证据分派表：每章挂哪些材料/事实 | `notes/outline.md`、`notes/evidence_assignment.md` | 300 |
| draft | 完整初稿：允许【待确认】标注，禁止 TODO/XXX 类占位符 | `deliverable.md` | 600 |
| audit | 自查：契约字段齐、无占位符、缺口已标注 | `notes/audit_report.md` | 780 |
| finalize | 装配 result.json 并交付（由 `deliver` 子命令生成产物） | — | 860 |

辅助产物（非门禁必需，但 `deliver` 装配时会读取）：`preserved_facts.json`（list）、
`evidence_map.json`（dict）、`selfcheck_report.md`（由 `selfcheck` 生成）。

## 门禁语义

- **GO**：该阶段全部 required_artifacts 存在、非空、无占位符，且当前秒数 ≤ deadline。
  进入下一阶段。
- **WARN-BUT-PROCEED**：产物齐备但已超 deadline。**不阻塞**。含义：预算纪律已被
  打破，立即以当前最好版本推进，压缩后续阶段；偏差写入 worklog。
- **FAIL**：产物缺失 / 为空 / 含占位符（退出码 1）。补齐后重跑 `check`；时间不足
  则跳过该阶段，FAIL 记录会经 worklog 汇入 result.json 的 `change_log`。
- `【待确认】` 不是占位符：它是合法的不确定性标注，允许存在于 draft 乃至终稿，
  但必须在 result.json 的 `uncertainty` 中有对应条目（装配器自动抽取）。

## 失败处置矩阵

| 失败场景 | 检测点 | 处置 |
|---|---|---|
| 材料缺失或无法读取 | intake | 在 material_inventory.md 标注"不可用"，缺失影响写入 uncertainty |
| 大纲来不及做细 | outline | 降级为最简 3 段式骨架（背景/主体/结论），直接开写 draft |
| 初稿写不完 | draft | 未完段落用【待确认】一句概括收尾，保证 deliverable 结构完整 |
| selfcheck 机器项 FAIL | audit | 修复后重跑；无法修复则记入 uncertainty/change_log，接受 partial |
| result.json 残留 PENDING | deliver（E3） | 每条 PENDING 必须在 change_log 有对应说明，否则出口 FAIL |
| deliverable 含 TODO/XXX 或【】未闭合 | deliver（E4/E5） | 修复后重跑 `deliver`；执意交付则失败项写入 manifest，诚实留痕 |
| 任何时刻进程被杀 | — | init 时已落骨架 result.json + deliverable 占位，即为诚实 partial |

## 留痕约定

- 每次 `init`/`check`/`selfcheck`/`deliver` 调用追加一行 JSONL 到
  `/app/work/worklog.jsonl`：`{ts, stage, verdict, notes}`。
- `deliver` 把 worklog 全量汇入 result.json 的 `change_log`，保证过程可审计。
- `deliver` 生成 `delivery_manifest.json`：输出目录全部文件的
  path/bytes/sha256 + 出口检查结果。sha256 使交付物可核验、不可抵赖。
