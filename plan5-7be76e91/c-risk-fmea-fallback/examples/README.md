# examples — 合成示例 / SYNTHETIC EXAMPLE

**本目录全部输入与输出均为合成示例（SYNTHETIC EXAMPLE）：数字、论文、契约、设备均为虚构，仅演示脚本流程，不代表真实案例结果。**

## 场景

虚构规划情景 `case.example.json`：比较 3 个候选工艺方案（P1 旋涂 / P2 刮涂 / P3 热蒸发-CVD 混合），预算 120000 CNY、6 周交付。base 成本时间在 `base_inputs.json`。

- `risk_register_P1.json`：低风险正例（全部 low，verdict=acceptable_risk）。
- `risk_register_P2.json`：高 RPN 正例（2 条 high，有缓解、有回退；含一处 `likelihood_prob_override` 覆盖声明；P2-F1 需专家确认 → verdict=needs_expert）。
- `risk_register_P3.json`：**负例 booby-trap** —— P3-R1 为 critical（S=5）且 `fallback_ref=null`，必须被 `fallback_graph.py` 以 exit 3 捕获，verdict=infeasible_without_change。
- `risk_register_neg_empty_trigger.json`：负例 —— `trigger_condition` 为空（「存在一定风险」式空话），`fmea.py` exit 3。
- `risk_register_neg_cycle.json`：负例 —— 回退链成环 NEG-F1→NEG-F2→NEG-F1，`fallback_graph.py` exit 3。

## 命令序列（在 bundle 根目录执行）

```bash
# 合成示例标注：嵌入每个 JSON 产物顶层 note 键与 Markdown 产物首行引用块
NOTE="合成示例 / SYNTHETIC EXAMPLE：本报告由虚构输入生成，仅演示接口与流程，非正式案例结果。"

# 每个方案：fmea -> expected_cost -> fallback_graph
for p in P1 P2 P3; do
  python3 scripts/fmea.py --register examples/risk_register_$p.json \
      --outdir examples/outputs/$p --note "$NOTE"
  python3 scripts/expected_cost.py --register examples/risk_register_$p.json \
      --base examples/base_inputs.json --outdir examples/outputs/$p --note "$NOTE"
  python3 scripts/fallback_graph.py --register examples/risk_register_$p.json \
      --fmea examples/outputs/$p/fmea.json --outdir examples/outputs/$p --note "$NOTE"
done

# 多方案风险调整代价对比排序
python3 scripts/expected_cost.py \
  --register examples/risk_register_P1.json \
  --register examples/risk_register_P2.json \
  --register examples/risk_register_P3.json \
  --base examples/base_inputs.json --outdir examples/outputs/compare --note "$NOTE"
```

期望退出码：P1/P2 三脚本全部 0；P3 的 fmea=0、expected_cost=0、**fallback_graph=3**；compare=0。

负例验证：

```bash
python3 scripts/fmea.py --register examples/risk_register_neg_empty_trigger.json --outdir /tmp/neg1   # exit 3
python3 scripts/fmea.py --register examples/risk_register_neg_cycle.json --outdir /tmp/neg2          # exit 0
python3 scripts/fallback_graph.py --register examples/risk_register_neg_cycle.json \
    --fmea /tmp/neg2/fmea.json --outdir /tmp/neg2                                                    # exit 3
```

一键自查（含双跑字节一致）：`python3 scripts/selfcheck.py` → exit 0。

## outputs/ 实际产物

`outputs/{P1,P2,P3}/` 内含 `fmea.json/.md`、`expected_cost_<plan>.json/.md`、`fallback.json/.md`；`outputs/compare/` 内含 `comparison.json/.md` 与 `expected_cost_<plan>.json/.md`。全部为上述命令真实跑出（P3 的 fallback.* 是 exit 3 时仍写出的缺陷产物）；每个 JSON 产物顶层含 `note` 键、每个 Markdown 产物首行含 `> 合成示例 / SYNTHETIC EXAMPLE…` 引用标注。
