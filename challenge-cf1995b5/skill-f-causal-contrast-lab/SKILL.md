---
name: causal-contrast-lab
description: 面向实验方案生成与优化的因果可识别性工作流。把可证伪假设、操作化变量、替代解释、显式映射对照、证据读数和前瞻决策规则编译成可执行、可核算、可降级的完整实验计划；不是通用六段式检查或证据台账复述。
---

# Causal Contrast Lab

先回答“什么观察会改变机制结论”，再排实验。核心是 **hypothesis → alternative/threat → control → readout → decision** 的可追溯链，同时交付资源、Decimal重算费用、有限参数域、时间、风险、修订对照及动态输出字段。

## 何时使用

- 要区分直接作用与光学、聚集、污染、漂移、载体、批次等竞争解释。
- 候选方案看似完整，却不能证伪、缺关键对照、混用技术复孔与独立重复，或成本/参数域不可执行。
- 需要把机制分歧转成带“支持 / 不支持 / 不可判定”分支的实验，而不是只追求一条漂亮剂量曲线。

不要把技术复孔当独立样本量；不要把一个通用阳性对照当成真正的机制互补读数；不要把洗涤剂敏感性、单一IC50或单一正交结果夸大为直接结合证明。

## 运行时合同（官方 Harness）

- 实际输入为 `/input/case.json`、`/input/task.md`，以及可选的真实PDF和其他材料。**实际输入是唯一事实来源**；不要信任文件名、标签或本技能示例所声称的内容。读取材料，不要补写不存在的参数、论文、仪器型号、价格、风险或实测结果。
- **canonical organizer schema 是主路径**：根字段为 `case_id`、`source:{paper_pdf,citation,key_claim}`、`resource_contract:{disclaimer,currency,budget_cap,deadline_days,equipment,reagents}`、`parameter_domains`、`equipment_domain_note`、`candidate_plans`、`output_contract`。设备含 `id/name/model/spec/price_per_hour/booking:{window_days,slots_per_week,slot_hours}`；试剂含 `id/name/spec/unit_price/unit/pack_size`。
- 数值域使用 `type:"range",min,max,step,basis,source`，枚举域使用 `type:"enum",values`。候选以 `version` 为主标识，含 `summary/parameters/cost_items/total_cost/est_days`；每条 `cost_items` 按 `unit_price×quantity` 重算，并核对已有 `subtotal`、`cost_subtotal` 和 `total_cost`。兼容旧别名 `id/candidate_id`、`costs`、`duration_days`、`budget_limit`，但新示例与测试均使用canonical字段。
- `inspect.facts.resource_register` 合并 `resource_contract.resources/equipment/reagents` 以及 `equipment_domain_note` 中用 `json.JSONDecoder.raw_decode` 解析的全部嵌入JSON对象，按ID去重并保留origins和冲突定义。设计资源ID必须属于该实际注册表；设计价格匹配 `planning_unit_price`，否则依次匹配 `price_per_hour` 或 `unit_price`。**费用quantity必须是已按实际包装规则折算的计费数量**；脚本不猜测数量，也不推断pack rounding。
- 只有 `case.synthetic===true` 或 `case_kind/scenario_label` 明确含“合成”时才标“合成示例输出”。其他实际案例统一标“前瞻性实验方案与机器校验输出；不是实测实验结果”。
- 在 `/app/work` 工作；最终制品写到 `/app/output`。技能安装根目录为 `/skills/weekly-skill`。
- `result.json` 必须有 `case_id` 以及 `case.json.output_contract.required_fields` 中的每个字段。通用字段有确定生成器；未知字段得到 `status=missing_generator`、`value=null`、`honest_partial=true` 的显式标记，结果保持 `partial`，绝不臆造。
- `status` 只能是 `complete`、`partial`、`blocked`。科学审计出现任何 `FAIL` 就必须 `partial`；输入无法读取则 `blocked`。`sources`、`uncertainty`、`change_log`、`confirmation_items` 始终保留。
- inspect 一启动即写合法早期 `partial result.json`，再盘点材料；compile 在读取智能体设计前也先写早期 partial。若时间紧张，交付真实 partial 比伪造 complete 更好。
- 资源、价格和预订为 **prospective contracts**，不是供应商报价、库存确认、审批或已完成的机时预订。无PDF或没有 `pdftotext` 时明确记录限制，不猜测PDF内容。
- 脚本只使用 Python 3 标准库；可选PDF盘点调用系统 `pdftotext`。除该步骤外正常运行远少于5秒。无需网络或额外安装。

