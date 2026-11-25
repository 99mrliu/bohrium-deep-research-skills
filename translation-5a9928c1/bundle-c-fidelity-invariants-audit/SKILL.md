---
name: fidelity-invariants-audit-translation
description: >-
  当科研翻译案例的核心风险是"数字、单位、公式、图表编号、文献引用、否定关系与限定条件在译文中被改动、漏译或凭添"时使用本 Skill。
  Use when a scientific-translation case (/input/case.json + task.md + source) requires fidelity-invariant verification: deterministic extraction of numeric+unit quantities (ranges, ±, ×10^n, full-width digit normalization), statistics (p, n=, CI, effect estimates), citations [n]/[n–m], figure/table/equation references, negation cues and qualifier/modality cues from BOTH source and translation; per-segment sentence-aligned comparison classifying missing / changed / added / negation_lost / qualifier_lost; a human-confirmation checklist; targeted revision loop; and contract-driven bilingual result.json with case_id and every output_contract field plus honest partial status.
  不做的事：不把审计信号当作改译指令（合法语序调整需 signal_explanation）、不自动改写数字、不臆造统计显著性、不把"无证据支持效应"译成"证明无效应"。
---

# fidelity-invariants-audit-translation（译文保真不变量核验，Bundle C）

本 Skill 的重心是**关系准**：译文与原文之间必须守恒的对象——数字与单位、统计量、
引用编号、图表与公式编号、否定与限定——由脚本从两侧**确定性抽取**后逐段比对。
审计输出是"修订清单 + 人工确认清单"，而不是一句"已检查"。翻译由 Agent 完成并修订；
脚本保证核验可重复、漏项可定位。

## 何时使用 / 边界

**适用**：含数值结果、统计检验、引用与图表编号的论文翻译；评分关注"关系准"的案例。
**不适用**：纯理论散文且无任何可抽取不变量的文本（此时审计报告如实写"无不变量"，
不虚构检查项）；审计是**信号**不是裁判——合法语序/单位换序需人工说明，不自动改译文。

## 运行契约

- 输入：`/input/case.json` + `/input/task.md` + 源文件。
- 中间产物（`/app/work/fidjob/`）：`source.md`、`segments.json`（分段）、`invariants_src.json`、`invariants_tgt.json`、`audit.json`、`human_review.md`。
- 交付（`/app/output/`）：`result.json`（`case_id` + 合同全部必填字段）、`bilingual.md`、`human_review.md`、`audit.json`。
- 诚实 partial：未决核验项写入 `uncertainties`；无法判定的段落明确标注，不写成"已核验"。

## 精确命令工作流

```bash
# 0. 定向
cat /input/case.json /input/task.md; ls -la /input
export SKILL_DIR=$(dirname $(find /skills -maxdepth 3 -name SKILL.md -path '*fidelity-invariants*' 2>/dev/null | head -1))
S=$SKILL_DIR/scripts; W=/app/work/fidjob; O=/app/output; mkdir -p $W $O

# 1. 源文（PDF 用 pdftotext；保留原始导出）
python3 $S/extract_source.py --input /input --out $W/source.md

# 2. 分段（复用语义段；译文按同段号回填）
python3 $S/segment_docs.py --source $W/source.md --out $W/segments.json

# 3. Agent 逐段翻译（携带前段尾部上下文），写 translations.json：
#    [{"id":"p003","source":"…","translation":"…"}]

# 4. 双侧不变量抽取（确定性，非模型判断）
python3 $S/extract_invariants.py --text $W/source.md --out $W/invariants_src.json
python3 $S/extract_invariants.py --text <(python3 $S/join_translations.py $W/translations.json) --out $W/invariants_tgt.json

# 5. 逐段句对齐比对
python3 $S/audit_invariants.py --translations $W/translations.json \
    --inv-src $W/invariants_src.json --inv-tgt $W/invariants_tgt.json \
    --out $W/audit.json --review $O/human_review.md
#    类别: missing/changed/added（数值与编号）, negation_lost, qualifier_lost
#    exit 1 = 存在硬性差异；修订 translations.json 后重跑直至清零或仅剩
#    带 signal_explanation 的人工确认项。

# 6. 组装交付
python3 $S/assemble_result.py --case /input/case.json --translations $W/translations.json \
    --audit $W/audit.json --out $O
```

`result.json`：完整译文进文本字段；`bilingual` 段级对照；`uncertainties` 为人工确认
清单（含 signal_explanation 的合法差异）；`status`：全部段已译且审计无硬性差异 →
`success`，有差异未决 → `partial`。

## 核验纪律

- 数字守恒：值（全角/千分位/负号归一）与单位分别比对；`1.8 Ω cm²` 不得变成 `18 Ω cm²` 或 `1.8 Ω`。
- 否定守恒：源句含否定而对应译句无任何否定标记 → `negation_lost`（"did not reduce"≠"reduced"）。
- 限定守恒：`may/suggests/approximately` 不得在译文中升格为"证明/恰好"。
- 编号守恒：引用 [n]、图表、公式编号逐个比对；缺一个都算 missing。
- 审计差异是信号：确属合法语序调整时，在译注写 `signal_explanation` 说明对应关系，
  由人工确认清单兜底，禁止为清零而强行改回正确译文。

## 最小调用示例（合成示例，非正式案例结果）

`examples/source_en.txt` 为**合成的**临床医学摘要（含 p 值、n=、95% CI、引用 [1, 2]、
Figure 2、否定与限定表述）。`run_example.sh` 跑通 抽取→翻译（合成坏译文，故意改数、
丢否定、添数字）→审计（必须检出全部三类问题）→修订→复审计清零→组装，
并断言 `result.json` 合同字段齐全。示意输出见 `examples/example_output/`。

## 预算、可靠性与限制

- 官方包线 64 请求 / 900 秒：抽取与比对为脚本零请求；Agent 工作集中在翻译与修订。
- 稳定性：脚本幂等可重跑；归一化规则固定（见 references/invariant-taxonomy.md）。
- 异常处理：抽取失败的段落标 `unauditable` 进 uncertainties；科学计数与单位新形态
  进入" unrecognized"清单而不猜测。
- 限制：句对齐以段内句序号为准，长段跨句合并/拆分会造成错位信号（进人工确认）；
  中文数字（"三折""十余"）只标记不换算；审计不判断语义对错，只守恒可抽取对象。
