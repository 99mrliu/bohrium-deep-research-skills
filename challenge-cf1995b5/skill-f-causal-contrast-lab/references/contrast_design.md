# 因果对照设计规范

本规范针对“方案是否能让不同机制产生可区分预测”，不是通用六段式评分表。最终只需提交一个 `design_spec.json` 给 compile。

## 一、先建立可识别性链

每个科学主张至少经过下列链条：

```text
假设H：机制陈述
  ├─ prediction：若H成立，哪些条件在何读数上出现何方向差异？
  ├─ falsification：什么预先可观察结果使H未获支持或不可接受？
  └─ 竞争解释A：不采用H时，还有什么过程能产生同一表观现象？
        └─ 对照C：哪个条件使H与A产生不同预测？
             ├─ excluded_alternative：C实际排除/削弱什么？
             ├─ threat：C自身的局限、伪迹和执行威胁是什么？
             └─ hypothesis_ids：C映射到哪些H，不能悬空？
                   └─ 主要读数R：direction / metric / unit
                        ├─ criterion：前瞻性数值或方向判据
                        ├─ decision_rule：支持/不支持/不可判定的下一步
                        └─ evidence：追溯实际case/材料，不伪造文献
```

对照的价值来自竞争假设在同一对照下产生**不同**预测。不是越多孔越好；无关联假设的对照会被 FAIL。对照“较完整”也不等于机制唯一确定。

### 一个合成酶抑制例子

| 对照 | 条件 | 主要排除/削弱 | 无法单独证明 |
|---|---|---|---|
| vehicle | 同酶/底物/载体，不加X | 载体、位置、区组漂移 | X的直接结合 |
| no-enzyme | 同底物和各X浓度，以缓冲液替酶 | 非酶催化、底物自发变化 | X是否与酶直接作用 |
| known-inhibitor | 已知阳性窗口的K | 系统失灵导致假阴性 | X与K同机制 |
| compound-only fluorescence | 无酶无底物、各X浓度 | X自身荧光/淬灭/散射背景 | 校正后的抑制一定为直接抑制 |
| detergent counter-screen | 同区组配对±低浓度洗涤剂 | 洗涤剂敏感的聚集相关抑制 | 聚集的超微结构或直接证据 |

## 二、`design_spec.json` 精确字段

根对象字段：

```text
schema_version, case_id, design_summary,
hypotheses[], variables[], controls[], readouts[],
replication{}, parameters{}, resources[], steps[],
costs[], total_cost, time_contract{}, schedule{}, evidence[], risks[],
revision{}, uncertainty[], change_log[], confirmation_items[]
```

`case_id` 必须等于实际case。compile不信任示例中的case_id或任何输入标签。

### hypotheses[]

每项必填：

```json
{"id":"H1","statement":"机制主张","prediction":"条件可观察预测","falsification":"可观察的失败标准"}
```

不要把“证明X直接结合”写成由荧光初速实验即可独立完成的结论。能力边界要进入不确定性。

### variables[]

独立变量和因变量都必填：

```json
{
  "id":"IV1", "kind":"independent", "name":"浓度",
  "operational_definition":"反应开始时的孔内标称终浓度",
  "unit":"µM", "measurement":"由母液和加样体积核算",
  "allowed_levels":[0.1,1,10],
  "level_source":"case_json:$.parameter_domains.compound_uM"
}
```

因变量 `kind=dependent` 同样要求这些字段。没有实测前数值范围时：

```json
"allowed_levels":["实测前不设数值范围；仅接受通过锁定的QC与固定分析窗口的孔级观测"]
```

不要把列表写成说明字符串，也不要填0假装已知实测值。

### controls[]

```json
{
  "id":"C_NO_ENZYME", "name":"无酶对照", "control_type":"no_enzyme",
  "condition":"完整梯度匹配，以缓冲液替酶",
  "excluded_alternative":"非酶催化/底物背景",
  "threat":"缺少某浓度的匹配会留下错误扣除",
  "hypothesis_ids":["H1","H2"]
}
```

五个文本字段均须非空；假设ID必须存在。复合对照可按实际情况配置多个条件，但不能只写“加阳性/阴性对照”。

### readouts[]

至少一个 `primary=true`。每个主要读数：

```json
{
  "id":"R1", "primary":true, "name":"背景校正初速",
  "direction":"相对同区组载体下降",
  "metric":"固定初速窗口斜率经匹配背景扣除后归一化",
  "unit":"RFU/min；percentage_of_vehicle",
  "criterion":"预先声明的幅度、方向、重复一致性和QC",
  "decision_rule":"满足如何解释；不满足如何解释；QC失败为何不可判定",
  "evidence":["E1","E2"], "control_ids":["C_NO_ENZYME"]
}
```

`control_ids` 用于SVG；科学硬审计主要依据对照自身的 `hypothesis_ids` 和读数的证据/决策结构。不要把任意选择的显著性阈值、通用统计方法或仪器品牌当作跨体系硬规范。阈值必须标为实际证据支持，或明确为前瞻协议假设。

