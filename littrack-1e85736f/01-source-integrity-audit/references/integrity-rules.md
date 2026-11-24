# 完整性校验规则（integrity-rules.md）

本文件定义 source-integrity-audit 的校验规则与阈值。脚本实现见 `scripts/`，
异常类型与严重度见 `references/anomaly-taxonomy.md`。

## 0. 总则

- **完全离线**：任何步骤不得发起网络请求；不得用模型先验"补全"元数据。
- **不编造**：所有字段值必须来自案例材料；材料未提供的值记为 `null`，
  并给出 locator（`文件路径 + #JSON Pointer`）供复核。
- **"现在"的定义**：一律以 `case.json` 的 `window.end` 作为当前时间基准，
  用于未来日期判定，不使用系统时钟。

## 1. 哈希台账（hash_ledger.py → source_ledger.json）

- 对材料目录下每个 `.json` 文件计算 SHA-256 与字节数。
- 固化时间仅取自材料自身字段，识别字段名（按优先级）：
  `snapshot_frozen_at`、`frozen_at`、`captured_at`、`snapshot_time`、
  `taken_at`、`generated_at`；未提供则 `frozen_at = null`，
  并在 uncertainty 中注明。
- 同一哈希出现于多个文件时标记 `content_duplicate_of`（内容完全重复）。
- 文件无法解析（JSON 语法错误、编码错误）记入 `parse_error`，
  该文件整体进入 quarantine，并构成 gating 的 block 条件。

## 2. Schema 校验（validate_schema.py → schema_report.json）

每条题录必须具备：

| 字段 | 规则 |
| --- | --- |
| `title` | 存在且为 `str`（空字符串由异常检测另行标记 `empty_title`） |
| `authors` | 存在、为 `list` 且非空 |
| 日期 | `published` / `date` / `issued` / `publication_date` / `published_date` / `created` 至少存在一个 |
| 标识符 | `doi` / `DOI` / `arxiv_id` / `arxiv` / `eprint` / `pmid` / `pmcid` / `record_id` / `id` 至少存在一个 |

- 历史快照（文件名形如 `*_v1.json`、`*_v2.json`）不参与逐条校验，仅用于漂移检测。
- 无法抽取题录列表的文件（如增量导入状态快照）标记 `skipped`，不计入失败率。
- 失败率 = 未通过题录数 / 题录总数；阈值见 §5。

## 3. 元数据一致性（detect_anomalies.py）

| 检查项 | 规则 |
| --- | --- |
| DOI 语法 | 必须匹配 `^10\.\d{4,9}/\S+$`，否则 `invalid_doi` |
| arXiv 号 | 新格式 `^\d{4}\.\d{4,5}(v\d+)?$` 或旧格式 `^[a-z][a-z\-]*(\.[A-Z]{2})?/\d{7}(v\d+)?$`，否则 `invalid_arxiv` |
| PMID | 必须纯数字 `^\d+$`，否则 `invalid_pmid` |
| 日期合法性 | 可解析为 `YYYY-MM-DD` / ISO 时间戳（含 `Z`）/ `YYYY-MM` / `YYYY` / Crossref `date-parts`，否则 `invalid_date` |
| 未来日期 | 解析结果 > `window.end` 判 `future_date`（high） |
| 缺失日期 | 无任何日期字段判 `missing_date` |
| 空标题 | 标题为空白字符串判 `empty_title` |
| 撤稿/更正 | 字段（`retracted`/`retraction`/`flags`/`update-type`）、`relation` 键名（含 `retraction`/`correction`/`erratum`）、标题前缀（`RETRACTED ARTICLE`、`CORRECTION:`、`CORRIGENDUM`、`ERRATUM` 等）判 `retraction_flag` / `correction_flag` |

## 4. 异常检测补充

- **源内重复**：同一文件内按规范化 DOI（小写、去空白）判重；无 DOI 时退化为
  规范化标题（小写、压缩空白）。后续出现的条目标记 `duplicate_in_source`，
  并记录首现条目 locator。
- **结构漂移**：材料目录中同前缀的 `*_v1.json` / `*_v2.json`（及更高版本）
  两两相邻对比，题录字段集合或顶层字段集合有增删即判 `schema_drift`，
  evidence 给出新增/消失字段清单。这是"来源改版迹象"的直接证据。
- **与增量导入状态对比**：`previous_snapshot.json`（本地增量导入状态）中
  此前已导入、但当前源快照中按 DOI/PMID/record_id 找不到的记录判
  `source_record_disappeared`（high，上游删除或改版迹象）。

## 5. gating 决策（gate.py）

| 决策 | 条件 |
| --- | --- |
| `block` | 任一源文件无法解析；或题录总数为 0；或 Schema 失败率 > 50% |
| `proceed_with_quarantine` | 未触及 block，但 quarantine 清单非空 |
| `proceed` | 零异常 |

- quarantine 清单：所有检出题录级异常（high/medium/low 一律隔离）的记录，
  动作统一为 `exclude_from_tracking_and_alert_review`；无法解析的文件整文件隔离。
- 阈值 50% 写在 `gating_decision.thresholds.block_schema_failure_rate`，可按
  案例要求在 gate.py 顶部常量调整。

## 6. 结果组装（assemble_result.py → result.json）

- `case_id` 原样取自 `case.json`；`window` 原样透传。
- `output_contract` 列出的字段全部必须存在；缺失以 `null` 补齐并降级
  `status = partial`、在 `limitations` 说明。
- `sources` 来自台账（文件、哈希、字节、固化时间及其 locator）。
- `uncertainty` 至少声明：固化时间取自材料字段无法独立验证；离线约束下
  不能证明固化前上游数据未被篡改；重复检测不含跨源合并。
- `change_records` 汇总本次审计发现的"变化"事实：台账初始化、结构漂移、
  与增量导入状态的差异（含消失记录）。
