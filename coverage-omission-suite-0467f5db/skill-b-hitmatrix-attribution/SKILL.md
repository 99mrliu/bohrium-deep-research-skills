---
name: hitmatrix-attribution
description: >-
  检索覆盖率测量与逐条漏检归因技能。当任务要求对给定参考集核算检索覆盖率、列出漏检条目并给出可归因证据、
  设计并评估定向补检时使用。核心能力为三级命中判定口径（L1 标识符精确命中、L2 题录近似命中、L3 人工
  裁决队列）与五类可执行诊断探针（词汇／字段／时间窗／来源／记录异常），将每一条漏检归因到具体的
  「查询×字段×来源×时间窗」并输出可独立复算的命中矩阵与 Wilson 置信区间。不适用于无本地参考集、
  无检索记录或要求实时联网检索的场景；不依据文件名臆断材料内容，不以检索结果本身充当覆盖分母。
---

# 命中判定规则化与逐条漏检归因（hitmatrix-attribution）

本技能面向「检索覆盖率与遗漏分析」类任务，提供一套可复算、可归因、可闭环的工作规程：
以冻结参考集为唯一分母，以三级命中判定口径裁定每一次「查询×来源」执行对参考条目的命中状态，
落盘为命中矩阵；对每一条漏检执行可执行的诊断探针，归因至具体的查询编号、字段、来源与时间窗；
据此设计定向补检并复算补检前后覆盖率，零增益必须如实报告。

## 适用场景与边界

适用：

- 给定本地案例材料（参考集、检索记录、各来源本地响应文件、参考关系图）时，核算检索覆盖率并列出漏检。
- 需要将漏检归因到「哪一次查询×哪一个字段×哪一个来源×哪一时间窗」并给出证据指针。
- 需要评估定向补检对漏检的真实削减量（边际增益），含零增益情形。

边界（不适用或须降级）：

- 无本地参考集或参考集不可解析时，不得自行以检索结果构造分母；应输出 `status=partial` 并说明。
- 不进行实时联网检索；覆盖率与新颖性结论仅以本地留存的响应文件为准。
- 不依据 PDF 文件名或目录标签臆断内容；须实际解析文件，解析失败按「不可用记录」登记。
- L2 近似命中必须记录相似度分数与证据；临界与冲突情形一律进入 L3 裁决队列，不得静默放行。

## 运行环境与定位兜底

- 运行契约：输入为 `/input/case.json` 与 `/task.md`；工作目录 `/app/work`；最终产物写入 `/app/output`，
  其中 `result.json` 必须包含 `case_id` 以及 `case.json` 中 `output_contract` 列出的全部字段。
- 预算约束：模型请求不超过 64 次，总时长不超过 900 秒；技能资源为纯 UTF-8 文本，无符号链接、无二进制。
- 脚本仅使用 Python 3 标准库；每个脚本支持 `--help`；退出码约定：0 成功，2 材料不足（诚实降级），3 校验失败。
- 文件缺失、网络不可达、PDF 解析失败时，置 `status=partial` 并在 `limitations` 中逐条说明，严禁编造数据。
- matplotlib 若可用可生成 PNG 预览，但属于可选增强，任何产物不得依赖其存在。

## 命中判定规范（L1／L2／L3）

命中判定的完整规则、归一化函数与算例见 `references/match_rules.md`，要点如下。

### L1 标识符精确命中

以下任一成立即为 L1 命中（分数记 1.0）：

- 归一化 DOI 相等：小写化，去除 `https://doi.org/`、`http://dx.doi.org/`、`doi:` 前缀与首尾空白。
- 归一化 PMID 相等：仅保留数字串后比较。
- 归一化 arXiv 标识相等：去除 `arXiv:` 前缀、小写化、去除版本后缀 `vN`。

### L2 题录近似命中

同时满足以下三项方为 L2 候选，且必须记录分数与证据：

1. 归一化标题的 token 集合 F1 ≥ 0.6（token F1 = 2|A∩B|／(|A|+|B|)，标题小写化、去标点、按空白切分）；
2. 第一作者姓氏归一化后相等（小写、去重音符号）；
3. 发表年份相差不超过 ±1。

### L3 人工裁决队列

以下情形一律进入裁决队列（`adjudication_queue.json`），须逐条裁决并记录理由，未裁决条目计为 `ambiguous`，
不得计入命中：

- token F1 处于 [0.5, 0.6) 且其余 L2 条件成立的临界对；
- 标识符冲突：同一 DOI／PMID／arXiv 在不同来源对应不同标题，或同一条目携带互相矛盾的标识符；
- L2 候选但年份缺失或作者字段缺失以致无法完整核验者。

裁决结果经 `--decisions` 文件回灌 `adjudicate.py` 后方可计入命中。

## 工作流程

1. **材料清点**：运行 `parse_case.py`，校验 `case.json` 结构，清点参考集、检索记录与各来源响应文件，
   输出 `work/case_normalized.json` 与材料清单；材料不足时以退出码 2 降级。
