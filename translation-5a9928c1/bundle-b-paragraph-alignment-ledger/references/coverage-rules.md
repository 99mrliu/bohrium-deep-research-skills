# 覆盖台账规则（Bundle B）

## apply 的硬性拒绝（exit 1）

1. 未知 ID（translations 出现台账没有的段）——防凭空造段。
2. 同一 translations 文件内重复 ID——防一段两译。
3. `sha256(source)` 与台账 `source_sha256` 不符——防错位与陈旧的段被当作当前段。

## 完整性判定（report）

- `complete = (missing == [] and duplicate_ids == [])`；exit 0 当且仅当 complete。
- 缺段 → `status=partial` + uncertainties 逐段列出；全缺 → `failed`。
- 幂等：同内容重复 apply 记 `idempotent-skip`，不改变已完成状态。

## 与翻译质量的关系

覆盖核验证明"块级不漏、不重、不乱序"，不证明句级语义正确；两者都要，但由不同机制负责。
