# Protocol statechart contract v1.0

本契约定稿的是**下游可执行过程控制**，不是 FMEA 表、预约日历或通用文书模板。agent 只编写一个 `protocol_spec.json`；编译器负责图验证、Decimal 审计、情景仿真和所有输出。

## 1. 输入路径与 organizer canonical case

运行时默认读取真实 `/input/case.json`、`/input/task.md`，材料发现根为 `/input`，所以直接放在 `/input` 和 `/input/materials/` 下的 PDF/文本均会发现。精确 case/task 路径从材料清单排除，只作任务来源而不作外部科学证据。文本材料实际读取；PDF 仅在系统已有 `pdftotext` 时抽取，否则明确记录限制。CLI 参数可替换路径以便本地示例运行。

```json
{
  "case_id": "case-001",
  "source": "organizer",
  "task": "Revise and compile the experimental plan",
  "research_goal": "Case-specific scientific goal",
  "resource_contract": {
    "disclaimer": "Planning resources are not reservations",
    "currency": "CNY",
    "budget_cap": "80",
    "deadline_days": "1",
    "equipment": [{"id":"EQ1","name":"instrument","model":"M","spec":"S","price_per_hour":"2","booking":{"window_days":1,"slots_per_week":5,"slot_hours":1}}],
    "reagents": [{"id":"MAT1","name":"reagent","spec":"S","unit_price":"5","unit":"lot","pack_size":"1"}]
  },
  "equipment_domain_note": "Extra device: {\"equipment\":[{\"id\":\"EQ_NOTE\",\"name\":\"note-only instrument\"}]}",
  "parameter_domains": {
    "reaction_temperature": {"type":"range","min":"20","max":"40","step":"5","unit":"degC"},
    "sample_matrix": {"type":"enum","values":["freshwater"]}
  },
  "candidate_plans": [{
    "version": "C1",
    "summary": "candidate",
    "parameters": {"reaction_temperature":"30","sample_matrix":"freshwater"},
    "cost_items": [{"item":"reagent","unit_price":"10","quantity":"1","subtotal":"10"}],
    "total_cost": "10",
    "est_days": "0.25"
  }],
  "output_contract": {"required_fields":["case_id","revised_plan","candidate_assessment","validation","status","uncertainty","sources","change_log","confirmation_items"]}
}
```

- canonical 数值域为 `type=range` + `min/max/step`，分类域为 `type=enum` + `values`；兼容 `decimal/number/integer` 与 `categorical/category/allowed`。所有数值计算使用 `Decimal`。
- 候选 ID 依次接受 `version/id/candidate_id`。成本条目接受 canonical `unit_price*quantity` 或旧 `amount`，并核对每条声明的 `subtotal` 以及候选 `total_cost/claimed_total_cost/cost_subtotal`。缺字段/坏字段进入该候选的 `errors`，不让其他候选审计崩溃。
- canonical `est_days` 对 `resource_contract.deadline_days` 审核，重算成本对 `budget_cap` 审核；候选天数保持天数单位。旧 `duration_items.minutes` 只用于旧分钟别名，不从 est_days 编造分钟。
- 资源注册表合并 `resource_contract.equipment/reagents` 与可选 `resources`，并用 `JSONDecoder.raw_decode` 抽取 `equipment_domain_note` 文本中的一个或多个 JSON object。条目按 ID 去重，冲突显式报告；note-only 设备可使用。合同存在时，spec 中未知 equipment/material ID 必须 FAIL。
- `required_fields` 也可以是 `[{"name":"..."}]` 或字段名到定义的映射。已知动态字段获得真实内容；未知字段获得 `{"partial":true,...}`，并使 `result.status=partial`。

## 2. `protocol_spec.json` 顶层结构

```json
{
  "schema_version": "1.0",
  "protocol_id": "PROTO-01",
  "title": "Protocol title",
  "outcome_status": "hypothetical_unmeasured",
  "parameters": {"reaction_temperature": "30", "sample_matrix": "freshwater"},
  "scientific_plan": {
    "hypotheses": [{"id": "H1", "statement": "falsifiable claim", "falsification": "observable rejection condition"}],
    "variables": {"independent": [], "dependent": [], "controlled": []},
    "controls": [{"id": "CTRL1", "purpose": "calibration blank", "procedure_states": ["S_BLANK"]}],
    "acceptance_criteria": [{"metric": "qc_recovery", "operator": "<=", "threshold": "105", "unit": "%", "record": "run_log.qc.recovery"}],
    "risk_and_revisions": [{"risk": "persistent QC failure", "revision": "stop at T_FAIL"}],
    "planning_evidence": [{"claim": "planning assumption", "source_type": "synthetic_planning_assumption", "measured": false}]
  },
  "resources": {
    "equipment": [{"id": "EQ1", "name": "instrument"}, {"id": "EQ_NOTE", "name": "note-only instrument"}],
    "materials": [{"id": "MAT1", "name": "reagent", "quantity": "1", "unit": "lot", "cost": "5.00"}]
  },
  "candidate_revisions": [{"candidate_id":"C1","action":"revise","changes":[{"field":"total_cost","from":"9","to":"10"}],"reason":"exact arithmetic correction"}],
  "uncertainty": [{"topic":"booking","statement":"calendar availability is unknown"}],
  "change_log": [{"action":"selected_bounded_graph"}],
  "confirmation_items": [{"owner":"resource_owner","item":"confirm booking/calendar duration"}],
  "settings": {"global_step_cap": 40, "cost_accounting": "sum visited state.cost only"},
  "states": [],
  "scenarios": []
}
```

