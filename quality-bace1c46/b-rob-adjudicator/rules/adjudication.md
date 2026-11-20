# 仲裁规则（adjudication rules）

`scripts/adjudicate.py` 对通道 P 与通道 N 的领域级初评逐域合并。规则按编号引用，
所有分歧与裁决理由写入 `adjudication_ledger.jsonl`，**分歧永不静默抹平**。

## 证据优先顺序

1. **方法学明文描述**（Methods 中对该领域做法的直接陈述）——最高优先；
2. **结果/表格暗示**（Results、表格注释、流程图中间接可推断的证据）；
3. **局限段自述**（作者承认的缺陷，可作为 `present`/`likely` 的证据）；
4. **无报告** → `insufficient`（弃权），**绝不默认安全**。

## 规则列表

- **R1 一致**：两通道判定相同 → 直接采用，`source=agreement`，不进分歧台账。
- **R2 证据优先**：判定不同且恰有一方附逐字摘录 → 采用有摘录一方的判定
  （`source=adjudicated_R2`）。依据：有证据的判断优先于无证据的判断。
- **R3 无证据默认弃权**：判定不同且双方都无摘录 → 判 `insufficient`
  （`source=adjudicated_R3`）。依据：无报告即证据不足。
- **R4 保守规则**：判定不同且双方都附摘录（真冲突）→ 采用**较高风险级**
  的判定（present > likely > no_indication > insufficient），并标
  `adjudicated_conservative=true`（`source=adjudicated_R4`）。
- **R5 单通道**：仅一个通道给出该领域判定 → 有摘录则采用并标
  `source=single_channel_P/N`，无摘录则 `insufficient`；记 `channel_missing`。
  两通道均缺失 → `insufficient`，记 `no_channel`。

## 分歧分类（台账字段 type）

| type | 含义 | 处理规则 |
|---|---|---|
| `disagreement` | 两通道判定不同 | R2/R3/R4 |
| `channel_missing` | 仅一通道报告 | R5 |
| `no_channel` | 两通道均缺失 | R5 |

## 保守规则的例外

- 若较高风险判定仅依赖"未披露"类线索（如资助声明缺失），而较低风险判定
  有方法学明文证据，则按 R2 的证据优先顺序处理，**不机械取高风险**；此时
  在台账 detail 中写明 "evidence priority overrode conservative default"。
- `insufficient` 与 `no_indication` 的分歧：若 N 通道记录了主动否定性检索
  范围（检索过哪些章节/关键词）而 P 通道无摘录，采用 `no_indication` 须以
  N 的检索范围记录为前提；否则按 R3 判 `insufficient`。
