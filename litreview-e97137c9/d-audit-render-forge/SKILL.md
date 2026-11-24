---
name: audit-render-forge
description: 文献综述生成的"下游渲染工程：可复核交付物锻造"协议。当综述的证据表与草稿已经产出、需要把结果交付给评审或下游系统时使用。核心思想：交付物不是一篇孤立文本，而是一套可独立复核的审计包——草稿中每条论断句 → 引用的证据行 → 逐字摘录 → 文档与页锚点，全部渲染进一份自包含 HTML 审计报告，评审无需任何外部工具即可点击核对；同时产出 Excel 可直接打开的证据矩阵 CSV（UTF-8 带 BOM）与文档×主题覆盖矩阵 JSON（含未被任何主题覆盖的文档清单）。交付前由三道脚本闸口把关：compile_audit.py 锻造审计产物、link_check.py 校验 [E#] 标记全部可解析并列出未被引用证据与无支撑句（失败即非零退出）、validate_result.py 按手写 schema（不依赖 jsonschema 库）校验 result.json 的必填键、类型、status 枚举与 output_contract 逐字段完备。适用于任何需要可审计交付的综述、系统筛选与证据合成任务；不负责来源取证、单篇精读与语言润色。
---

# audit-render-forge：可复核交付物锻造的文献综述生成

## 1. 本 Skill 解决什么问题

综述最常见的交付失败不是"写错"，而是**无法核对**：评审拿到一篇带 `[E#]` 标记的草稿，却没有地方点开看这条证据到底摘自哪篇文献的哪一页；结构化结果 result.json 缺了 output_contract 里的字段，下游系统静默报错。本 Skill 的重心是**把交付物本身工程化为一套可独立复核的审计包**：

1. **论断-证据-摘录-锚点四级可点击核对**：自包含 HTML 审计报告（内联 CSS、零外部资源）把草稿的每个论断句展开为引用的证据行、逐字摘录与 `p<页>.¶<段>` 锚点，评审在浏览器中即可完成复核。
2. **覆盖透明**：`coverage_map.json` 给出文档×主题覆盖矩阵，并显式列出"未被任何主题覆盖的文档"，防止语料被静默丢弃。
3. **链接闸口**：`link_check.py` 解析草稿全部 `[E#]` 标记，任何一个指向不存在的证据行即非零退出；同时列出从未被引用的证据行与无证据标记的实质句。
4. **契约闸口**：`validate_result.py` 按手写 schema 校验 result.json——必填键、类型、`status` 枚举、evidence_matrix/sources 元素必填字段、output_contract 逐字段完备、case_id 一致——校验通过才算交付。

## 2. 适用条件与不适用范围

适用：证据表（evidence_ledger.jsonl）与带 `[E#]` 标记的综述草稿已经或即将产出，需要面向评审/下游系统交付可审计结果的任务；材料可含 PDF、纯文本、仅摘要条目。不适用：来源身份取证（题名/DOI 核验、撤稿检测）、定量数值合成、单篇精读与润色。

## 3. 输入契约（防御式解析）

Harbor 运行契约：输入 `/input/case.json` 与 `/input/task.md`；材料由 case 指定或在 `/input/` 下发现；工作 `/app/work`；交付 `/app/output/`。**不得假设字段名**：

1. `case_id`：依次 `case_id`/`caseId`/`id`；缺失用文件名并记入 uncertainties。
2. 研究问题：递归查 `research_question`/`question`/`topic`/`title`/`objective`/`rq`；再读 task.md，task.md 具体要求优先。
3. 文献清单：递归查 `documents`/`papers`/`references`/`files`/`literature`/`corpus`/`materials`；元素可为路径字符串或含 `path`/`file`/`pdf`/`url`/`title` 的字典；都不命中则按 `*.pdf → *.txt → *.md → *.html` 扫描 `/input/`。URL 无本地文件记 `metadata_only`，不伪造全文。
4. `output_contract`：递归查 `output_contract`/`contract`/`output_fields`/`required_fields`；`build_result.py` 逐字段镜像，缺内容填 null 并说明，**不得漏字段**；`validate_result.py` 再对照 `work/case_profile.json` 复核一遍。

零文献或全部解析失败：照常写出 `status="blocked"` 的 result.json 并照常过校验，不得空跑。

## 4. 运行方式

```bash
S=<skills 目录>/audit-render-forge/scripts
python3 $S/run_case.py init     --case /input/case.json --task /input/task.md --input-dir /input --work /app/work --out /app/output
# …模型阶段（第 5 节阶段 1–3），全部落盘 /app/work …
python3 $S/run_case.py render   --work /app/work --out /app/output    # 任一闸口失败即非零退出
python3 $S/run_case.py finalize --work /app/work --out /app/output    # 校验失败即非零退出
```

`init` 在数秒内写出 partial result.json（`status=in_progress`），此后任何中断都留有可核对产物。

## 5. 工作流程（预算内完成：64 次请求 / 900 秒 / 16k token）

### 阶段 0：解析与锚点化（脚本，0 次模型请求）

`run_case.py init` 执行 `ingest.py`：防御式解析、材料发现、`pdftotext -layout` → 纯文本回退、分页锚点（`pages/<doc_id>.jsonl`）、SHA-256、分级（fulltext/abstract_only/failed/metadata_only）与近重复分组。产物：`case_profile.json`、`docs.jsonl`、`pages/`、`dup_groups.json`。

### 阶段 1：筛选与逐文档摘要（模型 1 次/文档或按页批）

写 `/app/work/criteria.md`（纳入/排除标准带编号、绑定研究问题）与 `/app/work/screening_log.json`；逐篇按 `pages/<doc_id>.jsonl` 锚点分块写 `/app/work/digests/<doc_id>.md`。仅摘要来源在摘要中标注 `abstract_only`。

### 阶段 2：主题归纳与证据表（模型 3–8 次）

主题从这批文献的 digest 中长出来，写 `/app/work/themes.json`（`[{"theme":"T1","label":"…","boundary":"…","docs":["D1"]}]`），禁止套"背景/方法/挑战/展望"模板；themes 的 `docs` 清单是覆盖矩阵的分母，**纳入主题的每篇文献都必须出现在某个 theme 的 docs 里**。建 `/app/work/evidence_ledger.jsonl`，每行：

```json
{"evidence_id":"E1","doc_id":"D3","locator":"p2.¶4","verbatim_quote":"……","supports":"……","theme":"T2","strength":"established|suggestive|contested"}
```

`verbatim_quote` 必须是从 `pages/<doc_id>.jsonl` 对应页复制的逐字子串（仅允许归一化空白/断词）；冲突证据并列 `contested`，不调和。

### 阶段 3：草稿、渲染与三道闸口（模型 2–4 次 + 脚本）

按模板 `templates/review_draft.md` 写 `/app/work/review_draft.md`：中文书面语、非人称；每个实质论断句尾标 `[E#]`；推断句前缀 `[推断]`；证据未覆盖处写 `[证据缺口]`。然后 `run_case.py render`：

1. `compile_audit.py` 锻造 `out/evidence_matrix.csv`（UTF-8 带 BOM）、`out/coverage_map.json`、`out/audit_report.html`（按 `templates/audit_report.html.tmpl` 渲染）。
2. `link_check.py` 校验标记可解析性，写 `out/link_check_report.json`；**有未解析标记即非零退出**，render 整体失败。
3. 修复闭环：按报告定位问题句 → 删除或补证据 → 重跑 render 直至退出码为 0。两轮仍无法修复的论断移入 uncertainties。

最后 `run_case.py finalize`：`build_result.py` 组装 result.json（镜像 output_contract 全字段），`validate_result.py` 按 `schemas/result.schema.json` 手写校验并写 `out/validation_report.json`，**校验不通过即非零退出，不得交付**。

## 6. 异常处置（必须写进 uncertainties）

- 仅摘要：strength ≤ suggestive，草稿与证据表标注 `abstract_only`。
- 元数据不全：以文件名标识，不猜测补齐。
- 近重复/版本变体：只纳入代表篇，其余在 `dup_groups.json` 与覆盖矩阵中可见。
- 未被任何主题覆盖的文档：在 `coverage_map.json.uncovered_documents` 显式列出并写入 uncertainties。
- 未被草稿引用的证据行、无标记实质句：保留在审计报告中，不删除，由评审裁决。
- 结论冲突：并列 `contested`，不取平均。
- 语料为空/全部解析失败：`status="blocked"`，照常交付并通过 schema 校验。

## 7. 默认输出结构（output_contract 缺失时）

```json
{"case_id":"…","status":"completed|partial|blocked",
 "research_product":{"question":"…","themes":[…],"draft_file":"review_draft.md","bottom_line":"…"},
 "evidence_matrix":[{"evidence_id":"E1","doc_id":"D1","locator":"p3.¶2","verbatim_quote":"…","supports":"…","theme":"…","strength":"…"}],
 "audit_artifacts":{"evidence_matrix_csv":"…","coverage_map_json":"…","audit_report_html":"…","link_check_report":"…"},
 "link_check":{"ok":true,"referenced":4,"unused":0,"unsupported":0},
 "uncertainties":[…],
 "sources":[{"doc_id":"D1","ref":"…","sha256":"…","tier":"fulltext"}],
 "change_log":[…]}
```

## 8. 自查方法

交付前依次确认：`render` 退出码为 0；`link_check_report.json.ok == true`；`audit_report.html` 可直接双击在浏览器打开（无外部请求）；`evidence_matrix.csv` 用 Excel 打开中文不乱码（BOM）；`coverage_map.json.uncovered_documents` 非空时已写入 uncertainties；`finalize` 退出码为 0 且 `validation_report.json.ok == true`。

## 9. 文件清单

- `scripts/run_case.py`：init/render/finalize 编排器。
- `scripts/ingest.py`：防御式解析、材料发现、抽取、分级、近重复检测。
- `scripts/compile_audit.py`：审计包锻造——evidence_matrix.csv、coverage_map.json、audit_report.html（签名脚本）。
- `scripts/link_check.py`：`[E#]` 标记解析校验、未用证据与无支撑句清单（签名脚本）。
- `scripts/validate_result.py`：按手写 schema 校验 result.json（签名脚本）。
- `scripts/build_result.py`：result.json 组装与 output_contract 镜像。
- `schemas/result.schema.json`：手写校验规约。
- `rules/audit_pack.md`：审计包规范。
- `templates/audit_report.html.tmpl`、`templates/review_draft.md`。
- `examples/`：合成示例（`make_example.py` 端到端生成并运行，含"校验-修复"闭环演示，产物标注 simulated）。
