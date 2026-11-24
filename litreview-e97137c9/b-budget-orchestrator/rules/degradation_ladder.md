# 降级阶梯规则（degradation ladder）

预算固定（默认 64 次模型请求），文献数量与质量不可控。降级不是临场妥协，而是
**预先定义、由脚本执行、全程留痕**的收缩顺序。所有触发的降级项写入
`run_plan.json` 的 `degradations`，并最终进入 result.json 的 uncertainties。

## 1. 阅读深度阶梯（文献数多时）

每篇文献的深度由 `budget_ledger.py plan` 裁定，依据两个信号：

- **tier**：`abstract_only` 恒为 abstract 深度；`metadata_only`/`failed`/`duplicate_of`
  恒为 skip（不分配 digest 请求，只进筛选记录与 uncertainties）。
- **相关度**：脚本对每篇全文文献计算"研究问题关键词 token 重叠得分"
  （拉丁词去停用词 + CJK 二字组，统计在研究问题与正文中的重合），按得分降序排名。

降级顺序（从高到低）：

| 档位 | 含义 | digest 批次 |
|-|-|-|
| full | 按 `pages/<doc_id>.jsonl` 锚点通读全文 | 每批 ≤2 篇合并 1 次请求 |
| sections | 只读与研究问题最相关的章节 | 每批 ≤4 篇合并 1 次请求 |
| abstract | 只读摘要页，strength ≤ suggestive | 每批 ≤8 篇合并 1 次请求 |
| skip | 不读，仅入筛选记录 | 0 次 |

触发条件：

1. 文献数较多时预防性限档：full 档最多 8 篇（得分最高者优先），sections 档最多
   12 篇，其余直接落 abstract。
2. 预算核算超支时：从**得分最低**的 full 档开始逐篇降 sections，再降 abstract，
   最后尾部 skip——降档永远先牺牲低相关文献。

## 2. 阶段裁剪阶梯（预算不足时）

按以下顺序砍，**保底组合（筛选 + 证据表 + 简草稿）不可再砍**：

1. **先砍草稿润色**：draft 从 3–4 次压到 2 次（一稿 + 一次自校，取消润色轮）。
2. **再砍主题细分**：themes 从 4–8 次压到 3 次（单轮综合，取消主题间交叉复核）。
3. **然后砍阅读深度**：按第 1 节顺序降档（full→sections→abstract→skip）。
4. 保底：screening（1 次）+ evidence_ledger（≥2 次）+ draft（2 次）+
   reserve（verify+repair 6 次）构成最低交付形态；连保底都装不下时，
   status=partial 交付并逐项说明。

reserve 的 6 次（verify+repair）**任何情况下不得挪用**给前面的阶段——
没有校验修复预算的交付等于没有一致性保证。

## 3. 中断恢复规则

- `state.json` 是唯一事实来源：每阶段 pending/completed、产物路径、实耗请求数。
  模型阶段每完成一步必须 `budget_ledger.py mark` 登记，否则中断后无法对账。
- 恢复流程：`budget_ledger.py status` 看剩余预算与已完成阶段 →
  `run_case.py check` 核对账本与磁盘（标记 completed 但产物缺失/为空的阶段
  判为虚报，改回 pending 重做；pending 且产物缺失的阶段即为续跑起点）→
  从续跑起点继续，最后 finalize。
- 契约兜底：contract_probe 在 init 时已写出 status=in_progress 的 partial
  result.json（全部契约字段为 null），任何时刻中断，交付目录都结构完整；
  恢复后 finalize 负责把 null 替换为真实内容，实在无产出的字段保留 null
  并在 uncertainties 说明。
- 预算对账：`requests_used` 只通过 mark 累加；发现实耗与账本不符时，以
  change_log 中各阶段登记为准手工修正 state.json，并把修正记入 change_log。
