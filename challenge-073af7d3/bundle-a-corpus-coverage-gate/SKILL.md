---
name: corpus-coverage-gate
description: 当 agent 在 /input 案例上执行「研究前沿与趋势分析」类文献综述任务时使用本技能：在任何趋势判断之前，先对文献语料做规范化解析、去重、年份溯源与覆盖度审计，并用计数闭合法则（records_total == kept + duplicates + excluded）做机器可检的门禁裁决。它产出 canon.jsonl、duplicates.json、coverage.json 与 gate_verdict.json 四类工件，为时间趋势、主题演化、代表作遴选、研究空白四个交付物提供可回链的语料地基。本技能不替代下游分析本身：它不判断何为前沿、不做引文网络分析、不做因果推断。
---

# corpus-coverage-gate — 语料真实性与覆盖审计门禁

## 1. 定位

本技能的重心是**上游语料真实性与覆盖审计**。其核心论点只有一句：**语料不过关，一切趋势皆空**。时间趋势、主题演化、代表作遴选、研究空白这四项交付物，每一项的可信度都不会超过其赖以建立的语料；一份混入重复记录、年份来源不明、覆盖边界不可审计的语料，会把噪声放大成"趋势"，把遗漏伪装成"空白"。因此本技能把语料质量做成机器可检的门禁：先规范化（多格式解析）、再去重（DOI 精确 + 标题 Jaccard）、再逐年计数与右删失评估，最后用计数闭合法则裁决——任何一项计数对不上，分析不得继续。

通过门禁后产出的 `canon.jsonl` 是后续全部分析的**唯一事实来源**：每一条趋势数字、每一个主题判断、每一篇代表作、每一处空白声明，都必须能回链到 canon 记录 id 与来源文件 sha256。

本技能显式击杀挑战点名的五类反模式：

| 反模式 | 本技能的反制 |
|---|---|
| 检索结果前排 = 前沿 | 前沿判断必须基于 canon 全体的逐年/逐主题切片，而非检索排序 |
| 关键词热度 = 趋势 | 趋势必须有逐年计数 + 噪声带 + 右删失校正的形态判断 |
| 换皮术语 = 新兴主题 | 去重与标题归一化先消灭变体；主题演化要求出现/消退的双侧证据 |
| 引用 Top-N = 代表作 | 代表作按"分阶段多标准遴选"，引用量至多是一项特征（见第 5 步） |
| "没检索到" = 研究空白 | 每条空白声明必须附排除证据：检索范围 + 近似命中分析（见第 6 步） |

## 2. 固定路径

| 路径 | 含义 |
|---|---|
| `/skills/weekly-skill/scripts/ingest_corpus.py` | 语料摄入与规范化引擎（第 1 步） |
| `/skills/weekly-skill/scripts/coverage_ledger.py` | 覆盖度台账生成器（第 2 步） |
| `/skills/weekly-skill/scripts/gate_check.py` | 审计门禁（第 2 步） |
| `/skills/weekly-skill/references/date_policy.md` | 日期字段取舍策略 |
| `/skills/weekly-skill/references/coverage_contract.md` | coverage.json 契约与闭环定义 |
| `/input/case.json` | 案例定义；**output_contract 字段名是硬性契约** |
| `/input/task.md` | 任务书；可能指定日期策略、年份窗口等偏好 |
| `/input/` 下其余材料文件 | json/jsonl/csv/bib/ris/txt/md 及真实 PDF（平台提供 pdf-text/pdf-render/ocr 工具） |
| `/app/work` | 全部中间工件（canon.jsonl、台账、各步表格） |
| `/app/output/result.json` | 最终交付物：case_id + output_contract 全部字段 + status + 证据 + 不确定性 |

PDF 材料必须先用平台 pdf-text 工具抽取为文本文件存入 `/app/work/pdf_text/`，再作为 txt 输入本引擎；**绝无预抽取的答案层，不得从文件名猜测内容**。

## 3. 执行协议

### 第 0 步 — 读契约 + 建档（先于一切分析）

1. 读 `/input/case.json`：记录 `case_id`，**逐字抄录 output_contract 的全部字段名**。
2. 读 `/input/task.md`：记录主题范围、时间窗口、日期策略偏好（print/online/preprint）、任何交付物格式要求。
3. 枚举 `/input/` 材料文件，记录格式清单。
4. **立即**写 `/app/output/result.json` 骨架：`case_id` + output_contract 每个字段的占位值 + `"status": "in_progress"` + `provenance`（材料文件清单）。此后每完成一步就回填一次，任何中断都留下部分结果。
5. 若 `/input/` 中找不到任何带年份信息的语料：置 `status = "blocked_no_corpus"`，说明检索过的位置，**停止，绝不编造**。

### 第 1 步 — 语料摄入（本技能引擎）

