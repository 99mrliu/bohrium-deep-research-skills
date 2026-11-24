---
name: source-truth-gate
description: 文献综述生成的"上游来源真实性门控"协议。当任务给出一批真实文献（PDF/文本，可能含题录错误、重复版本、仅摘要条目甚至撤稿论文）与具体研究问题，要求完成筛选、主题归纳、证据组织并产出可复核综述时使用。核心机制：任何写作之前先做来源取证——从解析文本中提取题名/年份/DOI/arXiv 等身份证据并与 case 元数据比对，识别近重复与版本变体并裁定代表篇，检测撤稿/预印本标记，把每篇文献分为 T1/T2/T3 信任层；随后每条实质论断必须建立在"逐字摘录+页锚点"的证据行上，交付前由脚本执行引用门控与信任强制（established 论断不得建立在 T2/T3 来源上），未通过门控的论断自动降级为推断或移出终稿。适用于任何学科的综述、系统筛选、趋势分析与选题评估；不负责单篇精读、全文翻译与语言润色。
---

# source-truth-gate：来源真实性先行的文献综述生成

## 1. 本 Skill 解决什么问题

综述出错最早、最隐蔽的环节在**上游**：case 给的题录与 PDF 实际内容不符、同一研究的预印本与期刊版被当成两篇、撤稿论文混入证据池、仅有摘要的条目被当成全文引用。这些错误会被后续所有步骤忠实放大。本 Skill 的重心是**在写作之前把文献集合本身核实清楚**，并把核实结果变成强制约束：

1. **身份核验**：每篇文献的题名/年份/DOI/arXiv 从解析文本中独立提取，与 case 提供的元数据比对；不一致即标 `metadata_mismatch` 并降级，绝不按错误题录补造数据。
2. **重复与版本裁定**：近重复分组（标题归一化 + 内容 shingle 相似度），每组裁定代表篇，其余 `duplicate_of`，不得各自独立进入证据池。
3. **信任分层**：T1（代表篇+全文+无撤稿标记）才可支撑 `established` 论断；T2（仅摘要/元数据待核）至多 `suggestive`；T3（题录无全文/抽取失败/撤稿标记）只记录、不引用。
4. **引用门控**：终稿每个 `[E#]` 标记必须解析到"逐字摘录确为所声称页文本子串"的证据行；失败句自动降级为推断。

## 2. 适用条件与不适用范围

适用：给定文献集合与研究问题，要求可复核综述、系统筛选、趋势分析或选题评估；材料可含 PDF、纯文本、仅摘要、缺元数据或重复条目。不适用：单篇精读、全文翻译、润色、选刊、事实层面学术审查。

## 3. 输入契约（防御式解析）

Harbor 运行契约：输入 `/input/case.json` 与 `/input/task.md`；材料由 case 指定或在 `/input/` 下发现；工作 `/app/work`；交付 `/app/output/`。**不得假设字段名**：

1. `case_id`：依次 `case_id`/`caseId`/`id`；缺失用文件名并记入 uncertainties。
2. 研究问题：递归查 `research_question`/`question`/`topic`/`title`/`objective`/`rq`；再读 task.md，task.md 具体要求优先。
3. 文献清单：递归查 `documents`/`papers`/`references`/`files`/`literature`/`corpus`/`materials`；元素可为路径字符串或含 `path`/`file`/`pdf`/`url`/`title` 的字典；都不命中则按 `*.pdf → *.txt → *.md → *.html` 扫描 `/input/`。URL 无本地文件记 `metadata_only`，不伪造全文。
4. `output_contract`：递归查 `output_contract`/`contract`/`output_fields`/`required_fields`；`build_result.py` 逐字段镜像，缺内容填 null 并说明，**不得漏字段**。

零文献或全部解析失败：照常写出 `status="blocked"` 的 result.json 与说明，不得空跑。

## 4. 运行方式

```bash
S=<skills 目录>/source-truth-gate/scripts
python3 $S/run_case.py init     --case /input/case.json --task /input/task.md --input-dir /input --work /app/work --out /app/output
# …模型阶段（第 5 节阶段 1–3），全部落盘 /app/work …
python3 $S/run_case.py verify   --work /app/work --out /app/output
python3 $S/run_case.py finalize --work /app/work --out /app/output
```

`init` 在数秒内写出 partial result.json（`status=in_progress`），此后任何中断都留有可核对产物。

## 5. 工作流程（预算内完成：64 次请求 / 900 秒 / 16k token）

### 阶段 0：解析、锚点化与来源取证（脚本，0 次模型请求）

