# 法律状态核验协议（登记优先 / 查询日期 / 滞后与 unknown 纪律）

> 本文件是 `scripts/status_ledger.py` 规则引擎（R-S1～R-S5）的人读版本。两者保持一致。

## 1. 登记优先原则

法律状态结论的**登记依据**只能是：
- `official_register`：官方登记簿（如 CNIPA 专利登记簿、USPTO Patent Center /
  Maintenance、EPO European Patent Register、WIPO 官方记录）；
- `official_gazette`：官方公报（授权公告、失效公告等）。

**`aggregation_page`（聚合页/转载页，如各类专利聚合站）永远不得作为登记依据**，
只能作线索（`leads_only=true`），且由它得到的状态必须标注"待官方登记复核"。
规则引擎对 `as_register_basis=true` 的聚合页记录直接拦截（exit 非 0）。

**`inference`**（按缴费期、期限推算等）只能给出降级结论：必须 `downgraded=true`
且附 `review_advice` 人工复核建议。

## 2. 查询日期纪律

- 每条状态记录**必须**携带 `query_date`（ISO YYYY-MM-DD），即"你实际查到这个状态
  的日期"，而不是文献本身的日期；
- 输出中的状态措辞统一为"**截至 YYYY-MM-DD 查询，……**"；
- `effective_date`（状态生效日）查不到就省略，**不得编造**。

## 3. 滞后与 staleness

- 查询日期距今超过 **180 天** 的记录必须填写 `staleness` 滞后备注
  （缺备注时规则引擎给出 warning）；
- 即便来源是官方登记，也存在"登记滞后于实际法律事实"的可能；对时效敏感的结论
  （如失效日临近、年费窗口）必须在 uncertainty 中声明滞后风险；
- 风险分级侧对应 R-G2：查询日期距今 >180 天 +2 分，90–180 天 +1 分。

## 4. unknown（未知）纪律

- 当前官方法律状态**查不到就如实标 `未知`**，这是本挑战语料的常态，不是失败；
- `未知` 状态下**禁止任何确定性措辞**："已授权 / 专利权有效 / 仍然有效 / 已失效 /
  已过期 / 确定有效 …"一律拦截（R-S2，含完整禁用词表见脚本 `FORBIDDEN_DETERMINISTIC`）；
- 合规表述模板："截至 {query_date}，在 {来源} 未检索到该案的当前官方法律状态，
  状态**未知**，建议到官方登记簿复核"；
- `未知` 记录必须附 `review_advice`；在风险分级中触发 R-G8（+2 分）。

## 5. 状态冲突处理

- 两个来源给出不同状态时：official_register > official_gazette > aggregation_page
  （线索）> inference（降级）；
- 冲突必须写入 result.json 的 `uncertainty`，不得静默二选一；
- 无法调和时回落到 `未知`。

## 6. 同族口径提醒

- 观察到的链接（聚合页"同族"标签、引文关系等）**不构成完整同族**；
- 输出中只能写"观察到与 X、Y 的关联（来源：…），未做完整同族核查"，
  否则触发风险规则 R-G3。
