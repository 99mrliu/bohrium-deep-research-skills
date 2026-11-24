# 编辑操作 DSL 规范（Skill C 核心资源）

诊断的产物不是改写稿，而是一组**可机器校验、可模拟应用**的编辑操作（edit ops）。每条 op 对应一处结构诊断，作者逐条圈定后执行。

## 1. 通用字段

| 字段 | 说明 |
|---|---|
| `id` | `OP001` 起顺序编号 |
| `op` | 操作类型（下表八种之一） |
| `finding_id` | 对应的诊断 finding（可溯源到六维分类） |
| `rationale` | 一句话说明结构理由，可证伪 |

## 2. 八种操作与前置条件

| op | 语义 | 额外字段 | 机器前置条件 |
|---|---|---|---|
| `move` | 把块移到另一块之后 | `target`, `after` | 两块 ID 均存在 |
| `merge` | 把块并入另一块末尾 | `target`, `into` | 两块 ID 均存在 |
| `split` | 从指定句子处把块拆成两块 | `target`, `at_quote` | `at_quote` 逐字在 target 内 |
| `narrow` | 收窄过强论断 | `target`, `quote`, `replacement` | `quote` 逐字在 target 内；`replacement` 不得引入新材料外事实 |
| `delete_duplicate` | 删除逐字重复块 | `target`, `duplicate_of` | 两块文本空白归一后完全相等，否则模拟器拒绝 |
| `insert_transition` | 在某块前插入过渡句 | `before`, `sentence` | `before` 存在；`sentence` 只起衔接作用，不含新事实 |
| `reorder_section` | 整节（标题块至下一同级标题前）移动 | `target`(标题块), `after` | target 必须是标题块 |
| `add_limitation` | 在某块后插入限制说明 | `after`, `sentence` | `sentence` 只能陈述材料中已给的限制条件 |

## 3. 纪律

1. **诊断先行**：先完成六维诊断（finding），再把每条可修复 finding 翻译成 op；一个 finding 可产多条 op，一条 op 必须指回一个 finding。
2. **无 op 不交付**：finding 若没有对应 op，只能是「需人工确认」类，并在 uncertainty 说明。
3. **不另起改写稿**：全文重写让作者无从对照，本 DSL 的存在就是为了避免它。`narrow` 的 `replacement` 只允许句级收窄，不允许段落级重写。
4. **顺序有意义**：ops 按执行顺序排列，结构级（reorder/move/merge/delete）先于句级（narrow/insert）；见 phasing.md。
5. **模拟验证**：`apply_editops.py` 全部 `applied` 才可交付；`skipped` 的 op 修正或撤下。
