# examples（合成 / synthetic）

本目录为端到端自证示例，所有数据均为**合成（synthetic/合成）**，不是真实文献。

## 内容

- `synthetic_case/` — 合成测试夹具
  - `case.json`：合成 case（case_id=SYNTH-001，6 个契约字段）
  - `corpus.jsonl`：15 条编造记录（2012–2024，id/title/year/abstract/keywords/citations，均带 `"synthetic": true`）
  - `result_bad.json`：埋雷结果——缺 `research_gaps` 字段、status 为非法值 `"done"`、一条 `SYNTH-R99` 悬空证据引用
- `run_example.sh`：一键演示
- `example_output/`：`run_example.sh` 真实跑出的工件（good/ 与 bad/）

## 运行

```bash
bash examples/run_example.sh
```

## 预期

GOOD 流程：manifest 建档 → mini_pipeline 产出 7 个工件 → gate_check 全门 G0–G8 通过 → replay_diff 全部字节一致（exit 0）→ contract_lint 对草稿 clean（exit 0），工件复制到 `example_output/good/`。

BAD 流程：contract_lint 对 `result_bad.json` exit 1，**恰好**三条违规：`missing_field`（research_gaps）、`invalid_status`（done）、`dangling_evidence`（SYNTH-R99），捕获到 `example_output/bad/`，脚本以 PROOF 行断言。

任何一步不符预期，`run_example.sh` 以非零退出。
