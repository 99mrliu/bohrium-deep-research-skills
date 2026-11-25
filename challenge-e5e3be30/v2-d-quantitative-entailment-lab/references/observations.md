# Observation、claim target 与 Agent verdict 格式

## 1. Source-linked observations

下面只是 **SYNTHETIC** 结构示例，不是实际论文：

```json
{
  "synthetic": true,
  "observations": [
    {
      "id": "obs_A", "synthetic": true, "kind": "proportion",
      "events": 70, "n": 100, "unit": "participants",
      "source_id": "paper", "location": {"section":"Results","table":1},
      "quote": "SYNTHETIC: 70 successes among 100 participants."
    },
    {
      "id": "obs_B", "synthetic": true, "kind": "proportion",
      "events": 60, "n": 120, "unit": "participants",
      "source_id": "paper", "location": {"section":"Results","table":1},
      "quote": "SYNTHETIC: 60 successes among 120 participants.",
      "reported_display": {"value":60,"unit":"percent",
        "quote":"SYNTHETIC: displayed control rate 60%."}
    },
    {
      "id": "obs_time", "synthetic": true, "kind": "mean",
      "mean":2500,"sd":300,"n":12,"unit":"ms",
      "source_id":"paper","location":{"section":"Outcomes","paragraph":4},
      "quote":"SYNTHETIC: mean 2500 ms, SD 300 ms, n 12."
    }
  ]
}
```

ID 必须唯一。quote、source_id、location 必须齐全。raw 与 display 可以是同一 observation 的两层记录，或像完整示例那样为 display treatment 设置单独 observation；关键是两者各自有 quote、ID 可追踪且冲突不丢失。比例 observation 的 `events` 必须为整数而非 70.0；均值观测的 mean/sd 可以是有限实数。

不允许把 `n=null` 补成“看起来合理的100”，不允许由 rounded percent 倒推出并未报告的 events/n，也不允许让模型生成 quote。不确定或不可读部分应在 uncertainty 中精确限定，相关 claim 保持 null/insufficient，而不是强行计算。

## 2. Claims 是问题

每项至少有：

```json
{
  "id":"Q1", "question":"SYNTHETIC: Does 70/100 versus 60/120 give 20 percentage points?",
  "metric":"percentage_point_difference", "basis":"raw_counts",
  "source_ids":["obs_A","obs_B"],
  "target":{"value":20,"unit":"percentage_point"},
  "tolerance":{"absolute":1e-9,"relative":0}
}
```

复合问题用 `components:[...]`，每个 component 独立有 metric/basis/source_ids/target/tolerance。`source_ids` 的顺序即第一组/第二组。`basis=raw_counts` 使用 events/n；`basis=reported_display` 使用单独 quote 的表观值，不会用于 z 检验。

可用 metrics 见 methods.md。`unit_conversion` 要求一个 kind=mean 的 source id 和 `target.unit`，对其 mean 做明确量纲换算；sd 和 n 保留但不参与换算。

如果 claim 问“原文是否报告精确 p”，用 `metric=two_proportion_p_value` 和 `target_origin=source_reported`。脚本会从 raw counts 给 normal-approximation p 作为并列派生证据，但不会把“可计算”偷换成“原文报告过”，也不会因 target 不匹配自动反驳。

## 3. 派生记录

每个 component 输出：

```json
{
  "id":"derived_Q1_1", "claim_id":"Q1", "role":"derived",
  "metric":"percentage_point_difference", "basis":"raw_counts",
  "source_ids":["obs_A","obs_B"],
  "formula":"100*(p1-p0)", "substitution":"100*(70/100 - 60/120)",
  "value":19.999999999999996, "unit":"percentage_point",
  "verdict":null,
  "comparison":{"within_tolerance":true}
}
```

`derived` 记录里的 `verdict:null` 不是“未知真值”的四级裁决，而是刻意禁止脚本自动裁决。派生检验 ID 形如 `ztest_obs_A_obs_B`，可在 Agent verdict 的 evidence_ids 引用。

## 4. Agent 裁决文件

```json
{
  "adjudicator":"agent",
  "verdicts":[{
    "claim_id":"Q1", "verdict":"supported",
    "rationale":"SYNTHETIC: 原文方向/分母与20pp目标一致；计算在容差内。",
    "evidence_ids":["derived_Q1_1","ztest_obs_A_obs_B"],
    "source_ids":["obs_A","obs_B"]
  }]
}
```

四级取值只能是 `supported`、`partially_supported`、`contradicted`、`insufficient_evidence`。每个 claim 恰好一项；claim ID 缺失、额外、重复、无 rationale、错误 evidence ID 或没有 `adjudicator=agent` 都拒绝合并。

- 复合命题只有一部分匹配：Agent 可考虑 `partially_supported`，并在 rationale 指出具体子项。
- 仅主题相关而没有目标证据：不能 supported。
- 原文未报告：通常 `insufficient_evidence`，而非 contradicted。
- 两个来源都能定位但数值冲突：并列记录各自来源和派生结果，不选择性删除。
- 非显著：不能写成“效应为零”；若有目标为非零的命题，Agent 仍应按估计值、区间、问题和证据决定。

## 5. 完整示例定位

`examples/minimal/paper.md` → `observations.json` + `claims-to-verify.json` → `output/quantitative-report.json` + `effect-plot.svg` → `agent-verdicts.json` → `output/result.json`。全链路每个示例和数值均为 **SYNTHETIC**。
