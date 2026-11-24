# 降级阶梯：预算耗尽时如何诚实交付

原则：任何时刻的交付物都反映"当时真实完成的部分"，不伪装完成、不交白卷。

## L0 完整（目标态）

全部工序完成 + review_queue 为空或全部复核完毕 → `status: success`。

## L1 完成但有未决（常见）

工序完成，review_queue 残留（键冲突、未知单位、不可逆换算）→
`status: partial`，limitations 逐条列出未决项与保守处置（保留原值）。
**这是大多数真实案例的正确终点**，不扣分；假装没有未决项才扣分。

## L2 工序未竟（时间不够）

水位 >750s 或工序中断：
1. `pipeline.py --resume` 能跑多远跑多远（已完成工序有检查点）；
2. 已落盘的产物（cleaned/ledger/quality_report 若为中间态，命名如实，
   如 `cleaned.stage-units.csv`）复制到 /app/output；
3. result.json：`status: partial`，limitations 写明断在哪个工序、
   哪些字段是中间值。

## L3 硬失败（输入不可处理）

表为空/不可解码/权限不足：
1. result.json：`status: failed`，error 写明失败点与证据（报错原文、
   文件 sha256）；
2. 已固证的输入快照与诊断信息落 /app/output；
3. 不交空 result.json，也不交"看起来完整"的假产物。

## 反模式（评审零分项）

- 报告数字手抄而非重算（与产物对不上）；
- status=success 但 review_queue 非空且无 limitations；
- 失败后覆盖/删除原始输入；
- 为赶在预算内而跳过固证（快照与 sha256）。
