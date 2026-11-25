# 契约门禁规则（validate.py 的判定依据）

设计原则：门禁与管线**相互独立**——validate.py 不 import pipeline.py 的任何函数，
只读 `/input/case.json` 与 `/app/output` 的产物文件。第三方可不看管线、只凭本规则
复核任何一次交付。

## 逐项规则

| ID | 规则 | 失败时的典型原因 | 修复方式 |
|-|-|-|-|
| C1 | result.json 存在且为 JSON 对象 | 管线未运行或中断 | 先跑 pipeline.py；中断时至少交付 probe 的骨架 |
| C2 | case_id 与 case.json 一致 | 串案例（复制了别的案例的产物） | 清空 /app/output 重跑 |
| C3 | output_contract 每个字段都出现且非 null | 契约被忽略、字段硬编码 | pipeline 动态读契约，重跑即可 |
| C4 | 空容器字段（[]/""/{}）必须有说明 | "忘了写"与"确实没有"无法区分 | 在 uncertainty 或 field_notes 写明原因 |
| C5 | status ∈ {complete,partial,blocked}；complete ⇒ uncertainty 为空 | 状态虚报 | 按 references/status-machine.md 重定状态 |
| C6 | sources 中 kind=file 的引用真实存在 | 路径写错、引用了 work 中间产物 | 改为 /input 相对路径 |
| C7 | candidates 每条含 rid/title/source，rid 可回溯台账 | 候选集与台账脱节（手工编辑产物） | 候选集只从 ledger 派生，重跑 |
| C8 | uncertainty 是非空字符串列表 | 结构化对象混入、空串占位 | 每条写成一句人话 |

## 为什么是这八条

C1–C3 对应"交付了什么"（契约完备性）；C4–C5 对应"说的是否实话"（诚实性）；
C6–C7 对应"能否被第三方复核"（可回溯性）；C8 是表达卫生。八条全部可复算，
不依赖任何模型判断——这是门禁与"自查清单"的本质区别。

## field_notes 约定

`field_notes` 是 result.json 中的字典：键为留空的契约字段名，值为一句原因说明。
它解决一个真实歧义：**空字段既可能是"没有"，也可能是"漏了"**。门禁 C4 强制两者
必居其一的书面说明，杜绝静默空字段。
