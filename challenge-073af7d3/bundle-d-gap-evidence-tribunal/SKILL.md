---
name: gap-evidence-tribunal
description: 当文献综述任务要求给出"研究空白"结论、或需要并列呈现冲突文献证据时使用。本技能把空白判定落实为可机器校验的排除证据纪律：校验检索日志闭合性（hits == kept + excluded）、空白声明的排除证据完整性（范围、查询号、近失记录及排除理由），并强制冲突证据双侧成对呈现。它只审计与校验证据协议，不代替系统数据库检索本身，也不对已记录范围之外的新颖性作保证。
---

# gap-evidence-tribunal：研究空白的排除证据法庭

## 1. 定位

本技能的重心是**研究空白判定的排除证据纪律与冲突证据配对**。设计公理直接取自挑战的评分准则："空白是否有排除证据而不是检索遗漏"。因此：

- 一条"研究空白"声明只有在附带完整排除证据时才可采信：检索/筛查范围（scope）、实际执行的查询（query_ids，须能回链到检索日志）、以及近失记录清单（near_misses，每条附 why_not 排除理由）。
- "没检索到"而没有协议记录，只是检索遗漏嫌疑（retrieval-omission suspect），不是空白。技能内置的法庭脚本会把这类裸声明判为 `bare_gap_claim` 并拒绝。
- 文献冲突必须双侧成对呈现：两侧各自的 record_ids、原文数值/结论、出处位置缺一不可；单侧陈述判为 `missing_side`，两侧数值相同判为 `not_a_conflict`。

本技能仍然走完整的四交付流水线（时间趋势、主题演化、代表作、研究空白+冲突），但把"空白与冲突"这两件最容易造假的产品做成了机器可校验。

## 2. 固定路径

- 技能脚本：`/skills/weekly-skill/scripts/`（build_corpus.py、retrieval_log.py、gap_tribunal.py、conflict_pairs.py）
- 参考文档：`/skills/weekly-skill/references/`（gap_taxonomy.md、evidence_schema.md）
- 输入：`/input/case.json`、`/input/task.md`、文献材料文件（格式不限，含 PDF；PDF 用平台 pdf-text/pdf-render/ocr 工具先抽文本）
- 工作目录：`/app/work`（canon.jsonl、检索日志、校验报告均放这里）
- 交付：`/app/output/result.json` + 综述正文与 gaps_report.md

## 3. 执行协议

### 第0步 读契约+建档（先做，不可跳过）

1. 读 `/input/case.json`：记下 `case_id` 与 `output_contract` 列出的**全部字段名**。
2. 读 `/input/task.md`；列出 `/input` 下的材料文件。**读实际文件内容，绝不从文件名/标签臆测内容**。
3. 立即写出 `/app/output/result.json` 骨架：`case_id` + 每个 output_contract 字段的占位（null）+ `status: "in_progress"` + `provenance`（材料文件清单）。之后每完成一步就回填对应字段。
4. 若找不到任何语料材料：`status: "blocked_no_corpus"`，写明检查过的路径，停止。**绝不编造文献。**

### 第1步 语料归一

```
python3 /skills/weekly-skill/scripts/build_corpus.py --work /app/work --inputs /input/materials/...
```

支持 json/jsonl/csv/bib/ris/txt/md。PDF 先用平台工具抽成文本存到 `/app/work/pdf_text/*.md` 再作为 inputs 传入。产出 `/app/work/canon.jsonl`（id/title/year/abstract/keywords/source_file），后续所有证据回链都以 canon id 为准。

### 第2步 检索协议建档

把**你自己**的阅读/筛查过程记成 `/app/work/retrieval_log.jsonl`，每行一条查询：

```json
{"query_id":"q1","query_string":"...","source":"...","date":"...","hits":N,"kept":K,"excluded":[{"record_ref":"...","reason":"..."}]}
```

- 即使语料是平台直接给定、没有执行外部检索，也必须记一条 `source:"provided-corpus"`、`query_string:"scope=provided-corpus: ..."` 的伪查询行——诚实说明本次"检索"到底是什么。
- 闭合纪律：`hits == kept + len(excluded)`；每条排除必须有非空 reason。
- 校验：`python3 /skills/weekly-skill/scripts/retrieval_log.py --work /app/work --log /app/work/retrieval_log.jsonl`。退出码 1 则修正日志直到通过。外部引用（不在 canon 中）允许存在，会被列入 external_refs 备查。

### 第3步 时间趋势

从 canon 统计年度分布：

```
python3 - <<'PY'
import json, collections
c = collections.Counter()
for line in open('/app/work/canon.jsonl', encoding='utf-8'):
    r = json.loads(line)
    if r.get('year'):
        c[r['year']] += 1
for y in sorted(c):
    print(y, c[y])
PY
```

纪律：年度计数小（<30）时按 Poisson 噪声 ±√n 解读，不把一两篇的波动写成趋势；最近年份可能因收录截断（censoring）偏低，不得解释为"热度下降"；只陈述有计数支撑的结论。

### 第4步 主题演化

1. 按年份把语料切成 2–4 个时段（每段尽量 ≥4 条记录）。
2. 对每个时段提取特征词（标题+摘要，去停用词，可按"本时段词频 − 其他时段词频"找区分词）。
3. 每条演化结论必须同时回答 **when**（在哪两个时段之间发生变化）与 **why**（绑定代表作 canon id，并给出可解释的动因：新数据集、新方法范式、硬件/部署需求等）。无 why 的"主题变了"不算演化分析。

### 第5步 代表作遴选

每个阶段至少选 1 篇代表作，遴选口径（selection caliber）必须写进交付物并覆盖多维：材料中提供的被引/影响信号、方法新颖性（是否开范式）、被后续工作沿用的程度、基准/综述地位。**禁止直接按引用量 top-N 交差**；若材料无引用数据，明说"遴选口径不含引用信号"。代表作必须覆盖全部阶段，不允许某阶段空缺而无解释。

