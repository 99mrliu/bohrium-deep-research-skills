# 最小调用示例（合成示例，非正式案例结果）

全部输入为**虚构合成数据**，仅演示接口与流程。

## 输入

- `input/preconditions.jsonl`：虚构提案的 8 条前提台账，覆盖五类——3 条 source-ok、4 条 assumption/unknown、1 条 source-blocked（P8：文献报告了与提案前提相反的证据）；
- `input/preconditions_bad.jsonl`：故意违例版（source 缺 evidence_ref、assumption 缺 note、id 重复）。

## 调用与预期输出（真实运行产生，已目检）

```bash
# 1. 正常台账 → 门控判定
python3 scripts/feasibility_gate.py \
    --ledger examples/input/preconditions.jsonl --out examples/output
# 退出码 0；verdict=not_feasible（P8 为 blocker）
# feasibility_memo.md：五类前提分组、阻塞项 P8、4 条成立条件/待核假设
# risk_register.md：P4/P5/P6/P7 全部 unknown/assumption 入册

# 2. 违例台账 → 拦下
python3 scripts/feasibility_gate.py \
    --ledger examples/input/preconditions_bad.jsonl --out examples/output_bad
# 退出码 1；3 条违例：Y1（source 缺定位）、Y2（assumption 缺理由）、Y4（id 重复）
```

产物：`examples/output/` 下 `verdict.json`、`feasibility_memo.md`、`risk_register.md`；`examples/output_bad/` 为违例版对照。

说明：not_feasible 在此为演示门控规则的正确触发；真实场景中 blocker 解除后应重跑门控更新结论。
