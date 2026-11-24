---
name: field-provenance-keeper
description: 科研资料库整理的"元数据真实性守门"技能。当任务要求把混杂文献目录（论文/预印本/补充材料/学位论文/数据集/扫描件，含重复下载、同名异版、别名、管理员说明、损坏或无权限文件）归档、规范命名、去重并交付可复核清单时使用。重心在上游数据真实性：每个元数据字段（标题/作者/年份/期刊/DOI）必须携带来源层与逐字证据片段，落地前经锚定 lint 机械复验，证据锚不住的字段一律降级 unknown 并记冲突，绝不凭空补全；输入只读、不删除任何文件、重跑幂等。不负责单篇精读、全文翻译与文献检索发现。
---

# field-provenance-keeper：字段级证据台账，锚不住就标 unknown

## 1. 核心思想

资料库整理最隐蔽的失败是"元数据看起来齐了，实际是编的"：只凭文件名猜作者、给扫描件补 DOI、把预印本年份当成正式版年份。本 Skill 把**上游数据真实性**作为第一性约束：

1. **字段即证据**：`metadata_ledger.jsonl` 中每个字段（title/authors/year/venue/doi）都是
   `{value, layer, evidence}` 三元组。layer 只取五个值：
   `pdf_text`（正文抽取，含行号定位）、`pdf_info`（PDF 信息字典）、`sidecar`
   （管理员说明/元数据表，含文件与行）、`filename`（文件名解析）、`model_inference`
   （模型综合判断，必须仍给出原文短引）。没有 `unknown` 之外的第六种来源。
2. **锚定 lint 机械复验**：`provenance_lint.py` 把每个非 unknown 的字段值做空白
   归一化后，必须在该文件的证据池（抽取文本全集 + 命中旁挂表行 + 文件名）中作为
   子串命中；`model_inference` 层的 evidence 短引本身也要能锚回原文。锚不住 →
   字段值降级 `unknown`、写入 `conflicts.json`、uncertainties 留痕。**lint 是脚本，
   不占模型预算，模型无法绕过。**
3. **冲突显性化**：文件名、正文、旁挂表三方取值不一致时不做静默选择，全部取值
   连同各自证据写入 `conflicts.json`，选用值须注明理由。
4. **输入只读、不删除**：`/input` 绝不修改；重复文件复制到 `_archive_dups/` 归档，
   原始文件与 SHA-256 全程留在 `sources`。

## 2. 适用边界

- 适用：给一批真实文件与明确组织规则（目录维度、命名模板、去重要求、检索问题），
  要求真实产出整理后目录树、清单、操作日志并回答问题的任务。
- 不适用：单篇精读、全文翻译、润色、文献检索发现；无文本层扫描件的 OCR（登记
  `no_text_layer`，不猜内容）；加密/损坏/无权限文件的内容判读（如实进 skipped）。

## 3. 运行时契约（Harbor）

- 安装路径 `/skills/weekly-skill`，脚本以 `python3 /skills/weekly-skill/scripts/xxx.py` 调用。
- 输入：`/input/case.json`、`/input/task.md` 与材料目录。case.json 字段名不可假设，
  `inventory.py` 防御式解析（细则见 `references/case_contract.md`）。
- 工作目录 `/app/work`；交付 `/app/output/`：`result.json`（含原 `case_id` 与
  `output_contract` 全部字段、诚实 status）、整理后 `library/`、`metadata_ledger.jsonl`、
  `operations.jsonl`、`conflicts.json`、`lint_report.json`。
- `status` 取值：`complete`（零跳过且核验通过）/ `partial`（有跳过或冲突，必须
  列出限度）/ `blocked`（库不可读等）。**partial 不得写成 complete。**
- 依赖：Python 3 标准库；`pdftotext` 存在则用于 PDF 文本抽取，缺失时降级为
  `extract_unavailable` 并留痕，不中断流程。
- 预算：64 次模型请求 / 900 秒。脚本零模型请求；模型只需 1–3 次响应
  （决策、版本关系、检索回答），且**第一步永远是脚本 init**，10 秒内落地保底
  partial result.json。

## 4. 工作流程

设 `S=/skills/weekly-skill/scripts`（本地验证替换为本 bundle 内 `scripts/` 绝对路径）。

### 第 1 步：只读盘点 + 字段级候选抽取（脚本，0 次模型请求）

```bash
python3 $S/run_case.py init --input /input --work /app/work --out /app/output
```

产物：
- `/app/work/files.jsonl`：每文件 `{fid, rel, size, sha256, readable, kind, extract_status, head_text, year_hint, doi_hint}`；
- `/app/work/aliases.json`：SHA-256 相同的字节级重复分组；
- `/app/work/meta_candidates.json`：每文件的候选元数据，**每个字段已带 layer 与 evidence 短引**（pdf_text/pdf_info/filename/sidecar 四层自动抽取的结果）；
- `/app/work/sidecars.json`：旁挂说明文件清单与其内容摘录（管理员版本说明、meta 表，**模型必读**）；
- `/app/output/result.json`：`status="in_progress"` 保底版。

### 第 2 步：模型决策（1–3 次模型请求）

