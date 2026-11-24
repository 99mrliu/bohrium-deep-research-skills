# 最小示例（合成示例，非正式案例结果）

演示取证门禁完整流程。输入为**合成数据**：两个 csv 批次文件，埋入完全重复
文件、行级重复、饱和段、常量列、单位歧义五类签名。

## 运行

```bash
cd examples
python3 make_synthetic_input.py --outdir ./demo
python3 ../scripts/run_gate.py --input ./demo/input --work ./demo/work --output ./demo/output
python3 ../scripts/gate_result.py check --case ./demo/input/case.json --out ./demo/output/result.json || true
```

## 预期（captured 于 expected/）

- `verdict=PASS_WITH_FLAGS`：findings 含 identical_files、duplicate_data_rows、
  saturation_suspects、constant_columns、unit_ambiguity（浓度 ↔ mg/mL, ug/mL）；
- result.json 的「异常点」「复核步骤」「依据与风险」「确认项」「数据质量评估」
  由脚本预填；若有未映射字段则保持 partial 并在 limitations 点名；
- 演示门禁规则：存在 flags 时不允许直接 success，须逐条处置后 update。

`expected/` 为一次真实本地运行的输出副本（数值为合成数据结果）。
