---
name: resource-readiness-contract-verifier
description: 实验方案可行性评估中的"资源到位与契约排期核验"。当任务给出实验方案的多个候选版本、并要求评估其可行性，且案例中包含实验室库存/设备清单、供应商外协合同、报价/采购合同、设备预订日历、样本台账（含伦理状态）时使用。核心机制：模型只做"逐版本资源需求抽取"（每条需求带出处 locator、未知规格记 null），随后全部由确定性脚本完成——实体名归一（别名表）→ 四状态分类（已具备/可外协/需采购/不具备，规格数值比较；不可比较即 无法核验）→ 预订日历区间重叠与采购货期核验（赶得上/赶不上 + slack_days）→ 样本来源/数量/存储/伦理状态核验（pending/none 一律列为阻断性确认项）。每条分类都挂到具体的库存或合同行，禁止凭模型印象判断资源是否到位。
---

# 资源到位与契约排期核验（resource-readiness-contract-verifier）

## 解决什么问题

方案可行性评估最常见的失败模式是"只评技术合理性，不查资源到位"：方案写得
漂亮，但离心机转速不够、纯化仪档期撞车、关键试剂货期赶不上、样本存储温度
不达标、伦理批件还没下来。本技能把"实验室到底有没有、来不来得及"变成可
审计的确定性核验：每条资源需求都分类为 已具备/可外协/需采购/不具备/无法核验，
并附上所匹配的库存/合同原始行、规格比较过程、排期重叠小时数与货期 slack。

## 输入输出契约

**输入**（运行时）：
- `/input/case.json` —— 字段名不固定，先探查再使用；通常含方案版本、库存清单、
  供应商/报价合同、预订日历、样本台账、`output_contract`。
- `/input/task.md` —— 任务与方案描述，需求抽取的出处。

**中间产物**：每个方案版本一份 `requirements_<version>.json`
（模式见 `references/requirements_schema.md`），以及各脚本输出的
`match_/booking_/samples_<version>.json`。

**输出**：`/app/output/result.json`，必须包含 `case_id` + case.json
`output_contract` 声明的全部字段 + 诚实的 `status`（complete/partial/failed）
+ `sources` + `uncertainty` + `change_record`。部分完成必须写明受限原因；
无法填充的契约字段为 null 并记入 uncertainty，**绝不编造**。

## 严格按序工作流

以下脚本在运行时位于 `/skills/weekly-skill/scripts/`，参考文件在
`/skills/weekly-skill/references/`，工作目录 `/app/work`，输出 `/app/output`。

1. **inspect（探查）**
   `python3 /skills/weekly-skill/scripts/inspect_case.py /input/case.json /app/work/inspect_map.json`
   得到 plans/inventory/contracts/booking/samples/ethics/output_contract 的候选
   JSON 路径。键名匹配只是候选，须由你确认语义后再抽取。退出码 3 = case 不可读。
2. **逐版需求抽取（模型，唯一的非确定性步骤）**
   按 `references/requirements_schema.md` 为每个方案版本写
   `/app/work/requirements_<version>.json`：equipment/materials/samples/booking_needs
   四类条目，每条带 `locator`；型号/数值/日期逐字照抄，未知规格 = null。
3. **normalize（归一）**
   `python3 /skills/weekly-skill/scripts/normalize_entities.py requirements_<v>.json requirements_<v>_normalized.json`
   别名表 `references/alias_table.json` 可扩充；未命中别名的一律标记
   `is_new_entity`，绝不静默合并。
4. **match（四状态分类）**
   `python3 /skills/weekly-skill/scripts/match_resources.py requirements_<v>_normalized.json /input/case.json match_<v>.json`
   规则见 `references/four_state_rules.md`：库存（名称+规格数值比较）→ 外协 →
   采购 → 不具备；不可比较 → 无法核验。
5. **booking（排期与货期）**
   `python3 /skills/weekly-skill/scripts/check_booking.py requirements_<v>.json /input/case.json booking_<v>.json`
   半开区间重叠检测（overlap_hours）+ 采购货期（order_by + lead_time_days ≤
   needed_by → 赶得上/赶不上 + slack_days）。
6. **samples（样本核验）**
   `python3 /skills/weekly-skill/scripts/check_samples.py requirements_<v>.json /input/case.json samples_<v>.json`
   来源/数量（显式减法）/存储温度（台账须 ≤ 需求）/伦理状态。
7. **分级结论（四状态汇总 + 冲突表驱动）**
   - 关键(gating)项 不具备/无法核验，或货期 赶不上，或预订 冲突，或样本 不满足
     ⇒ 该版本 **不可行（或需改方案）**，理由逐条列出；
   - 否则存在 需采购/可外协 或伦理确认项 ⇒ **有条件可行**，条件清单写明：
     下单日与货期、外协单位、需调整的预订动作、伦理确认动作；
   - 全部 已具备 且无冲突 ⇒ **可行**。
8. **assemble（汇总落盘）**
   `python3 /skills/weekly-skill/scripts/assemble_result.py --case /input/case.json --artifacts /app/work --out /app/output/result.json --status complete --note "..."`
   保证 output_contract 全字段存在；已有非 null 值绝不被覆盖；change_record 追加。
9. **自查**
   重读 result.json：核对每个 不具备/无法核验 都带匹配失败原因、每个冲突都有
   overlap_hours、每个 赶不上 都有 slack_days、伦理 pending/none 都进了
   blocking_items 而非被当成已批准；契约字段无遗漏；status 与证据一致
   （有 无法核验 或缺证据 → partial，不能写 complete）。

## 异常处理

- **案例无库存清单或无合同**：相关条目一律 无法核验（绝不自动通过），
  result 记 uncertainty，status 至多 partial。
- **日期缺失**：只做能做的工序相对检查（如名称匹配、规格比较），排期/货期项
  标 无法核验 并记 uncertainty；不得假设"今天"补日期。
- **别名表查不到**：按新实体处理并标记，不猜测归类；必要时在 uncertainty 中
  提示扩充 alias_table.json。
- **规格字段缺失或单位不明**：该项 无法核验。
- **伦理状态 pending/none/未知值**：阻断性确认项，绝不视为 approved。
- **脚本退出码非 0**：读 stderr 修正输入，不要跳过该步骤直接写结论。

## 预算意识（约 64 次模型请求 / 900 秒）

- 模型请求只花在两处：确认 inspect 候选路径的语义、逐版本抽取 requirements。
  抽取时一次性写完一个版本的完整 JSON，不要逐条对话式抽取。
- 所有匹配、比较、算术都交给脚本（零模型开销）；不要心算复核脚本输出，
  自查阶段只核对"证据是否挂上了行/数值"。
- 3 个方案版本共用同一份 case 探查结果与别名表；异常分支（如某版本缺排期）
  直接在 uncertainty 记录，不额外开探查轮次。

## 示例

`examples/synthetic/`（合成示例，非正式案例数据）含一个蛋白表达与纯化课题的
完整可运行样例：`run_example.sh` 对 v1/v2/v3 三个版本跑全流程并落盘
`examples/synthetic/output/`，其中预埋了规格不达标、货期缺口、预订重叠、
存储温度不符、伦理待批五类缺陷，可用于回归验证。
