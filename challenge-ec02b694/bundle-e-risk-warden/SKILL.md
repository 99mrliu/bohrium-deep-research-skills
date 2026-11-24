---
name: risk-warden
description: 实验参数优化流水线的异常分流与诚实状态守护层。当案例可能出现约束冲突（如目标温度超过材料耐温）、数据缺失、设备报错、指标矛盾或无可行解时必须使用；在流水线启动、异常处置、交付前审计三个节点强制执行机器可判定检查，保证状态诚实、过程可复核。
---

# risk-warden — 异常处置决策与诚实状态运行契约

## 定位声明（先读）

本技能**不替 Agent 做参数搜索**：不生成候选配方、不跑贝叶斯优化、不评估实验指标。
它是包裹在任意参数优化流水线**之外**的两层过程质量控制：

1. **异常分流层**：把无可行解、约束冲突、数据缺失、设备报错、指标矛盾、权限问题
   六类异常，按显式规则矩阵映射为机器可判定的四类动作：
   `proceed / proceed_with_degradation / handoff_to_human / terminate`。
2. **诚实状态层**：强制"首份 partial 先于任何实质计算落盘"的不变量，
   交付前最终审计，绝不把未经确认的建议写成可执行事实。

Agent 的典型失败不是算错，而是：过程不可复核、失败后无法定位是数据/约束还是模型
问题、把假设当成结论。本技能把状态机与异常分流变成**强制检查**，而不是可选建议。

## 何时使用 / 何时不适用

**必须使用（触发条件）**
- 任务描述或材料中出现硬性约束（温度、压力、材质耐受、安全红线、预算上限）；
- case.json 声明的材料可能缺失或不可读；
- 多个优化目标/指标可能互相矛盾；
- 涉及真实设备、真实执行，任何"写死的建议"都可能被当作指令执行；
- 预算受限（约 64 次模型请求 / 900 秒）且要求诚实 partial 的评测环境。

**不适用**
- 纯文献综述、纯代码题，无实验参数、无约束、无可执行后果；
- Agent 需要的参数搜索算法本身（本技能不提供，去找优化算法类技能）。

## 运行契约（评测环境）

- 技能安装于 `/skills/weekly-skill`；Agent 在 `/app/work` 工作，交付写 `/app/output`。
- 输入：`/input/case.json`（`case_id`、任务描述、`output_contract` 字段清单、材料路径）、
  `/input/task.md`、案例材料。
- 交付：`/app/output/result.json` 必须含 `case_id`（照抄输入）、`output_contract`
  **全部字段**（动态读取 case.json，不得硬编码）、诚实的 `status`
  （success / partial / unable_to_determine / refused）、`sources`、`uncertainty`、
  `change_log`（变更记录）。
- 预算：约 64 次模型请求 / 900 秒 / 单次响应 16384 token。

## 固定命令顺序（不可调换）

```
python3 scripts/warden_boot.py  --case /input/case.json --output /app/output --work /app/work
#   → 首份 partial result.json + intake_manifest.json + work_plan.md（任何实质计算之前落盘）
python3 scripts/triage.py       --facts <Agent汇总的事实.json> --out /app/work/triage.json
#   → 机器可判定动作；exit 3 表示 handoff_to_human / terminate
#   …… 主体工作（仅当 triage 允许；本技能不管主体怎么做，只管异常与状态）……
python3 scripts/final_audit.py  --result /app/output/result.json --case /input/case.json
#   → audit_report.json；exit 3 表示审计失败且已强制回退 partial
```

triage 可在主体工作中**多次运行**：每当新发现约束冲突、设备报错、材料缺失，
立即重新汇总事实并重跑 triage，以最新 `final_action` 为准。

## 含预算分配的工作流程（900 秒）

| 阶段 | 建议占比 | 内容 |
|---|---|---|
| intake | ~10%（≤90 秒） | warden_boot；读 task.md；确认 intake_manifest 的缺失清单 |
| triage 初判 | ~5% | 汇总已知异常事实，跑首轮 triage |
| 主体工作 | ~55–60% | 按 triage 动作执行参数优化/降级方案/待裁决清单 |
| 收尾填充 | ~15% | 填齐 output_contract 全部字段，逐条补证据或"待确认" |
| 审计对账 | ~10–15% | final_audit；修复违例重审；核对 status/uncertainty/change_log |

