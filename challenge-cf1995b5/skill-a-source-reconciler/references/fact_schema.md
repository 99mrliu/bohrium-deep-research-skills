# facts.json 结构契约（fact_schema）

`scripts/case_reconcile.py extract` 的输出。事实登记表是后续对账与方案写作的唯一事实来源。

## 顶层结构

```json
{
  "case_id": "MOCK-...",
  "generated_by": "scripts/case_reconcile.py extract",
  "fact_count": 138,
  "partial": false,
  "errors": [],
  "facts": [ /* Fact, ... */ ],
  "equipment_table": [ /* EquipmentEntry, ... */ ]
}
```

- `partial: true` 表示 case.json 读取失败或结构残缺，此时 `facts` 可能为空，`errors` 给出原因；
  脚本仍以 exit 0 结束，下游按 partial 流程降级。

## Fact

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | `F001` 起单调编号，方案中以此引用（如 `[F023]`） |
| `value` | any | 事实值（标量 / 列表 / dict 原样） |
| `unit` | string\|null | 单位（如 `CNY/h`、`day`、`C`）；无量纲为 null |
| `jsonpath` | string | case.json 内定位路径，如 `resource_contract.equipment[0].price_per_hour`；文本内嵌补充用 `equipment_domain_note~embedded[0].price_per_hour` |
| `source_class` | enum | 见下表 |
| `note` | string | 补充说明（如"前瞻约定价，非已确认报价"） |

### source_class 枚举

| 值 | 含义 | 信任级别 |
|---|---|---|
| `case_meta` | case_id/title/task/research_goal/output_contract 等元信息 | 任务定义 |
| `contract` | resource_contract 内的预算、周期、设备、试剂、预约参数 | 前瞻约定，约束性事实 |
| `parameter_domain` | parameter_domains 的 range/enum/step/basis/source | 有限参数域，约束性事实 |
| `candidate_claim` | candidate_plans 宣称的参数、成本、周期 | **不可信**，须经 reconcile 验证后才可用 |
| `literature` | source.paper_pdf/citation/key_claim | 需 pdfscan 佐证；无 PDF 时仅可引 key_claim |
| `text_embedded` | equipment_domain_note 等文本中解析出的内嵌 dict 字段 | 与 contract 同等参与对账，但需注明来源 |
| `inferred` | 由脚本/Agent 推导的量 | 必须能给出推导算式 |

## EquipmentEntry（统一设备表）

```json
{"id": "EQ-HP", "name": "精密加热台", "model": "...", "spec": "...",
 "price_per_hour": 30, "booking": {...},
 "origin": "contract | text_embedded", "jsonpath": "..."}
```

- `origin=contract`：来自 `resource_contract.equipment[]`；
- `origin=text_embedded`：来自 `equipment_domain_note` 文本中内嵌的 JSON/dict 片段
  （extract 用平衡花括号扫描 + json/ast 双解析器抽取；解析失败的片段不会出现，需人工复读原文）。
- 对账（C 类检查）与方案写作的设备清单**以此表为准**，不得只读 `equipment` 列表。

## 文本内嵌解析规则

1. 扫描 `equipment_domain_note`（及未来同义字段）的全部平衡 `{...}` 片段；
2. 依次尝试 `json.loads` 与 `ast.literal_eval`（兼容单引号 python dict 写法）；
3. 含 `id` 或 `name` 键的 dict 登记为设备，进入 equipment_table；
4. 其全部标量/嵌套字段逐条登记为 `text_embedded` 事实，jsonpath 用 `~embedded[j]` 记号，
   与真实 JSON 路径区分（该路径在 case.json 文本字段内，不是结构化键路径）。
