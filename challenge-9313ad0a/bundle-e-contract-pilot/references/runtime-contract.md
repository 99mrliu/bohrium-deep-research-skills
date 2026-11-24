# 运行契约全文（/input → /app/work → /app/output）

本文件陈述 contract-pilot 技能所理解与执行的全部运行契约。该契约是评测环境（DeepSeek Harness 类运行器）与代理人之间的接口约定；任何产物在交付前均须满足本文条款。

## 1. 目录与文件角色

- `/input/case.json`：案例定义。必备信息为案例标识（`case_id` 或 `id`）与输出契约（`output_contract`，字段名列表或"字段→规格"字典）；材料以 `materials` 或 `material_files` 给出，元素为路径字符串或含 `path` 键的对象。
- `/input/task.md`：自然语言任务说明。其语言决定 result.json 中说明性文字（如 partial_reason）的语言。
- `/input/` 下其余材料文件：案例的真实素材，路径以 case.json 登记为准。
- `/app/work`：过程工作区。放置 work_plan.md、intake_manifest.json、中间稿与临时文件。工作区内容不参与交付评分，但应保留以便复核。
- `/app/output`：交付区。最终必须包含 result.json；本技能另要求 change_record.md 与 contract_audit.json；契约产物文件（如导图文件、证据映射）亦放置于此。

## 2. result.json 字段语义

| 字段 | 语义 |
| --- | --- |
| `case_id` | 与 case.json 完全一致，逐字符相等；缺失 case.json 时为 "unknown" |
| `status` | success / partial / unable_to_determine / refused 四值之一，定义见 status-taxonomy.md |
| 契约字段（逐字段） | output_contract 指定的每个字段必须存在；未完成时为占位值 "__pending__"（列表型字段为 []）；完成时为真实值（路径、结构化对象或文本） |
| `sources` | 实际使用的材料/来源路径列表；只登记真正被内容使用的来源 |
| `uncertainty` | 非空字符串列表：材料缺口、冲突、推断依据不足、需人工确认之事项；无则空列表 |
| `contract_fields` | 契约字段名快照，供 checkpoint 校验 --set 与 --artifact 的合法性 |
| `artifacts` | 已登记产物：[{"name","path","exists","bytes"}]；exists 与 bytes 由脚本按文件系统实测 |
| `partial_reason` | 仅 partial 状态必备：以精确语言说明"完成了什么、缺什么、为什么缺" |

## 3. 过程不变量

1. **先落盘，后计算**：任何实质计算开始前，/app/output/result.json 已存在且为合法 JSON，状态为 partial，全部契约字段已占位。
2. **单调改进**：result.json 只允许"占位 → 实值"与"uncertainty 增/删"两类变化；不得把已填实值改回占位。
3. **变更留痕**：每次 checkpoint 向 change_record.md 追加一行单调序号记录；序号不复位、不使用时间戳，以保证确定性。
4. **状态诚实**：success 仅当全部契约字段非占位且无契约违例；无法满足时保持 partial 并精确说明限制。
5. **缺口显式化**：材料缺失、来源冲突、需人工确认事项必须出现在 uncertainty 中，禁止静默忽略。

## 4. 为什么 900 秒预算下"尽早 partial"至关重要

评测运行器按墙钟时间强制终止进程。若结果仅在流水线末端一次性写出，则任何超时、请求耗尽或异常崩溃都会使交付为空——等价于零分，且丢失全部已完成工作。相反，若首份 partial 在第 60 秒前落盘，并在此后每个检查点原地改进：

- 任意时刻被终止，交付区都有一份**状态诚实、字段齐备（含占位）、限制已声明**的 result.json；
- partial 的评分通常显著高于缺失或非法 JSON；诚实的 partial 也优于虚假的 success（后者在审计与复核中会被识别并惩罚）；
- 原地改进策略使"完成度"成为时间的单调函数，预算切割点（何时停止改进）可依据剩余时间机械决策，而不依赖运气。

因此本技能把"boot 即写 partial"设为第一不变量，把"最终对账通过或诚实 partial"设为交付判据。