**模型请求规则：剩余约 8 次模型请求时，立即停止一切改进**，无条件转入收尾填充
与 final_audit。宁可交付诚实的 partial，不可交付来不及审计的"success"。
任何实质结论一旦得出，立即增量写回 result.json（落盘优先于继续思考）。

## 输出物说明表

| 文件 | 产生者 | 内容 |
|---|---|---|
| /app/output/result.json | warden_boot 首写，Agent 增量更新 | case_id + output_contract 全部字段 + status/sources/uncertainty/change_log |
| /app/work/intake_manifest.json（并副本到 /app/output） | warden_boot | 每项材料 path/exists/size/sha256/readable/note |
| /app/work/work_plan.md | warden_boot | 六步勾选清单 |
| /app/work/triage.json | triage（可多次） | 触发规则 {rule_id, condition, evidence, action} + final_action |
| /app/output/audit_report.json | final_audit | 逐项检查（C1–C8）+ verdict + forced_partial |

## 异常处理表（机器可判定）

| 异常类别 | 判定信号 | 动作 | triage 退出码 | result.json 要求 |
|---|---|---|---|---|
| feasible | 无异常事实 | proceed | 0 | 正常推进 |
| constraint_conflict（可消解） | 冲突全部 resolvable=true | proceed_with_degradation | 0 | uncertainty 记录降级内容 |
| constraint_conflict（不可消解） | 存在 resolvable=false | handoff_to_human | 3 | status=partial + 待裁决清单 |
| missing_data（关键） | critical=true 材料缺失 | handoff_to_human | 3 | status=partial + 缺失清单 |
| missing_data（非关键） | 缺失均非关键 | proceed_with_degradation | 0 | uncertainty 记录影响 |
| metric_conflict | 指标互相矛盾 | 降级或转人工（按 critical） | 0/3 | 矛盾双方并列呈现，不擅自取舍 |
| device_error | 可恢复 / fatal | 降级 / terminate | 0/3 | terminate 时写明理由 |
| infeasible_constraints | 无可行解 | terminate | 3 | status=unable_to_determine + 理由 |
| permission_issue | 权限不足 | handoff_to_human | 3 | status=partial |

详见 references/failure-modes.md（含"目标温度 vs 材料耐温"处理先例）与
references/status-taxonomy.md（状态判据与转移规则）。

## result.json 契约

```json
{
  "case_id": "<照抄 case.json>",
  "status": "success | partial | unable_to_determine | refused",
  "partial_reason": "<status 非 success 时必填，写明诚实原因>",
  "<output_contract 字段 1>": "...动态读取 case.json，逐一填齐...",
  "sources": ["..."],
  "uncertainty": [{"kind": "...", "detail": "...", "impact": "..."}],
  "change_log": [{"ts": "...", "event": "...", "detail": "..."}]
}
```

- 占位约定：warden_boot 以 `{"_placeholder": true, ...}` 占位；final_audit 递归扫描，
  任何占位残留（含 null、TODO、TBD、待填写）都视为违例并强制回退 partial。
- 每条推荐参数值（含 `value` 与 `param`/`name`/`parameter` 的条目）必须带
  `evidence`/`evidence_ref`/`source` 之一，或显式 `"confirmed": false` 或标注"待确认"。
- 存在 `"assumption": true` 的条目时，`confirmation_items`（或契约对应字段）必须非空。

## 合成示例

examples/synthetic-input/ 含一个合成 case（焙烧工艺优化）：材料中故意包含
"目标焙烧温度 1000°C vs 材料耐温上限 950°C"的冲突事实，以及一个不存在的材料路径。
examples/synthetic-output/ 是真实端到端运行产物：首份 partial、triage 命中
constraint_conflict + missing_data → handoff_to_human（exit 3）、修复后
proceed（exit 0）、final_audit 通过（exit 0）、占位残留负例被强制 partial
（exit 3）。复现命令见 examples/README.md。

## 局限

- 规则矩阵是显式启发式，`critical`/`resolvable`/`severity` 的标注质量取决于
  Agent 汇总事实时的判断；本技能保证"标注一旦给出，分流必然一致、可复核"，
  不保证标注本身正确。
- final_audit 的证据检查是结构性的（是否存在证据引用），不能验证证据内容真实支持结论。
- 不处理主体优化算法本身的正确性；triage 说 proceed 不代表参数建议是对的。
- 全部脚本仅用 Python 3 标准库、无网络；极端损坏输入下保证不崩溃、尽力落盘，
  但不保证输出目录本身不可写时仍能落盘（会退而求其次写到当前目录并告警）。
