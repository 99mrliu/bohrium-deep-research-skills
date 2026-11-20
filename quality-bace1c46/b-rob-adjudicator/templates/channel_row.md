# 通道记录格式（channel_p / channel_n）

每个通道输出一个 JSONL 文件：`channel_p/<doc_id>.jsonl` 与
`channel_n/<doc_id>.jsonl`。**每行一个 JSON 对象**，覆盖该文献
domain_plan 中的每个领域。

## 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `doc_id` | 是 | 与 docs.jsonl 一致 |
| `domain` | 是 | 领域 id（如 `randomization`），见 domain_plan.json |
| `judgment` | 是 | `present` / `likely` / `no_indication` / `insufficient` |
| `quote` | 判 present/likely 必填 | **逐字摘录**（将过归一化子串校验；不要改写、不要拼接省略号之外的内容） |
| `locator` | 有 quote 时必填 | 页锚 `p<页>.¶<段>`，如 `p3.¶2` |
| `rationale` | 是 | 判断理由；`no_indication` 必须写明主动检索范围 |

## 示例行

```json
{"doc_id": "smith2023", "domain": "randomization", "judgment": "insufficient", "quote": "", "locator": "", "rationale": "Methods 仅写 'Patients were randomized'，无序列生成与分配隐藏细节。"}
{"doc_id": "smith2023", "domain": "selective_reporting", "judgment": "present", "quote": "The primary endpoint was changed to progression-free survival after unblinded interim analysis", "locator": "p6.¶1", "rationale": "局限段自述未盲中期分析后更换主要终点。"}
```

## 通道职责

- **通道 P（正向取证）**：从 signals 的 `candidates_p` 出发，找支持
  "偏倚被控制 / 问题有正面答案"的证据，或支持 "偏倚存在" 的明文证据。
- **通道 N（反向查漏）**：从 `candidates_n`、局限段、表格注释、摘要与
  正文差异出发，专找未报告项与矛盾；发现"未披露 X"本身不是偏倚证据，
  应导向 `insufficient` 而非 `present`。
