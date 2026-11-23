---
name: litqa-claim-craft
description: 文献智能问答的"论断表达与不确定性"路线。当任务给出 /input/case.json（带段落编号的论文案例包与中文问题清单）并要求把结构化结果写入 /app/output/result.json 时使用。本 Skill 的重心在表达侧：为每条论断规定可判定的写作语法（一条论断一个可核对事实、数值必须出现在引文中、作者解释必须带"作者"、推断必须带推断措辞），为四种回答状态给出决策树，为"材料未报告/部分可答/原文冲突"三类不确定性各给一套中文句式库，最后用 claim_lint.py 做只报告不改写的表达质量检查。适用于要求结论可信、可逐条核对、不夸大不缩水的文献问答。
---

# 论断表达与不确定性（litqa-claim-craft）

版本：1.0.0　运行环境：Python 3.10+（仅标准库）、shell。零外部依赖。

**方法重心**：同一份材料、同一个模型，失分常常不是"没读到"而是"没写好"——
把作者解释当成实测事实、把推断当成原文结论、给数值不给条件、
"材料未报告"写成含糊的沉默。本 Skill 不建索引、不做检索（阅读策略从简：
小语料直接通读），把全部功夫下在**论断怎么写、状态怎么定、不确定性怎么说**
三件可判定的事情上，并配一个只报告不改写的检查器 `claim_lint.py`。

## 1. 运行契约

- 输入：`/input/case.json`；工作目录 `/app/work/`；输出 `/app/output/result.json`
  与 `/app/answers.json`（同内容，旧契约兼容）。
- `result.json` 字段契约：`case_id`、`paper_id`、`material_version` 与输入一致；
  `answers[]` 覆盖全部问题（`question_id`、`answer`、`conditions[]`、`status`
  ∈ `answered|partial|insufficient_evidence|input_error`、`claims[]`
  （`claim_id`、`text`、`kind` ∈ `reported|inferred`、`evidence[]`
  （`paragraph_id` + 逐字 `quote`））、`unanswered_parts[]`）；`coverage`。
  `output_contract` 额外字段逐一照抄。
- **诚实 partial**：读不出、材料不够、时间不足都如实落盘，不编造答案或引文。

## 2. 流程（每案例约 5–8 次工具调用）

```bash
mkdir -p /app/work /app/output
SRC=$(find /skills -maxdepth 3 -name claim_lint.py -path '*/scripts/*' 2>/dev/null | head -1)
[ -z "$SRC" ] && SRC=$(find /app /opt -maxdepth 5 -name claim_lint.py -path '*/scripts/*' 2>/dev/null | head -1)
cp -r "$(dirname "$SRC")" /app/work/scripts && ls /app/work/scripts

# 步骤 1：生成每题写作单（含论断语法提示）
python3 /app/work/scripts/claim_lint.py scaffold --case /input/case.json --work /app/work
# 输入损坏时：手写 status=input_error 骨架落盘，如实结束。

# 步骤 2：通读 /input/case.json 全部段落（摘要、正文、表格、图注、参考文献
# 都读；不跳读）。语料大时按问题相关性分批，但每题至少覆盖方法+结果+讨论。

# 步骤 3：按 references/claim-grammar.md 的语法在写作单上写论断，
# 按 references/status-tree.md 的决策树定状态，按
# references/uncertainty-phrases.md 的句式写不确定性。

# 步骤 4：汇编 result.json（answer 由论断区合并成连贯段落），写
# /app/output/result.json 与 /app/answers.json。

# 步骤 5：表达质量检查，ERROR 修到归零（WARN 逐条人工判断）
python3 /app/work/scripts/claim_lint.py lint --case /input/case.json --result /app/output/result.json
```

## 3. 论断写作语法（本 Skill 的核心，详见 references/claim-grammar.md）

1. **一句一个事实**：一条 claim 只承载一个可独立核对的论断；
   需要两个事实就写两条。
2. **数值必在引文**：claim 的 text 中每个数值都必须能在该 claim 的引文中找到
   （`claim_lint.py` 的 E2 会查）；条件词出现在引文中就必须进 `conditions`。
3. **三分来源**：实测/原文直陈 → `reported`；跨段比较、换算、组合 → `inferred`
   （text 以"由 P…与 P…对比可知/综合可知"开头）；作者归因或解释 → `reported`
   但 text 中必须出现"作者"字样。
4. **引文逐字**：≤60 词，空白可规范化，措辞不可改。
5. **冲突并列**：两处不一致各写一条 claim，附各自段落；`unanswered_parts`
   中说明冲突位置。

## 4. 状态决策树（详见 references/status-tree.md）

```
全部子问都有材料支撑的论断？ ──是──> answered（unanswered_parts 必须为空）
  └──否──> 部分子问有支撑？ ──是──> partial（缺口逐条写 part+reason）
            └──否──> 通读相关章节后确认材料未报告？ ──是──> insufficient_evidence
                      （answer 写明"已核对 P…，材料未报告 X"）──否──> 回到阅读
输入无法读取/解析 ──> input_error（骨架落盘，不编造）
```

## 5. 检查器退出码与处置

| 退出码 | 含义 | 处置 |
|-|-|-|
| 0 | 无 ERROR（可能仍有 WARN） | 逐条人工确认 WARN 后可交付 |
| 1 | 有 ERROR | 按条目修复后重跑，直到 0 ERROR |

E1（引文不逐字）、E2（数值无引文支撑）、E3（状态不自洽）、E4（reported 无证据）、
E5（覆盖/字段错）是硬性错误；W1–W4 是提示，模型须逐条给出"改"或"不改"的理由。

## 6. 已知限制

- 阅读策略从简（通读），不替代检索类工具；超长材料需自行分批并保证覆盖。
- 检查器是词面规则：能查"数值有没有出现在引文里"，不能查"论断语义是否被引文支持"。
- 句式库是中文表达的建议而非模板填空；生硬套用会被视为低质。

## 7. 资源清单

| 路径 | 作用 |
|-|-|
| `scripts/claim_lint.py` | scaffold / lint 两子命令 |
| `references/claim-grammar.md` | 论断写作语法与反例 |
| `references/status-tree.md` | 四状态决策树与判定检查表 |
| `references/uncertainty-phrases.md` | 三类不确定性的中文句式库 |
| `examples/synthetic-case.json` | 合成示例输入（虚构论文，非正式案例） |
| `examples/run-record.md` | 合成示例的本地端到端真实运行记录 |
| `GITHUB_URL.txt` | 本作品的 GitHub 公开链接 |
