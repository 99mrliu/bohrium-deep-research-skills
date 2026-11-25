# 指标定义与计数规则（definitions_version: 1.0）

本文档是本 Skill 全部指标的唯一定义来源。计算实现见 `scripts/metrics.py`，
任何实现与本文不一致时以本文为准并修正实现。

## 1. 规范化匹配键（canonical key）

对每条快照记录或候选声明，按下列优先级取其主键（primary key）：

1. **DOI**：去首尾空白、转小写、去掉 `https://doi.org/`、`http://doi.org/`、`doi:` 前缀 → `doi:<norm>`；
2. **arXiv 号**：转小写、去 `arXiv:` 前缀、去尾部版本号 `vN` → `arxiv:<norm>`；
3. **标题**：转小写、所有非字母数字（及非 CJK）字符替换为空格、压缩连续空白 → `title:<norm>`。

同一条记录的三种键全部登记进索引；候选声明先按 DOI、再按 arXiv、再按标题顺序查索引，
解析到快照记录身份（identity = 该记录主键）。因此同一文献一次用 DOI、一次用标题声明，
仍被识别为同一身份。

## 2. 真值类别

由 `scripts/truth_build.py` 机械构造（构造规则与假设见 `truth_construction.md`）：

| 类别 | 定义 |
| --- | --- |
| `truth_new` | t_now 有、t_prev 无，且 published ∈ [window.start, window.end]（两端含） |
| `truth_backfill` | t_now 有、t_prev 无，且 published < window.start（晚入库的旧文献） |
| `truth_out_of_window` | t_now 有、t_prev 无，且 published > window.end |
| `unclassifiable` | 上述新增候选中 published 缺失或无法解析者（单列，不猜测） |

## 3. 候选清单的计数单位

- **候选条目（candidate_entries）**：候选清单中的原始条目数，含重复。
- **重复声明（duplicates）**：解析出的 identity 在清单中第 2 次及以后出现的条目。
  重复条目只进 duplicate 统计，**不重复计入 TP/FP**。
- **唯一声明（unique_claims）**：去重后的 identity 数 = candidate_entries − duplicates。

## 4. TP / FP / FN

以唯一声明为单位，对照真值：

- **TP**：唯一声明 ∈ `truth_new`；
- **FP**：唯一声明 ∉ `truth_new`，并按落点细分 `fp_reason`：
  - `backfill_misreported_as_new`：落在 `truth_backfill`（旧文献被报为新增，单独计数）；
  - `out_of_window`：落在 `truth_out_of_window`；
  - `truth_unclassifiable_date`：落在 `unclassifiable`；
  - `already_in_prev_snapshot`：记录早在 t_prev 就存在（并非新增）；
  - `in_snapshot_but_not_truth_new`：在快照中但不属于任何真值类别（兜底）；
  - `not_in_snapshot`：连 t_now 快照中都不存在（疑似编造或键错误）。
- **FN**：`truth_new` 中未被任何唯一声明覆盖者。

TP/FP/FN 逐条列出，每条带 locator：`{snapshot, index, source, doi, arxiv_id, title}`，
可直接回放到快照文件中的具体记录，保证可复算。

## 5. 指标公式

| 指标 | 公式 | 分母为 0 时 |
| --- | --- | --- |
| precision | TP / (TP + FP) | null |
| recall | TP / \|truth_new\| | null |
| duplicate_rate | duplicates / candidate_entries | null |
| false_alert_rate | FP / unique_claims | null |
| backfill_misclassification_count | fp_reason = `backfill_misreported_as_new` 的条数 | 0 |
| backfill_misclassification_rate | 上值 / \|truth_backfill\| | null |

说明：在"唯一声明"约定下 false_alert_rate ≡ 1 − precision；两者同时报告是为了让
"发给用户的提醒中有多大比例是误报"这一口径显式可见。重复带来的噪声由
duplicate_rate 独立度量，不混入 precision/recall。

## 6. 合成示例的手算基准（examples/minimal）

候选清单 4 条：syn.201（DOI 声明）、N2（变体标题声明）、syn.201（标题声明，重复）、
syn.099（backfill 误报）。

- candidate_entries=4，duplicates=1，unique_claims=3；
- TP=2（syn.201、2611.10234），FP=1（syn.099，backfill_misreported_as_new），FN=2（syn.203、syn.204）；
- precision = 2/3 ≈ 0.6667；recall = 2/4 = 0.5；
- duplicate_rate = 1/4 = 0.25；false_alert_rate = 1/3 ≈ 0.3333；
- backfill_misclassification_count = 1，rate = 1/1 = 1.0。
