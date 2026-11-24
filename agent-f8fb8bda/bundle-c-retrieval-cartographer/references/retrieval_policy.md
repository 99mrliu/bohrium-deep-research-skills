# 检索策略规范（retrieval policy）

本规范约束检索计划的波次设计、停止条件、去重键与预算纪律。检索计划在执行前必须通过
`scripts/plan_check.py` 的 P1–P5 门控。

## 1. 波次设计（waves）

- **W1 背景定界先行**：先检索 SQ-1（背景与定界）及一切被其他 SQ 依赖的子问题。
  W1 的结果用于校准关键词、同义词与纳排口径，再展开主体检索。
- **W2 各 SQ 并行主体**：无相互依赖的 SQ 在 W2 并行展开；每个 SQ 至少 1 个 action，
  每个 action 必须写清 `query`、`source_scope`、`stop_condition` 三键。
- **W3 仅对 unmet SQ 缺口补检**：只有覆盖矩阵判定为 unmet（相关命中不足阈值）的 SQ
  才允许进入 W3 补检；met 的 SQ 不再追加检索，searched_absent 的 SQ 转入空白判定，
  不再无目的扩检。
- 波次必须与依赖一致（P4）：SQ-x 依赖 SQ-y 时，SQ-y 的全部 action 不得晚于 SQ-x 的
  最早 action 所在波次。

## 2. 停止条件（stop_condition）写法

每个 action 的 `stop_condition` 必须是可判定语句，推荐二选一或并列：

- **达标即停**："该 SQ 去重后相关命中 ≥ 3 条即停"（阈值与 coverage.py 的
  `--met-threshold` 默认 3 保持一致）；
- **边际为零即停**："连续两次检索新增相关命中为 0 即停"（对应覆盖矩阵中
  `saturation.new_relevant_last_action == 0` 的 saturated 信号）。

禁止写法："多搜一些""尽量全面"等不可判定表述——plan_check P2 只查非空，
可判定性由 Agent 自律，评测按六要点核查。

## 3. 去重键规范（dedup_key）

全局去重按 `dedup_key` 进行，重复命中计入 `dupes_skipped` 而不计入覆盖：

1. **DOI 优先**：命中有 DOI 时，`dedup_key = "doi:" + 小写 DOI`；
2. **兜底键**：无 DOI 时，`dedup_key = 首作者姓 + 年份 + 标题前 40 字符归一化`
   （归一化 = 小写、空白压缩、去标点）；
3. 同一文献被多个 action 命中是正常且被鼓励的（证明检索式收敛），但必须共用同一
   dedup_key，否则去重失效、覆盖矩阵失真。

## 4. 一次检索、多 SQ 标注

同一条检索式若同时服务多个 SQ，**只执行一次**，用 `sq_ids` 列表标注所有受益 SQ。
跨 action 出现归一化后完全相同的检索式将触发 plan_check P3 违例。

## 5. 边际收益与预算纪律

- action 总数 ≤ 25（plan_check P5，可用 `--max-actions` 收紧）；
- 每追加一个 action 前回答："它服务哪个 SQ？期望新增什么？"答不出就不加；
- 检索预算与模型请求预算同样稀缺：宁可少检索、把每次检索的 query/source_scope/
  stop_condition 写扎实，也不要用重复检索式凑数（P3 会直接判违例）；
- **搜过没有 ≠ 没搜过**：覆盖结论只能基于 search_log.jsonl 的实际记录导出，
  未检索的方向一律 not_assessable，严禁写入研究空白。