`run_case.py init` 依次执行 `ingest.py`（防御式解析、材料发现、`pdftotext -layout` → 纯文本回退、分页锚点、SHA-256、分级）与 `source_forensics.py`（身份提取与比对、撤稿/预印本标记、近重复裁定、T1/T2/T3 信任分层）。先读 `/app/work/forensics_report.md` 与 `source_manifest.json` 再动手——**信任层决定每篇文献能怎么用**。

### 阶段 1：筛选与逐文档摘要（模型 1 次/文档或按页批）

先写 `/app/work/criteria.md`：纳入/排除标准各 3–6 条、带编号（IC1…/EC1…）、绑定研究问题措辞；再逐篇给出 `include/exclude + 标准编号` 写入 `/app/work/screening_log.json`。T3 来源不进入证据池但必须在筛选记录中说明原因。逐篇（按 `pages/<doc_id>.jsonl` 锚点分块，宁多请求不超 token）写 `/app/work/digests/<doc_id>.md`：研究对象/数据、方法路线、核心结论（带锚点）、关键数字、局限自述。

### 阶段 2：主题归纳与证据表（模型 3–8 次）

主题从这批文献的 digest 中长出来（合并同义方法/对象/结论簇），写 `/app/work/themes.json`（`[{"theme":"T1","label":"…","boundary":"…","docs":["D1"]}]`），禁止套"背景/方法/挑战/展望"模板。建 `/app/work/evidence_ledger.jsonl`，每行：

```json
{"evidence_id":"E1","doc_id":"D3","locator":"p2.¶4","verbatim_quote":"……","supports":"……","theme":"T2","strength":"established|suggestive|contested"}
```

`verbatim_quote` 必须是从 `pages/<doc_id>.jsonl` 对应页复制的逐字子串；`strength` 不得高于该来源信任层允许的上限（见 `rules/provenance_policy.md`）；冲突证据并列 `contested`，不调和。

### 阶段 3：草稿与门控（模型 2–4 次 + 脚本）

按模板 `templates/review_draft.md` 写 `/app/work/review_draft.md`：中文书面语、无第一人称；每个实质句尾标 `[E#]`；推断句前缀 `[推断]`；证据未覆盖处写 `[证据缺口]` 并落到具体缺口。然后 `run_case.py verify` 执行引用门控与信任强制：失败证据行移出，依赖句降级为推断，报告写入 `/app/output/gate_report.json`。修复流程：回原文重取摘录 → 重跑 verify；两轮仍失败则该行进 uncertainties。最后 `run_case.py finalize` 组装 result.json。

## 6. 异常处置（必须写进 uncertainties）

- 题录与内容不符：标 `metadata_mismatch`，按 T2 降级，不得按题录补造内容。
- 撤稿/撤回标记：T3，不引用，只记录。
- 仅摘要：T2，strength ≤ suggestive，草稿与证据表标注 `abstract_only`。
- 元数据不全：以文件名标识，不猜测补齐。
- 重复/版本变体：只纳入代表篇，其余 `duplicate_of`。
- 结论冲突：并列 `contested`，说明各自对象与条件，不取平均。
- 语料为空/全部解析失败：`status="blocked"`，照常交付。

## 7. 默认输出结构（output_contract 缺失时）

```json
{"case_id":"…","status":"completed|partial|blocked",
 "research_product":{"question":"…","themes":[…],"draft_file":"review_draft.md","bottom_line":"…"},
 "evidence_matrix":[{"evidence_id":"E1","doc_id":"D1","locator":"p3.¶2","verbatim_quote":"…","supports":"…","theme":"…","strength":"…"}],
 "screening_log":{…},"uncertainties":[…],
 "sources":[{"doc_id":"D1","ref":"…","sha256":"…","tier":"fulltext","trust_tier":"T1","metadata":{}}],
 "change_log":[…],"gate_report":{…}}
```

## 8. 文件清单

- `scripts/run_case.py`：init/verify/finalize 编排器。
- `scripts/ingest.py`：防御式解析、材料发现、抽取、分级、近重复检测。
- `scripts/source_forensics.py`：身份核验、版本与撤稿标记、信任分层（签名脚本）。
- `scripts/quote_gate.py`：引用门控与信任强制、草稿降级修订。
- `scripts/build_result.py`：result.json 组装与 output_contract 镜像。
- `rules/provenance_policy.md`：信任分层与表述强度规则。
- `templates/evidence_ledger.md`、`templates/review_draft.md`。
- `examples/`：合成示例（`make_example.py` 端到端生成并运行，产物标注 simulated）。
