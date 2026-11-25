# Deterministic fault injection

## 1. 原则

仿真回答“**若这个决策被注入该标签，控制流、成本和时间如何展开**”，不回答“实验测到了什么”。禁止把合成测量值、恢复概率或分支结局写成实测。编译器没有 `eval`/`exec`，不会计算科学信号，也不会自动选择更有利分支。

每个 spec 必须恰好有一个 `scenario_id=nominal`，可附任意故障情景。所有情景必须写 `outcome_basis="synthetic_what_if"`。`decision_outcomes` 的键是决策状态 ID，值是按该决策第 1、2、… 次访问依次消费的分支标签列表。

## 2. 最小情景 schema

```json
{
  "scenario_id": "recoverable_high_blank",
  "description": "First blank high, post-reblank blank passes; both are unmeasured injections",
  "fault_injection": {
    "target_decision": "D30_BLANK_QC",
    "type": "transient_high_blank",
    "measured": false
  },
  "outcome_basis": "synthetic_what_if",
  "decision_outcomes": {
    "D30_BLANK_QC": ["high_blank", "else"]
  }
}
```

- 标签只能是该决策的显式 `branches[].label` 或保留字 `else`。
- 每次到达决策必须尚有对应注入标签；缺失会成为 `detected_failure`，不会偷偷取 else。
- 所有决策（包括 nominal）都使用同一机制。`guard` 被复制进事件轨迹以说明规划 Predicate，但不用来计算分支。
- `fault_injection` 可描述目标与故障类型；真正驱动仿真的是 `decision_outcomes`。

## 3. 三个互补情景

假设 `D30_BLANK_QC` 有 `high_blank`, `retries_exhausted` 和 `else`：

```json
[
  {
    "scenario_id": "nominal",
    "outcome_basis": "synthetic_what_if",
    "fault_injection": null,
    "decision_outcomes": {"D30_BLANK_QC": ["else"]}
  },
  {
    "scenario_id": "recoverable_high_blank",
    "outcome_basis": "synthetic_what_if",
    "fault_injection": {"type": "transient_high_blank", "measured": false},
    "decision_outcomes": {"D30_BLANK_QC": ["high_blank", "else"]}
  },
  {
    "scenario_id": "persistent_qc_failure",
    "outcome_basis": "synthetic_what_if",
    "fault_injection": {"type": "persistent_high_blank", "measured": false},
    "decision_outcomes": {"D30_BLANK_QC": ["high_blank", "retries_exhausted"]}
  }
]
```

三者共同覆盖三个标签，只表示**注入分支覆盖**，不表示科学覆盖、故障覆盖率或实测成功率。若还有未选择的标签，`validation.json` 列出 `untested_decision_branches`，产生 warning，`result.status=partial`；不得声称 full branch coverage。

## 4. 路径与事件输出

每个 `scenario_results[]` 包含：

- `path`: 按顺序访问的状态 ID；
- `events`: `state_visit`, `decision`, `terminal` 或 `detected_failure`；
- `state_visits`: 每状态访问次数；
- `totals`: 精确 `cost`, `duration_minutes`, `state_visits`；
- `termination`: `explicit_terminal`（含 success/failure）或 `detected_failure`（含原因）。

显式 failure 终态是有效的 fail-safe 路径，不等于编译失败。相反，缺少注入、未知目标、超过状态 `max_visits` 或 `global_step_cap` 是检测到的仿真失败，使结果 partial 且 compile 返回 2。

## 5. 有界重试反例与正例

以下正例允许初次 QC 加一次重新空白后的 QC：

```json
[
  {"id":"S_MEASURE", "kind":"action", "next":"D_QC", "duration_minutes":"3", "cost":"0.20", "max_visits":2},
  {"id":"D_QC", "kind":"decision", "branches":[{"label":"repeat", "guard":{"metric":"qc", "operator":">", "threshold":"105", "unit":"%", "record":"run_log.qc"}, "next":"S_REPEAT"}], "else":"T_SUCCESS", "duration_minutes":"0", "cost":"0", "max_visits":2},
  {"id":"S_REPEAT", "kind":"action", "next":"S_MEASURE", "duration_minutes":"5", "cost":"0.50", "max_visits":1}
]
```

实际 spec 还应有可达的 `retries_exhausted → T_FAIL` 出口。故意给 `D_QC` 第三次访问会触发 `detected_failure`，不是静默截断。`global_step_cap` 是另一道保险，不能替代环内显式 `max_visits`。

## 6. 诚实包络

报告分开列示：

1. nominal 路径总量；
2. 所有已提供情景的成本/时间逐分量最大值；
3. 所有可达状态 `max_visits × cost/time` 的保守图上界；
4. 未测试分支。

不能仅根据 nominal 推断 worst case，也不能把故障情景的 failure terminal 当作已经观察到的实验失败。任何实际执行仍需方法负责人、安全负责人和资源负责人的独立确认。
