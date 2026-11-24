---
name: bounded-topic-appraiser
description: 文献综述生成的"决策端点：空白驱动的有界选题评估"协议。当任务除综述外还要求回答"接下来做什么选题"（case 给出候选选题与约束，或需要模型提出候选）时使用。核心机制：研究空白不允许凭空声明——先按 population/method/metric/outcome 四类 facet 词表给全部文献打标，检测仅单篇覆盖的主题、0 覆盖的 facet 值与模型论断中方向相反的未裁决冲突，登记为空白且每条必须绑定"已查文献清单"与可回链证据；选题评估是带显式约束的决策——候选选题按语料内新颖度（1 − 直接覆盖文献比例）、证据充分度（相关文献数与分级加权）、约束契合度（体内/随机/样本量等约束关键词与文献 facet 逐条核查）加权打分，给出 strong/conditional/not_recommended 推荐档位，产出决策备忘录而非泛泛的综述结尾。适用于选题论证、基金/开题候选评估、研究议程排序；不负责单篇精读、全文翻译与语言润色，新颖度结论仅在所给语料内有界成立。
---

# bounded-topic-appraiser：空白驱动的有界选题决策

## 1. 本 Skill 解决什么问题

综述类任务常以"未来研究方向"收尾，而这类结尾最容易失控：凭空断言"尚无研究"、
把语料未覆盖当成领域空白、用"有待进一步研究"敷衍交差。本 Skill 的重心是
**把选题评估变成一个带显式约束、可复核的决策端点**：

1. **空白从证据分布里长出来**：先用 `vocab/facets.json`（population/method/metric/
   outcome 四类词表）给每篇文献打标，空白只有三种合法来源——仅 1 篇覆盖的主题
   （single_source）、模型论断中方向相反的未裁决冲突（unresolved_conflict）、
   0 篇覆盖的 facet 值（facet_absent）。每条空白必须绑定"已查文献清单"
   （docs_checked）与可回链证据（binding_evidence），见 `rules/gap_evidence_binding.md`。
2. **选题评分是带约束的决策**：候选选题（从 case.json 递归探测，缺失时用模型产出的
   topics.md）按三维打分——语料内新颖度、证据充分度、约束契合度——加权得到
   strong / conditional / not_recommended 推荐档位，规则见 `rules/appraisal_rubric.md`。
3. **交付决策备忘录而非泛泛结尾**：`out/decision_memo.md` 给出结论一览表、逐题理由、
   绑定空白清单与边界声明；`research_product` 内嵌备忘录全文。

## 2. 适用条件与不适用范围

适用：给定文献集合 + 研究问题 + 候选选题/约束（或要求模型提出候选选题）的选题
论证、开题候选排序、研究议程评估。不适用：单篇精读、全文翻译、润色、选刊；新颖度
结论仅在所给语料内有界成立，不构成"全球首创"判断。

## 3. 输入契约（防御式解析）

Harbor 运行契约：输入 `/input/case.json` 与 `/input/task.md`；材料由 case 指定或在
`/input/` 下发现；工作 `/app/work`；交付 `/app/output/`。**不得假设字段名**：

1. `case_id`：依次 `case_id`/`caseId`/`id`；缺失用文件名并记入 uncertainties。
2. 研究问题：递归查 `research_question`/`question`/`topic`/`title`/`objective`/`rq`；
   再读 task.md。
3. 文献清单：递归查 `documents`/`papers`/`references`/`files`/`literature`/`corpus`/
   `materials`；元素可为路径字符串或含 `path`/`file`/`pdf`/`url`/`title` 的字典；
   都不命中则按 `*.pdf → *.txt → *.md → *.html` 扫描 `/input/`。URL 无本地文件记
   `metadata_only`，不伪造全文。
4. **候选选题**：递归查 `candidate_topics`/`proposals`/`options`/`topics`，全部命中
   收集、拍平去重写入 `work/case_extras.json`；缺失时 appraise 阶段回退读取模型产物
   `work/topics.md` 并记 uncertainties。
5. **约束**：递归查 `constraints`/`budget`/`limitations`/`requirements`，同样写入
   `case_extras.json`；缺失时 constraint_fit 记 null，权重按 0.6/0.4 归一。
6. `output_contract`：递归查 `output_contract`/`contract`/`output_fields`/
   `required_fields`；`build_result.py` 逐字段镜像，缺内容填 null 并说明，不得漏字段。

零文献或全部解析失败：照常写出 `status="blocked"` 的 result.json 与说明，不得空跑。

## 4. 运行方式

```bash
S=<skills 目录>/bounded-topic-appraiser/scripts
python3 $S/run_case.py init     --case /input/case.json --task /input/task.md --input-dir /input --work /app/work --out /app/output
# …模型阶段（第 5 节阶段 1）：写 work/themes.json、work/claims.jsonl、（可选）work/topics.md …
python3 $S/run_case.py gaps     --work /app/work
python3 $S/run_case.py appraise --work /app/work --out /app/output
python3 $S/run_case.py finalize --work /app/work --out /app/output
```

`init` 在数秒内写出 partial result.json（`status=in_progress`），此后任何中断都留有
可核对产物。

## 5. 工作流程（预算内完成：64 次请求 / 900 秒 / 16k token）

### 阶段 0：解析、锚点化与 facet 打标（脚本，0 次模型请求）

