---
name: quant-evidence-synth
description: 文献综述生成的"定量证据字段与数值冲突合成"协议。当任务给出一批真实文献（PDF/文本）与涉及效果、性能、剂量、耗时等定量指标的研究问题，要求完成趋势分析、效果比较或证据合成时使用。核心机制：任何定量论断之前先做数值证据结构化——用正则从分页锚点文本中抽取"数值+单位+指标词+定位"的 quant candidate；按词表把 ms/s/min、g/kg、cm/m、%/ratio 归一化到 canonical 量纲；对同一指标、同一量纲的跨文献数值对做冲突检测（相对差异 >20% 或置信区间不重叠 → 冲突候选，供模型裁决，绝不自动调和或取平均）；交付前由脚本执行数字回链门控——草稿与证据表中出现的每个数值必须能匹配到某个 quant candidate（容忍单位换算后的 canonical 相等，容差 1e-6，百分数与 ratio 等价），无法回链的数字在草稿中就地标 [数值未定位] 并写入门控报告。适用于趋势分析、系统综述的效果合成、性能基准比较；不负责统计推断本身（不做 meta 分析加权合并）、不裁决冲突谁对谁错。
---

# quant-evidence-synth：定量证据字段与数值冲突合成

## 1. 本 Skill 解决什么问题

综述中的**数字**是最容易出错、最难复核的部分：一篇用 ms 一篇用 s 被直接比较；同一指标两篇相差 30% 被平均成一个"总体提升"；草稿里的数字找不到出处；单篇摘要的数值被表述为"平均提升"。本 Skill 的重心是**把文献中的数值先结构化为可机检的证据字段，再用脚本强制约束写作**：

1. **数值抽取**：`extract_quant.py` 用正则从每篇分页文本中抽取数值候选——含数字+可选单位的句子（`%`、`ms/s/min`、`n=` 样本量、`p<0.05`、`CI [..]`/`(..)`、`mean±sd`、`0.xx` 小数），按 `vocab/metric_terms.json` 标注规范化指标名，带 `p<页>.¶<段>` 定位，写 `work/quant_candidates.jsonl`。
2. **单位归一化**：`normalize_units.py` 按 `vocab/units.json` 为每个候选增加 `value_canonical/unit_canonical/dimension`（ms→s、g→kg、cm→m、%→ratio，含换算系数）；无单位但指标有默认量纲的按默认处理；无法归一化的标 `unnormalized`，**禁止参与跨文献比较**。
3. **数值冲突检测**：`numeric_conflict.py` 对同一 metric 且归一化量纲相同的跨文献数值对，判相对差异 >20% 或 CI 不重叠 → 冲突候选写 `work/numeric_conflicts.json`；冲突**供模型裁决**（说明对象/条件差异后并列 contested），脚本不自动调和；近重复组内只取代表篇参与比较，避免同一研究的重复版本被当成独立证据。
4. **数字回链门控**：`verify_quant.py` 扫描草稿与证据表中的每个数值（与抽取共用同一套 tokenizer），必须能匹配到某个 quant candidate——容忍单位换算后的 canonical 相等（容差 1e-6），百分数与 ratio 等价；无法回链的数字在文中就地标 `[数值未定位]` 并写入 `out/quant_gate_report.json`。

## 2. 适用条件与不适用范围

适用：研究问题涉及定量指标比较（效果、性能、耗时、剂量等）的综述、趋势分析、证据合成；材料可含 PDF、纯文本、仅摘要、近重复条目。不适用：统计层面的 meta 分析加权合并、原始数据重分析、冲突真相裁决（只检测并并列，不判定谁对）、纯定性综述。

## 3. 输入契约（防御式解析）

Harbor 运行契约：输入 `/input/case.json` 与 `/input/task.md`；材料由 case 指定或在 `/input/` 下发现；工作 `/app/work`；交付 `/app/output/`。**不得假设字段名**：

1. `case_id`：依次 `case_id`/`caseId`/`id`；缺失用文件名并记入 uncertainties。
2. 研究问题：递归查 `research_question`/`question`/`topic`/`title`/`objective`/`rq`；再读 task.md，task.md 具体要求优先。
3. 文献清单：递归查 `documents`/`papers`/`references`/`files`/`literature`/`corpus`/`materials`；元素可为路径字符串或含 `path`/`file`/`pdf`/`url`/`title` 的字典；都不命中则按 `*.pdf → *.txt → *.md → *.html` 扫描 `/input/`。URL 无本地文件记 `metadata_only`，不伪造全文。
4. `output_contract`：递归查 `output_contract`/`contract`/`output_fields`/`required_fields`；`build_result.py` 逐字段镜像，缺内容填 null 并说明，**不得漏字段**。

零文献或全部解析失败：照常写出 `status="blocked"` 的 result.json 与说明，不得空跑。

## 4. 运行方式

