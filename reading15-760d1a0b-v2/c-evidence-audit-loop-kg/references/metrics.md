# 证书指标定义（audit_certificate.json）

签名产物 `audit_certificate.json` 是"质量可度量、增益可验证"的载体。
所有指标由 `audit.py` 在每一轮机械计算，`assemble.py` 汇总成证书。

## 1. 指标定义

| 指标 | 定义 | 口径 |
|---|---|---|
| `quote_precision_pct` | `quotes_valid / quotes_total × 100` | 一条 evidence 的 quote 是所引段落 text 的精确子串记 valid；地址错误导致无法校验的 quote 记 invalid |
| `address_validity_pct` | `addresses_valid / addresses_total × 100` | source_id 存在且 paragraph_id 存在于该 source 记 valid |
| `attribution_accuracy_pct` | `无 ROOT_META_MISATTRIBUTION 的条目 / 总条目 × 100` | 根元数据（case.json doi/title）错配到 secondary 记违规 |
| `paragraph_coverage_pct` | `被 accept 条目引用的段落数 / 语料总段落数 × 100` | 仅统计 accept 条目的有效地址 |
| `accepted / repair / rejected` | 三轮裁决计数 | 逐轮 |

## 2. baseline_vs_final（增益可验证性）

证书中的 `baseline_vs_final` 记录第 1 轮（模型原始草案，相当于"不加载审计环的
基线流程"会交付的质量）与最后一轮（修复后）的差值：

- `quote_precision_gain_pp`、`address_validity_gain_pp`、
  `attribution_accuracy_gain_pp`、`paragraph_coverage_gain_pp`：百分点增益；
- `accepted_items_gain`：净增的可入图条目数。

正增益 = 审计-修复闭环带来的可度量质量改进；若末轮仍有 reject，则
`verdict = pass-with-quarantine`，被隔离条目数在 `quarantined_count`。

## 3. verdict 取值

- `pass`：末轮全部 accept（可有 quarantine 之外的 0 失败）。
- `pass-with-quarantine`：末轮有 reject，失败项已隔离，图谱只含干净条目。
- `incomplete`：末轮仍有 repair 状态（不应出现，出现即流程错误）。
- `no-audit-run`：未找到任何 audit_report.iter*.json。

## 4. 合成示例的实测数字（SYNTHETIC，仅演示）

示例草案故意埋入 3 个缺陷（错误引文、坏 paragraph_id、根元数据错配）：

| 轮次 | quote-precision | address-validity | attribution-accuracy | coverage | accept/repair/reject |
|---|---|---|---|---|---|
| 1（原始草案） | 93.9% | 97.0% | 96.7% | 50.0% | 27 / 3 / 0 |
| 2（修复后） | 100.0% | 100.0% | 100.0% | 50.0% | 30 / 0 / 0 |

增益：+6.1pp / +3.0pp / +3.3pp / 0pp，accepted +3；`verdict = pass`，
`quarantined_count = 0`。覆盖率两轮持平是预期行为——定向修复只修失败条目，
不新增引用。
