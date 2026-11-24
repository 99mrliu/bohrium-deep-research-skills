# constraint-schema.md — domain.json / proposal / audit_report / conflicts 字段规范

面向运行契约：评测方以官方 DeepSeek Harness 在固定案例上运行加载本技能的 Agent；
Agent 在 `/app/work` 工作、结果写 `/app/output`；本文件定义三个脚本之间流转的
全部 JSON  schema（schema_version 均为 `"1.0"`）。所有脚本仅用 Python 3 标准库、
无网络，任何输入不得 traceback 崩溃。

## 1. domain.json（extract_domain.py 产物）

```json
{
  "schema_version": "1.0",
  "generated_by": "extract_domain.py",
  "source_case": "/input/case.json",
  "case_id": "照抄 case.json（若可读）",
  "targets": {"参数名": 1200.0},
  "constraints": [ /* 见第 2 节 */ ],
  "ungrounded_parameters": ["任务提及但无任何约束依据的参数名"],
  "uncertainty": ["人类可读的诚实声明，播种自 ungrounded/空可行域等"],
  "extraction_log": {
    "files_scanned": ["..."],
    "files_skipped": [{"path": "...", "reason": "..."}],
    "errors": ["..."],
    "warnings": ["..."],
    "constraints_extracted": 8
  }
}
```

- `targets`：来自 case.json 的 `targets` / `target_values` / `objectives`（dict 形态，
  值可转 float 才收录）。无则为 `{}`。
- `ungrounded_parameters`：来自 case.json 的 `parameters` / `expected_parameters` /
  `parameters_of_interest` 中、在 constraints 里找不到（规范化名匹配）的条目。
  **绝不编造数值**，仅列名并播种 uncertainty。
- 脚本失败（case.json 不可读、材料缺失等）时仍落盘：errors/warnings 记录原因，
  exit 0；仅输出路径不可写时 exit 1。

## 2. constraint（约束条目）

```json
{
  "parameter": "载气流量",
  "unit": "mL/min",
  "lower": 10.0,
  "upper": 500.0,
  "step": null,
  "mutex_group": null,
  "safety_related": false,
  "origin": "text | case_explicit",
  "source": {"file": "相对路径", "line": 4, "quote": "原文整行（≤300 字符）"}
}
```

- `lower`/`upper`/`step`：数值或 `null`（开放端）。`unit` 做最小归一
  （℃→°C、ml/min→mL/min、r/min→rpm），**不做量纲换算**。
- `mutex_group`：字符串组名或 null。语义：同组成员不得在方案中**同时被赋非空值**。
- `safety_related`：quote 含 耐温/安全/危险/失活/爆炸/safety/hazard 时为 true；
  影响 conflict_scan 中 target_outside_domain 的 recommended_action（true→terminate）。
- `source`：**每条约束必须有证据定位**。case.json 显式字段的 line 为 null，
  quote 为该字段的 JSON 片段。
- 同名参数可出现多条（多来源）；审计/冲突扫描按"最紧合并"：
  `lower=max(lowers)`、`upper=min(uppers)`、step 取全部非空值且须同时满足。

### case.json 显式字段识别

- 约束：`parameter_domains` / `constraints` / `domain` / `parameter_constraints`，
  支持 dict（参数名→{min/max/lower/upper/unit/step/mutex_group}）与
  list（[{parameter, ...}]）两种形态。
- 目标：`targets` / `target_values` / `objectives`。
- 提及：`parameters` / `expected_parameters` / `parameters_of_interest`。

## 3. proposal.json（Agent 起草，domain_audit.py 输入）

```json
{
  "case_id": "可带",
  "parameters": {
    "温度": 800,
    "焙烧时间": {"value": 120},
    "载气流量": [100, 300],
    "升温速率": {"range": [3, 8]}
  }
}
```

- `parameters` 缺省时按扁平 dict 处理（忽略 case_id/status/notes/sources/
  uncertainty/change_log/gate/schema_version 等元键）。
