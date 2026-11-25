# 溯源报告（provenance_report）

## 种子

- DOI：10.0000/synth.001
- 标题：A Synthetic Gradient Method for Citation Flow
- 种子解析途径：case.json:seed_paper；语料内命中：是

## 状态：partial

- 候选数：3；边数：9；stub（未解析引用目标）数：1

## 候选清单（逐条可回指）

| # | 深度 | 方向 | 标题 | DOI | 来源定位 |
|---|---|---|---|---|---|
| 1 | 1 | backward(参考文献) | Foundations of Veracity-Gated Indexing | 10.0000/synth.002 | `crossref_batch1.json` `/message/items/1` |
| 2 | 1 | forward(施引) | Improving Synthetic Gradient Flow with Veracity Gates | 10.0000/synth.003 | `crossref_batch2.json` `/message` |
| 3 | 1 | forward(施引) | Parallel Methods for Citation Tracing at Scale | 10.0000/synth.004 | `europepmc_batch1.json` `/resultList/result/0` |

## 引用边（每条边带数据源定位）

| from | to | 类型 | direction_restored | source |
|---|---|---|---|---|
| doi:10.0000/synth.001 | doi:10.0000/synth.002 | reference | False | `crossref_batch1.json` `/message/items/0/reference/0` |
| doi:10.0000/synth.002 | doi:10.0000/synth.001 | citation | True | `crossref_batch1.json` `/message/items/0/reference/0` |
| doi:10.0000/synth.001 | stub:78ef428df21a | reference | False | `crossref_batch1.json` `/message/items/0/reference/1` |
| doi:10.0000/synth.003 | doi:10.0000/synth.001 | reference | False | `crossref_batch2.json` `/message/reference/0` |
| doi:10.0000/synth.001 | doi:10.0000/synth.003 | citation | True | `crossref_batch2.json` `/message/reference/0` |
| doi:10.0000/synth.004 | doi:10.0000/synth.001 | reference | False | `europepmc_batch1.json` `/resultList/result/0/referenceList/reference/0` |
| doi:10.0000/synth.001 | doi:10.0000/synth.004 | citation | True | `europepmc_batch1.json` `/resultList/result/0/referenceList/reference/0` |
| doi:10.0000/synth.004 | doi:10.0000/synth.002 | reference | False | `europepmc_batch1.json` `/resultList/result/0/referenceList/reference/1` |
| doi:10.0000/synth.002 | doi:10.0000/synth.004 | citation | True | `europepmc_batch1.json` `/resultList/result/0/referenceList/reference/1` |

## 不确定性与诚实说明

- 合并字段冲突：doi:10.0000/synth.001 的 title 存在多个值 A Synthetic Gradient Method for Citation Flow / A Synthetic Gradient Method for Citation Flow: Extended Conference Version（保留可回指）
- 合并字段冲突：doi:10.0000/synth.001 的 venue 存在多个值 Journal of Synthetic Bibliometrics / Proceedings of the Imaginary Conference on Graph Mining（保留可回指）
- 1 条引用目标在语料内无记录，已保留为 stub（不补造元数据）
- 真实性瑕疵（status 降级依据）：1 个语料文件解析失败/未判定：broken_response.json
- 真实性瑕疵（status 降级依据）：2 组合并字段冲突
- 真实性瑕疵（status 降级依据）：1 条未解析引用目标（stub）
- output_contract 字段 'novelty_statement' 语义未在本 Skill 中定义，已按诚实空值(null)填充
