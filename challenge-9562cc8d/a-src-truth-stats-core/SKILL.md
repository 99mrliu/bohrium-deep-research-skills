---
name: src-truth-stats-core
description: 上游数据真实性优先的科研数据可视化。两套独立算法（朴素累加 + Welford 在线方差/type-7 分位数）对全部统计量做双向复核，CSV 快照与 SQLite 数据库做逐单元格对账，清洗只留痕不静默修改，在此基础上产出发表级图件（300dpi PNG + 嵌入字体 PDF + 可编辑 SVG）、中文图注与可机读的复核报告。Use when a case requires cleaning/statistics/visualization of research tables (CSV/TSV/SQLite/JSON) where every reported number must be independently recomputable from the source files (科研数据可视化, 数据清洗, 描述统计, 统计复核, 数据口径, 来源对账).
---

# 上游数据真实性：双算法复核的统计与可视化流水线

## 适用场景

输入为科研数据表（CSV/TSV/TXT/JSON/SQLite，含中文列名、GB18030 编码、
单位嵌入列名），任务要求清洗、描述统计、分组比较与发表级图件，且**每个
数字必须可由源数据复算**。典型平台场景：`/input/case.json` +
`/input/task.md` + 数据文件，输出写入 `/app/output`。

## 运行契约（平台环境）

```bash
python3 /skills/weekly-skill/scripts/run_case.py \
    --case /input/case.json --input-dir /input \
    --work /app/work --out /app/output
```

- 一条命令跑完整链条；`result.json` 从第一阶段就以 `partial` 状态存在，
  每完成一个阶段原地更新，任何中断都留下诚实 partial。
- 结束后依次查看：`/app/output/verification_report.json`（第二套独立
  实现的复核结果）、`check_report.json`（重读源文件复算 + 导出物理
  检查）、PNG 预览（确认无遮挡/乱码）。
- 非平台环境：把 `--case/--input-dir/--work/--out` 换成实际路径即可。
- 依赖：Python 3 标准库 + numpy + matplotlib（缺失时自动尝试
  `pip install`；失败则交付统计与清洗结果并标注图件缺失，绝不崩溃）。

## 本 Skill 的重心：数字必须经得起第二套算法复核

1. **双实现复核**（`scripts/verify_stats.py`，流水线自动调用）：
   流水线自身的统计用朴素两遍累加；复核器用 Welford 在线算法重算
   均值/SD/SEM、独立实现 type-7 分位数、按原始行重新成对累加 Pearson
   相关，逐字段比对 `statistics.json`（相对容差 1e-6），任一字段不一致
   都写入 `verification_report.json` 并进入 `result.json` 的
   `uncertainty`——`status` 不会谎报 success。
2. **多源对账**：同时存在 CSV 快照与 SQLite 数据库时做行数、列集合、
   逐单元格比对（数值容差 1e-9），不一致写入 `reconciliation.json` 与
   `uncertainty`，以哪个文件为准必须显式声明，绝不静默取舍。
3. **清洗只留痕**：去空白、逐列数值化（记录失败计数）、缺失值逐列计数
   （不插补）、重复行标记保留、1.5×IQR 异常值仅标记不删除；整数编码的
   分组列（如 class=1/2/3）改判为分类变量并写入规则。全部规则与计数在
   `cleaning_report.json`。
4. **图件与图注**：分布图（直方图+KDE，右偏正值变量对数轴并标注）、
   分组箱线图叠加散点（须线 1.5×IQR）、|r| 最高变量对散点（分组着色，
   标注 r 与 n）、相关热图（格内系数，色标固定 [-1,1]）；中文图注含
   样本量、误差/须线含义、数据来源与清洗口径（captions.md/json）。

## 输出物（/app/output）

`result.json`（含 case.json `output_contract` 全部字段与原始 `case_id`）、
`statistics.json/md`、`cleaning_report.json`、`verification_report.json`
（双算法复核）、`reconciliation.json`（有多源时）、`check_report.json`、
`figures.figdata.json`（每个视觉元素到源列的绑定）、`captions.md/json`、
`run_manifest.json`（环境版本、随机种子 20240501、源文件 SHA-256）、
图件 PNG/PDF/SVG。

## 异常与边界

- 无 CJK 字体：图内标注回退英文变量名，图注仍为中文文本，写入
  `uncertainty`；绝不允许豆腐块。
- 缺列、空列、类型混杂、读取失败：对应面板/统计跳过并明确报告，
  `status=partial` 并说明缺什么。
- 不做统计推断（p 值/显著性检验）与建模；不修改任何源数据。
- 单表为主；多表需先整理为一张宽表。

## 最小示例

`examples/` 内含**合成示例**（模拟数据，非真实实验）：运行
`examples/README.md` 中的一条命令即可端到端复现，文本形式的预期输出在
`examples/expected_outputs/`。
