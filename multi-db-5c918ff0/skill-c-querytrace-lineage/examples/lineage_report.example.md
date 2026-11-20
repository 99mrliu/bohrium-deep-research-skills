# 多源查询编排与全链来源回溯报告

- case_id：EX-SYN-C01
- skill：querytrace-lineage-chain
- 链完整性核验结论：pass

## 1. 查询台账（query_ledger.jsonl）

| query_id | source_db | query_text | total_hits | items_returned | response_file |
|---|---|---|---|---|---|
| Q-CR-1 | crossref | query.bibliographic=synthetic lattice photon routing | 5 | 2 | raw_crossref_page1.json |
| Q-CR-2 | crossref | query.bibliographic=synthetic lattice photon routing | 5 | 2 | raw_crossref_page2.json |
| Q-EP-1 | europepmc | (TITLE:"synthetic lattice" OR TITLE:"metamaterial cloak") | 3 | 3 | raw_europepmc.json |
| Q-UNR-004 | publisher | （query_unrecorded） | - | 3 | raw_publisher.json |

## 2. 编排审计（query_audit.json）

### 2.1 机械复制检查（逐库查询串两两 diff）

adapted（各库查询按方言分别构造，未见机械复制）

### 2.2 分页完整性检查（Σ items_returned vs total_hits）

- crossref: suspected_truncation（pages=2, returned=4, total=5）
- europepmc: complete（pages=1, returned=3, total=3）
- publisher: unknown（pages=1, returned=3, total=None）

### 2.3 限流 / 配额痕迹分类

- crossref: not_recorded []
- europepmc: not_recorded []
- publisher: not_recorded []

## 3. canonical 记录溯源表（canonical_records.json）

| canonical_id | cluster_basis | identifier | title | members |
|---|---|---|---|---|
| C001 | tier2_title_exact | 10.55555/synth.001 | Adaptive Photon Routing in Synthetic Lattices | crossref:raw_crossref_page1.json:item[0], europepmc:raw_europepmc.json:item[2] |
| C002 | tier1_identifier_exact | 10.55555/synth.002 | Quantum Error Buffers for Noisy Intermediate Devices | crossref:raw_crossref_page1.json:item[1], publisher:raw_publisher.json:item[0] |
| C003 | unique | 10.55555/synth.003 | Cryogenic Control of Superconducting Qubit Arrays | crossref:raw_crossref_page2.json:item[0] |
| C004 | tier1_identifier_exact | 10.55555/synth.004 | Metamaterial Cloaks for Acoustic Waveguides | crossref:raw_crossref_page2.json:item[1], europepmc:raw_europepmc.json:item[0] |
| C005 | unique | 10.55555/synth.006 | Lattice Gauge Simulations on Hybrid Clouds | publisher:raw_publisher.json:item[1] |

## 4. unresolved 模糊对（交模型仲裁，不臆断）

[]

## 5. 断链清单（chain_gaps.jsonl，逐条报告，不静默修补）

（无）

## 6. 增量导入 diff 摘要（import_diff.json）

- **already_imported**：1 条
- **conflicting**：1 条
- **new**：2 条
- **updated**：1 条

## 7. 重放一致性声明

确定性重放双跑 hash 一致（SHA-256 前缀 c6d9998141676ebb），同输入同输出。

> 本文件为合成示例数据的渲染结果（示例输出，非真实案例结果），由 examples/ 下虚构数据自动生成，用于展示报告结构。
