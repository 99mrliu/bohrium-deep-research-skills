---
name: caption-annotation-lab
description: 标注与图注语义优先的科研数据可视化：图注中的每个数字（n、r、均值）都由统计结果程序化插入并可被审计器逐一核对，图注完备性（样本量、误差线/须线含义、数据来源、清洗口径、各组 n）、图例与数据分组取值 1:1、面板编号连续、坐标轴单位声明全部由 caption_audit.json 机器核验，保证图注脱离正文也能独立读懂。Use when a case requires standalone-readable Chinese figure captions, error-bar/whisker semantics, legend-data correspondence and annotation consistency auditing (科研数据可视化, 图注, 误差线含义, 显著性标注, 单位, 图例一致性).
---

# 标注与图注：可独立阅读、且每个数字可核对

## 适用场景

输入科研数据表与出图任务，要求图注脱离正文独立读懂、误差线/须线含义
明确、图例与数据一一对应、图注数字与源数据一致。典型平台场景：
`/input/case.json` + `/input/task.md` + 数据文件，输出写入
`/app/output`。

## 运行契约（平台环境）

```bash
python3 /skills/weekly-skill/scripts/run_case.py \
    --case /input/case.json --input-dir /input \
    --work /app/work --out /app/output
```

- 一条命令跑完；`result.json` 自始以 `partial` 存在、逐阶段更新。
- 结束后先读 `/app/output/caption_audit.json`（本 Skill 的核心交付：
  图注机器审计），再目检 PNG。
- 依赖：stdlib + numpy + matplotlib（缺失自动 pip 安装；失败交付文本
  结果并标注）。

## 本 Skill 的重心：图注是计算出来的，不是写出来的

1. **程序化生成**：`captions.md/json` 中所有 n、r、组样本量、偏度、
   均值±SD 都在模板中由 `statistics.json` 的计算结果插入，不存在
   手抄数字。
2. **机器审计**（`scripts/caption_lint.py`，流水线自动调用）：
   - 完备性：每条图注必须含样本量 n、数据来源、清洗口径；分组图必须
     含各组 n 与须线/误差线含义（箱体 Q1–Q3、须线 1.5×IQR、离群点仅
     标记；误差线出现时写明 SD/SEM/CI 之一种）；
   - 数字一致性：图注中每个 `r=…`、`n=…` 与 `statistics.json` 逐一
     比对，出现统计结果中不存在的数字即失败；
   - 图例 1:1：`figures.figdata.json` 的分组水平与统计中的分组取值
     完全一致；
   - 面板编号：(a)(b)(c) 连续无跳号；
   - 单位声明：列名含单位的变量在坐标轴与图注中声明单位。
3. **审计失败不沉默**：任一检查失败写入 `uncertainty` 并降
   `status=partial`，明确指出哪条图注缺什么。

## 数据与图件（与标注同链完成）

清洗留痕、全量描述统计与分组统计、Pearson 相关；四张发表级图件
（300dpi PNG + 嵌入字体 PDF + 可编辑 SVG，单栏 89mm，Okabe-Ito 色盲
安全配色）：分布（右偏正值自动对数轴并在轴标注明）、分组箱线叠加
散点（须线 1.5×IQR，图注写明含义）、关键变量对散点（分组着色，面板
标题标注 r 与 n）、相关热图（格内系数，色标固定 [-1,1]）。

## 输出物（/app/output）

`result.json`（遵守 `output_contract`）、`caption_audit.json`
（核心交付）、`captions.md/json`、`check_report.json`、
`statistics.json/md`、`cleaning_report.json`、`figures.figdata.json`、
`run_manifest.json`、图件 PNG/PDF/SVG。

## 异常与边界

- 源数据未声明误差线含义时：只标注箱线图须线的确定含义，不虚构
  显著性检验；任务若要求显著性标记而无检验依据，写入
  `uncertainty` 而非编造 p 值。
- 无 CJK 字体：英文图内标注 + 中文图注文本 + `uncertainty`，
  不出豆腐块。
- 不做统计推断（显著性检验）与论文写作。

## 最小示例

`examples/` 为**合成示例**（模拟数据），按 `examples/README.md` 一条
命令端到端复现；预期文本输出（含 caption_audit.json）在
`examples/expected_outputs/`。
