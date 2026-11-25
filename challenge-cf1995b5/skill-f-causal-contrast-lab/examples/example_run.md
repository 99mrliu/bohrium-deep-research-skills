# 合成示例复现与检查

本目录的完整酶案例为 `synthetic:true` 的**合成示意案例**，用于审计“真实直接酶抑制”与“化合物荧光干扰/聚集相关抑制”的因果对照设计。没有真实论文参数、真实设备型号、供应商报价或实测结果。`output/*` 每次由脚本重新生成并标注“合成示例输出，非正式测评结果”。同一脚本还在 `work/compat_smoke` 生成一个独立的**非合成**canonical临时案例；该案例只验证兼容性，输出严禁标成合成示例。

## canonical organizer 输入

完整 `mock_case.json` 已转换为主测试合同：

- `source` 为 `paper_pdf/citation/key_claim`；
- `resource_contract` 为 `disclaimer/currency/budget_cap/deadline_days/equipment/reagents`，设备使用 `price_per_hour` 与 `booking`，试剂使用 `unit_price/unit/pack_size`；
- 数值参数域均为 `type=range`，枚举为 `type=enum,values=[...]`；
- 三个候选均以 `version` 标识，使用 `summary/cost_items/subtotal/total_cost/est_days`；
- `output_contract.required_fields` 包含 `case_id` 及其余八个字段；
- `EQ_MULTICHANNEL` **只**存在于 `equipment_domain_note` 的嵌入JSON设备对象中，且设计的S1/S2/S3/S6实际绑定它。inspect通过 `JSONDecoder.raw_decode` 将其列入 `facts.resource_register`，并保留 `equipment_domain_note@...` origin。

脚本兼容旧的 `id/candidate_id`、`costs`、`duration_days`、`budget_limit`、`planning_unit_price`，但完整示例不断言这些旧字段。计费quantity必须已经按包装规则折算；示例不会推断pack rounding。

## 1. 一条命令真实运行

在任意当前目录执行（路径按实际Skill位置调整）：

```bash
/Users/liuhengshen/Desktop/bhr_product/bohrium/challenge-cf1995b5-v3/skill-f-causal-contrast-lab/examples/run_example.sh
```

也可使用相对路径：

```bash
cd /Users/liuhengshen/Desktop/bhr_product/bohrium/challenge-cf1995b5-v3/skill-f-causal-contrast-lab
./examples/run_example.sh
```

可移植性来自脚本以自身位置解析Skill根目录；无需安装依赖。默认解释器是 `python3`，可用 `PYTHON=/path/to/python3 ./examples/run_example.sh` 覆盖。脚本先复制合成输入到 `examples/work/input`，然后真实运行：

```bash
python3 scripts/causal_contrast.py inspect \
  --case examples/work/input/case.json \
  --input-dir examples/work/input \
  --work-dir examples/work \
  --output-dir examples/output

python3 scripts/causal_contrast.py compile \
  --case examples/work/input/case.json \
  --design-spec examples/design_spec.json \
  --input-dir examples/work/input \
  --output-dir examples/output
```

包装脚本在缺失产物、科学FAIL、动态字段缺失、成本/时间不符、SVG不可解析或控制节点不全时非零退出。正常结束打印：

```text
EXAMPLE_OK status=complete cost=436 single_pass_min=150 total_work_min=350 total_days=4 candidates_FAIL=3 SVG_controls=5 note_resource=EQ_MULTICHANNEL
COMPAT_SMOKE_OK synthetic_label=false version/cost_items=true subtotal_defect=true range_step_defect=true note_resource=EQ_NOTE_ONLY
```

它会清空并重建的目录仅为解析并白名单校验后的 `examples/work` 和 `examples/output`。

## 2. 输入中的三个可检出候选错误

- `CAND_A_PARTIAL`：小计写成174，但80+24+80=184；`enzyme_nM=0.15` 偏离min=0.1、step=0.1的合法网格。
- `CAND_B_OPTICAL_GAP`：总价写成266而重算276；`compound_uM=0.005` 小于min=0.01；`technical_wells=8` 超过max=6。
- `CAND_C_FULL_OVERDUE`：算术333正确，但10天超过7天期限；`detergent_percent=0.015` 偏离min=0、step=0.01。

这三个候选的原始FAIL保留在 `candidate_assessment`，不会因为修订方案通过就被改写。修订以CAND_C为基准：洗涤剂改为0.01、10天改4天；补齐光学/洗涤剂资源后7项费用按Decimal重算为 **436**，低于800预算；六步单轮合计 **150分钟**；S1/S6一次，S2–S5随三个独立重复展开，重算总工作 **350分钟**；仪器预订480分钟另列，总日程4天。所有价格均为合成规划价，不是报价或预订批准。

## 3. 如何检查产物

### result.json

```bash
python3 - <<'PY'
import json
r=json.load(open('examples/output/result.json',encoding='utf-8'))
c=json.load(open('examples/mock_case.json',encoding='utf-8'))
print(r['case_id'],r['status'],r['validation']['status'])
print({k:(k in r) for k in c['output_contract']['required_fields']})
print(r['revised_plan'])
print(r['candidate_assessment']['failed_candidate_count'])
PY
```