```bash
S=<skills 目录>/quant-evidence-synth/scripts
python3 $S/run_case.py init     --case /input/case.json --task /input/task.md --input-dir /input --work /app/work --out /app/output
# …模型阶段（第 5 节阶段 1–2），全部落盘 /app/work …
python3 $S/run_case.py verify   --work /app/work --out /app/output
python3 $S/run_case.py finalize --work /app/work --out /app/output
```

`init` 在数秒内完成解析+抽取+归一化+冲突检测并写出 partial result.json（`status=in_progress`，契约字段以 null 占位），此后任何中断都留有可核对产物。

## 5. 工作流程（预算内完成：64 次请求 / 900 秒 / 16k token）

### 阶段 0：解析与数值证据结构化（脚本，0 次模型请求）

`run_case.py init` 依次执行 `ingest.py`（防御式解析、材料发现、`pdftotext -layout` → 纯文本回退、分页锚点、SHA-256、分级、近重复分组）、`extract_quant.py`、`normalize_units.py`、`numeric_conflict.py`。先读 `work/quant_normalized.jsonl` 与 `work/numeric_conflicts.json` 再动手——**草稿里允许出现的数字集合已经确定**。

### 阶段 1：定量证据表（模型 2–6 次）

按 `templates/evidence_table.md` 从 quant candidates 中挑选与研究问题相关的行，写 `work/evidence_table.md`：每行绑定 qid 与 locator，"数值(原文)"列照抄候选的 value/unit，"归一化值"列照抄 value_canonical；需要解读时写备注列，**不得改动数值本身**。对 `numeric_conflicts.json` 中的每个冲突对，在备注中说明两篇的对象/条件差异假设，强度标 contested。单源数值不得写"平均提升/总体效应"（规则见 `rules/numeric_strength.md`）。

### 阶段 2：草稿与数字门控（模型 2–4 次 + 脚本）

按 `templates/review_draft.md` 写 `work/review_draft.md`：中文书面语、非人称；**每个数值必须来自 quant candidate**（可写原文值，或写归一化值并注明换算，如"350 ms（归一化 0.35 s）"）；冲突数值并列呈现，标 contested，禁止取平均；推断句前缀 `[推断]`；证据未覆盖处写 `[证据缺口]`。然后 `run_case.py verify` 执行数字回链门控：未匹配数字就地标 `[数值未定位]`，报告写 `out/quant_gate_report.json`。修复流程：把未定位数字替换为 quant candidate 中的值（或删除该论断）→ 重跑 verify；两轮仍失败则记入 uncertainties。最后 `run_case.py finalize` 组装 result.json。

## 6. 异常处置（必须写进 uncertainties）

- 单位不一致：先归一化再比较；`unnormalized` 候选一律不参与跨文献比较，只在文中定性提及。
- 数值冲突：并列 contested，说明各自对象/条件，不取平均、不只留正向；冲突对全部留在 result.json 的 `numeric_conflicts` 字段。
- 单源数值：不得称"平均提升""总体效应"；强度 ≤ suggestive。
- 仅摘要：strength ≤ suggestive，草稿与证据表标注 `abstract_only`。
- 近重复：只取代表篇参与冲突检测，重复篇数值不作独立证据。
- 派生数字（如相对差异百分比、均值）：不得直接写进草稿正文，以"见 numeric_conflicts.json"方式引用脚本产物。
- 语料为空/全部解析失败：`status="blocked"`，照常交付。

## 7. 默认输出结构（output_contract 缺失时）

```json
{"case_id":"…","status":"completed|partial|blocked",
 "research_product":{"question":"…","themes":[…],"draft_file":"review_draft.md","draft_excerpt":"…"},
 "quant_summary":{"candidates":12,"normalized":11,"unnormalized":1,"by_dimension":{"ratio":4,"time":3},"conflict_pairs":1},
 "numeric_conflicts":[{"conflict_id":"C1","metric":"recall@10","a":{…},"b":{…},"rel_diff":0.297,"reasons":[…]}],
 "evidence_table":{"file":"evidence_table.md","excerpt":"…"},
 "uncertainties":[…],
 "sources":[{"doc_id":"D1","ref":"…","sha256":"…","tier":"fulltext","metadata":{}}],
 "change_log":[…],"quant_gate_report":{…}}
```

## 8. 文件清单

- `scripts/run_case.py`：init/verify/finalize 编排器。
- `scripts/ingest.py`：防御式解析、材料发现、抽取、分级、近重复分组。
- `scripts/extract_quant.py`：数值候选抽取（签名脚本 1）。
- `scripts/normalize_units.py`：单位归一化（签名脚本 2）。
- `scripts/numeric_conflict.py`：跨文献数值冲突检测（签名脚本 3）。
- `scripts/verify_quant.py`：数字回链门控（签名脚本 4）。
- `scripts/build_result.py`：result.json 组装与 output_contract 镜像。
- `vocab/metric_terms.json`：指标词表；`vocab/units.json`：单位归一化表。
- `rules/numeric_strength.md`：数值证据强度规则。
- `templates/evidence_table.md`、`templates/review_draft.md`。
- `examples/`：合成示例（`make_example.py` 端到端生成并运行，产物标注 simulated）。