- 值四种形态：数值 / `{"value": v}` / `[lo, hi]` / `{"range": [lo, hi]}`
  （`{"min": a, "max": b}` 也接受）。区间形态两端点都须过检。
- 无法解析出任何数值 → 该参数判 violation（check=parse）。

## 4. audit_report.json（domain_audit.py 产物）

```json
{
  "schema_version": "1.0",
  "domain_file": "...", "proposal_file": "...",
  "results": [
    {
      "parameter": "温度",
      "proposed": 1200,
      "verdict": "pass | violation | ungrounded",
      "checks": [
        {"check": "upper_bound", "passed": false,
         "detail": "1200.0 > 上限 1100.0 °C",
         "evidence": {"file": "...", "line": 3, "quote": "..."}}
      ]
    }
  ],
  "summary": {"total": 4, "pass": 1, "violation": 2, "ungrounded": 1},
  "status": "pass | fail"
}
```

判定规则（逐参数）：
1. **grounded**：参数（规范化名：去空白/下划线、小写）必须存在于 domain；
   不存在 → verdict=ungrounded，**按违规处理**，evidence=null。
2. **lower_bound / upper_bound**：对每个建议值（区间两端点）核验合并界限；
   证据取提供生效（最紧）界限的那条约束的 source。
3. **step**：以 lower（无则 0）为基准，`(v-base)/step` 须为整数（容差 1e-9）；
   多个 step 依据须同时满足。
4. **mutex**：同一 mutex_group ≥2 个成员被赋非空值 → 全部判 violation。

退出码：`status=pass` → **exit 0**；任一 violation/ungrounded → **exit 3**；
输入文件不可读 → 仍写出 fail 报告并 exit 3；输出不可写 → exit 1。

## 5. conflicts.json（conflict_scan.py 产物）

```json
{
  "schema_version": "1.0",
  "domain_file": "...",
  "status": "ok | conflicts_found | error",
  "summary": {"conflict_count": 3,
              "by_action": {"degrade": 1, "handoff": 2, "terminate": 0}},
  "conflicts": [
    {"type": "inverted_bounds", "parameters": ["载气流量"],
     "detail": "单条约束 lower(500.0) > upper(10.0)",
     "evidence": {"file": "...", "line": null, "quote": "..."},
     "recommended_action": "handoff"}
  ]
}
```

检查项与动作映射：

| type | 含义 | recommended_action |
|---|---|---|
| inverted_bounds | 单条约束 lower > upper | handoff |
| effective_bounds_inverted | 多来源合并后 max(lower) > min(upper)，可行域为空 | handoff |
| target_outside_domain | 目标值越出合并可行域；约束 safety_related 时升级 | degrade / terminate（安全相关） |
| ungrounded_target | 目标参数在 domain 中无依据 | handoff |
| invalid_step | step ≤ 0 或区间内无可达格点 | handoff |
| mutex_degenerate | 互斥组仅 1 个成员 | degrade |
| mutex_unsatisfiable | 互斥组 ≥2 个成员被固定为单点值 | handoff |

动作语义：`degrade`=以约束界限替代并在 uncertainty 显式声明；
`handoff`=列入 result.json 的确认项（如 confirmation_items）请求人工裁决；
`terminate`=停止相关推荐，status 不得为 success。

退出码：无冲突 → **exit 0**；有冲突 → **exit 3**；domain 不可读 → exit 1（仍落盘 error 报告）。

## 6. 健壮性契约（三个脚本共用）

- 任意输入（缺失文件、坏 JSON、二进制冒充文本、空材料、非 dict 顶层）不得
  traceback；stderr 给出一行简明诊断，stdout 不变。
- 输出目录不存在时自动创建；输出不可写时 stderr 报错并 exit 1。
- 文本读取按 utf-8 → gb18030 → latin-1 回退，最终 errors=replace。
