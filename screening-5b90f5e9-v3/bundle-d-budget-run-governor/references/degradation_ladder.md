# 降级阶梯（L0–L3）：触发条件与诚实表述规则

> 本文件是降级决策的**写死规则**。两条红线：
> 1. 降级必须如实反映在 result.json 的 `status` 与 `uncertainty` 中；
> 2. 任何档位都不得声称未执行的工作已完成——"诚实 partial 永远优于虚假完整"。

## 1. 档位定义

| 档位 | 启用阶段 | 砍掉什么 | result.json 形态 |
|---|---|---|---|
| L0 完整流程 | 全部 8 阶段 | 无 | status=completed；全部合同字段有值 |
| L1 收缩诊断 | 全部 8 阶段，diagnose 仅覆盖被标记/不确定子集（约 1/3） | 全量深度诊断 | status=completed，uncertainty 声明诊断覆盖率 |
| L2 核心判定 | inventory/scaffold/normalize/dedupe/decide/fill/final_check | 诊断阶段整体 | status=completed，decisions 仅骨架证据，diagnostics=null+说明 |
| L3 最小诚实 partial | inventory/scaffold/fill/final_check | 去重、判定、诊断 | **status=partial**；已完成计数有值，未完成字段 null+说明 |

## 2. 触发条件

**预先选档（plan_run.py）**：自 L0 起逐档试算，取第一个同时满足
`预估请求 ≤ 预算 − reserve` 且 `预估墙钟 ≤ 90% 预算` 的档位。

**运行中降级（budget_ledger.py status 信号）**：

| 信号 | 条件 | 动作 |
|---|---|---|
| ok | 剩余请求 ≥ reserve + 未完成阶段最小请求，且墙钟 < 75% | 维持当前档位 |
| warn | 剩余请求 < reserve + 未完成阶段最小请求，或墙钟 ≥ 75% | 降一级：跳过下一档被砍的阶段 |
| critical | 剩余请求 ≤ reserve，或墙钟 ≥ 90% | 直接降 L3：停止一切非必要调用，仅 fill + final_check 收尾落盘 |

**中断续跑（checkpoint.py resume-point）**：产物缺失或 sha256 不一致的阶段
及其后续阶段重跑；已完成且产物完好的阶段不重复消耗预算。

## 3. 诚实表述模板（写入 result.json）

降级或中断时，`flush_partial.py` 按以下模板生成 `uncertainty` 条目（中文，可照抄）：

- 档位声明：
  `本次运行处于降级档位 L2：预估请求超预算。缩减的范围不得以任何形式声称已完成。`
- 字段缺失：
  `字段 diagnostics 为 null：当前档位 L2 未启用 diagnose 阶段。`
- 中断 partial：
  `status=partial：运行在 decide 阶段后中断；已完成的盘点/去重计数真实有效，判定字段为 null。`
- 预算耗尽：
  `剩余模型请求触及预留线（reserve=2），按 L3 收尾：仅完成 fill 与 final_check。`
- 待复核：
  `以下记录判为 uncertain，需人工复核（本调度器不做内容判定）：R04。`

## 4. 禁止事项

- 不得把 `status` 写成 completed 而实际停在 L3 或中途；
- 不得把未执行阶段对应字段填成占位假值（如空数组冒充"判定完毕且无纳入"）——
  应填 `null` 并在 uncertainty 说明；
- 不得为省请求而静默跳过 dedupe 中的夹具重复/冲突标记，若跳过必须显式声明；
- 不得删除 output_contract 要求的任何字段；
- 不得伪造人工复核结论（冲突双人意见只能标 uncertain 留待人工）。
