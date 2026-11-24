---
name: cross-section-consistency
description: >-
  论文逻辑与论证审查的结构层工作流：专攻跨章节的一致性与衔接断裂。当任务是审查
  /input 中的科研论文（case.json + task.md + PDF/文本材料），需要核查摘要与正文是否
  一致、引言承诺是否在结果章交付、图表引用与标题是否配对、术语缩写口径是否统一时
  使用。核心立场：跨章节矛盾是长文审查漏检率最高的一类——单章阅读永远发现不了
  "摘要 65% 而结果 43%"。本 Skill 用 scripts/xcheck.py（纯标准库、确定性、零依赖）
  提取摘要数值、引言承诺句、图表标题与引用、缩写定义状态，生成 X1–X4 确定性候选
  （摘要—正文数值不一致 / 承诺未交付 / 图表不配对 / 缩写未定义），每条候选锚定
  断裂的两侧句子；verify 门禁强制双侧锚定与逐字 quote。不适用：文字润色、查重、
  参考文献格式规范、统计复算。
---

# cross-section-consistency：矛盾住在章节接缝里

## 定位

本 Skill 的重心在**结构层**，对应题目突破方向 4（章节衔接与前后一致性）。
方法论核心：**双侧锚定**——每条跨章 finding 同时给出断裂两侧的句子
（side_a / side_b），评审一次核对两处原文，不用自己回原文找。

## 固定路径与运行契约

- 引擎：`/skills/weekly-skill/scripts/xcheck.py`（下文 `$XC`，`python3`，≥3.8，纯标准库）
- 参考：`/skills/weekly-skill/references/xcheck_rules.md`（X1–X4 定义、口径冲突
  类型表、误报边界、严重度判据）
- 输入：`/input/case.json`、`/input/task.md`、论文材料（PDF 先转文本）
- 工作区：`/app/work`；交付：`/app/output/result.json` + `report.md`
- `result.json` 必须含原 `case_id` 与 `output_contract` 全部字段；第 0 步先写骨架

## 执行协议

### 第 0 步：读契约、写骨架

读 case.json、task.md；立即写 result.json 骨架（全字段占位 + in_progress）。

### 第 1 步：结构清单

```bash
python3 $XC scan --paper /app/work/paper.txt --work /app/work
```

`structure_map.json`：摘要全部数值、正文全部数值、引言承诺句、图表标题表、
正文图表引用、高频缩写及其定义状态。exit=3（空文本）→ `未检查/no_text_layer`
诚实 partial。

### 第 2 步：X1–X4 候选

```bash
python3 $XC xcheck --work /app/work
```

- X1 摘要—正文数值不一致：摘要数值在正文未检出同值（按句聚合）。
- X2 引言承诺未交付：承诺句关键词 ≥70% 在结果/讨论章零覆盖。
- X3 图表不配对（双向）：引用无标题 / 有标题从未被引用。
- X4 缩写未定义：出现 ≥3 次且无括号定义。

### 第 3 步：人工核对（主战场）

逐条候选回原文两侧核对。X1 定案前必须判断口径：同指标同口径数值不同 →
事实错误级；同指标不同口径（最佳工况 vs 均值、相对 vs 绝对）未说明 →
口径冲突；摘要四舍五入 → 驳回记理由。X2 定案前通读结果/讨论确认承诺真的
未交付（定性交付也算交付，驳回记理由）。同时按 task.md 覆盖六类检查项；
跨章一致性与事实核验、统计报告、论证链天然交织，每条 finding 同样要求
sentence_id + 逐字 quote。

### 第 4 步：verify 门禁

```bash
python3 $XC verify --work /app/work --findings /app/work/findings.json
```

强制：quote 逐字（对 side_a 句）；X1/X2 类 finding 定案必须给 side_b，另一侧
确认不存在时 basis 须写明"未交付/未检出"，无法确认设 status=待复核；
suggestion ≥15 字且落到改哪一侧哪一句。exit=4 逐条修正重跑。

### 第 5 步：交付

result.json：output_contract 全字段 + case_id + findings（type/severity/
side_a/side_b/quote/basis/suggestion）+ status（通过/问题/待复核/未检查
分列）+ uncertainty + provenance。report.md 按严重度排序。

## 严重度判据

critical：主结论数值摘要与正文相反或严重不符（X1 落在核心指标）。major：
X2 成立（承诺的分析未交付）；关键指标口径冲突。minor：X3、X4、次要数值
不一致。info：建议。判据写入 basis。

## 反误报规则

1. X1 先做口径判断再定案；四舍五入与单位换算差异不算不一致。
2. X2 是关键词近似：定性交付、以图为载体的交付都算交付——定案前通读
   结果/讨论章。
3. 摘要对结果的合法概括（"提高约四成"对应 43%）不是不一致。
4. 拿不准 → 待复核 + 说明。

## 预算规划（64 次模型请求 / 900 秒）

工具不占模型预算。第 0–2 步 ≤6 次；第 3 步 X1 > X2 > X3 > X4 优先；第 4–5
步 ≥4 次。未定案项标待复核交付诚实 partial。

## 异常处理

| 情况 | 处置 |
|-|-|
| 扫描版无文本层 | `未检查/no_text_layer` 交付 partial |
| 章节未检出 | 降级为全文扫描，注明粒度损失 |
| 图表为图片无标题文本 | X3 候选转待复核，用 pdf-render-tool 目检后定 |
| verify exit=4 | 按 xcheck_verify.json 逐条修正 |

## 不适用

文字润色、查重、参考文献格式规范、统计复算（X1 只比对同值出现，不判断
统计正确性）。

## 最小示例

`examples/minimal/`（**合成示例，非正式案例**）：合成短文故意含"摘要 65%/20%
而结果 43%/15%""承诺建动力学模型未交付""引用不存在的表2、表1 从未被引用"
"VRF 三次未定义"。`sh examples/minimal/run_example.sh` 真实执行：scan →
X1=1/X2=1/X3=2/X4=1 候选 → 伪造 quote 与缺 side_b 的 finding 被拦下
（exit=4）→ 双侧锚定的合规 findings 通过。产物在
`examples/minimal/outputs/work/`。
