# 平台运行契约与预算阶梯（contract-gate）

本 Skill 的重心不是排版技术，而是**让任何适配任务在平台契约下可交付、
可复核、可中断恢复**。以下是契约要点（源自题目 Harbor 技术提交约定）
与本 Skill 的执行纪律。

## 契约要点（不可协商）

| 项 | 要求 |
|---|---|
| 输入 | `/input/case.json` + `/input/task.md` + 材料；读实际文件，不按标签猜内容 |
| 工作区 | `/app/work`；交付 `/app/output` |
| result.json | `case_id` + case.json `output_contract` 全部字段；status/sources/uncertainty/changes 诚实 |
| 部分结果 | partial 必须指明局限（limits）；材料缺失/无法判断/运行失败分别说明 |
| 预览 | 可编辑 Office/幻灯/图示产物须附真实渲染 PDF/PNG |
| 预算 | 64 次模型请求 / 900 秒 / 每次响应 16384 token |
| 禁止 | 预置答案、伪造软件状态或科学数据、虚构基准分数 |

## 执行纪律（本 Skill 的实现）

1. **骨架先行**：probe 在第一分钟内落 partial result.json——此后任何中断，
   盘上都有一份诚实 partial，而不是什么都没有。
2. **阶段打卡**：每个阶段结束跑 checkpoint，产物哈希进 result.json，
   事件进 journal.jsonl。复核者按 journal 可重放"从输入件到成品"的全过程。
3. **封印独立**：seal.py 不采信 Agent 自述，只核对盘上证据；
   SEAL REFUSED 时修交付物，**不许改 seal**。

## 预算阶梯（900 秒的价值排序，从高到低）

| 梯级 | 动作 | 保证 |
|---|---|---|
| T0 | probe 骨架 | 有 partial 可交 |
| T1 | 读 task.md + 材料，写清任务理解进 uncertainties 旁注 | 不做错对象 |
| T2 | 完成核心适配动作，产出可编辑交付物 | 主结果存在 |
| T3 | 填契约字段 + checkpoint 登记产物 | 契约完整 |
| T4 | 渲染预览（可用时）+ 机器校验 | 证据链 |
| T5 | seal 裁决 + 人工目检补 uncertainties | 封印交付 |

时间告急时自上而下截断：任何一级停下，status=partial 并在 limits
写清"未完成的梯级"。**绝不**为了凑 complete 跳过 T1/T3。

## status 语义

- complete：契约字段全填、limits/manual_confirm/uncertainties 全空、
  seal 八项全过。绝大多数真实运行不该轻易到达这里。
- partial：有未了事项，每项在 limits/manual_confirm 可点名。
- failed：输入损坏/工具链失效导致主结果不存在；sources 与 limits
  仍须如实填写（failed 也是一种诚实交付）。