```bash
python3 /skills/weekly-skill/scripts/ingest_corpus.py \
  --work /app/work --inputs /input [--date-policy print|online|preprint|earliest]
```

- 日期策略：默认 `print`；task.md 另有指定时从其指定，并在 result.json 记录所选策略。策略含义见 `references/date_policy.md`。
- 产出 `canon.jsonl`（每条含 id/title/authors/year/三个分源年份/doi/venue/abstract/source_file/source_sha256/date_provenance）、`duplicates.json`（重复对 + 触发规则）、`ingest_report.json`（计数闭环 + 分格式统计 + 输入 sha256 清单）。
- 检查 `ingest_report.errors`：损坏文件被容忍但必须计入 result.json 的 uncertainty。

### 第 2 步 — 覆盖台账 + 门禁（本技能引擎）

```bash
python3 /skills/weekly-skill/scripts/coverage_ledger.py --work /app/work   # 闭环不成立时 exit 1
python3 /skills/weekly-skill/scripts/gate_check.py --work /app/work        # fail 时 exit 1
```

- `coverage.json` 给出逐年计数、按来源计数、年份缺失率、右删失评估、排除日志模板与闭环块。
- 门禁五查：(a) canon 存在且每条有 id+年份溯源；(b) 摄入闭环与 duplicates.json 一致；(c) 台账闭环**重算**成立（不信任文件内 closure_ok 标志）；(d) 年份缺失率 >0.2 仅 warn；(e) canon 内无重复 id。
- `gate=fail`：修复上游（重新摄入、核对排除日志）后重跑，**不得带病进入第 3 步**。
- `gate=warn`：可继续，但 warn 原因必须写入 result.json 的 uncertainty。
- 筛选阶段每排除一条记录，向 `coverage.json` 的 `exclusion_log` 追加 `{id, reason, note}`（reason  taxonomy 见 `references/coverage_contract.md`），追加后同步把 `closure.excluded` 加一并重跑门禁——闭环必须始终成立。

### 第 3 步 — 时间趋势（年度分布）

从 `canon.jsonl` 构建**逐年计数表**（可直接采用 coverage.json 的 `per_year_counts`，它已对 min..max 之间缺年补零）：

- 表格列：`year | n_papers | canon_ids（或存档于 /app/work/trend_table.json）`。
- 每个计数附 **Poisson 噪声带**（约 ±√n）：计数 3 与 4 的差异不构成趋势；形态判断（上升/平台/下降）必须跨≥3 个年份点且有超出噪声带的变化。
- `right_censoring.assessment == "suspected_partial"` 时，末年点必须标注"疑似不完整"，趋势结论不得依赖末年斜率；可在正文中给出"按上半年速率年化"的敏感性说明，但须注明是估计。
- 趋势声明的引用格式：`"2021–2023 年发文量 2→3→3（canon 计数，噪声带 ±√n）"`，禁止无数字的"快速增长"。

### 第 4 步 — 主题演化

从 canon 的 title/abstract/keywords 构建**年度术语队列**（term cohort）表 `/app/work/topic_table.json`：

- 每年取术语（单词/二元组，去停用词），记录 `term | first_year | per_year_counts | total`。
- **新兴**（emerging）= first_year 落在窗口后半段 且 出现次数 ≥2（排除一次性噪声）；**消退**（declining）= 前半段活跃、后半段归零或跌破噪声带。两类判断都要有双侧（出现与消退）证据，单侧不算。
- **术语漂移**：同一概念的换皮术语（如去重阶段的标题变体所示）必须先归并再计数；把同义词当新主题是本挑战点名的反模式。
- 每个主题演化声明必须给出：首次出现年份、峰值年份、支撑该主题的 canon id 列表，以及"为何此时出现/消退"的机制性解释（联系该年代表作或领域事件），不允许只报热度。

### 第 5 步 — 代表作遴选

**禁止裸引用 Top-N**。流程：

1. 按第 3 步趋势形态把窗口划分为若干阶段（如起步期/扩张期/成熟期），**每个阶段至少遴选一篇**，保证全阶段覆盖。
2. 候选池 = 该年份区间的 canon 记录；每条记录打多维特征：被引（若材料含该字段）、venue 质量信号、方法新颖性（摘要证据）、后续阶段术语是否溯源到它（第 4 步主题表的锚点）。
3. 遴选口径（caliber）必须**显式写出且可复算**，例如："每阶段选 2 篇：一篇该阶段术语锚点最多者，一篇方法新颖性最强者；被引仅作并列时的裁决"。
4. 每篇代表作附：canon id、入选阶段、命中了口径中的哪一条、一句话入选理由。选不出时如实写"该阶段语料不足"，不得硬凑。

### 第 6 步 — 研究空白

