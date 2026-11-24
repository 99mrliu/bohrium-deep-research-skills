# failure-modes.md — 异常分类法与分流动作矩阵

本文是 triage.py 规则矩阵的设计依据与判例库。每条异常必须落到唯一类别与唯一动作，
分流结果可复核、可重放。

## 一、六类异常分类法

| 类别 | 定义 | 典型信号 |
|---|---|---|
| feasible | 无可判定异常 | 事实清单为空 |
| infeasible_constraints | 约束集合无可行解（无论怎么调参都不可行） | 可行域为空、两个硬约束在数学上互斥 |
| constraint_conflict | 目标与硬约束冲突，或约束之间冲突，但存在（或不存在的）消解路径 | 目标温度 > 材料耐温；产率目标与纯度目标在同一参数上反向 |
| missing_data | 决策所依据的材料/数据缺失或不可读 | case.json 声明的材料路径不存在；关键表征报告损坏 |
| metric_conflict | 多个评价指标互相矛盾，无法同时最优 | 指标 A 最优的参数使指标 B 越红线 |
| device_error | 执行/测量设备报错 | 炉温漂移报警、传感器离线、控制软件返回错误码 |
| permission_issue | 缺少执行或读取权限 | 设备预约未获批、数据目录无读权限 |

## 二、分流动作矩阵（与 triage.py 一一对应）

| 规则 | 条件 | 动作 | 理由 |
|---|---|---|---|
| R_PERM_01 | 任何权限问题 | handoff_to_human | 权限只能由人授予，Agent 不得绕过 |
| R_DEV_01 | 设备 fatal 报错 | terminate | 继续执行有安全/损坏风险 |
| R_DEV_02 | 设备可恢复报错 | proceed_with_degradation | 用备用测量/降低精度继续，并记录 |
| R_INF_01 | 无可行解 | terminate | 不存在可交付的方案，硬撑只会编造 |
| R_CON_01 | 冲突 resolvable=false | handoff_to_human | 消解意味着改变既定目标，目标属于委托人 |
| R_CON_02 | 冲突全部 resolvable=true | proceed_with_degradation | 在约束内降级可满足，记录降级即可 |
| R_MIS_01 | 关键材料缺失 | handoff_to_human | 关键依据缺席时任何结论都是猜测 |
| R_MIS_02 | 非关键材料缺失 | proceed_with_degradation | 降级继续，uncertainty 标注影响 |
| R_MET_01 | 关键指标矛盾 | handoff_to_human | 指标取舍是价值判断，须人裁决 |
| R_MET_02 | 非关键指标矛盾 | proceed_with_degradation | 并列呈现矛盾双方，不擅自取舍 |
| R_OK_01 | 未命中任何规则 | proceed | — |

优先级：terminate > handoff_to_human > proceed_with_degradation > proceed。
多规则同时命中时取最高优先级动作，全部命中规则均写入 triage.json 供复核。

## 三、典型冲突处理先例

### 先例 P1：目标焙烧温度 1000°C vs 材料耐温上限 950°C（本 bundle 合成示例原型）

- **事实**：任务简报要求 1000°C 焙烧；材料规格书给出耐温上限 950°C。
- **分类**：constraint_conflict。
- **resolvable 判定**：若把温度降到 ≤950°C 仍可得到（较差的）产物，则物理上可行，
  但"1000°C"是委托人设定的目标，擅自降标等于替委托人改目标 → **resolvable=false**。
- **动作**：handoff_to_human。交付 partial，待裁决事项写明：
  (a) 接受 ≤950°C 的降级方案及其性能损失估计；
  (b) 更换耐温更高的材料；
  (c) 委托人确认修改目标。
- **反例（禁止）**：直接输出"焙烧温度 950°C"并声称 success——这是把假设当成结论。

### 先例 P2：历史实验数据文件缺失，但材料规格与简报齐全

- **分类**：missing_data。若历史数据仅用于加速搜索而非可行性判定 → critical=false。
- **动作**：proceed_with_degradation；uncertainty 记录"无先验数据，搜索轮次与置信度下降"。

### 先例 P3：产率指标与能耗指标互相矛盾

- **分类**：metric_conflict。若合同只以产率为验收指标、能耗为参考 → 非关键，
  proceed_with_degradation，并列呈现两者；若两者同为验收硬指标 → handoff_to_human。

### 先例 P4：马弗炉温控模块 fatal 报错

- **分类**：device_error(severity=fatal) → terminate。写明终止理由，
  status=unable_to_determine，禁止给出"基于假设设备正常"的参数建议。

## 四、给 Agent 的事实汇总要求

triage 的判定质量取决于事实 JSON 的质量。汇总时必须：
1. 每条异常附 evidence（材料路径 + 原文摘录或 sha256 引用），禁止无证据断言；
2. critical/resolvable/severity 只能取布尔或规定枚举，拿不准时按更严处理
   （critical=true、resolvable=false、severity=fatal）；
3. 新异常出现立即重跑 triage，以最新 final_action 为准。
