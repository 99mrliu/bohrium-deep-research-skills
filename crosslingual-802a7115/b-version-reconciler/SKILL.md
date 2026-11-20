---
name: xlang-version-reconciler
description: 对跨语言检索得到的候选文献记录做正文语种识别与跨语种版本归并：判定每条记录的正文语种（以实际文本的 Unicode 区间统计与功能词打分为准，文本优先于元数据标签）与版本类型（original / publisher-translation / abstract-only-english / bilingual / exact-duplicate / undetermined），再把同一工作的多语版本（含出版方官方全译本、仅英文摘要记录、完全重复副本）归并为一个 work 并按 work 去重计数，防止多语种重复计入导致指标虚高。当任务要求"每条命中说清来自哪个语种和哪个版本"、需要区分原文版与译文版、或结果集中疑似存在同一论文的多个语种视图时使用；适用于 /input/case.json + task.md 的 Harbor 运行契约，也适用于任何检索后记录解析阶段。
---

# 语言识别与跨语种版本归并（xlang-version-reconciler）

## 用途与适用条件

对检索（由其他 Skill 或人工完成）产出的**候选文献记录集**做两件事：

1. **语言与版本判定**：逐条判定正文语种与版本类型（original / publisher-translation / abstract-only-english / bilingual / exact-duplicate / undetermined）。语种判定以**实际文本**为准——Unicode 区间统计（Latin Extended 变音、CJK、平/片假名、Hangul、西里尔、阿拉伯）＋拉丁文字语言的功能词打分＋特征字符裁决；元数据语言字段只是证据之一，标签与文本冲突时文本胜出并记录冲突。证据不足的记录显式标 `undetermined`，绝不猜测。
2. **跨语种同文归并与去重计数**：把同一工作的多语版本（葡语原文正文、出版方官方英译本、仅英文摘要记录、完全重复副本等）归并为一个 work 记录、挂多个 version 视图；每个归并决策记录所用信号与置信；指标按 **work 级**去重计数，同时给出版本级/记录级计数对照，杜绝同一论文以多个语种重复计入。

不适用：检索本身（查询构造、数据库访问）、主题相关性判读、全文翻译质量评估。本 Skill 只做检索后的记录解析、语种/版本判定与归并，与查询扩展、误译复核等方向完全解耦。

## 输入

- `/input/case.json`：案例文件，含 `case_id` 与 `output_contract`（阶段 2 组装 result.json 时镜像其全部字段）。
- 候选记录文件：自动发现 `/input`、`/app/work`、当前目录下的 `.json/.jsonl/.ndjson/.csv/.tsv`（异构文献记录：Crossref / EuropePMC / OpenAlex / 出版方记录等均可）以及 `.txt/.md`（视为整篇提取文本，例如平台 pdf-text-tool / ocr-tool 的输出）。**读取实际文件内容，绝不根据文件名或标签假设正文语种**。
- 若有 PDF：优先用平台提供的 pdf-text-tool/pdf-render-tool/ocr-tool 抽取文本为 `.txt/.jsonl` 后再交给本 Skill；本 Skill 不直接解析 PDF 二进制。

## 调用方式（按顺序执行）

```bash
# 1. 语言识别与版本类型判定（900 秒预算内数秒即可完成常规规模）
python3 scripts/langid_version.py \
    --roots /input,/app/work,. \
    --out /app/work/langid_report.json --workdir /app/work

# 2. 跨语种同文归并＋去重计数＋组装 result.json（--roots 用于从原始文件补提显式译本/重复关系，可选但建议提供）
python3 scripts/reconcile_works.py \
    --report /app/work/langid_report.json \
    --roots /input,/app/work \
    --case /input/case.json --out /app/output --workdir /app/work
```

可选参数：阶段 1 `--max-chars`（单条采样字符上限，默认 12000）、`--min-fulltext`（fulltext 字段最短字符数，默认 300；CJK/假名/谚文字符按双倍计）；阶段 2 `--merge-threshold`（默认 0.75）、`--candidate-threshold`（默认 0.55）。

## 输出

- `/app/work/langid_report.json`：逐条记录的语种判定（code/confidence/basis）、版本类型、采样定位（字段＋切片偏移）、Unicode 区间统计量、功能词得分、元数据语言、判定规则编号（R0–R6）、冲突记录、来源 locator（file＋JSON 路径/行号）。
- `/app/work/reconcile_report.json`：work 组（每组挂 version 视图列表：source 定位、DOI、版本类型、正文语种）、merge 决策日志（信号×权重×置信）、被保留分列的候选对（rejected_candidates）、去重计数对照（raw records → distinct versions → distinct works，含分语种两级计数）、孤儿记录清单（含原因）、uncertainty。
- `/app/work/version_table.md`：人读归并表（work × 版本 × DOI × 版本类型 × 正文语种 × 来源定位）。
- `/app/output/result.json`：`case_id`、`status`（ok/partial/failed）、`counts`、`works`、`merge_decisions`、`rejected_candidates`、`orphans`、`sources`、`evidence_records`、`uncertainty`、`change_records`，并镜像 `output_contract` 的全部字段（无内容字段置 null 并在 uncertainty 说明）。
- 运行日志：`/app/work/langid_run_log.json`、`/app/work/reconcile_run_log.json`。

