# 失败分类法与处置（PDF 解析任务）

题面要求"材料缺失、无法判断和运行失败要分别说明"。本文件是 status_writer.py
三类边界的完整分类表，每类给出识别信号与写法。

## 1. 材料缺失 / 未报告（not_reported）

**定义**：任务问到了，但原文材料中确实没有该信息。这不是解析失败。

识别信号：全文检索关键词无命中；相关章节（如 Methods/Results）通读无该字段。

写法：`[not_reported] 原文未报道 <具体字段>（检索范围：全文/指定章节）`。
禁止：编造一个"合理"数值填上。

## 2. 无法判断（cannot_judge）

**定义**：材料里可能有，但当前手段读不出来或证据互相不足。

常见子类与处置：

| 子类 | 识别信号 | 处置 |
|-|-|-|
| 无文字层扫描页 | 抽取字符数≈0 | 移交 ocr-tool；OCR 后复核 |
| 加密 PDF | 抽取器报 password | 报 failed + handoff（需解密） |
| 乱码字体（CID 未映射） | 抽取为 / 替换符 | 标记页码，尝试 OCR 回灌 |
| 图片型表格/公式 | 版式文本中该区域空白 | 标记 figure_pixels，可 OCR |
| 引文近似但不逐字 | 门禁 near_miss | 回原文核对修正，不凭记忆改 |
| 单元格归属歧义 | 重建器标 unresolved | 保留标记，由任务方裁定 |

写法：`[cannot_judge] <对象>：<原因>（位置：页码/区块）`。

## 3. 材料冲突（material_conflict）

**定义**：材料内部两处以上说法不一致。

识别信号：同一数值/结论在正文与表格、不同页之间不一致；图题与正文叙述矛盾。

写法：`[material_conflict] <对象>：位置A 说 X，位置B 说 Y（均给出页码）`。
禁止：擅自二选一当作事实写进结果。

## 4. 运行失败（运行状态，与上面三类并列）

`status: failed` 仅用于流水线无法产出可用结果的情形（加密且无解密途径、
全卷无文字层且无 OCR、输入文件损坏）。failed 必须带 handoff（人工接管点）。

## 降级纪律

- 任何一条边界说明存在 → status 不允许为 success（status_writer 强制降级）。
- partial 必须带 uncertainty 或 handoff；contract_check 强制校验。
- 三份报告（gate/coverage/contract）的任何 FAIL 信号都会被 status_writer
  摘要折进 uncertainty，保证报告链口径一致。