## 两步工作流（只编辑一个设计文件）

### 1. 盘点与候选审计

```bash
mkdir -p /app/work /app/output
python3 /skills/weekly-skill/scripts/causal_contrast.py inspect \
  --case /input/case.json \
  --input-dir /input \
  --work-dir /app/work \
  --output-dir /app/output
cp /app/output/design_spec.template.json /app/work/design_spec.json
```

读取 `/app/output/inspect.json` 中的 `facts`、`facts.resource_register`、`materials`、PDF状态和 `candidate_assessment`，读取 `/app/output/result.json`。候选每条 `subtotal`、`cost_subtotal` 与 `total_cost` 都按 `unit_price × quantity` 逐项重算；`budget_cap`、`est_days/deadline_days`、`range`的步长（以min为原点）和`values`枚举分别审计。审计结果中的 `schema_aliases` 与每候选 `aliases` 明示实际使用的别名。候选 FAIL 是原候选的机械事实，不会自动让修复后的新设计 FAIL。

### 2. 编写一个 design_spec.json 并编译

把以下骨架复制到 `/app/work/design_spec.json`（也可直接修改上一步模板），一次性填写。详细字段、可复制示例及决策写法见 `references/contrast_design.md` 与 `references/evidence_and_decisions.md`。

```json
{
  "schema_version": "1.0",
  "case_id": "必须等于实际case_id",
  "design_summary": "先检验哪个替代解释，再据何读数分流",
  "hypotheses": [{"id":"H1","statement":"...","prediction":"...","falsification":"..."}],
  "variables": [{"id":"IV1","kind":"independent","name":"...","operational_definition":"...","unit":"...","measurement":"...","allowed_levels":["..."],"level_source":"case_json:$.parameter_domains...."}],
  "controls": [{"id":"C1","name":"...","control_type":"vehicle","condition":"...","excluded_alternative":"...","threat":"...","hypothesis_ids":["H1"]}],
  "readouts": [{"id":"R1","primary":true,"name":"...","direction":"...","metric":"...","unit":"...","criterion":"...","decision_rule":"...","evidence":["E1"],"control_ids":["C1"]}],
  "replication": {
    "biological_repeats": 3, "technical_wells": 3,
    "independent_unit":"独立制备/日期", "technical_unit":"同批孔", "distinction":"先汇总孔，以独立批次为n",
    "randomization":{"relevant":true,"method":"..."},
    "blocking":{"relevant":true,"method":"..."},
    "blinding":{"relevant":true,"method":"..."}
  },
  "parameters": {"参数名": "必须在case.parameter_domains内"},
  "resources": [{"id":"EQ1","resource_class":"equipment","model":"未提供则写未指定，勿编造","requirement":"可观察能力","booking_status":"prospective_unbooked"}],
  "steps": [{"id":"S1","duration_min":30,"instruction":"...","equipment_resource_ids":["EQ1"],"parameters":{"参数名":"合法值"},"qc":"...","acceptance":"..."}],
  "costs": [{"item":"...","resource_id":"EQ1","unit_price":1,"quantity":1,"unit":"..."}],
  "total_cost": 1,
  "time_contract":{"one_time_step_ids":["S1"],"per_biological_repeat_step_ids":[],"total_work_minutes":30,"instrument_booking_minutes":60,"note":"一次性与每独立重复工作分开；仪器预订含周转余量"},
  "schedule": {"total_days":1,"milestones":[{"day":1,"activity":"..."}]},
  "evidence": [{"id":"E1","source_class":"case_json","locator":"$.path.to.value","supports":["H1","R1"],"quote":"该位置的规范JSON值"}],
  "risks": [{"id":"RISK1","risk":"...","likelihood":"unknown","impact":"...","mitigation":"...","trigger":"...","contingency":"..."}],
  "revision": {"base_candidate_id":"实际候选version（兼容id/candidate_id）","changes":[{"field":"...","from":"...","to":"...","reason":"..."}],"comparison":[{"dimension":"...","before":"...","after":"...","effect":"..."}]},
  "uncertainty": ["..."], "change_log": [{"id":"CL1","change":"...","reason":"..."}],
  "confirmation_items": ["设备、价格、库存、SOP等真实待确认项"]
}
```