模型读 `/app/work/decision_digest.md`（init 生成的紧凑摘要）、task.md 与旁挂说明，
写 `/app/work/decisions.json`：

```json
{
  "assignments": [{"fid": "F001", "category": "journal-articles", "subcategory": "2022",
    "new_name": "Smith-2022-GNN Screening of Perovskite Catalysts",
    "metadata": {"title": {"value": "...", "layer": "pdf_text", "evidence": "……逐字短引……"},
                 "authors": {"value": "Smith, J.; Lee, K.", "layer": "pdf_text", "evidence": "……"},
                 "year": {"value": "2022", "layer": "pdf_text", "evidence": "……"},
                 "venue": {"value": "unknown"}, "doi": {"value": "10.xxxx/yyy", "layer": "pdf_text", "evidence": "……"}},
    "disposition": "keep", "rationale": "……", "evidence": "……"}],
  "version_relations": [{"group": ["F001", "F002"], "relation": "preprint_of/published",
    "canonical": "F002", "evidence": "……"}],
  "answers": [{"qid": "Q1", "answer": "……", "evidence": "……"}]
}
```

规则（细则见 `references/provenance_rules.md`）：

- 模型**优先采用** `meta_candidates.json` 中已带证据的候选值；自行给出的值必须
  提供 `evidence`（从抽取文本逐字复制的短引，≤200 字符），layer 标 `model_inference`。
- 拿不准的字段写 `"value": "unknown"`，**这是加分行为不是失败**；lint 会惩罚编造，
  不会惩罚 unknown。
- 旁挂表（meta.csv 等）与正文取值冲突时：两值都保留，正文层优先，冲突写进
  `conflicts` 数组。
- `disposition ∈ {keep, archive_dup}`：仅字节级重复（同 SHA-256）可 `archive_dup`；
  同题异版全部 `keep`，只在 version_relations 登记。
- 无法解析/无权限文件不给归档目标，自动进 skipped。

### 第 3 步：锚定 lint（脚本，0 次模型请求）

```bash
python3 $S/run_case.py lint --work /app/work
```

`provenance_lint.py` 逐字段锚定复验：值与 evidence 双向锚定（值必须出现在证据池，
evidence 必须出现在该文件抽取文本）。未通过字段降级 `unknown` 并记
`/app/work/lint_report.json` + `/app/work/conflicts.json`。**模型若不同意降级，只能
补充更强的逐字证据后重跑 lint，不得手改 lint 结果。**

### 第 4 步：落地 + 核验 + 交付（脚本，0 次模型请求）

```bash
python3 $S/run_case.py finalize --work /app/work --out /app/output
```

- 复制到 `/app/output/library/<category>/<subcategory>/<new_name>.<ext>`（名称清洗、
  冲突自动加序号、不覆盖）；旁挂说明复制到 `00-admin/`；`archive_dup` 进 `_archive_dups/`。
- 逐条写 `/app/output/operations.jsonl`（src/dst 双侧 SHA-256）；幂等：已完成的操作
  重跑自动跳过。
- 重扫输出树核验哈希与覆盖率，写 `verify_report.json`。
- 终版 `result.json`：`case_id` + `status` + mirror `output_contract` 全字段
  （`library_index`/`operations_log`/`version_relations`/`skipped`/`answers`/
  `sources`/`uncertainties`/`change_log`，契约外字段保留为附加键）+
  `metadata_ledger.jsonl`（终版字段级台账，含 lint 降级痕迹）+ `conflicts.json`。

## 5. 异常处理

| 情况 | 处置 |
|---|---|
| 损坏/加密 PDF | `extract_status=extract_error`，进 skipped，元数据全 unknown，不猜 |
| 无文本层扫描件 | `no_text_layer`，进 skipped，登记"需 OCR"，不猜内容 |
| 无权限文件 | `permission_denied`，进 skipped，记录路径与错误 |
| 中文乱码/编码异常 | `utf-8 errors=replace` 读取并记 `encoding_issue` |
| 旁挂表与正文冲突 | 双值留档进 conflicts.json，正文层优先并注明 |
| lint 降级 | 字段 unknown + conflicts.json + uncertainties 留痕 |
| 库目录不存在 | `status="blocked"` 的 result.json，不空跑 |

## 6. 最小调用示例（合成示例）

`examples/` 内含合成夹具生成器与一键脚本：

```bash
cd examples && python3 make_fixture.py && bash run_example.sh
```

生成 12 个合成文件（含字节级重复、预印本/正式版/SI 三件套、损坏 PDF、无权限文件、
无文本层扫描件、管理员版本说明、meta.csv），跑通 init →（预写决策，代替模型步骤）
→ lint → finalize，输出见 `examples/sample_output.md`。**该示例为合成示例，输入与
决策均为演示数据，非正式案例结果。**

## 7. 自查清单

- [ ] result.json 含 case_id 与 output_contract 全部字段；status 与 skipped 一致。
- [ ] metadata_ledger 中无"无 evidence 的非 unknown 值"（lint 报告零未决）。
- [ ] 输入目录 mtime/hash 未变；operations.jsonl 每条含双侧哈希。
- [ ] 重跑 finalize 后输出树不变（幂等）。
- [ ] conflicts.json 非空时已同步写入 uncertainties。
