---
name: run-ledger-replay-qc
description: 过程质量控制优先的科研数据可视化：每个阶段写检查点（result.json 从第一秒就是合法 partial）、全量运行台账（阶段记录 + 产物 SHA-256 清单）、流水线整体确定性复跑并逐文件比对（文本逐字节、图件归一化元数据后比对）出具 replay 证明，再叠加源数据复算校验——换一台机器重跑不会得到另一张图。Use when a case requires reproducible data cleaning/statistics/visualization with auditable process evidence and rerun-proof artifacts (科研数据可视化, 可复核, 复跑证明, 过程留痕, 质量控制, 确定性).
---

# 过程质量控制：检查点台账 + 复跑证明的可视化流水线

## 适用场景

任务不仅要求"图画对"，还要求**从数据到成图的过程能被他人按记录重跑**：
阶段可恢复、规则全留痕、产物可复跑比对。典型平台场景：
`/input/case.json` + `/input/task.md` + 数据文件，输出写入
`/app/output`。执行预算紧张（约 900 秒）时本 Skill 的检查点设计保证
任何中断都留下可用的诚实 partial。

## 运行契约（平台环境）

```bash
python3 /skills/weekly-skill/scripts/run_case.py \
    --case /input/case.json --input-dir /input \
    --work /app/work --out /app/output
```

- 一条命令跑完；`result.json` 每个阶段原地更新（partial → success），
  阶段序列记录在 `ledger.json`。
- 结束后先读 `/app/output/replay_report.json`（复跑证明）与
  `ledger.json`（台账），再目检 PNG。
- 依赖：stdlib + numpy + matplotlib（缺失自动 pip 安装；失败交付文本
  结果并标注）。

## 本 Skill 的重心：过程证据链

1. **检查点（checkpoint）**：初始化后即写合法 partial `result.json`
   （含 `case_id` 与 `output_contract` 全部字段），此后每个阶段（盘点
   →清洗→统计→图件→校验）原地升级；任何崩溃都留下已完成的全部产物与
   准确的进度状态。
2. **运行台账**（`ledger.json`）：每次状态更新的阶段序列（序号、状态、
   摘要、当时产物清单）+ 全部输出文件的 SHA-256 与字节数清单。
3. **确定性复跑证明**（`scripts/replay_check.py`，流水线自动在隔离
   目录完整复跑一遍）：文本产物（statistics/cleaning/captions 等 JSON/
   Markdown）与 PNG **逐字节比对**；PDF/SVG 归一化挥发性元数据（嵌入
   时间戳、文档 ID、随机 clip-path/image id、内嵌位图的 PNG 编码时间戳）
   后比对；任何不一致列出文件与首处差异偏移。随机性只有一个来源——散点
   抖动与抽样的固定种子 20240501，写入 `run_manifest.json`。
4. **源数据复算校验**（`check_report.json`）：重读原始文件复算均值、
   n、Pearson r 并与报告值比对；CSV 与 SQLite 并存时逐单元格对账。

## 数据与图件（与过程同链完成）

清洗只留痕（缺失计数不插补、重复标记保留、1.5×IQR 仅标记、整数编码
分组列改判分类）、全量描述统计与分组统计、Pearson 相关；四张发表级
图件（300dpi PNG + 嵌入字体 PDF + 可编辑 SVG，单栏 89mm，Okabe-Ito）：
分布（右偏正值自动对数轴并标注）、分组箱线叠加散点、|r| 最高变量对
散点（分组着色）、相关热图（格内系数，色标 [-1,1]）；中文图注含 n、
误差/须线含义、来源与清洗口径。

## 输出物（/app/output）

`result.json`（遵守 `output_contract`）、`ledger.json`（台账）、
`replay_report.json`（复跑证明，核心交付）、`check_report.json`、
`statistics.json/md`、`cleaning_report.json`、`figures.figdata.json`、
`captions.md/json`、`run_manifest.json`、图件 PNG/PDF/SVG。

## 异常与边界

- 复跑不一致：说明环境存在未声明的随机源，写入 `uncertainty` 并降
  `partial`，绝不谎报。
- 复跑子进程通过环境变量 `RUN_CASE_REPLAY_CHILD` 防止递归；复跑限时
  600 秒，超时记为失败而非挂起。
- 无 CJK 字体：英文图内标注 + 中文图注文本 + `uncertainty`。
- 不做统计推断与建模；不修改源数据。

## 最小示例

`examples/` 为**合成示例**（模拟数据），按 `examples/README.md` 一条
命令端到端复现（含复跑证明）；预期文本输出在
`examples/expected_outputs/`。