应见 `complete` / `PASS`、`case_id`加其余八个动态required field全部存在、三个候选FAIL。`sources` 含case JSONPath与合成Markdown原文；`uncertainty` 明确无实测、无真实PDF、型号/价格/预订待确认。

### validation.json与inspect.json

```bash
python3 - <<'PY'
import json
v=json.load(open('examples/output/validation.json',encoding='utf-8'))
i=json.load(open('examples/output/inspect.json',encoding='utf-8'))
print('errors=',v['errors'],'warnings=',v['warnings'])
print('evidence=',[(x['id'],x['status']) for x in v['evidence_checks']])
print('cost=',v['cost_recompute']['computed_total'])
print('pdf_tool_available=',i['facts']['pdf_inventory'] is not None,
      i['facts']['pdf_inventory'])
print('note_resource_origin=',i['facts']['resource_register']['origins']['EQ_MULTICHANNEL'])
print('candidate_aliases=',i['candidate_assessment']['candidates'][0]['aliases'])
PY
```

"PASS_WITH_WARNINGS" 的证据并不妨碍计划完成，但警告不可隐藏。案例证据 E1–E6 应机械核验PASS；其中E3是source_note.md的精确子串，其他为case定位值的规范JSON。

### plan.md / plan.json

依次检查：

1. H1–H3是否有预测和证伪；五类control是否写条件、替代解释、威胁与假设ID。
2. R1–R3是否有方向、指标、单位、前瞻判据、支持/不支持/不可判定动作；R2先分流光学干扰，R3不夸大聚集证据。
3. 三个独立制备/日期与三个技术孔是否分层，是否明确n=3而非n=9。
4. 每步骤资源ID、时长、QC/验收；费用逐项小计和总成本436；单轮150分钟、重复展开350分钟、仪器预订480分钟；日程4天；风险触发/备选；相对候选修订。
5. 所有数值仍是合成前瞻假设，不冒充实测。

### contrast_map.svg

这是可直接查看的UTF-8 SVG，不是二进制。机械检查：

```bash
python3 - <<'PY'
import xml.etree.ElementTree as ET
p='examples/output/contrast_map.svg'
r=ET.parse(p).getroot()
print('root=',r.tag)
print('controls=',len(r.findall(".//{http://www.w3.org/2000/svg}rect[@class='c']")))
print(open(p,encoding='utf-8').read().splitlines()[1])
PY
```

应有5个控制矩形节点、3个假设节点和3个主要读数节点；连线表示控制映射，SVG metadata同样标记合成示例。

## 4. 非合成 canonical compatibility smoke

`run_example.sh` 会在 `examples/work/compat_smoke/input/case.json` 写入极小的非合成organizer案例，并真实执行inspect。它使用 `version=smoke-v1`、`cost_items`、`type=range`、`budget_cap/est_days`，故意设置 `2×3=6` 却申报行 `subtotal=5` 与 `total_cost=5`，并令 `dose=0.15` 偏离 `min=0.1,step=0.1`。另一个设备 `EQ_NOTE_ONLY` 只在note内嵌JSON中声明。

脚本断言：逐项subtotal与total_cost错误均被发现，range/step缺陷被发现，候选version与cost_items别名被明示，note-only设备及origin进入注册表；`inspect.json/result.json/design_spec.template.json` 的 `_header` 都是“前瞻性实验方案与机器校验输出；不是实测实验结果”，且不含“合成示例”。这些输出与完整合成示例分离，不依赖完整设计，也不会冒充实测。

## 5. 可重复的有意义失败测试

负例放在允许的工作目录 `examples/work/failure`，不修改权威 `examples/design_spec.json`：

```bash
cd /Users/liuhengshen/Desktop/bhr_product/bohrium/challenge-cf1995b5-v3/skill-f-causal-contrast-lab
mkdir -p examples/work/failure
cp examples/design_spec.json examples/work/failure/design_spec.json
python3 - <<'PY'
import json
p='examples/work/failure/design_spec.json'
x=json.load(open(p,encoding='utf-8'))
control=next(c for c in x['controls'] if c['id']=='C_COMPOUND_ONLY')
del control['hypothesis_ids']
open(p,'w',encoding='utf-8').write(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
PY
python3 scripts/causal_contrast.py compile \
  --case examples/work/input/case.json \
  --design-spec examples/work/failure/design_spec.json \
  --input-dir examples/work/input \
  --output-dir examples/work/failure/output
python3 - <<'PY'
import json
r=json.load(open('examples/work/failure/output/result.json',encoding='utf-8'))
v=json.load(open('examples/work/failure/output/validation.json',encoding='utf-8'))
assert r['status']=='partial',r['status']
assert v['status']=='FAIL',v['status']
assert any('C_COMPOUND_ONLY' in e and 'hypothesis_ids' in e for e in v['errors'])
print('NEGATIVE_TEST_OK status=partial control_mapping_FAIL=1')
PY
```

compile对科学FAIL本身返回0（以便保留并检查全部partial制品），`validation.status=FAIL`、`result.status=partial`。若是脚本不存在、CLI参数错误、Python无法启动或产物断言失败，则shell测试非零退出。再次运行 `./examples/run_example.sh` 会清理负例工作目录并恢复权威成功示例。
