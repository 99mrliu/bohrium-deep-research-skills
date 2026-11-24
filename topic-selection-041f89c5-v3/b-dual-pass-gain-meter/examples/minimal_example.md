# 最小示例（合成，非正式测试案例结果）

## 输入

`examples/input/`：虚构案例 `SYNTH-GAIN-001`（契约 4 个待填字段）+
基线稿 `pass0_result.json`（故意保留 4 处无边界越界断言："尚无人研究""填补空白"
"首次提出""国际首创"；0 锚点；uncertainties 为空）+
严谨稿 `pass1_result.json`（带边界断言、4 处来源锚点、3 条不确定性、冲突并列登记）。
两稿均为合成示例，仅演示接口。

## 运行

```bash
bash examples/run_example.sh
```

## 实跑结果（示例产物，标注为合成示例）

1. `overclaim_lint` 扫基线稿：**exit 1**，命中 4 处无边界越界断言
   （`examples/output/lint_pass0.json`）；
2. `overclaim_lint` 扫严谨稿：**exit 0**（边界限定词使断言解绑）；
3. `gain_meter` 差分（`examples/output/gain/`）：填充率 0.75→1.0、证据锚点 0→+4、
   无边界越界断言 4→0、不确定性 0→+3、冲突登记 0→+3，**五项判定全过**。

关键观察点：增益结论不来自文字自述，而来自可对同一输入独立重算的指标差分；
若严谨稿某一维度无增益，判定会真实地打出 ✗。