2. **参考集与检索记录接入**：冻结参考集，按 `usable` 标记剔出不可用记录并公布剔除清单（含原因），
   剔除后条目数即为覆盖分母；检索记录逐条登记 `query_id`、来源、执行时间、字段范围与时间窗。
3. **L1／L2 判定**：运行 `adjudicate.py`，对每一「参考条目×查询×来源」单元执行 L1、L2 判定，
   记录 `match_level`、相似度分数、命中记录在结果文件中的位次与证据。
4. **裁决队列**：临界对与冲突对写入裁决队列；逐条裁决并以 `--decisions` 回灌，未裁决者计 `ambiguous`。
5. **命中矩阵落盘**：运行 `hit_matrix.py`，生成 `hit_matrix.csv` 与 `hit_matrix.json`；
   行＝参考集条目，列＝（query_id × source × executed_at），单元＝`{status, match_level, rank_in_results, evidence}`。
6. **覆盖率与置信区间**：覆盖率＝命中数／可用参考数，仅从命中矩阵复算，不得凭记忆或口头估计；
   同时输出分来源、分查询召回率与 Wilson 95% 置信区间。
7. **漏检决策树探针归因**：运行 `attribute_miss.py`，对每条漏检依次执行记录异常、来源、时间窗、字段、
   词汇五类探针，每条漏检恰好得到一个主归因类别、探针证据（文件、字段、引用片段）与致漏的
   query_id／字段指针。
8. **定向补检**：运行 `supplement_eval.py`，按主导漏检类别各设计一条定向补检查询（词汇缺口→取自漏检
   记录实际词汇的新检索式；字段过窄→放宽字段；时间窗截断→放宽时间窗；来源缺失→切换来源），
   在本地语料文件上执行。
9. **复算对比**：对补检结果重跑完整三级判定，从同一冻结参考集复算补检前后覆盖率与边际增益；
   补检零新增命中必须如实报告为零边际增益，不得宣称遗漏已削减。
10. **复核与交付**：运行 `render_report.py`，生成 `coverage_report.md` 与 `result.json`；
    复核每条结论的证据指针、各阶段状态与不确定性说明后交付。

## Wilson 置信区间

对命中率 p̂＝k／n（k 为命中数，n 为可用参考数），置信水平 95%（z＝1.96）的 Wilson 区间为：

    中心 = (p̂ + z²/(2n)) / (1 + z²/n)
    半径 = z·√(p̂(1−p̂)/n + z²/(4n²)) / (1 + z²/n)
    区间 = [中心 − 半径, 中心 + 半径]

实现见 `hit_matrix.py` 的 `wilson_interval()`，推导与性质见 `references/wilson_interval.md`。
n 较小或 p̂ 接近 0／1 时 Wilson 区间仍保持良态，优于正态近似，须在报告中一并给出。

## 异常处置

| 情形 | 处置 |
| --- | --- |
| 参考记录撤稿 | 保留于参考集并标记 `retracted`；是否计入分母依 `output_contract`，默认剔除并公布 |
| 重复记录 | 归一化标题或标识符相同者合并为一条，登记 `duplicate_of` |
| 标识符冲突 | 进入 L3 裁决队列，未裁决计 `ambiguous`，不计命中 |
| 全文不可用 | 以题录字段判定；题录亦缺失则标记 `unusable` 并从分母剔除，公布剔除清单 |
| 响应文件缺失／损坏 | 该来源全部单元计 `source_unavailable`，置 `status=partial` |
| 脚本超时或异常 | 记录失败阶段与 stderr 摘要，已落盘中间产物保留，置 `status=partial` |

## result.json 契约

`result.json` 必须包含：`case_id`；`status`（ok／partial／failed）；`output_contract` 要求的全部字段
（缺失字段以 null 填充并在 `limitations` 说明）；`coverage`（overall、per_source、per_query、wilson_ci、
denominator、excluded）；`misses`（逐条：ref_id、primary_category、probe_evidence、query_id、field）；
`supplements`（逐条：类别、查询式、来源、新增命中、边际增益）；`sources`（实际使用的本地文件清单）；
`uncertainty` 与 `change_records`（各阶段动作与时间戳）。

## 失败与降级

- 退出码 2：参考集为空、检索记录为空或全部响应文件不可用，输出部分产物并说明缺口。
- 退出码 3：`case.json` 结构校验失败（缺必填键、类型错误），不修不猜，直接报告。
- 任何阶段失败均不得中断后续可独立完成的阶段；最终状态取最严重的降级级别。

## 最小调用示例

```bash
python3 scripts/parse_case.py --case /input/case.json --work /app/work
python3 scripts/adjudicate.py --work /app/work --decisions /app/work/decisions.json
python3 scripts/hit_matrix.py --work /app/work --out /app/output
python3 scripts/attribute_miss.py --work /app/work --out /app/output
python3 scripts/supplement_eval.py --work /app/work --out /app/output
python3 scripts/render_report.py --case /input/case.json --work /app/work --out /app/output
```

逐脚本参数见各脚本 `--help`。中间产物全部落盘于 `/app/work`，最终产物落盘于 `/app/output`，
任何覆盖率数字均可由命中矩阵独立复算。
