# frontier-run-gates

过程质量控制、契约强制与可复跑 —— 面向预算受限文献趋势分析运行（Playground challenge-073af7d3）的 Skill bundle。
**重心**：让"运行本身"可审计 —— 哈希建档 + 阶段门 G0–G8 + 契约 lint + 确定性复跑；partial-first 纪律保证中途断供也交出诚实部分结果。

## 布局

```
SKILL.md                  技能说明（协议、契约、预算、异常处理）
scripts/
  run_manifest.py         确定性建档：输入 sha256、阶段状态、命令日志（无时间戳，seq 计数）
  mini_pipeline.py        小型确定性参考管线：canon/slices/cohorts/representatives/gaps/证据矩阵/result 草稿
  gate_check.py           阶段门 G0–G8 检查（单门或全门，JSON 报告，exit 1 = 失败）
  contract_lint.py        result.json 对 case.json output_contract 逐字段强制（含证据引用解析）
  replay_diff.py          影子目录重跑管线，逐字节比对产物，非确定性探测器
references/
  gates.md                G0–G8 定义、通过条件、失败动作
  contract_rules.md       lint 规则、status 枚举、证据引用格式、空字段规则
examples/
  run_example.sh          端到端证明：好流程全过 + 坏样本恰好三条违规
  synthetic_case/         合成（synthetic）语料 15 条、case.json、埋雷 result_bad.json
  example_output/         run_example.sh 真实产出的工件
GITHUB_URL.txt            仓库链接
```

## 快速开始

```bash
bash examples/run_example.sh          # 端到端自检（好+坏）
python3 scripts/run_manifest.py --work /app/work init --input-dir /input
python3 scripts/mini_pipeline.py --work /app/work --corpus <corpus> --case /input/case.json
python3 scripts/gate_check.py --work /app/work          # G0..G8
python3 scripts/replay_diff.py --work /app/work         # 必须为 identical
python3 scripts/contract_lint.py --case /input/case.json --result /app/output/result.json \
  --evidence-matrix /app/work/evidence_matrix.jsonl     # 必须 clean
```

## 约束

Python 3 标准库，离线，确定性（无墙钟时间，sort_keys，稳定排序）；exit 0/1 语义统一。
