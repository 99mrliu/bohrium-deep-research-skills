# 引用支持判定 Rubric（supports / partially_supports / not_supported / cannot_verify）

本 rubric 约束"正文论断 ↔ 被引文献主张"的支持判定。核心纪律：**能机械对照的机械对照，
不能机械对照的一律降级，绝不臆断文献内容**。

## 四级判定

| 判定 | 条件 | 处置 |
|---|---|---|
| `supports` | 被引文献全文/摘要可见，且被引位置句的核心主张（对象、方向、量级）与文献明确表述一致 | 登记 finding（severity=info），注明启发式初判需人工复核 |
| `partially_supports` | 文献可见，主张方向一致但范围/条件/量级被正文放大或缩小（如文献在小样本成立、正文推广为普遍结论） | 登记 finding（severity=minor），列入待复核 |
| `not_supported` | 文献可见，且文献明确表述与正文主张相反或无关 | 登记 finding（severity=major），列入待复核。**仅人工复核后可下定论**，脚本不自动产出此级 |
| `cannot_verify` | 文献全文/摘要不可见，或可见但重叠信号不足 | **一律**进 `pending_review`，写明原因与所需材料，不凭空补结论 |

## 文献材料不可见时的纪律

1. 被引文献全文/摘要不在 `/input` 中（无 `fulltext/` 子目录、无 `ref<n>` 命名文件）
   → 该引用支持判定为 `cannot_verify`，进待复核。**禁止**依据文献标题、著录格式、
   作者名望推测其主张。
2. 禁止编造页码、DOI、文献结论、被引次数。无法确认 → `pending_review`。
3. 悬空引用、未被引用、重复著录、DOI 格式异常属于**机械判定**，不依赖文献可见性，
   可直接产出 finding。

## 防误报规则

- **合理简写不算错配**：作者对文献的转述允许省略条件状语、合并相近结论，
  只要不改变主张方向与适用对象。如文献称"在 ImageNet 上达到 76.1% top-1"，
  正文写"此前工作已在 ImageNet 上验证有效"——不算错配。
- **综述性引用不算错配**："[1-3] 及其引用"式背景性引用只要求主题相关。
- 词元重叠启发式（cite_match.py `judge_support`）：Jaccard ≥ 0.25 → `supports` 初判；
  0.08–0.25 → `partially_supports` 初判；< 0.08 → `cannot_verify`（**不**反向推
  `not_supported`，防止把表述差异误判为不支持）。
- 同一引用多处出现，以最靠近主张句的一处为准；背景段引用降权。

## 待复核条目写法

每条 `pending_review` 必须含：`item`（判什么）、`reason`（为什么不能判）、
`action_needed`（需要什么材料/步骤）。
