---
name: upstream-forensics-gate
description: 面向「实验结果解释与异常分析」的上游数据真实性取证门禁。在解释任何实验数据之前，先对 /input 做文件级与数值层取证（完全重复文件、行级重复、饱和截断、常量列、单位歧义、跨文件数值重叠、xlsx 隐藏 sheet、MATLAB 参数对照），输出带阈值的取证报告与契约驱动 result.json。当任务要求解释实验结果且结论必须建立在可信输入上时触发。
---

# upstream-forensics-gate：上游数据真实性取证门禁

## 用途与重心

本 Skill 的重心是**上游数据真实性**。解释类任务最隐蔽的失败是「在不可信的输入上给出通顺的解释」：重复导出的曲线被当成平行重复、量程截断被当成材料性能平台、单位歧义被静默择一。本 Skill 把取证前置为**门禁**：F1–F8 八项确定性检查先跑，任何 finding 都必须被逐条处置（确认/排除/降级结论），下游五段结论（趋势/异常/原因/复核/建议）才允许定稿。

**边界**：
- 只做取证与门禁，不替代统计判读与原因分析；finding 是「嫌疑对象 + 阈值 + 定位」，定性由 Agent 回原始文件确认。
- 不修改、不删除任何输入文件；所有检查只读。
- 禁止编造测量值或把 finding 直接写成结论；单位歧义必须保留并显式标注。
- 纯 stdlib（xlsx 用 zipfile+xml 只读结构盘点）。

## 运行时契约

- 输入：`/input/case.json`（含 `case_id`、`output_contract`）、`/input/task.md`、案例材料。
- 工作目录 `/app/work`；成果目录 `/app/output`，必须含 `result.json`（原始 `case_id`、契约全部字段、诚实 `status`、`sources`、`uncertainty`、`change_records`）。
- 预算：约 64 次模型请求 / 900 秒 / 每响应 16384 tokens。**partial-first**：第一步即落骨架。
- 脚本路径按 `/skills/weekly-skill/scripts/` 书写；安装路径不同则逐字替换前缀。`python3` 直接运行。

## 一键管线

```bash
python3 /skills/weekly-skill/scripts/run_gate.py --input /input --work /app/work --output /app/output
```

产出：`forensics_report.json`（F1–F8 全量 + 阈值声明 + findings 汇总 + verdict）、
`authenticity_brief.md`（人读简报）、`result.json`（取证相关契约字段预填，其余点名待撰写）、`report.md`。

**门禁规则（强制）**：
1. `verdict=PASS_WITH_FLAGS` 时，`status` 不得直接 `success`——须在 `limitations` 或结论中逐条处置每个 finding（确认其影响/排除其为伪迹/将受影响结论降级），之后才可置 success。
2. Agent 撰写的每条下游结论，若其证据涉及某个 finding 的对象，必须写明「该结论不受 finding Fn 影响，因为…」或「已据此降级」。
3. 交付前必须通过：

```bash
python3 /skills/weekly-skill/scripts/gate_result.py check \
  --case /input/case.json --out /app/output/result.json
```

## 八项取证检查

| ID | 检查 | 判定阈值 |
|-|-|-|
| F1 | 文件谱系与完全重复文件 | 全文 sha256 相同 |
| F2 | 行级重复 | 数据行全部数值列完全相同 |
| F3 | 饱和/截断 | 同列相同读数连续段 ≥5 |
| F4 | 常量/退化列 | 列内取值唯一（方差 0） |
| F5 | 单位歧义 | 同一物理量关键词对应多个单位记号 |
| F6 | 跨文件数值重叠 | 两文件数值集合（6 位小数）完全一致 |
| F7 | xlsx 结构 | 隐藏 sheet（state≠visible）登记 |
| F8 | MATLAB 参数对照 | 脚本引用文件名须与实到文件对应 |

阈值可在 `forensics.py` 顶部常量调整；调整后须在结论中引用实际所用阈值。

## 异常与失败处理

- 编码/分隔符导致解析失败：按 stderr 与文件头修正理解后重跑；不手算替代。
- PDF 不做语义解析（本题 PDF 无预提取层）；如需 PDF 数值交叉，用系统 `pdftotext` 转文本后放入 /input 扫描范围外单独处理，并在 sources 登记。
- 材料缺失、无法判断、运行失败分别用 `unable_to_determine`、partial + limitations、`change_records` 记录失败命令与 stderr。

## 最小示例

`examples/`（**合成示例**）：合成一组含完全重复文件、行内重复、饱和段、常量列、单位歧义的 csv 输入，一条命令跑通门禁并演示 PASS_WITH_FLAGS → 逐条处置 → success 的流程。见 `examples/README.md`。
