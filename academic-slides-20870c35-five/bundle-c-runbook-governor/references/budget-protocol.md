# 预算协议：64 请求 / 900 秒的五阶段配额 + reserve 与降级顺序

预算硬上限：64 次模型请求、900 秒墙钟、每响应 16384 tokens（含推理）。`contract_init.py` 生成的 `budget_ledger.json` 已含下列配额；每阶段结束向 `usage` 追加一条实际消耗，格式 `{phase, requests, seconds, note}`。

## 1. 配额表（quota + 每阶段 reserve）

| 阶段 | 请求 quota | 请求 reserve | 秒 quota | 秒 reserve | 要点 |
|---|---|---|---|---|---|
| p0 契约接管 | 0 | 0 | 脚本 | — | contract_init.py 完成，不耗模型请求 |
| p1 材料索引与主线 | 12 | 2 | 180 | 20 | 逐页文本先落盘再判断；关键图页渲染目检 |
| p2 storyboard | 8 | 1 | 110 | 10 | 听众模型 + 页级规划一次响应成型 |
| p3 建 deck | 13 | 2 | 200 | 20 | 模板内构建 + notes + 证据定位 |
| p4 渲染 QA | 10 | 2 | 150 | 20 | 导出 + 预览 + 至多两轮修复回路 |
| p5 交付门 | 12 | 2 | 170 | 20 | 回填 + 门控 + 修复，先存快照再改 |
| 合计 | 55 | 9 → **64** | 810 | 90 → **900** | quota 用尽才支取本阶段 reserve |

reserve 支取规则：仅当本阶段 quota 耗尽时可支取**本阶段** reserve；跨阶段挪用必须伴随一次显式降级决定（写入 usage 的 note），禁止无声挪用。

## 2. 省请求纪律

1. **先跑脚本骨架再思考**。Phase 0 全程零请求；模型读的是 contract.json，不是反复揣摩原始 case.json。
2. **一次响应多做事**。storyboard 一次成型；deck 的多页内容合并构建；result.json 的回填按"能一次填完就不分两次"。
3. **写盘即忘**。已落盘的中间产物（逐页文本、mainline.json、storyboard.json）不重读校验——机械一致性由 delivery_gate 把关，模型不复查机械项。
4. **快照不耗请求但要有节奏**。p0/p1/p2/p3/p4/p5-pre-gate 各存一次；每改一处就存只会干扰 recover 选择。
5. **渲染至多两轮**。全量导出+预览是最贵的工具回路；两轮修不净就在 `limitations` 写明残留问题，以 partial 交付。
6. **失败响应也算配额**。工具报错、解析失败都消耗预算；先小步验证（一页试导出）再批量。

## 3. 超支前的降级顺序

某阶段 usage 逼近 quota+reserve 时，按以下顺序降级，每级都保持交付诚实：

1. **收缩索引深度**：非核心材料只做元数据级索引，全文精读留给主线关键文献；在 `uncertainty` 声明索引级别。
2. **压缩页数打磨**：storyboard 不变，notes 先写要点后补全文；备用页砍掉，主叙事页优先。
3. **砍修复回路**：渲染 QA 一轮定音，残留问题写入 `limitations`。
4. **提前进交付门**：保留 ≥5 请求 / ≥60 秒给 Phase 5；以 `partial` 交付，`limitations` 逐字段写清未竟事项（D2/D4 会核验）。
5. **blocked 兜底**：仅当材料/环境根本性不可用时使用，写清 `blocked_reason`。

禁止的"伪降级"：删 `limitations` 凑 completed、编造 `sources` 凑 D4、把 PENDING 改空串绕 D2、跳过 checkpoint 直接大改——这些直接摧毁可信度与可恢复性。

## 4. 早存盘、增量改进

第一阶段结束时就应存在一份可交付的诚实 partial result.json（骨架即 partial）；之后每个阶段让它更接近 completed。这样即使 900 秒在任意时刻耗尽，`/app/output` 里始终是一份状态诚实、产物可核、可从快照恢复的交付，而不是一地中间文件。