### replication{}

```json
{
  "biological_repeats":3, "technical_wells":3,
  "independent_unit":"不同日期独立制备",
  "technical_unit":"同批条件内孔",
  "distinction":"孔先汇总，决策n=独立批次，不把9孔当n=9",
  "randomization":{"relevant":true,"method":"条件位置预登记随机化"},
  "blocking":{"relevant":true,"method":"每区组包含全条件和配对"},
  "blinding":{"relevant":true,"method":"编码样品，QC锁库后揭盲"}
}
```

如果某种方法确实不相关，例如自动化固定位置且已论证没有位置/顺序风险，可用：

```json
"randomization":{"relevant":false,"rationale":"具体体系与偏倚威胁的理由"}
```

compile要求显式相关性判断，不强迫所有实验采用同一种随机化、区组或盲法。

### parameters{} 与 steps[].parameters{}

顶层参数对象及步骤参数对象中的可执行参数，如果case声明了同名域，会检查：

- `min` / `max`；
- 以 `min` 为原点的 `step`，例如min=0、step=0.01时0.015非法；
- canonical `type=enum` 的 `values`（兼容旧 `enum`）；
- canonical `type=range` 为数值域；旧 `integer` 仍检查整数，canonical整数网格以 `step=1` 表达；
- 列表中的每个水平。

使用十进制 `Decimal`，不使用二进制浮点余数。未声明域会产生警告，而非任意创造范围。所有步骤 `duration_min` 为正；如case声明 `duration_min` 域也检查。

### resources[]、steps[]、costs[]、schedule{}

每个资源：

```json
{"id":"EQ_READER","resource_class":"equipment","model":"未指定","requirement":"可核验能力","booking_status":"prospective_unbooked"}
```

未知型号写“未指定”；不要写真实外观的虚构型号。每个步骤：

```json
{
  "id":"S1","duration_min":30,"instruction":"具体操作",
  "equipment_resource_ids":["EQ_READER"],
  "parameters":{"enzyme_nM":1},
  "qc":"过程检查","acceptance":"不满足时不得判读/进入下一步的标准"
}
```

每个费用条目 `computed_subtotal=unit_price×quantity`；已有 `subtotal` 和 `total_cost` 必须与重算值精确相等。实际注册表合并 `resource_contract.resources/equipment/reagents` 与 `equipment_domain_note` 内由 `JSONDecoder.raw_decode` 解析的资源，保留origins并标记同ID冲突定义。设计资源ID必须存在于此注册表；单价按该资源的 `planning_unit_price`，无该字段时按 `price_per_hour`，再无则按 `unit_price` 精确匹配。`quantity` 必须已经是应用实际pack_size/包装规则后的**计费数量**，compile不会猜测采购量、用量或取整规则。compile检查 `budget_cap`（兼容budget_limit）、日程期限和资源ID。前瞻价格/预订不是报价或批准。

时间不能只把不同重复层级的步骤机械相加一次。用时间合同显式展开：

```json
{
  "time_contract": {
    "one_time_step_ids":["S1","S6"],
    "per_biological_repeat_step_ids":["S2","S3","S4","S5"],
    "total_work_minutes":350,
    "instrument_booking_minutes":480,
    "note":"一次性50分钟 + 3×每独立重复100分钟 = 350分钟；480分钟仪器预订含周转余量"
  }
}
```

每个步骤ID必须且只能出现于一个组。compile按实际独立重复数重算 `total_work_minutes`；没有仪器时预订分钟可为0。净工作、日程日历时间和含缓冲余量的仪器预订分别呈现，不能互相冒充。

### risks[]

```json
{"id":"RISK1","risk":"具体风险","likelihood":"unknown_before_measurement","impact":"影响哪个推断","mitigation":"预防","trigger":"可观察触发","contingency":"触发后的分支"}
```

未知可能性不要编百分比。风险不能只写“注意安全”。

### revision{}

`base_candidate_id` 必须来自实际候选的canonical `version`（兼容 `id/candidate_id`）。`changes` 至少列 `field/from/to/reason`；`comparison` 至少列 `dimension/before/after/effect`。优先修正inspect实际发现的逐项subtotal/总计算术、域、`budget_cap`或`est_days/deadline_days`问题，再说明对照因果覆盖率、费用和时间的前后差异。原候选FAIL与新设计验证分开保存。

## 三、100%与不可判定的取舍

完整方案不是“总能得到阳性结论”。一个高质量决策树至少允许：

- **支持**：方向、幅度、QC和多个对照均符合；
- **不支持**：系统窗口有效，但预测未出现；
- **不可判定**：干扰、窗口失效、缺材料或关键QC失败。

无法得到关键证据时交付诚实partial，保留 `uncertainty` 和 `confirmation_items`。不要自动补未知输出字段来追求complete。
