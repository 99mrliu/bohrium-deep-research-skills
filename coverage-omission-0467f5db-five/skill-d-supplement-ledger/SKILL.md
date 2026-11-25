---
name: supplement-ledger-economics
description: 补检账本与边际收益治理技能。用于"检索覆盖率与遗漏分析"类任务：把每条查询（初始与补检轮）记入查询账本——命中数、为参考集新挽回的文献、边际收益；用三条显式停止规则（零新增轮 / 边际收益低于阈值 / 预算耗尽）决定何时停止补检，判定引用账本行号；用两个查询族的 Chapman 校正 Lincoln–Petersen 捕获-再捕获模型估计残余遗漏规模，并附假设与局限。当任务需要证明"补检后遗漏真实下降"并说明残余遗漏时使用。边界：同义词重跑记零收益、禁止补检空转；残余估计只是下界启发式，绝不替代逐条漏检清单；不发起实时检索。
---

# 补检账本与边际收益治理（supplement-ledger-economics）

## 重心与适用条件

重心是**补检的决策质量**。常见失败不是不补检，而是空转：换个同义词重跑、命中集合零新增，却报告"遗漏已下降"。本技能用三本账治理：

1. **查询账本**（query_ledger.json）：每条查询一行——轮次、来源、命中记录数、`new_recovered`（该查询**首次**为参考集挽回的文献）、边际收益。收益只按"首次挽回"记账，重复命中不计；
2. **停止规则**（stop_decision.json）：S1 最近一轮零新挽回；S2 最近两轮平均每查询边际收益 < 0.5；S3 预算耗尽（材料无预算字段时声明"不可评估"而不是假装评估过）。每条规则的判定都引用账本行号；
3. **残余遗漏估计**（residual_estimate.json）：以两个不同来源的查询族为两次捕获，Chapman 校正 LP 估计参考集中仍遗漏的规模；显式列出等可捕获性、族独立性、封闭总体三条假设，并声明这是下界启发式。

## 运行环境

- 输入 `/input/case.json`、`/task.md`；材料递归扫描。工作 `/app/work`，交付 `/app/output`。
- Python 3 标准库，零依赖，不联网；一条命令跑完。预算 ≤64 请求 / ≤900 秒。

## 调用方式

```bash
python3 /skills/weekly-skill/scripts/ledger_engine.py \
  --input /input --work /app/work --output /app/output
```

退出码 `0` 完成 / `2` partial / `3` 契约字段缺失。查询若带 `round`/`phase`/`iteration` 字段则按轮次记账；补检轮查询与初始查询放在同一结果文件中即可，账本按轮次自动分列。

## 产物

| 产物 | 内容 |
|---|---|
| /app/output/result.json | case_id、output_contract 全字段、status、sources、uncertainty、change_log |
| /app/output/coverage_report.md | 账本表、停止规则判定、残余估计全文 |
| /app/work/query_ledger.json | 逐查询账本（new_recovered、marginal_yield、zero_gain） |
| /app/work/stop_decision.json | 三条规则的触发状态、证据行号、停止建议 |
| /app/work/residual_estimate.json | 捕获-再捕获估计、假设、caveat |

## 判读规则

- 账本中 `zero_gain=true` 的补检查询是"空转"的直接证据；报告中不得把零收益轮表述为"遗漏下降"；
- 覆盖率只按账本累计的 `new_recovered` 计算，与逐条命中状态一致，可独立复算；
- 残余估计仅在存在 ≥2 个不同来源时给出；单来源时写入"不可估计"并列入 uncertainty。

## 异常处理

- 无查询材料：status=partial，账本为空，覆盖/停止/估计各环节分别说明；
- 查询缺轮次字段：全部记为第 1 轮，S1/S2 自动不满足并如实说明；
- 参考集为空：status=partial，其余产物照常交付。

## 最小调用示例（合成示例）

`examples/input/` 为**合成**数据：9 条参考题录、两个来源共 5 条查询（第 1 轮 2 条、第 2 轮补检 2 条、第 3 轮补检 1 条零收益）。运行：

```bash
python3 scripts/ledger_engine.py --input examples/input --work examples/run/work --output examples/run/output
```

预期（合成示例，非正式案例结果）：账本显示第 2 轮挽回 2 条、第 3 轮零收益；S1 触发、建议停止；捕获-再捕获给出残余遗漏估计（含假设）；覆盖 7/9，漏检 2 条逐条列出。详见 examples/README.md。

## 自查方法

1. result.json 含 case_id 与契约全部字段；
2. 账本所有行的 new_recovered 并集大小 = coverage.hit；
3. stop_decision 每条 fired=true 的规则都有非空 evidence_rows；
4. residual_estimate 存在时 estimated_residual_omission ≥ 0 且附 assumptions。
