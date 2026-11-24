# 异常分类法（anomaly-taxonomy.md）

source-integrity-audit 检出的全部异常类型、严重度、判定证据与处理动作。
处理动作只有两种：进入 `quarantine`（题录级，隔离出追踪流水线并提示人工
复核）或记录在 `integrity_report`（文件级/快照级，供人工判断）。

## 严重度定义

- **high**：直接威胁追踪结果真实性的异常；对应记录必须隔离。
- **medium**：数据质量存疑，需人工复核后方可使用；对应记录必须隔离。
- **low**：字段缺失/格式瑕疵，记录不可用性低但仍隔离，避免污染窗口统计。

## 异常类型一览

| type | severity | 判定依据（证据位置） | 处理 |
| --- | --- | --- | --- |
| `invalid_doi` | high | DOI 不匹配 `^10\.\d{4,9}/\S+$`；locator 指向该 `doi` 字段 | quarantine |
| `future_date` | high | 日期解析结果 > `window.end`（以窗口终点为"现在"） | quarantine |
| `retraction_flag` | high | `retracted`/`retraction` 字段、`relation` 键含 retraction、`flags`、`update-type`、标题前缀 `RETRACTED ARTICLE` 等 | quarantine |
| `source_record_disappeared` | high | 增量导入状态中有、当前源快照中无（按 DOI/PMID/record_id 比对） | 记入 integrity_report + change_records |
| `duplicate_in_source` | medium | 同一文件内规范化 DOI（或标题）重复；evidence 含首现 locator | quarantine（后续重复条） |
| `invalid_pmid` | medium | PMID 非纯数字 | quarantine |
| `invalid_arxiv` | medium | arXiv 号不符合新/旧格式 | quarantine |
| `correction_flag` | medium | 更正/勘误标记（`relation` 键含 correction/erratum、标题前缀 `CORRECTION:`/`CORRIGENDUM` 等） | quarantine |
| `schema_drift` | medium | 同源 v1/v2 快照题录字段或顶层字段集合有增删 | 记入 integrity_report + change_records |
| `missing_date` | low | 无任何日期字段 | quarantine |
| `invalid_date` | low | 日期值无法解析 | quarantine |
| `empty_title` | low | 标题为空白字符串 | quarantine |
| `file_unparseable`（仅出现于 quarantine） | high | 文件 JSON/编码解析失败 | 整文件 quarantine + gating block |

## 判定原则

1. **证据先行**：每条异常必须携带 `locator`（文件 + JSON Pointer）与
   `evidence`（材料中的原始值）， reviewer 无需信任脚本的措辞即可复核。
2. **宁隔离不误放**：metadata 异常的记录一律进 quarantine；是否解除隔离由
   人工/下游流程决定，本 Skill 不做自动豁免。
3. **不跨源合并**：同一论文出现在 Crossref 与 Europe PMC 属正常冗余，
   只检测"源内"重复，跨源重复不做异常判定（见 result.json uncertainty）。
4. **漂移即信号**：`schema_drift` 本身不代表数据错误，但它是"来源改版"
   的直接证据，必须与 `frozen_at` 时间线一起呈现给人工。

## 合成示例中的预期检出

`examples/minimal/` 刻意埋入以下异常，供回归验证（运行
`python3 scripts/run_minimal_example.py` 应全部命中，每类各 1 个）：

- `future_date`：crossref_response.json #/records/1（published 2027-01-15 > 窗口终点 2026-11-21）
- `invalid_doi`：crossref_response.json #/records/2（"10.123/abc def"）
- `retraction_flag`：crossref_response.json #/records/3（retracted=true + 标题前缀 + relation）
- `duplicate_in_source`：europepmc_response.json #/records/1 与 #/records/0 重复
- `invalid_pmid` + `empty_title` + `missing_date`：europepmc_response.json #/records/2
- `invalid_arxiv`：arxiv_response.json #/records/1（"2026.abc"）
- `schema_drift`：crossref_snapshot_v1.json → v2（authors→author_list 等）
- `source_record_disappeared`：previous_snapshot.json #/imported/1（epmc-000）

预期 gating：`proceed_with_quarantine`，quarantine 共 6 条记录。
