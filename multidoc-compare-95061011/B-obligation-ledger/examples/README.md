# examples/ — 最小可运行合成示例

> **声明：本目录全部数据均为虚构（合成），不对应任何真实论文或正式案例，仅供演示义务台账流程。**

## 内容

| 文件 | 说明 |
|---|---|
| `corpus/DOC-01.jsonl` | 虚构论文 1：g-C3N4 / 罗丹明B（RhB），可见光，去除率 96% / 90 min，报成本约 12 CNY/g，未报速率常数 |
| `corpus/DOC-02.jsonl` | 虚构论文 2：N-TiO2 / 亚甲基蓝（MB），UV，去除率 88% / 120 min，k = 0.012 min-1，未报预算（与 DOC-01 污染物不同 → pollutant 维度不可比） |
| `corpus/DOC-03.jsonl` | 虚构论文 3：g-C3N4-Ag / RhB，可见光，只报速率常数 k = 0.031 min-1（与 DOC-01 指标口径不同），含一条无定量支撑的“优于 96%”声称（冲突示例） |
| `comparison-workorder.json` | 合成工单（case_id `SYNTH-EXAMPLE-001`）：六个维度、三个字段、两条显式问题 |
| `case.json` | 合成 case.json，含 output_contract（comparison_matrix / comparability_notes / coverage / ledger） |
| `sample_closures.jsonl` | 示例关闭记录 29 条，覆盖四种关闭状态：answered_with_evidence / not_reported_confirmed / conflict_preserved / out_of_scope（前三者有实例） |
| `run_example.sh` | 端到端脚本：compile → close → coverage → 组装 result.json → contract_gate |

## 运行

```bash
cd examples
bash run_example.sh
```

无需任何第三方依赖（python3 标准库），无网络访问。产物写入 `examples/output/`：

- `obligations.jsonl` — 29 条义务（9 field_cell + 18 comparability + 2 question），全部关闭；
- `coverage.json` — 覆盖度：总关闭率 **100%**；per-dimension / per-document 分组；
- `obligation-ledger.md` — 义务 × 状态台账；
- `comparison-matrix.md` — 比较矩阵（含可比性判定表）；
- `result.json` — 演示交付物，`contract_gate.py` 输出 **GATE PASS**。

## 预期看点

1. 六个维度（task/metric/units/material/pollutant/budget）× 三对文档 = **18 条可比性义务**真实生成；
2. `CMP-pollutant-DOC-01-vs-DOC-02` 判定为 **not_comparable**（RhB vs MB，不同染料不得合并）；
3. `CMP-metric-DOC-01-vs-DOC-03` 判定为 **not_comparable**（去除率 % vs 速率常数 min-1）；
4. `FC-budget-DOC-02/03` 以 **not_reported_confirmed** 关闭（附检索范围），而非静默留空；
5. `FC-removal_efficiency-DOC-03` 与 `Q-2` 以 **conflict_preserved** 关闭，双方 quote 均逐字核验落地。

## 负面测试（手动）

```bash
# 删掉 result.json 的一个 output_contract 字段，门禁应失败（退出码 1）
python3 -c "
import json
r = json.load(open('output/result.json'))
del r['comparison_matrix']
json.dump(r, open('/tmp/bad_result.json','w'), ensure_ascii=False)
"
python3 ../scripts/contract_gate.py --result /tmp/bad_result.json --case case.json --obligations output/obligations.jsonl
# 预期：GATE FAIL，提示 output_contract 字段 'comparison_matrix' 未出现
```
