---
name: recalc-verify-engine
description: 派生量重算验证（recomputation-based numeric verification）。当学术写作任务给定原始表格数据（CSV/TSV）并要求撰写或核验结果段、摘要、图注，且稿件中的均值、标准差、百分比变化、比值等派生数字必须真实可复算时触发。核心能力：脚本从原始表格确定性重算一切可计算派生量（n/mean/median/SD/SEM/min/max、组间差值、比值、百分比变化），每条派生量附 formula 与 inputs 溯源；成稿后逐数字做三态核验——材料原文直接命中为 RAW-SUPPORTED，与重算值在容差内（按上下文语义就近匹配派生量类型）为 DERIVED-SUPPORTED，其余为 UNSUPPORTED 并给出最接近的重算值；材料未给出的 p 值标 UNSUPPORTED-PVALUE（环境不算 p 值，绝不伪造显著性）。红线：稿件中的派生数字必须能指回某条重算记录（含公式与输入）；UNSUPPORTED 一律删除、改写为账上数字或标【待确认】；趋势描述不得写成因果。不适用：无表格数据的纯定性写作、需要统计推断检验（t 检验/方差分析等）的任务（本 skill 只做描述性重算，不做推断）。
---

# 重算验证引擎（Recalc-Verify Engine）：先重算，后写作，再对账

一句话定位：**稿件里的每个派生数字都要能指回一条带公式与输入的重算记录**。
与字符串级数字对账的本质区别：本 skill 从原始数据**重新计算**派生量，验证的是计算过程的可复现性，而不只是文本匹配。

## 0. 运行契约

- 输入：`/input/case.json`（含 case_id 与 output_contract）、`/input/task.md`、材料文件（CSV/TSV/MD/TXT 等；找不到 case.json 时遍历 /input）。
- 工作区 `/app/work`，交付区 `/app/output`。
- `result.json` 必须原样包含 case.json 中 output_contract 的全部字段与 case_id，并含诚实的 status、sources、uncertainty、change records；无内容的字段填 `"PENDING"`，不删字段、不编内容。
- 脚本仅 Python3 标准库，确定性、秒级完成。预算 64 次请求 / 900 秒。

时间表（900 秒预算）：
- 0–2 分钟：`recalc.py` 摄入全部表格并重算派生量；
- 2–20 分钟：模型读 `recalc_table.md` 与材料原文写作，数字一律先查账；
- 20 分钟起：`verify_draft.py` 三态核验 → 修补 → 复验（最多 3 轮）；
- **35 分钟前必须已交付一版**（哪怕 UNSUPPORTED 未清零，也先交付并如实标 partial）。

## 1. 运行流程（命令可直接复制）

```bash
SKILL_DIR=<本 SKILL.md 的绝对目录>
python3 "$SKILL_DIR/scripts/recalc.py" --input-dir /input --output-dir /app/work
# 读 /app/work/recalc_table.md（重算表）与 derived_values.json（机器可读账）
# 写作 /app/work/deliverable.md —— 数字只能来自材料原文或重算账
python3 "$SKILL_DIR/scripts/verify_draft.py" \
    --draft /app/work/deliverable.md \
    --input-dir /input \
    --derived /app/work/derived_values.json \
    --case /input/case.json \
    --output-dir /app/output
# 按 /app/output/verify_report.md 修补，重跑直到 UNSUPPORTED=0（或全部标【待确认】）
```

任务结束的唯一标准：`verify_report.md` 中 UNSUPPORTED 与 UNSUPPORTED-PVALUE 数量为 0，
或每一条都已被删除、改写为账上数字，或显式标注【待确认：原因】并登记在 change_log。

## 2. 三态核验语义

| 判定 | 含义 | 处置 |
|---|---|---|
| RAW-SUPPORTED | 数字在材料原文行中直接命中（含行号定位） | 可保留 |
| DERIVED-SUPPORTED | 与某条重算值在容差内匹配（默认相对容差 0.5%，并按上下文语义就近限定派生量类型：均值/SD/百分比变化等） | 可保留，evidence 注明公式与输入 |
| UNSUPPORTED | 原文与重算账均不匹配；报告给出最接近的重算值 | 删除、改写为账上数字，或标【待确认】 |
| UNSUPPORTED-PVALUE | 形似 p 值的数字在材料中查不到 | 必须删除或标【待确认】；本环境不计算 p 值 |

## 3. 写作规则（模型侧）

1. 只写账上有的数：材料原文行，或 `derived_values.json` 中带公式与输入的派生量。
2. 派生数字保留合理有效位数；容差判定按重算值有效位数舍入后比较，誊写舍入不会误报。
3. 百分比变化必须带基线（基线均值也要在账上）；趋势不写成因果；材料写"显著"才能写"显著"且须带材料给出的检验方式与 p 值。
4. 无 CSV 材料时引擎如实降级为"仅原文数字核对"（无重算账），在 result.json 的 uncertainty 中说明。
5. 每处删除/改写/标注都在 change_log 留一条（动作、原因、依据）。

## 4. 异常处理

- 材料无表格数据：`derived_values.json` 为空账，核验退化为 RAW 核对，报告如实标注。
- 单列无数值列 / 全缺失列：profile 中记缺口，不臆造统计量。
- 同值不同义误配（如"均值 4.79"误中 max=4.8）：核验按上下文语义线索就近限定派生量类型（见 references/recalc-method.md）。
- 材料间同一量两个数：正文采用其一时 change_log 记录取舍理由；无法裁决标【待确认】。
- 多分组：以组在数据中首次出现顺序的第一组为基线，报告中显式注明。

## 5. 最小调用示例

见 [examples/README.md](examples/README.md)（**合成示例，非正式案例结果**）：
输入为虚构的两组重复测量 CSV 与一份故意含四类数字（原文数、正确派生数、
错误派生数、编造 p 值）的草稿，演示三态核验全流程与 `result.json` 装配。

## 6. 文件导览

- `scripts/recalc.py`：CSV/TSV 摄入、列类型判定、派生量重算（输出 recalc_table.md / derived_values.json / dataset_profile.json）。
- `scripts/verify_draft.py`：三态数字核验、verify_report.md、装配契约化 result.json。
- `references/recalc-method.md`：公式定义、容差规则、语义就近匹配、已知限制。
- `references/writing-rules.md`：模型写作规则与留痕要求。
