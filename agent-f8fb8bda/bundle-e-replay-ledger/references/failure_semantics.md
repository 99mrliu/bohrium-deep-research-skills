# 失败语义与诚实记账（Failure Semantics）

运行日志的 `status` 恰有四个取值。语义必须严格区分，否则 `journal.py stats` 的覆盖率统计与第三方复跑都会被误导。

## 四态语义

| status | 语义 | 记账要求 |
|---|---|---|
| `ok` | 调用成功且返回了可用内容（含"成功返回 0 条但本就预期为空"之外的一切正常返回） | `results_count` 为实际条数；`results_digest` 为返回原始内容的 SHA-256 |
| `empty` | 调用成功执行，但检索/解析结果为空 | **必须记 empty，禁止记 failed**——"没有证据"本身是研究空白的重要信号，须与"工具坏了"分开计数。`results_count=0`，`note` 说明该角度后续如何处理（换检索词 / 转入 uncertainty 声明） |
| `failed` | 工具本身报错（限流 429、超时、PDF 损坏、权限拒绝等），未获得有效返回 | `note` **必须**写明：①失败原因；②降级决策（改用摘要/换源/放弃该角度）。`results_count=0`，`results_digest` 可记空串的 SHA-256 或错误文本的 SHA-256 |
| `retry` | 对同一动作的再次尝试 | **重试的每一笔都保留**，不得与最终成功笔合并，也不得删除先前 failed 笔。`args` 中应能看出与原笔的对应关系（相同 query / 相同 url） |

## 记账纪律

1. **append-only**：日志行只增不改。记错了就再 append 一笔更正（note 说明"更正 seq=N"），绝不动既有行——哈希链会使任何改动立刻暴露。
2. **一动作一笔**：复合动作（检索后立刻抓取命中页面）拆成多笔，各自记账。
3. **digest 口径**：`results_digest` 一律对"工具返回的原始内容字节"计算 SHA-256，不做人为摘选，保证第三方可重算。

## 诚实 partial 与日志的关系

当证据不足以给出 complete 结论时，`result.json` 的 `status` 记 `partial`，且：

- **日志即证据**。partial 的限度不靠口头声明，而由账本直接支撑：
  - 已做哪些 → 全部 `ok` / `empty` 笔及其检索角度；
  - 卡在哪 → `failed` 笔的 note（限流、来源不可得等）与未执行的子问题；
  - 降级决策 → 每笔 `failed` / `retry` 的 note。
- result.json 的 uncertainty/研究空白区块必须逐条对应账本中的 `empty` 角度与 `failed` 降级影响，不得出现"账本无记录"的限度声明，也不得隐瞒账本里已有的失败。
- `journal.py stats` 中 empty 与 failed 分开计数，使读者一眼区分"查过但没有"与"没查成"。这是 partial 结论可信度的量化依据。

## 反例（判分上属于不诚实）

- 检索为空却记 `failed`，再在文中声称"未检索"——夸大了未覆盖程度，或掩盖了已确认的研究空白。
- 失败后静默换源而不记 `failed` 笔——第三方复跑时会发现结果来源与账本不符。
- 重试成功后删除先前的 `failed` 笔——哈希链断链，`verify` 直接 exit 1。
- partial 但 uncertainty 区块为空——与账本中的 `empty`/`failed` 记录矛盾。