每条空白声明必须附带**排除证据**，否则删除该声明。证据结构（写入 result.json）：

- `retrieval_scope`：本空白判断基于哪份语料（canon 记录数、年份窗口、来源文件清单）；
- `near_miss_analysis`：列出 2–5 条与空白主题**最接近**的 canon 记录 id，逐条说明它们"差在哪里"（用了 A 方法但非 B 场景；综述提及但未实证）；
- `exclusion_evidence`：说明不是"没检索到"——例如该主题的术语在第 4 步术语表中出现次数为 0/仅出现于未来工作小节。
- 若语料覆盖本身有盲区（右删失、年份缺失 warn、来源单一），空白声明必须降级为"初步判断"并在 uncertainty 中声明。

### 第 7 步 — 证据回链与 result.json 定稿

- 构建证据矩阵 `/app/work/evidence_matrix.json`：`claim | deliverable | canon_ids | artifact（趋势表/主题表/遴选表/排除日志）`。
- 逐条核对：result.json 中每个 output_contract 字段都有实质内容；每条声明至少回链一个 canon id 或工件文件；status 反映真实完成度（见第 4 节）。
- 回填 `provenance`：引擎三工件路径、所选日期策略、门禁 verdict。

## 4. 输出契约

`/app/output/result.json` 必须包含：

- `case_id`：与 case.json 逐字一致；
- **output_contract 列出的全部字段，字段名逐字一致**，值为实质内容（数组/对象/字符串按其语义）；
- `status`：`ok`（四项交付物齐备且门禁 pass）/ `partial`（说明完成了哪些、缺哪些、为何缺）/ `blocked_no_corpus` / `blocked_gate_fail`（门禁 fail 且无法修复）；
- `sources` / `evidence`：canon id 回链 + 工件路径；
- `uncertainty`：右删失、年份缺失 warn、损坏文件、覆盖盲区等。

诚实部分结果规则：宁可 `partial` + 明确限制，不可 `ok` + 注水；占位符必须在定稿前全部清除。

## 5. 预算规划（64 次请求 / 900 秒）

引擎调用是本地脚本，**不消耗判断预算**，应尽早跑完：

| 阶段 | 请求预算 | 要点 |
|---|---|---|
| 第 0 步 契约建档 | ≤4 | 一次读全 case.json/task.md/文件清单 |
| 第 1–2 步 引擎+门禁 | ≤4 | 脚本执行 + 读三份 JSON 摘要 |
| 第 3–4 步 趋势+主题 | ≤16 | 表格由脚本式思维构建，判断留给形态解读 |
| 第 5–6 步 代表作+空白 | ≤20 | 逐个阶段/空白做遴选与排除推理 |
| 第 7 步 回链定稿 | ≤8 | 证据矩阵核对 + result.json 回填 |
| 余量 | ~12 | 修复门禁 fail、补充证据 |

纪律：**每完成一步立即回填 result.json**；超过 600 秒未完成第 5 步时，优先保证四项交付物都有诚实内容（可 partial），不留空字段。

## 6. 异常处理

| 异常 | 处置 |
|---|---|
| /input 无语料或语料无年份 | status=blocked_no_corpus，停止，不编造 |
| 年份缺失率 >0.2 | 门禁 warn 继续；趋势/主题声明显式声明该限制；考虑 freetext 兜底抽取 |
| 检出重复记录 | 正常流程：duplicates.json 留痕，闭环自动平衡；在 provenance 中报告去重数 |
| 末年疑似右删失 | 末年趋势点标注"疑似不完整"，结论不依赖末年斜率；空白声明降级 |
| 个别文件损坏 | 引擎容错继续；errors 计入 uncertainty；关键文件损坏则 partial |
| 材料仅 PDF | 先用平台 pdf-text 工具抽取文本至 /app/work/pdf_text/，再作 txt 摄入；扫描件走 pdf-render/ocr |
| 日期字段冲突（print≠online≠preprint） | 按 task.md 指定或默认 print 策略取舍，date_provenance 留痕；策略影响在 uncertainty 中说明 |

## 7. 不适用

- 因果性声明（"X 导致 Y 兴起"）：本技能只支持时序共现证据；
- 引文网络分析（共被引、耦合、影响力传播）：无相应数据结构与引擎；
- 超出所提供材料的全文挖掘：不访问外部数据库，不臆造语料外的文献。

## 8. 合成示例

`examples/` 含端到端自证：`synthetic_case/corpus.jsonl` 为 **10 条合成记录（全部标注 synthetic）**，植入 DOI 重复、标题变体重复、缺年记录与右删失末年；`run_example.sh` 跑出 GOOD（gate=pass, exit 0）与 BAD（注入不闭环台账 → gate=fail, exit 1）两个真实运行，工件在 `examples/example_output/`。运行方式：`bash examples/run_example.sh`。
