# 四级判定定义与领域→整体等级映射

## 四级判定

| 等级 | 中文 | 定义 | 证据要求 |
|---|---|---|---|
| `present` | 明确存在 | 有明文/可推断的证据表明该偏倚**存在** | 必须附逐字摘录 + 页锚 |
| `likely` | 可能存在 | 有线索提示偏倚很可能存在，但证据不决定性 | 必须附逐字摘录 + 页锚 |
| `no_indication` | 未见迹象 | **主动检索过**否定性证据后未发现任何迹象 | 必须在 rationale 记录检索范围（查过哪些章节、哪些信号问题关键词）；摘录可附肯定性证据 |
| `insufficient` | 证据不足 | 信息缺失，无法判断 | 弃权，不是默认安全等级；须在 rationale 写明缺什么 |

### "未见迹象"的主动检索要求

判 `no_indication` 前必须：
1. 运行过 `collect_signals.py` 的通道 N 召回（含通用未报告词表）；
2. 人工/模型浏览过该领域全部 N 通道候选句，确认无否定性证据；
3. 在 rationale 中写明检索范围，如"已检索 Methods/Results/局限段及
   全部 N 通道候选 12 条，未见分配隐藏相关描述之外的风险线索"。

### 弃权规则

- `insufficient` 是诚实弃权，常见于：abstract_only 文献、方法段缺失、
  关键声明（注册、资助、COI）全文未出现。
- 引用门控失败的记录一律降级为 `insufficient` 并保留原判定于
  `judgment_original`。
- 连续多个领域 `insufficient` 时，整体等级按映射表封顶为
  `insufficient_evidence`。

## 领域 → 整体风险等级映射表

按序逐条判定，**首次命中即停**，推导过程写入 `overall_derivation`：

| # | 条件 | 整体等级 |
|---|---|---|
| M0 | 文献为 abstract_only，或无可评价领域，或 >50% 领域 `insufficient` | `insufficient_evidence` |
| M1 | 任一**核心**领域 `present` | `high` |
| M2 | ≥2 个领域（任意）`likely` | `some_concerns` |
| M3 | 任一核心领域 `likely` | `some_concerns` |
| M4 | 任一非核心领域 `present` | `some_concerns` |
| M5 | 无 present/likely 但存在 `insufficient`（保守） | `some_concerns` |
| M6 | 全部领域 `no_indication` | `low` |

- **禁止孤立等级**：整体等级必须伴随上述映射的推导记录，第二个人按
  记录应能复现同一等级。
- 人工复核改判（`review_overrides.jsonl`）后按同一映射重新推导，并在
  result.json 的 `overrides_applied` 中记录改动前后等级。