## 关键方法（详见 rules/version_policy.md）

1. **文本优先原则**：正文语种以实际采样文本的统计证据为准；元数据语言字段、期刊/出版方字段仅作旁证。标签与文本冲突时文本胜出，冲突写入 `conflicts` 与 `uncertainty`。
2. **Unicode 区间统计＋功能词打分**：非拉丁文字由文字区间直接定语种（假名→ja、谚文→ko、无假名的 CJK→zh、西里尔→ru、阿拉伯→ar）；拉丁文字由 en/pt/es/fr/de/it 六语功能词命中计数判定，得分接近时用特征字符（ã/õ→pt，ñ→es，ä/ö/ü/ß→de 等）裁决，仍不分明则降置信或标 `undetermined`。
3. **版本类型判定优先级**（R0→R6）：显式重复副本字段/指纹+文本哈希一致 → exact-duplicate；显式译本关系字段（translation_of、relation[].type 含 translat）→ publisher-translation；元数据多语种 → bilingual；无正文但英文摘要＋非英语元数据/非英语标题 → abstract-only-english（正文语种据元数据/标题推断并标注推断依据）；正文可得且无译本标记 → original；正文与标签冲突且无译本声明 → undetermined。
4. **多信号归并打分**：DOI 精确/前缀-后缀关系、译名标题折叠后 token Jaccard（变音折叠＋大小写折叠，含数字 token 辅助）、作者姓氏罗马化折叠匹配（首作者＋姓氏集合）、年/卷/期/首页指纹；权重与阈值固定并写入决策日志。≥0.75 归并（显式关系/同 DOI 为高置信，其余中置信）；0.55–0.75 保持分列并列入 rejected_candidates 与 uncertainty；<0.55 忽略。**证据不足时保持分列，绝不猜测归并**。
5. **去重计数**：exact-duplicate 记录吸收进同一 version 视图（多 locator 保留）；指标统计以 work 为单位，报告同时给出记录级/版本级/work 级三级计数对照，使"多语种重复计入"在数字上可见、可审计。

## 异常处理

| 情况 | 处置 |
|-|-|
| 记录无正文也无可用元数据 | `body_language=undetermined`、`version_type=undetermined`，写入 uncertainty；不猜测 |
| 元数据语言标签与正文文本冲突 | 文本胜出；冲突逐条写入该记录的 `conflicts` 并汇总进 uncertainty |
| 无正文、仅英文摘要、元数据显示正文非英语 | 判 `abstract-only-english`，正文语种据元数据/标题推断并标注 `basis` 与较低置信 |
| 正文与标签冲突且无译本声明 | `version_type=undetermined`（无法区分原文与未声明译本），写入 uncertainty |
| 疑似同文但证据不足（打分 0.55–0.75） | 保持分列，列入 rejected_candidates 与 uncertainty |
| 文件损坏/格式不识/JSONL 坏行 | 跳过并记入 parse_notes 与 sources；不中断运行 |
| 阶段 1 报告缺失（阶段 2 运行时） | `status=failed`，写出占位结果并说明先运行 langid_version.py |
| 输入为空（无任何候选记录） | 正常交付空 works，`status=ok`（无记录可判不是错误），sources 记录扫描过的文件 |

## 自查方法

交付前逐项核对（均可由脚本输出直接回答）：

1. 每条记录的 `body_language` 都有 `basis`（fulltext/abstract/title/metadata）与可回指的 `evidence`（采样字段、切片偏移、统计量）；凡 `basis=metadata` 的必须在 uncertainty 中有对应说明。
2. `counts` 三级计数自洽：raw_records ≥ distinct_versions ≥ distinct_works；若 raw > works 而案例不含多语版本或副本，检查 merge_decisions 是否有误并。
3. 每个 work 的 versions 列表中，每个 version 都带 `sources`（file＋pointer）与 `version_type`、`body_language`；人工抽查 2–3 条，用 locator 回指原始记录核对。
4. rejected_candidates 非空时，逐条确认"保持分列"理由已写入 result.json 的 uncertainty。
5. `status` 与实际完成情况一致（有 undetermined 记录或被拒候选对时为 partial）；`output_contract` 字段全部镜像。
6. 全程无补造：works 中的元数据只能来自原始记录，归并不创造新文献。

## 最小调用示例

见 `examples/example_walkthrough.md`（合成语料，仅说明接口与输出形态，**非正式案例结果**）。
