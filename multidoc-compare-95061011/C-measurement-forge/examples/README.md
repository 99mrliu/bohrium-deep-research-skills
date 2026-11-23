# examples/ — 合成最小示例（非真实文献，非官方答案）

本目录是 measurement-forge 的**合成**端到端示例：三篇虚构的 g-C3N4/RhB 光催化"论文"，仅用于演示管线，不含任何官方正式案例答案。

## 目录

- `corpus/DOC-01.jsonl` — 报 "degraded **96%** within 90 min"，并给出公式口径 η=(C0−Ct)/C0、UV-Vis @ 554 nm；投加量 0.5 **g/L**。
- `corpus/DOC-02.jsonl` — 同催化剂同染料，但只报速率常数 "k = **0.031 min⁻¹**"（pseudo-first-order）。
- `corpus/DOC-03.jsonl` — 报 "removal **0.92**"（无量纲 fraction 而非 %）；投加量 500 **mg/L**（与 DOC-01 的 g/L 混用）。
- `comparison-workorder.json` — 合成工单，`case_id = "SYNTH-EXAMPLE-001"`。
- `sample_measurements.jsonl` — 模拟 agent 在候选抽取之后逐条确认、补 `metric_definition` 与 `condition_context`/`conditions` 的 7 条记录。
- `run_example.sh` — 一键管线。
- `output/` — 运行产物（candidates.jsonl / paras-index.jsonl / measurement-ledger.md / comparison-matrix.md / result.json）。

## 运行

```bash
bash examples/run_example.sh
```

依赖：python3（仅标准库）、bash。无网络。

## 预期输出与看点

1. **候选抽取**：26 条候选，其中 `min⁻¹`、`mg/L`、`g/L`、`%` 均解析成功（`unit_status=parsed`）；`0.92` 后无单位（候选保留上下文词，标 `unparsed`），`550 °C` 的尾巴带非单位词也标 `unparsed`——体现"先机器提候选、后 agent 判读"。
2. **机检**：7 条确认记录通过（2 条 WARNING：值串 `10`、`1` 同时出现在他篇，属同体系重复实验条件，agent 判读后保留——告警不致命，`--strict` 可升为失败）。
3. **比较矩阵**（`output/comparison-matrix.md`）：
   - **DOC-01 ↔ DOC-02 判不可比**：degradation_efficiency（%）与 rate_constant（min⁻¹）是不同 quantity_kind，矩阵"跨 quantity_kind 可比性(机检)"一节直接列出 `degradation_efficiency ↔ rate_constant: 不可比`。同染料同材料也不可把 k 与 % 当一个量。
   - **DOC-03 的 0.92 → 92 % (derived)**：fraction 与 % 量纲相同（均无量纲），换算列给出 92 % 并标 derived，原值 0.92 保留。
   - **500 mg/L → 0.5 g/L (derived)**：投加量单位混用归一；与 DOC-01 的 0.5 g/L 在换算列对齐。
   - **budget 维判 not_comparable**：300 W 氙灯 / 300 W 氙灯+420 nm 截止 / 150 W LED 三种光源预算不同，矩阵按规则**不得合并**，原样保留。
   - **metric 维对 degradation_efficiency 判 review**：两条记录公式写法不同（η=(C0−Ct)/C0 vs 1−Ct/C0），机器标 agent 复核。
4. **result.json 骨架**：`case_id` 原样复制（"SYNTH-EXAMPLE-001"）；因合成工单无 `output_contract`，按退化形态给出 `{case_id, status, main_result, sources, uncertainty}` 并附六维度 comparability；`status` 预置 `partial` 待 agent 完成后改 `success`。

## 自验机检（负例）

```bash
# 缺 metric_definition 应报错退出(exit 1):
python3 - <<'EOF'
import json
recs=[json.loads(l) for l in open('examples/sample_measurements.jsonl') if l.strip()]
recs[0]['metric_definition']=''
open('/tmp/no_metric.jsonl','w').write('\n'.join(json.dumps(r,ensure_ascii=False) for r in recs)+'\n')
EOF
python3 scripts/validate_measurements.py /tmp/no_metric.jsonl --paras examples/output/paras-index.jsonl; echo "exit=$?"
# 预期: ERROR: M-001: status=reported 但 metric_definition 为空 ... exit=1
```
