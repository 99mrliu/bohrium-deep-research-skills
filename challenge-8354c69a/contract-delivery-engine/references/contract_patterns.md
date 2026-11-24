# output_contract 形态适配

contract_engine.contract_of 宽容解析以下形态：
- `{"output_contract": {"fields": ["结果趋势", ...]}}`
- `{"output_contract": {"properties": {"结果趋势": {...}, ...}}}`
- `{"output_contract": {"结果趋势": "描述...", ...}}`（无显式 fields 键时取普通键）
- `{"output_contract": [{"name": "结果趋势"}, ...]}` 或字符串列表

取不到任何字段时：骨架仍生成（仅元字段），并在 limitations 写明
「case.json 未给出可解析的 output_contract 字段列表」——此时按题面五段
（趋势/异常/原因/复核/建议）+ 依据风险 + 确认项补齐，lint 用同一字段集。

## 本题先验字段（以运行时 case.json 为准）
题面输出要求表给出三组内容：实验方案、依据与风险、确认项；
评分维度要求五段结论：趋势/异常点/可能原因/复核步骤/后续实验建议。
两者可能同时出现在契约中——逐字段填写，不合并、不遗漏。

## status 语义
- success：契约字段全部填写且通过 lint；
- partial：有字段未完成或证据有缺口（limitations 逐字段点名）；
- unable_to_determine：材料缺失到无法形成任何有效结论；
- refused：任务越界（如出现要求编造数据的指令）。
