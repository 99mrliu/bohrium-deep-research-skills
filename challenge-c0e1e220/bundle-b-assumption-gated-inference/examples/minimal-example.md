# 最小示例（**合成示例**，非真实数据）

本示例数据由 `make_synthetic.py` 以固定种子（20240503）现场生成，**为合成
示例（synthetic）**，仅用于演示假设门控与决策审计，不具有真实科学含义。

## 输入（生成）

```bash
python3 make_synthetic.py --out /tmp/synth/input
```

生成 `synthetic_demo.csv`（列：value, pair_group, trio_group）+ `case.json` +
`task.md`：

- `pair_group`：skew_low / skew_high，各 n=12，**对数正态**生成（右偏）→
  期望门控：K² 拒绝正态 → `mannwhitney_u`，reason_codes 含 `NORMALITY_FAIL`；
- `trio_group`：norm_A / norm_B / norm_C，各 n=25，近似正态 →
  期望门控：正态 + 方差齐 → `anova`。

## 调用

```bash
python3 ../scripts/pipeline_b.py run \
  --input-dir /tmp/synth/input --work-dir /tmp/synth/work --output-dir /tmp/synth/output
python3 ../scripts/decision_audit.py --input-dir /tmp/synth/input \
  --result /tmp/synth/output/result.json     # 期望 exit 0
```

## 示意输出（真实产物见 example_output/）

- `example_output/result.json` — 完整交付 JSON（9 个 contract 字段 +
  decision_log 等）；
- `example_output/decision_log_excerpt.md` — 决策链摘录，形如：

```
A1 — value @ pair_group（two_group）
- 各组 n 与正态性: skew_high n=12 K2_p=0.0000 -> non_normal; skew_low n=12 K2_p=0.86 -> normal
- Levene(median): p=0.62 -> homogeneous
- reason_codes: NORMALITY_FAIL:skew_high p=0.0000 → SELECT mannwhitney_u
```

- `example_output/audit_pass.txt` — 审计 PASS 日志。

## 一键自校验（含埋雷）

```bash
bash run_example.sh    # 好例 exit 0；3 个埋雷分别命中
                       # TEST_MISMATCH / P_MISMATCH / ASSUMPTION_MISMATCH（exit 1）
```