每个独立/因变量都需要操作定义、单位、测量、允许水平和来源；因变量没有预设水平时，用非空列表明确写“实测前不设数值范围”，不要填假测量。随机化/区组/盲法只在相关时启用；若 `relevant=false` 必须给 `rationale`，不一律强加同一方法。`case.parameter_domains` 中声明的域会审计顶层参数与每步 `parameters`；步骤时长也受 `duration_min` 域约束。`time_contract` 必须把每个步骤恰好分为一次性或每独立重复执行，并重算展开总工作；仪器预订时间与净工作分开。设计资源ID须存在于合并后的合同注册表（包括note-only设备）；费用单价按 `planning_unit_price → price_per_hour → unit_price` 匹配相应资源，计费quantity必须已考虑包装规则。

```bash
python3 /skills/weekly-skill/scripts/causal_contrast.py compile \
  --case /input/case.json \
  --design-spec /app/work/design_spec.json \
  --input-dir /input \
  --output-dir /app/output
```

compile 独立重跑实际候选审计，不依赖先前inspect；一次生成：

- `plan.json`：完整计划、逐项成本重算、证据定位核验和验证状态。
- `plan.md`：人读执行方案，含步骤QC/验收、精确费用、日程、风险、修订对照。
- `contrast_map.svg`：UTF-8 文本的假设—对照—读数映射。
- `validation.json`：`PASS` / `PASS_WITH_WARNINGS` / `FAIL`、具体错误与警告、证据核验；`FAIL ⇒ result.status=partial`。
- `result.json`：`case_id` 和动态 required_fields；未知字段保留显式缺失生成器标记。

科学/结构不完整不返回脚本错误而返回诚实partial；CLI拼写错误由argparse非零退出。脚本或数据真正运行失败由包装shell非零退出。

## 智能体优化顺序（64次模型调用、900秒预算下）

1. **立即inspect并确认result存在。** 读取实际task和输入盘点；无材料或PDF不可读就记录，不调用想象补齐。
2. **定位因果歧义。** 对每个核心主张写可观察预测与会使其失败的观察；列出至少一个真正不同的替代解释，不堆无关对照。
3. **显式映射。** 每个对照写 `control_type`、`condition`、`excluded_alternative`、`threat`、`hypothesis_ids`。说明哪些结论仍不能区分。
4. **锁定读数。** 给方向、指标、单位、阈值/方向判据、支持/不支持/不可判定的前瞻规则。QC失败是“不可判定”，不是阴性。
5. **操作化和执行。** 参数只取case有限域；区分独立/技术重复；逐步骤绑定资源ID、时长、QC和验收。资源能力未知就待确认，不编造型号。
6. **证据与费用。** 优先用可机械定位的case JSONPath及实际材料的精确短引文；根据reference中的规范JSON编码填写quote。重算总计、限期、风险及候选前后比较。
7. **compile、读validation、只修错误后重跑。** 警告要解释或保留；无法解决就诚实partial。不要花调用构造几十个文件，也不要做提交、推送或凭据操作。

## 完成门槛

只有在无科学/算术 `FAIL`、所有动态字段有生成器、证据记录可追溯时，结果才为 `complete`。候选FAIL数量与修订计划是否FAIL分开报告。所有预算、机时和采购仍待实际确认；方案完整不等于机制已证实，也不等于已有实测结果。

## 本地合成示例

示例是 `synthetic:true` 的**合成示意案例**：直接酶抑制 vs 化合物荧光干扰 vs 聚集效应，不是旧过氧化物案例，也不是论文事实。输入本身已转换为canonical organizer schema，`resource_contract` 使用 `budget_cap/equipment/reagents`，候选用 `version/cost_items/est_days`，且 `EQ_MULTICHANNEL` 仅由note内嵌JSON声明并被设计实际使用。运行与检查方法见 `examples/example_run.md`；`examples/output/*` 标为“合成示例输出，非正式测评结果”。同一运行还包含一个临时非合成canonical smoke，其页眉必须是不含合成标签的前瞻性声明。
