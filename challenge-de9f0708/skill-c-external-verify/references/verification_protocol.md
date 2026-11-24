# 外部事实核验规程（verification protocol）

本规程约束 skill-c-external-verify 的全部外部核验行为。核心原则：**判定只建立在
"实际检索到的记录"之上，绝不靠模型印象；单一信号永远不足以判死刑。**

## 1. 核验流水线与优先级排序

1. `extract_refs.py` 切分文献表、抽取字段初值、抓正文引文语境 → `refs.json`。
2. `lint_refs.py` 本地初筛（不耗预算）→ `lint.json` 候选问题。
3. `crossref_check.py` 按优先级消耗预算做外部核验。优先级从高到低：
   - P0 lint 标记 `doi_format_invalid` / `year_anomaly` 的条目（疑似硬伤，先查）；
   - P1 支撑核心结论（摘要/结论中被引）的条目（由 Agent 指定或按引文位置判断）；
   - P2 lint 标记 `duplicate_reference` 的条目；
   - P3 缺 DOI 的条目（只能书目检索，命中率低，排后）；
   - P4 其余条目按编号顺序。
   预算（默认 ≤12 次网络请求）耗尽后，剩余条目一律 `pending_review`，不得猜。

## 2. 两信号规则（判 fabrication_suspected 的唯一通道）

判定一条文献 `fabrication_suspected`（疑似捏造）必须**同时**满足：

- 信号 A：Crossref 检索无结果。合法 DOI 时 `api.crossref.org/works/<doi>` 返回 404；
  无 DOI 时 `query.bibliographic` 最佳命中标题相似度 < 0.80。
- 信号 B：DOI 不可解析。`https://doi.org/<doi>` 跟随重定向后返回 4xx。
  （无 DOI 的条目天然缺少信号 B → 永远不可能判 fabrication_suspected。）

两信号齐备时给出 `fabrication_suspected / critical`，但 `verdict_status` 仍写
`待人工终裁`——脚本提供证据，人做终裁。
**只有信号 A（没搜到）时，一律 `not_found → 待复核`**，可能原因必须在 rationale 中列出：
收录延迟、预印本未被 Crossref 收录、小语种/人文期刊、著录错误导致检索偏差等。
"没搜到" ≠ "不存在"。

## 3. 可采信来源清单（按优先级）

| 来源 | 用途 | 采信方式 |
|---|---|---|
| api.crossref.org | DOI 记录与元数据比对 | HTTP 200 返回的 message 原文逐字段记录 |
| doi.org 解析 | DOI 是否真实注册 | 跟随重定向后的最终 HTTP 状态码 |
| PubMed (eutils) | 生物医学文献复核 | 仅在 Crossref 无结果且领域匹配时作为补充信号 |
| arXiv API | 预印本合法性确认 | 预印本存在的正面证据（见 §5） |

所有来源只记录**本次实际返回**的内容（含 URL、状态码、检索时间），记入
`query_log` 与 `retrieved_records`；检索失败/超时如实记 error，不得回填。

## 4. 字段级比对口径

| 字段 | match 判据 | mismatch 判据 |
|---|---|---|
| title | 归一化（小写、去标点）相似度 ≥ 0.90 | < 0.90 |
| year | 整数相等（published-print/online/issued 任一） | 不等 |
| container-title | 归一化相似度 ≥ 0.80 | < 0.80；Crossref 记录缺容器名 → unknown，不判 |
| authors | 姓氏集合重叠率 ≥ 60% | < 60% |
| volume/issue/page | 字符串相等 | 不等（单独不符只算 minor） |

**作者拼写变体不构成 mismatch**：比对前归一化大小写、连字符、空格，并剥离
von/van/de/der/den/del/la/di 等贵族前缀；名只比对姓氏，名缩写差异忽略。
中文姓名按"姓氏 = 首字"处理。

## 5. 误报抑制清单

- **预印本合法存在**：bioRxiv/arXiv/SSRN 版本与期刊版 DOI 不同属正常；
  命中预印本记录视为 `match`（在 rationale 注明版本形态），不判 mismatch。
- **无 DOI 不判违规**：人文期刊、会议论文集、书籍章节常无 DOI，仅记 info_notes。
- **年份边界**：跨年见刊（online 2024 / print 2025）任一年份命中即 match。
- **小语种期刊**：Crossref 收录不全，检索无结果时降级理由必须写明此可能。
- **著录截断**：et al. 导致的作者列表不完整，只按已有姓氏比对重叠率。
- **标题相似≠同一文献**：`duplicate_reference` 候选必须人工核对作者/期刊/年份
  是否实质相同后才可升级；综述撞题常见。

## 6. 断网与降级

`--offline` 或任何网络异常：本条目及后续所有条目 `pending_review`，
rationale 如实记录原因（"offline mode"/"network error: …"）；
本地可判项（lint 候选、字段缺失、年份异常等）**照常出结论**，不受断网影响。
输出中 `mode`、`budget`、`query_log` 使降级过程可审计。