所有六个 `scientific_plan` 区块必须非空；假设必须有 `statement` 和 `falsification`。完整实验计划还应把变量、控制、材料、验收、风险/修订写具体。编译器要求这些区块存在，但不把机器检查伪装为科学同行评审。未由 case 或材料提供的方法参数不得臆造；将待确认项写入 `confirmation_items`。

顶层 `candidate_revisions/uncertainty/change_log/confirmation_items` 可省略，也可为数组或单个对象。编译后作者条目与编译器默认条目合并，不被丢弃；候选修订还链接到对应 `candidate_assessment[].revision_records` 和 `revised_plan.candidate_revisions`。`sources` 同时包含输入哈希和 `scientific_plan.planning_evidence`，保留 `source_locator/locator/citation/url/doi/path/source` 等已有定位信息；agent-authored spec 本身明确不是科学证明。

`parameters` 和每个状态的 `parameters` 中的名称必须存在 case 域，值必须通过 Decimal 范围/步进或分类检查。资源 ID 必须唯一；状态引用的设备/材料必须预先声明。

### 成本口径

每个状态的 `cost` 是该次访问的**全部增量成本**，`duration_minutes` 是该次访问的持续时间，两者均为有限、非负 Decimal。路径成本/时间只按实际访问状态求和。资源对象的 `cost` 仅是分摊说明，不会再次相加。不要把资源成本同时无说明地计入多个状态。

## 3. 状态与转移

| kind | 必需字段 | 转移要求 |
|---|---|---|
| `start` | `id`, `duration_minutes`, `cost`, `next` | 全图恰好一个；一个 `next` |
| `action` | `id`, `duration_minutes`, `cost`, `next` | 一个 `next`；可绑定 `equipment`, `materials`, `parameters`, `record` |
| `decision` | `id`, `duration_minutes`, `cost`, `branches`, `else` | 至少一个显式分支，且必须有非空 `else` 目标 |
| `terminal` | `id`, `outcome`, `duration_minutes`, `cost` | `outcome=success|failure`；不得有出边 |

所有状态 ID 唯一；所有目标存在；所有状态均由 start 可达；至少一个 success 和一个 failure 终态可达。`max_visits` 为整数且至少为 1（缺省为 1），但**每个有环 SCC 中的每个状态都必须显式写出 `max_visits`**。每个有环 SCC 必须有通向 SCC 外的边。结合 `global_step_cap`，仿真具备双重硬终止约束。

### 可观测 guard 与决策分支

```json
{
  "id": "D_QC",
  "kind": "decision",
  "duration_minutes": "0",
  "cost": "0",
  "max_visits": 2,
  "branches": [
    {
      "label": "high_blank",
      "guard": {
        "metric": "calibration_blank_recovery_percent",
        "operator": ">",
        "threshold": "105",
        "unit": "%",
        "record": "run_log.blank_qc.recovery_percent"
      },
      "next": "S_REBLANK"
    }
  ],
  "else": "S_CALIBRATE"
}
```

- 每个非 else 分支都有唯一 `label` 和完整 `guard`；`else` 是保留标签，不可重复用作显式分支名。
- guard 必须包含非空 `metric/operator/threshold/unit/record`；操作符仅限 `<`, `<=`, `>`, `>=`, `==`, `!=`。
- `record` 是现实执行时的观测记录位置。仿真**不求值 guard**，只选择情景注入的标签；guard 与分支均为规划假设。
- 一个 `else/default` 是显式控制流出口，不是“缺数据也默认成功”的许可。现实观测缺失时，作者应增加可观测的失败分支或 fail-safe 决策。

## 4. 验证与输出

`compile` 写出 `plan.json`, `plan.md`, `result.json`, `validation.json`, `simulation.json`, `statechart.svg`（UTF-8 XML 文本）和 `path_report.md`。验证记录每项检查，不隐藏错误：

- ID/start/出边/else/目标/可达性/终态；
- guard 可观测性、科学区块、资源绑定、参数有限域；
- 有环 SCC 的出口和显式访问界；
- 每情景终止、全局步数/状态访问越界；
- 分支覆盖缺口、每路径成本/时间、nominal/已给情景/保守图上界及预算期限。

保守上界为 `sum(reachable state.max_visits * state cost/duration)`。它可包含互斥终态，因此是安全但可能宽松的上界，不声称是一条可达路径。已给情景最大值与图上界分别报告。canonical 成本/货币取 `resource_contract.budget_cap/currency`；`deadline_days` 审核用 `graph_minutes / 1440`，同时输出原分钟、换算天数、明确换算式和 `booking/calendar time may be longer; confirmation required`。这只是 elapsed-time 对比，不冒充预约日程。旧 `budget.deadline_minutes` 保留为分钟别名。

退出语义：

| exit | 含义 |
|---:|---|
| 0 | 命令完成；仍须查看 `result.status`，未知合同字段或覆盖缺口可为 `partial` |
| 2 | 输入缺失/不可读或验证/仿真失败；`result.status=partial|blocked`，绝不是假 complete |

`complete` 只表示规划文档和机器可检仿真完整，不表示科学有效性、安全性、实测成功或正式测评通过。成本、期限均为前瞻规划值，不是报价、预约或批准。
