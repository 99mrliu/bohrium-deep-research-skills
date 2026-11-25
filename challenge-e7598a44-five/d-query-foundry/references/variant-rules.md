# 变体规则表与缺口诊断码

术语变体用来弥合"RQ 用词"与"文献用词"之间的表层差异。规则全部内置、零网络；
变体生成受**双重预算上限**约束，防止长尾变体发散淹没查询预算。

## 1. 变体规则表（foundry.py `raw_variants`，按序应用）

| 规则 | 名称 | 触发条件 | 产出示例 | 备注 |
|-|-|-|-|-|
| R1a | 连字符化 | 术语含空格 | `hard carbon` → `hard-carbon`、`hardcarbon` | 覆盖拼写习惯差异 |
| R1b | 去连字符 | 术语含连字符 | `sodium-ion` → `sodium ion`、`sodiumion` | R1a 的逆操作 |
| R2 | 单复数 | 末词为纯拉丁词 | `anode`→`anodes`；`batteries`→`battery`；`boundary`→`boundaries` | 规则化推导（-s/-es/-ies），不追求语言学完备 |
| R3 | 缩写双向 | 命中内置 ABBR 表 | `ice` ↔ `initial coulombic efficiency` | 表见 foundry.py 顶部，声明式可维护 |
| R4 | 同源扩展并入 | 术语来自 XLEX 跨语扩展 | `钠离子`→`sodium-ion` 的词表变体 `sodium ion`、`na-ion` 并入变体列 | 不占规则推导名额 |

## 2. 预算上限（防发散）

- `--max-variants-per-term`（默认 4）：每个术语最多保留的变体数；
- `--max-variant-total`（默认 80）：全部术语合计变体数上限；
- 被砍掉的变体逐条计数，写入 `query-families.json.budget.truncated`——
  预算耗尽是**可观察事件**，不是静默丢失。

## 3. 跨语扩展纪律（XLEX）

- 仅当词表左侧概念**真实出现**在 RQ 文本中才扩展右侧英文检索词；
- 概念 CJK 整词本身同时立为术语（直接命中中文文献）；
- 领域外 RQ 自动退化为"拉丁词 + CJK 二元组"，不臆造术语、不联网补词表。

## 4. known-item 缺口诊断码（known_item_audit.py）

每篇 missing 的清单文献给出以下诊断码的若干条（可复核、对应具体产物）：

| 诊断码 | 含义 | 复核入口 |
|-|-|-|
| `snapshot_absent` | 快照内无 DOI 精确或标题相似度≥0.6 的记录 | work/records.jsonl |
| `year_gap` | 查询召回了记录，但记录年份在 RQ 年份窗之外，被年份条款排除 | screening-ledger.jsonl 的 reason_codes |
| `doctype_gap` | 记录类型被文献类型条款排除 | 同上 |
| `fixture_duplicate` | 记录带合成重复夹具标记，登记不入候选 | 同上 |
| `query_recall_zero` | 无任何查询命中该记录（最深的术语缺口） | work/hits.jsonl |
| `weak_recall` | 仅单个 term 查询弱命中，未达纳入强度 | 同上 |
| `term_gap` | 清单标题中的实义词未被任何查询术语/变体覆盖（列出前 6 个） | term-base.json 与 hits.jsonl 对照 |

`term_gap` 的修复方式：把缺口词按领域补进 XLEX/ABBR（foundry.py 顶部声明式
词表）或改写 RQ，然后整体重跑——两步管线都是确定性的，重跑成本约数秒。