### 第6步 空白判定（本技能重心）

1. 按四分类起草空白声明（见 `references/gap_taxonomy.md`）：repeated-unsolved-question / method-failure-on-object-or-scale / conflict-unresolved / missing-population-or-setting。
2. 按 `references/evidence_schema.md` 写 gaps.json：每条声明必须带 exclusion_evidence（scope_description + query_ids + near_misses[record_id, why_not]）。近失记录必须与空白主题真实相关——它们是最接近空白但仍被排除的记录。
3. 裁决：`python3 /skills/weekly-skill/scripts/gap_tribunal.py --work /app/work --gaps /app/work/gaps.json`（默认读取第2步的 retrieval_report.json）。
4. 被拒绝的声明只有两条出路：**补强真实排除证据后重跑**，或**降级措辞**为"在本次检索/本语料范围内未见……"（措辞规则见 gap_taxonomy.md）。被拒绝后原样保留"研究空白/尚无人研究"字样属于评分反模式。

### 第7步 冲突证据配对

1. 综述中遇到的每处文献冲突写一条 conflicts.json 条目：`quantity_or_claim` + side_a/side_b 各含 `record_ids`、`value_or_finding`、`location`。
2. 校验：`python3 /skills/weekly-skill/scripts/conflict_pairs.py --work /app/work --conflicts /app/work/conflicts.json`。
3. 两侧数值不可直接比较（指标/设置不同）时，不强判胜负：`status` 记为 `unresolvable-without-harmonization`，如实记录各自原文数值与位置。

### 第8步 证据回链与定稿

- 综述正文与 result.json 中的每条事实性结论都挂 canon id；空白挂 gap_verdicts 中的 gap_id；冲突挂 conflict_id。
- 写 `/app/output/gaps_report.md`：空白声明 + 排除证据（scope/查询/近失表）+ 冲突双侧对照表。
- 回填 result.json 全部契约字段；四交付齐备则 `status:"ok"`，否则 `status:"partial"` 并逐项说明缺口与原因。

## 4. 输出契约

`/app/output/result.json` 必须包含：

- `case_id`（与 case.json 完全一致）；
- `output_contract` 列出的**每一个字段**（先占位后回填，缺一不可）；
- `status`：`ok` / `partial` / `blocked_no_corpus` / 其他 `blocked_*`；
- 证据字段：结论附 canon ids / gap_ids / conflict_ids；
- `uncertainty`：如实写明噪声、截断、范围限制。
- partial 是诚实状态而非失败：必须说明哪些字段未完成、卡在哪一步、已有的中间产物路径。

## 5. 预算规划

64 次请求 / 900 秒的建议分配：

- 第0–2步（契约、归一、建档）：≤8 次。脚本校验免费（不占模型请求），日志闭合性问题交给 retrieval_log.py 而不是靠模型肉眼查。
- 第3–5步（趋势/演化/代表作）：≤14 次。批量读 canon（一次读多条），不要逐条请求。
- 第6–7步（空白+冲突）：≤14 次。先跑 tribunal 拿到违规清单再针对性补证据，避免盲改。
- 第8步定稿：≤8 次。
- 预留 ≥10 次给重试与最终自检（重新读 result.json 对照 output_contract 逐字段核对）。
- 时间红线：剩 120 秒时无论进展如何都必须写出当前 result.json（哪怕 partial）。

## 6. 异常处理

| 异常 | 处理 |
|---|---|
| 无语料材料 | `status=blocked_no_corpus`，写明检查过的路径，停止；绝不编造 |
| 语料由平台给定、未执行外部检索 | 检索日志必须含 `source=provided-corpus` 伪查询行；空白结论措辞限定为"本语料范围内未见"，不得暗示数据库级穷尽 |
| 近失重叠地板误杀/误放 | 重叠规则（Jaccard≥0.08 或共享≥2 词）只是健全性地板而非语义判断（见 evidence_schema.md）；被误杀时在 why_not 中补充与空白声明共用的关键词并重跑，同时在 uncertainty 中注明人工复核过 |
| 空白声明被法庭拒绝 | 补真实排除证据重跑；或降级为"检索范围内未见……"。禁止保留"研究空白/尚无人研究"字样 |
| 冲突两侧数值不可直接比较（不同指标/实验设置） | 不强判胜负；`status=unresolvable-without-harmonization`，记录各自原文数值与 location |
| 冲突条目缺 location | 回原文补页码/表号/章节；材料确无位置信息时 location 写 `"location unavailable in provided material"`（保持非空） |
| PDF 无法抽取文本 | 用平台 ocr 工具；仍失败则该文献列入 provenance.unreadable，不计入 canon，在 uncertainty 中声明 |

## 7. 不适用

- 不执行 Crossref/OpenAlex 等系统数据库检索本身（本技能审计检索协议，不代替检索执行）。
- 不做 meta 分析式的效应量合并。
- 不对已记录范围之外的新颖性作任何保证："本范围未见"不等于"全世界没有"。
- 不做 PDF 版面/图像理解（交给平台 pdf 工具）。

## 8. 合成示例

`examples/` 下为**全合成**演示案例（synthetic，低光图像增强主题，15 条虚构记录，其中 L009 与 L010 对同一量给出相反结论，用于冲突配对演示）。运行：

```
bash examples/run_example.sh
```

产出 `examples/example_output/` 内的真实校验产物：good/ 全流程通过（exit 0），bad/ 演示 closure_violation、bare_gap_claim、irrelevant_near_miss、unknown_gap_type、unknown_query、missing_side、not_a_conflict 七类违规必然触发（exit 1）。
