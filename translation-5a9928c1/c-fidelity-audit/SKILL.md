---
name: translation-fidelity-audit
description: 对英译中科技文献译文做忠实度机器核验与人工接管管理：抽取源文不变量（数字、单位、引文、图表/公式引用、否定与模糊/转折语气），逐段比对译文，阻断项（数字丢失/篡改、单位变更、引文/引用丢失、否定丢失）必须先修复才能交付，警告项与一切未决问题全部进入显式人工确认队列，任何事项都不允许静默通过。Use this skill after a translation draft exists, to gate delivery on machine-checkable fidelity and to hand unresolved items to a human-review queue.
---

# 译文核验与人工接管（Translation Fidelity Audit）

## 目的
在译文草稿已经存在之后，对"机器可判定的不变量"做确定性核验，防止数字、单位、引文、图表/公式引用、否定与模糊语气在 EN→ZH 翻译中被静默破坏。本技能不评判文风，只做忠实度门禁：阻断项不消除不得交付；一切无法自动确认的事项显式进入人工审阅队列，由人关闭。

## 何时使用 / 不使用
- 使用：已有英文源文 + 中文译文草稿；需要交付前的忠实度把关；需要给人工审阅者一份逐条待确认清单（"需要人工确认的清单"）。
- 不使用：尚无译文草稿（先做翻译而非审计）；需要评估文风、术语优雅度等机器无法判定的问题（交由人工，但可用本技能生成的人工队列承接）；源文与译文无法做段落级对齐时（先做对齐，再审计）。

## Runtime contract
- 本技能安装于 `/skills/weekly-skill`。
- 输入：`/input/case.json`（含 `case_id` 与 `output_contract`）、`/input/task.md` 以及案例材料（真实论文 PDF，无预抽取的答案层）。
- 工作目录：`/app/work`（中间产物：pairs.jsonl、invariants.json、fidelity_report.* 等）；最终产物在 `/app/output`，其中 `result.json` 必须包含原始 `case_id` 以及 `output_contract` 声明的每一个字段。
- 预算：约 64 次模型请求 / 900 秒。必须**先用** `scripts/finalize_result.py` 写出一份部分 result.json（状态 `partial`），再就地改进；任何时候中断都有一份可提交的合法结果。
- 状态字段诚实取值：`success` / `partial` / `unable_to_determine` / `refused`；绝不捏造数据、检查计数或结论；机器无法判定的内容明确标注为无法判断，而不是当作通过。

## 不变量与检查代码一览
- 不变量五族（仅从 source 侧抽取，详见 `references/invariant_taxonomy.md`）：numbers（数值+单位+科学计数）、citations（`[12]`/`(Surname, 2020)`）、refs（Fig./Table/Eq./图/表/式 + 编号）、negations（no/not/never/without/cannot/fail(s|ed) to/neither/nor/none/unable）、hedges（however/although/may/approximately/up to/at least/only 等）。
- BLOCKER（必须先修复再交付）：`number-dropped`、`number-changed`、`unit-changed`、`citation-lost`、`ref-lost`、`negation-lost`、`target-missing`。
- WARNING（可放行但必须入人工队列）：`hedge-lost`、`number-format`。
- 判据与理由详见 `references/severity_and_queue.md`。

## Workflow（编号步骤）
1. **先保底**：运行 `scripts/finalize_result.py --case /input/case.json --out /app/output/result.json --status partial`，确保任何时候都有一份合法 result.json。
2. **组装双语段落对**：从译文草稿构造 `pairs.jsonl`，每行 `{"seg_id","source","target"}`；对齐粒度以句/段为宜，seg_id 稳定且唯一；来源不明或 OCR 失败的段落不要丢弃，保留并标记。
3. **抽取不变量**：`scripts/extract_invariants.py --pairs pairs.jsonl --out invariants.json`。不变量只从 **source 侧** 挖掘（数字+单位、引文、图表/公式引用、否定提示词、模糊/转折提示词）；引文/图表引用区段内的数字会先被掩蔽，避免被误当作数值不变量。
4. **忠实度门禁**：`scripts/check_fidelity.py --invariants invariants.json --pairs pairs.jsonl --out fidelity_report.json --md fidelity_report.md`。BLOCKER（number-dropped、number-changed、unit-changed、citation-lost、ref-lost、negation-lost）必须回译文修复并**重跑直至清零**（脚本退出码 1 ⇔ 存在 blocker）；WARNING（hedge-lost、number-format）可放行但必须进入人工队列。
5. **生成人工队列**：`scripts/review_queue.py --report fidelity_report.json --out human_review_queue.md`，每条未决项带 seg_id、源/译逐字片段、原因与建议动作；报告与队列一一对应，不增删条目。
6. **交付**：`/app/output` 下交付 `result.json` + `invariants.json` + `fidelity_report.json` + `human_review_queue.md`，并用 finalize_result.py 更新状态与 change_record（每次调用追加一条处理记录，非空字段无 `--force` 不覆盖）。

## Output requirements
- 每条 finding 必须携带 `seg_id`、源文与译文的逐字片段（verbatim snippet）、代码（code）与严重级别（severity）；不得改写或转述片段。
- 状态为 `success` 当且仅当 blocker 数为 0；有 blocker 时不得交付为 success，只能 `partial` 或 `unable_to_determine`。
- 即使全部通过，报告也必须声明执行了多少项检查（`summary.checks`）与覆盖多少段（`summary.segments`），不得只写"通过"。
- 人工队列中任何条目不得在未修复/未人工确认的情况下被关闭；关闭时须在处理记录中注明处理人与依据。
- result.json 的每个 `output_contract` 字段都必须存在（未填则为空字符串），缺失字段视为交付失败。

## Exception handling
| 情况 | 处理 |
|---|---|
| 数字出现在图/表图片中 | 标记 `unable_to_determine`（无法判断）并入人工队列，绝不静默通过 |
| 段落形似参考文献列表（≥3 个引文标记） | 跳过否定/模糊语气检查（references 节不适用） |
| OCR 乱码 / 文本抽取失败 | 该段标记 `unable_to_determine`，原因写入队列，由人工直接比对原文 |
| 单位命中词典外形式 | 记 WARNING（unit lexicon miss）而非 BLOCKER，人工确认后决定是否扩展词典 |
| 数字格式差异（1,000 vs 1000、μ vs u、空格） | 归一化后等价则通过，必要时记 `number-format` WARNING |
| 译文缺段（pairs 中无对应 seg_id） | `target-missing` BLOCKER，补齐译文后重跑，不得跳过 |
| 引文区间写法差异（`[5-9]` vs 逐条 `[5][6]…`） | 多重集不等会报 `citation-lost`；人工确认仅为写法差异后按流程关闭 |

## Self-check（交付前逐项确认）
- [ ] result.json 存在且含原始 case_id 与 output_contract 全部字段
- [ ] fidelity_report.json 的 blockers == 0，否则状态非 success
- [ ] summary.checks 与实际检查条数一致且 > 0；summary.segments 与 pairs 段数一致
- [ ] human_review_queue.md 覆盖全部 warning 与未决项，无静默丢弃
- [ ] 所有 finding 的 snippet 均逐字来自 source/target，未改写
- [ ] 任何异常（图片内数字、OCR 乱码、词典外单位、缺段）均已显式标注而非跳过
- [ ] change_record 记录了每次状态变更与字段写入
- [ ] 用 examples/minimal_example.md 的命令做过回归（bad→exit 1 且恰 4 个 blocker；fixed→exit 0）