`run_case.py init` 依次执行 `ingest.py`（防御式解析、材料发现、`pdftotext -layout` →
纯文本回退、分页锚点、SHA-256、分级、候选选题与约束探测 → `case_extras.json`）与
`facet_scan.py`（按 `vocab/facets.json` 打标 → `work/facet_matrix.json`：每篇 facet、
覆盖统计、underpowered/absent facet、theme 覆盖缺口）。先读 facet_matrix 再动手——
**它决定空白能从哪里长出来**。

### 阶段 1：主题与论断（模型 3–8 次请求）

- 写 `work/themes.json`：`[{"theme":"T1","label":"…","docs":["D1","D2"]}]`；主题从
  facet 分布与文献内容中长出来，禁止套"背景/方法/展望"模板。不写则由脚本按 facet
  共现粗聚类代替，并记 uncertainties。
- 写 `work/claims.jsonl`，每行
  `{"claim_id":"C1","doc_id":"D1","topic":"…","direction":"positive|negative|neutral","statement":"…"}`；
  结论冲突的论断按相反 direction 如实登记，**并列不调和**。
- case 未给候选选题时写 `work/topics.md`（每行 `- 选题`），数量 3–7 个，至少一个应
  对应 facet_absent 空白（否则说明理由）。

### 阶段 2：空白登记（脚本）

`run_case.py gaps` 执行 `gap_register.py`：合并 single_source 主题、claims.jsonl 中
同 topic 方向相反的论断对、facet_absent 值 → `work/gap_register.json`，每条
`{gap_id, gap_type, description, docs_checked, binding_evidence, …}`。模型应逐条
复核 docs_checked 是否与描述一致；任何无绑定空白必须删除或补绑定。

### 阶段 3：选题评估与交付（脚本 + 模型复核）

`run_case.py appraise` 执行 `appraise.py`：按 `rules/appraisal_rubric.md` 逐题打分
→ `out/appraisal_matrix.json` 与 `out/decision_memo.md`。模型复核：分数与档位是否
与规则一致、绑定空白是否真实、备忘录第 4 节是否需要补充 [模型判断]。随后
`run_case.py finalize` 组装 result.json。

## 6. 异常处置（必须写进 uncertainties）

- 仅摘要（abstract_only）：相关文献计数按 0.5 篇计，不当作完整证据底座。
- 元数据不全/URL 无全文：metadata_only，不参与覆盖统计，不伪造全文。
- 文本抽取失败：failed，不入分母。
- 模型未产出 themes.json：facet 共现粗聚类代替，标注 themes_source。
- 候选选题缺失：回退 topics.md；两者皆无 → appraise 产出空矩阵，status=partial。
- 约束无法核查：unverifiable 按 0.5 计入，逐条说明，不猜测为满足。
- 结论冲突：并列登记 unresolved_conflict，绑定该空白的选题在理由中注明冲突存在。
- 语料为空/全部不可用：`status="blocked"`，照常交付。

## 7. 默认输出结构（output_contract 缺失时）

```json
{"case_id":"…","status":"completed|partial|blocked",
 "research_product":{"kind":"bounded_topic_appraisal","decision_memo_file":"decision_memo.md",
   "decision_memo":"<备忘录全文>","recommendations":{"<选题>":{"weighted_total":0.9,"recommendation":"strong","bound_gaps":["G01"]}},
   "constraints_checked":[…],"bottom_line":"<最高分选题>"},
 "appraisal_matrix":{"appraisals":[{"topic":"…","novelty_within_corpus":1.0,
   "evidence_sufficiency":0.667,"constraint_fit":1.0,"weighted_total":0.9,
   "recommendation":"strong","rationale":"…","bound_gaps":[…]}]},
 "gap_register":{"gaps":[{"gap_id":"G01","gap_type":"facet_absent","description":"…",
   "docs_checked":[…],"binding_evidence":[…]}]},
 "facet_matrix":{…},"uncertainties":[…],
 "sources":[{"doc_id":"D1","ref":"…","sha256":"…","tier":"fulltext"}],
 "change_log":[…]}
```

## 8. 文件清单

- `scripts/run_case.py`：init/gaps/appraise/finalize 编排器。
- `scripts/ingest.py`：防御式解析、材料发现、抽取分级、候选选题与约束探测。
- `scripts/facet_scan.py`：facet 打标、underpowered/absent 检测、theme 覆盖缺口（签名脚本）。
- `scripts/gap_register.py`：空白登记，强制 docs_checked/binding_evidence 绑定（签名脚本）。
- `scripts/appraise.py`：候选选题三维评分、档位裁定、决策备忘录渲染（签名脚本）。
- `scripts/build_result.py`：result.json 组装与 output_contract 镜像。
- `vocab/facets.json`：population/method/metric/outcome 四类 facet 词表。
- `rules/appraisal_rubric.md`、`rules/gap_evidence_binding.md`。
- `templates/decision_memo.md`、`templates/gap_register.md`。
- `examples/`：合成示例（`make_example.py` 端到端生成并运行，产物标注 simulated）。

## 9. 自查方法

1. `work/gap_register.json` 每条空白都有非空 `docs_checked` 与 `binding_evidence`；
   全文检索备忘录，不得出现"有待进一步研究"。
2. `out/appraisal_matrix.json` 每题分数可按 `rules/appraisal_rubric.md` 手工复算；
   档位与总分阈值一致。
3. result.json 含 output_contract 全部字段；`research_product.decision_memo` 非空；
   `status` 与实际产物相符（无候选选题不得为 completed）。
4. uncertainties 涵盖：降级文献、粗聚类 theme、topics.md 回退、unverifiable 约束。
