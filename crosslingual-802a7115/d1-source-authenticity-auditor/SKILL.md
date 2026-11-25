---
name: xlang-source-authenticity-auditor
description: 跨语言文献检索的上游数据真实性核验（upstream corpus authenticity audit）。在任何检索、匹配、排序之前，先对组织方提供的语料做发现与核验：真实抽取每个文件的正文（含用 pdftotext 处理 PDF）、对每条记录做内容指纹与近重复检测、核对"声明语种 vs 正文实际语种"、标记缺失 DOI/语种/版本归因的缺口，输出可复核的溯源台账（provenance ledger）与人读审计报告。当跨语言检索任务的输入语料可能混有语种标错、完全重复副本、仅有摘要的记录或未经核验的元数据时使用；适用于 /input/case.json + task.md 的 Harbor 运行契约，是版本去重计数与诚实结论的前置步骤。
---

# 跨语言检索上游数据真实性核验（xlang-source-authenticity-auditor）

## 用途与适用条件

跨语言检索结论的可信度上限由输入语料决定：语种标错会导致查询词与结果错配，完全重复副本会虚高命中计数，仅有摘要的记录不能当作全文证据。本 Skill 的重心是**在任何下游处理之前核验上游数据**，产出一份第三方可独立复核的溯源台账。

本 Skill 不做：查询生成、术语翻译、相关性排序（这些由其他环节负责）。核验结果（尤其 duplicate_pairs 与 language_label_mismatch）必须传给下游的去重与覆盖核算步骤。

## 运行契约

- 输入：`/input/case.json`（含 `case_id`、`output_contract`）、`/input/task.md`、语料文件（可能在 `/input` 或其子目录，格式可为 JSON/JSONL/CSV/TSV/TXT/MD/PDF）。
- 工作目录：`/app/work`；最终交付：`/app/output`。
- `/app/output/result.json` 必须含 `case_id` 与 `output_contract` 的全部字段；无法完成的部分写 `status=partial` 并在 `uncertainty` 中说明，**绝不补造文献或元数据**。
- 实际输入文件是事实依据：不依据文件名或标签字段臆断正文内容与语种，一律以抽取出的真实正文为准。

## 调用方式

```bash
# 1. 核验语料（自动发现 /input 与 /app/work 下的语料文件；PDF 调 pdftotext）
python3 scripts/corpus_audit.py --roots /input /app/work \
    --out /app/work/audit --exclude examples

# 2. 阅读审计报告，人工确认每条 finding 的处置
#    /app/work/audit/audit_report.md（人读）+ provenance_ledger.json（机读）

# 3. 在 result.json 中引用台账：sources 列 provenance_ledger.json，
#    uncertainty 收录 language_undetermined 与 missing_doi 的处置说明，
#    duplicate_pairs 用于下游去重计数。
```

脚本完全离线、仅用标准库；PDF 抽取依赖平台预装的 `pdftotext`（缺失时正文标为空并记入 parse_notes，不中断）。900 秒预算下数秒内完成。

## 输出

`/app/work/audit/`：

- `provenance_ledger.json`：每文档一条——`record_id`、`source_file`（绝对路径）、`declared_language`、`detected_language`＋置信度＋证据（停用词得分/kana/han 计数）、`doi`、`has_abstract`/`has_body`、`content_sha256`；全局 `findings`（`language_label_mismatch`/`missing_doi`/`language_undetermined`）、`duplicate_pairs`（shingle Jaccard ≥ 0.9）、`parse_notes`。
- `audit_report.md`：人读表格＋finding 清单，每条 finding 给出建议处置。

## 关键方法（详见 references/authenticity_policy.md）

1. **正文优先**：语种判定用正文+摘要+标题的真实文本（停用词得分、变音字符画像、CJK/假名计数），声明语种仅作对照；二者冲突时记 `language_label_mismatch`，以后续以正文为准并两者都保留。
2. **内容指纹**：规范化（NFKD 变音折叠、小写、空白压缩）后 SHA-256；不同文件指纹一致或 5-gram shingle Jaccard ≥ 0.9 → `near_duplicate`，计数只能算一次但保留双方归因。
3. **缺口显式化**：缺 DOI、缺语种、缺版本信息的记录不推断、不补齐，逐条写入 findings 与 result.json 的 `uncertainty`。
4. **失败不中断**：单个文件损坏/格式不识/抽取失败记入 `parse_notes` 后继续；整体状态在 `ok`/`ok_with_findings` 间如实给出。

## 异常处理

| 情况 | 处置 |
|-|-|
| 根目录不存在 | 记入 parse_notes，继续扫描其余根 |
| PDF 无 pdftotext | 正文为空、has_body=false，parse_notes 记录；不伪造正文 |
| JSON/CSV 单行损坏 | 跳过该行并记录行号 |
| 文本过短无法判语种 | detected_language=und，finding 提示人工查看，不计入任何语种 |
| 声明与检测语种冲突 | finding 记录两者，建议以正文为准，下游必须可见 |

## 自查方法

1. 台账中文档数与实际语料文件数（按记录拆分后）一致；
2. 每条 finding 都能在 `audit_report.md` 中找到对应行并回指 `source_file`；
3. 重复对双方记录都保留归因，下游计数确为去重后数字；
4. `result.json.status` 与 findings 严重度一致（有 und 或 mismatch 时不得声称 fully verified）。

## 最小调用示例

见 `examples/example_walkthrough.md`（**合成示例**，仅说明接口与产物形态，非正式案例结果）。
