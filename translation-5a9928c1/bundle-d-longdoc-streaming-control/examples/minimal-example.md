# 最小调用示例（合成示例，非正式案例结果）

输入：`make_synthetic.py` 生成的**合成**长文（28 单元、题注、公式）。

```bash
python3 examples/make_synthetic.py --out /tmp/ld.txt
S=scripts; W=/tmp/streamjob; O=/tmp/streamout
mkdir -p $W/chunks $W/context $O
python3 $S/plan_chunks.py --source /tmp/ld.txt --budget-tokens 150 --out $W/plan.json
python3 $S/stream_state.py init --plan $W/plan.json --out $W/state.json
python3 $S/stream_state.py list-pending --state $W/state.json
python3 $S/context_pack.py --plan $W/plan.json --state $W/state.json --chunk c001 --out $W/context/c001.md
# …翻译该块（实际案例由 Agent 完成；本示例用 ⟨SYNTH-ZH⟩ 占位合成译文）…
python3 $S/stream_state.py mark-done --state $W/state.json --plan $W/plan.json \
  --chunk c001 --translations $W/chunks/c001.translated.json --requests 1 --seconds 25
python3 $S/assemble_result.py --case examples/case.json --plan $W/plan.json \
  --state $W/state.json --translations-dir $W/chunks --out $O
```

一键自测（19 组断言，含篡改拒绝、缺单元拒绝、幂等、中断 partial）：
`bash examples/run_example.sh`。

示例译文为 ⟨SYNTH-ZH⟩ 占位合成译文，仅演示切块、续跑与预算台账；
不得当作任何真实文献的翻译结果。
