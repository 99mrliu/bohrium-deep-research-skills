# examples — 合成示例（synthetic demo）

**本目录全部数据为合成虚构**（管式炉 GSL-1500X 焙烧工序为演示而编造），仅用于
验证三个脚本的端到端行为与退出码契约，不构成任何真实实验建议。

## 目录内容

```
synthetic-input/
  case.json                    # case_id + output_contract 三字段
                               #   (experiment_plan / evidence_and_risk / confirmation_items)
                               #   + 材料路径列表 + 任务提及参数（含无依据的"搅拌转速"）
  materials/furnace_spec.txt   # 合成设备规格：温度量程 室温–1100°C、升温速率 ≤10°C/min、
                               #   催化剂耐温 950°C、载气流量 10–500 mL/min、焙烧时间步进 30 min、
                               #   氢气/空气载气互斥（组 atmosphere）
  materials/history.csv        # 合成历史实验记录（备注行含隐性上限 900°C）
  proposal_pass.json           # 合格方案（全部在可行域内）
  proposal_violation.json      # 负例：温度 1200°C 越界 + 焙烧时间 100 违步进 + ungrounded 搅拌转速
  domain_variant_conflict.json # 由 domain.json 人工播种冲突的变体
                               #   （targets.温度=1200 越界；载气流量上下限倒置）
synthetic-output/              # 三个脚本的真实运行产物（已目检）
  domain.json                  # (a) extract_domain 产物：8 条约束 + 1 个 ungrounded 参数
  audit_pass.json              # (b) 合格方案审计：status=pass，exit 0
  audit_violation.json         # (c) 负例审计：status=fail（2 violation + 1 ungrounded），exit 3
  conflicts_clean.json         # 干净 domain 的冲突扫描：ok，exit 0
  conflicts.json               # (d) 冲突变体扫描：3 条冲突（2 handoff + 1 degrade），exit 3
```

## 复现命令（在 examples/ 目录下执行）

```bash
cd examples

# (a) 抽取可行域 → exit 0
python3 ../scripts/extract_domain.py \
  --case synthetic-input/case.json \
  --materials synthetic-input/materials \
  --out synthetic-output/domain.json

# (b) 合格方案过闸门 → exit 0
python3 ../scripts/domain_audit.py \
  --domain synthetic-output/domain.json \
  --proposal synthetic-input/proposal_pass.json \
  --out synthetic-output/audit_pass.json

# (c) 负例被闸门抓住 → exit 3
python3 ../scripts/domain_audit.py \
  --domain synthetic-output/domain.json \
  --proposal synthetic-input/proposal_violation.json \
  --out synthetic-output/audit_violation.json

# (d1) 干净 domain 无冲突 → exit 0
python3 ../scripts/conflict_scan.py \
  --domain synthetic-output/domain.json \
  --out synthetic-output/conflicts_clean.json

# (d2) 播种冲突的变体被抓住 → exit 3
python3 ../scripts/conflict_scan.py \
  --domain synthetic-input/domain_variant_conflict.json \
  --out synthetic-output/conflicts.json
```

## 预期结果（已实测）

| 步骤 | 退出码 | 关键产物摘要 |
|---|---|---|
| (a) | 0 | 8 条约束（温度≤1100、升温速率≤10、催化剂温度≤950 safety、载气流量 10–500、焙烧时间 step 30、互斥组 atmosphere 两成员、历史焙烧温度≤900）；ungrounded=[搅拌转速] |
| (b) | 0 | 6 个参数全部 pass（含互斥组只申报氢气载气） |
| (c) | 3 | 温度 1200 越上限 1100（证据定位 furnace_spec.txt 第 3 行 quote）；焙烧时间 100 不满足步进 30；搅拌转速 ungrounded |
| (d1) | 0 | 无冲突 |
| (d2) | 3 | inverted_bounds + effective_bounds_inverted（载气流量 500>10，handoff）；target_outside_domain（温度目标 1200 > 1100，degrade） |

## 冲突变体的播种方式（如需重建）

```python
import json
d = json.load(open('synthetic-output/domain.json'))
d['targets'] = {'温度': 1200.0}                      # 目标越出设备量程
for c in d['constraints']:
    if c['parameter'] == '载气流量':
        c['lower'], c['upper'] = 500.0, 10.0         # 上下限倒置
json.dump(d, open('synthetic-input/domain_variant_conflict.json', 'w'),
          ensure_ascii=False, indent=2)
```
