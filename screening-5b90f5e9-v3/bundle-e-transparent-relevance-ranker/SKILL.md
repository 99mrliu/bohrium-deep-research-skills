---
name: transparent-relevance-ranker
description: >-
  系统性文献检索与题录筛选任务中，当需要"按相关性排序候选题录"且排序必须可解释、
  可复算、可审计时触发。方法链：研究问题 → facet 分解（人群/干预/对照/结局/研究设计，
  词表由模型运行时填写）→ 命中锚定门（每个 facet 词必须是题名/摘要原文的规范化真实
  子串，位置与片段留痕，零命中词 exit 3 强制重修）→ 确定性强评分（facet 覆盖加权和 +
  时效分 + 文献类型权重 + 来源多样性调整，权重全部在 config，公式全部在 references）
  → 显式 high/medium/low 分档与并列如实标注 → 权重 ±20% 扰动稳定性检验
  （rank instability 列表）→ 可复核的排序依据报告。边界：不做纳入/排除判定、
  不去重、不联网、不使用预算内不可复算的 embedding/ML 打分。
---

# transparent-relevance-ranker — 透明可分解的相关性排序器

给候选题录一个**完全可解释、可复算**的排序，而不是一句"按相关性排序"。
每条记录的得分附完整分解单：哪个 facet 哪个词命中在哪、权重多少、贡献多少分。

## 适用场景与边界（红线）

**适用**：题录筛选阶段的阅读优先级排序；需要向评审交代"为什么这篇排在这篇前面"的场合；
有限快照、离线、预算受限（64 请求 / 900 秒）环境下的可复算排序。

**红线（本 skill 明确不做）**：
1. **不做纳入/排除判定**——排序只表达阅读优先级，与 eligibility 判定解耦；
2. **不去重**——疑似重复导出按原样排序并在 uncertainty 中提示；
3. **不联网**——只用 /input 快照与本地配置；
4. **不用 embedding / ML 打分**——预算内不可复算的方法一律不用；
5. **不伪造命中**——facet 词锚定失败（exit 3）必须重修词表，不得跳过门禁；
6. **不用伪精度强排**——同分即并列，如实标注 tie_group；
7. **权重不得硬编码或在对话中临时发明**——只能改 `config/scoring_config.json` 并留痕。

## 运行环境

- Python 3 标准库，零第三方依赖；脚本位于 `scripts/`。
- 退出码约定（全部脚本一致）：
  - `0` 成功；
  - `2` 完成但有警告（partial，如合同字段置 null、材料有缺项）；
  - `3` 门禁/致命失败（**facet 词锚定失败、facet 结构校验失败、输入缺失**），必须处理后才能继续。
- 路径默认值均可覆盖：`--input-dir /input`、`--work /app/work`、`--output-dir /app/output`、
  `--config <bundle>/config/scoring_config.json`。
- **幂等**：全部产物由脚本整体重写，无随机数、无时间戳；同输入重跑字节一致。
- 每个脚本都有顶层 try/except：未预期异常打印到 stderr 并 exit 3，绝不静默。

## 工作流程

0. **[脚本] 解析输入**：`parse_case.py --input-dir /input --work /app/work`
   → `case_summary.json`（case_id、research_question、output_contract 字段列表、材料清单）
   与 `records.json`（规范化题录）。材料为零 → exit 3。
1. **[脚本] 尽早落骨架**：`scaffold_result.py --work /app/work --output-dir /app/output`
   → 按 output_contract 生成 `result.json` 骨架（字段占位 null，status=in_progress），
   防超时零交付。
2. **[脚本] 建 facet 骨架**：`build_facets.py --init --work /app/work`
   → `facets_skeleton.json`（facet 集合来自 config，terms 留空）。
3. **[模型] 填 facet 词表**：读研究问题与若干题录样本，为每个 facet 填 2–6 个
   **会在题录文本中真实出现**的词/短语（中英文同义可并列），写成 `filled_facets.json`。
   模型只填词表；权重在 config，facet 集合在 config，模型均不得改。
4. **[脚本] 结构校验**：`build_facets.py --validate filled_facets.json --work /app/work`
   → 不通过 exit 3，回第 3 步重修。
5. **[脚本] 锚定校验门**：`anchor_hits.py --work /app/work --facets filled_facets.json`
   → `anchors.json`（每词的命中位置与原文片段）。**任一词零命中 → exit 3，回第 3 步重修**。
