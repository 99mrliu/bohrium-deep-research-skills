---
name: recompute-lab
description: 面向「实验结果解释与异常分析」的双通道数值复算实验室。每个准备写进结论的统计量（均值/方差/中位数/峰值/斜率/曲线下面积）都用两条实现路径独立的算法各算一遍并做容差判定；结论中的每个数在交付前必须通过 claims 审计。当任务要求报告可复算、可核验的实验数值结论时触发。
---

# recompute-lab：双通道数值复算实验室

## 用途与重心

本 Skill 的重心是**数值可复算性**。解释类结论的可信度下限是「这个数本身算得对」：单次实现的均值可能踩数值稳定性坑（二阶矩法求方差在大均值小方差时失真）、手抄数可能错位、有效数字可能悄悄进位。本 Skill 规定：**任何写进 result.json 的数值，必须先过双通道复算（同输入、两种算法、容差判定），再过 claims 审计（claimed vs recomputed）**。

**边界**：
- 只保证「算得对」，不判断「该不该这么算」——方法适用性（非线性段做线性拟合等）由 Agent 论证并写入 uncertainty。
- 通道一致 ≠ 物理正确；通道不一致 ⇒ 该数禁止上报。
- 纯 stdlib；阈值集中：默认 abs_tol=1e-9、rel_tol=1e-9（复算级），claims 审计默认 rel_tol=1e-6（报告级），可在 claims.json 逐条覆盖。

## 运行时契约

- 输入：`/input/case.json`（`case_id` + `output_contract`）、`/input/task.md`、数据材料。
- 工作目录 `/app/work`（账本在 `/app/work/ledgers/`）；成果 `/app/output/result.json`（原始 case_id、契约全部字段、诚实 status、sources、uncertainty、change_records）。
- 预算：约 64 次模型请求 / 900 秒 / 每响应 16384 tokens。partial-first：第一步落骨架。
- 脚本路径以 `/skills/weekly-skill/scripts/` 书写；安装路径不同逐字替换前缀。

## 标准流程

```bash
# 1) 一键：partial 骨架 + 全部数值文件的双通道账本 + result.json 预填
python3 /skills/weekly-skill/scripts/run_lab.py --input /input --work /app/work --output /app/output

# 2) Agent 撰写结论前：把每个要报的数登记成 claims.json（格式见下），再审计
python3 /skills/weekly-skill/scripts/run_lab.py --input /input --work /app/work \
    --output /app/output --claims /app/work/claims.json
```

claims.json 每条：`{"claim_id","text","quantity","value","source_file","col","rel_tol"}`，
`quantity ∈ mean|variance_pop|median|max|slope|auc_trapz`。

**审计 verdict 与处置**：
- `CONFIRMED` → 可写入结论，引用格式「812.3 (recomputed 812.3002, rel_diff 2e-7, ledger ledgers/x.series.ledger.json)」；
- `TOLERANCE_MISS` → 改数或显式放宽容差并说明理由；
- `CHANNEL_DISAGREE` → 该数禁报，排查实现/数据（常见于病态输入）；
- `UNVERIFIABLE` → 缺定位，不得交付。

**交付硬规则**：`claims_audit.json` 的 `deliverable=false` 或存在 CHANNEL_DISAGREE 账本时，status 保持 partial 并在 limitations 点名。

## 双通道设计（实现路径必须不同）

| 统计量 | 通道 A | 通道 B |
|-|-|-|
| mean | sum/n 单次遍历 | 增量式在线均值 |
| variance | 二阶矩 E[x²]−E[x]² | 两遍法 |
| median | 排序取中 | Quickselect |
| slope | 正规方程闭式 | 协方差/方差 |
| auc | 逐项梯形累加 | 成对平均×步长 |
| max/argmax | 一次遍历 | 排序取首 |

## 失败处理

- 解析失败（编码/表头）：修正理解后重跑；不手算替代脚本。
- DISAGREE 排查顺序：数据列选错 → 单位/尺度 → 病态条件数 → 最后才怀疑算法；排查记录写入 change_records。
- 900 秒预算紧张时：优先 claims 审计（只算要报的数），全量账本可降级为抽样并在 limitations 说明。

## 最小示例

`examples/`（**合成示例**）：一条合成载荷-位移曲线 + 一份含 1 个正确数与 1 个故意写错数的 claims.json，演示 CONFIRMED 与 TOLERANCE_MISS，及 deliverable 规则如何阻止带错交付。见 `examples/README.md`。
