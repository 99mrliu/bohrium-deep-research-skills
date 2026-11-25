# 审计理由码（reason codes）与处置建议

`audit.py` 对每条抽取条目给出 `accept` / `repair` / `reject` 裁决与一组理由码。
裁决规则：无理由码 → `accept`；有理由码且当前轮次 < 2 → `repair`（进入
`repair_queue.json`）；第 2 轮仍有理由码 → `reject`（进入 `quarantine.json`，
不进入图谱）。

| 理由码 | 机械判定方式 | 模型处置建议 |
|---|---|---|
| `ITEM_NOT_OBJECT` | 条目不是 JSON 对象 | 重写该条目 |
| `UNKNOWN_OP` | op 不在 node/edge/merge/nonmerge/unreported/note | 改正 op |
| `MISSING_FIELD` | 该 op 的必填字段缺失/为空 | 补齐字段（见 extraction_schema.md） |
| `EVIDENCE_MISSING` | 实质条目没有任何 evidence | 补 evidence 或 drop |
| `QUOTE_NOT_SUBSTRING` | `quote` 不是所引段落 `text` 的精确子串 | 从原文**复制**逐字片段，整体替换 evidence |
| `QUOTE_TOO_SHORT` | quote 缺失或 < 8 字符 | 换更长的逐字片段 |
| `SOURCE_UNKNOWN` | `source_id` 不在语料中 | 改为 corpus.json 里存在的 source_id |
| `ADDRESS_UNKNOWN` | `paragraph_id` 在该 source 中不存在 | 查 corpus.json 的段落清单，改成真实段落 id |
| `ROOT_META_MISATTRIBUTION` | secondary 证据上的 paper 节点标签等于根标题，或 quote 中含根 DOI | 根元数据只属于 primary：改成该源自己的标题/DOI 与证据 |
| `ENDPOINT_UNKNOWN` | edge 的 subject/object 不是已知条目 id | 指向已声明的条目 id，或先补节点 |
| `MERGE_MEMBER_UNKNOWN` | merge/nonmerge 成员 id 不存在 | 修正成员 id |
| `MERGE_MISSING_KEY` | merge 缺 `normalized_key` | 补规范键（casefold、去连字符/空格） |
| `MERGE_MISSING_REASON` | merge 缺 `reason` | 补一句可核查的合并依据 |
| `INVALID_NUMERIC_MERGE` | 合并的 claim 同 metric 但 value 不同 | 拆回两条 claim，加 `conflicts-with` 边 |
| `NONMERGE_TOO_FEW_MEMBERS` | nonmerge 成员 < 2 | 补足成员或删除该条目 |

## 全局（非逐项）度量

- **段落覆盖率**：被 accept 条目引用的段落数 / 语料总段落数。覆盖率不是越高越好
  （数据可用性等段落可能无抽取价值），但异常低的覆盖率提示漏抽；
  未被引用的段落列在 `audit_report.json → uncited_paragraphs`。
- 指标逐轮写入 `audit_certificate.json`，`baseline_vs_final` 给出首轮基线与末轮的
  百分点增益，用于证明审计-修复闭环的质量改进。

## 审计器的独立性

审计只做机械检查：字符串包含（quote ⊆ paragraph text）、集合成员（地址存在）、
键存在（必填字段）、跨条目一致性（端点、成员、数值冲突）。它不调用模型、不猜测
语义；语义判断（抽什么、怎么修）全部留给模型，但**是否合格由脚本说了算**——
这就是"独立"的含义，也是证书数字可信的原因。