6. **[脚本] 确定性强评分**：`score_records.py --work /app/work`
   → `scores.json`（每记录总分 + 完整分数分解单）。
7. **[脚本] 分档与并列**：`tier_and_ties.py --work /app/work`
   → `tiers.json`（high/medium/low；同分共享名次并列标注）。
8. **[脚本] 扰动稳定性**：`sensitivity.py --work /app/work`
   → `sensitivity.json`（每 facet 权重 ±20% 共 10 个方案；换档记录进 rank instability）。
9. **[脚本] 填充交付**：`fill_result.py --work /app/work --output-dir /app/output`
   → 填充 `result.json` 全部合同字段 + 写出 `ranking_rationale.md`。
   合同字段无法填充 → 置 null 并在 uncertainty 说明，status=partial。
10. **[脚本] 终检**：`selfcheck.py --work /app/work --output-dir /app/output`
    → 合同齐备、分数确定性回放、分解自洽、锚定切片复验、分档自洽。失败 exit 3。

预算意识：第 1 步保证任何时刻都有可交付的 result.json；预算紧张时可在第 8 步后
直接跳第 9 步（sensitivity 置 null 并说明，status=partial）。

## 输出合同映射

output_contract 在写 skill 时未知，运行时从 case.json 读取；逐字段映射如下：

| 合同字段 | 填充来源 |
| --- | --- |
| case_id | case_summary.json |
| skill_name | 固定 `transparent-relevance-ranker` |
| status | success / partial / failed（诚实反映） |
| product / ranked_candidates / ranking / results | 排序清单（rank、record_id、分数、档位、并列组、主要得分驱动） |
| ranking_rationale | `ranking_rationale.md` 文件名（人读报告） |
| score_decomposition | 每记录完整分数分解单 |
| sensitivity | rank_instability 列表与扰动方案数 |
| counts | 记录总数、各档条数、并列组数、不稳记录数 |
| sources | 材料文件清单 + 配置文件 |
| uncertainty | 解析警告、置 null 字段说明、扰动换档提示、"排序≠纳排"声明 |
| change_records | 流水线各步骤留痕 |
| 其他字段 | 无法由本 skill 语义填充 → null + uncertainty 说明 |

## 异常处理表

| 异常 | 处理 | 退出码 |
| --- | --- | --- |
| /input/case.json 缺失 | 报错并终止 | 3 |
| 题录材料为零 | 报错并终止（骨架已落，可手动填 failed） | 3 |
| output_contract 缺失 | 仅通用字段，warning 留痕 | 2 |
| 记录缺年份 | 时效分按 unknown_year_factor 折算，warning | 2 |
| facet 结构非法（键集合不符/空词表/重复词/私改权重） | 拒绝并提示，模型重修 | 3 |
| facet 词零命中（锚定失败） | 写入 anchor_failures，强制重修词表 | 3 |
| 前序产物缺失（fill/selfcheck 时） | 报错指明缺哪个产物 | 3 |
| 合同字段无法填充 | 置 null，uncertainty 逐字段说明，status=partial | 2 |
| 任何未预期异常 | 顶层 try/except，stderr + exit 3 | 3 |

## 最小调用示例

```bash
SKILL=/skills/weekly-skill
cd "$SKILL/scripts"
python3 parse_case.py --input-dir /input --work /app/work
python3 scaffold_result.py --work /app/work --output-dir /app/output
python3 build_facets.py --init --work /app/work
# [模型] 填写 /app/work/filled_facets.json 后：
python3 build_facets.py --validate /app/work/filled_facets.json --work /app/work
python3 anchor_hits.py --work /app/work --facets /app/work/filled_facets.json   # exit 3 则重修词表
python3 score_records.py --work /app/work
python3 tier_and_ties.py --work /app/work
python3 sensitivity.py --work /app/work
python3 fill_result.py --work /app/work --output-dir /app/output
python3 selfcheck.py --work /app/work --output-dir /app/output
```

完整合成示例（含一次锚定失败负例的真实 exit 3 演示）见 `examples/`。

## 维护信息

- 版本：v1.0.0
- 日期：2026-11-25
- 维护：bohrium-deep-research-skills 项目组
- 公式与权重：`references/scoring_model.md`；锚定规则：`references/anchoring_rules.md`；
  全部参数：`config/scoring_config.json`（改权重只改这里，并在 change_records 说明）。
