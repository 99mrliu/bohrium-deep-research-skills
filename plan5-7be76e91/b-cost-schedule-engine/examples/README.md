# 合成示例 / SYNTHETIC EXAMPLE — 运行说明

本目录全部输入与输出均为**合成示例**，数字是虚构演示值，不是真实案例结果、
不是真实报价或实测数据。

## 文件

- `case.example.json`：虚构案例（budget=20000、deadline_days=30、
  workday_hours=8、rubric 权重 cost 0.6 / time 0.4、output_contract 示例键）。
- `contract_pricing.example.md`：虚构价格/预订契约文本（模型抽取条目的"材料"）。
- `plan_record_P1.json`：P1 便宜但慢（总成本 8480.9，自然周期 27 天）。
- `plan_record_P2.json`：P2 贵但快（总成本 14800，自然周期 9.2 天，含返工期望
  `0.2 × 1 day = 1.6 h`）。
- `plan_record_P3.json`：P3 被支配方案（总成本 14100 > P1，周期 28 天 > P1 的
  27 天，被 P1 严格支配）。
- 三份 booby-trap 负例：
  - `plan_record_bad_missing_price.json`：条目缺 `unit_price`；
  - `plan_record_bad_overbudget.json`：总成本 30000 超预算 20000；
  - `plan_record_bad_probability.json`：`rework_probability=1.4` 越界。
- `outputs/`：以下命令序列**真实跑出**的产物（json + md）。

## 命令序列（在 examples/ 目录下执行）

```bash
# 1) 三份好方案：成本台账（exit 0）
for P in P1 P2 P3; do
  python3 ../scripts/cost_ledger.py --plan plan_record_$P.json --out-dir outputs
done

# 2) 三份好方案：时间模型 + 预算/截止门（exit 0，gate=pass）
for P in P1 P2 P3; do
  python3 ../scripts/time_model.py --plan plan_record_$P.json \
    --case case.example.json --ledger outputs/ledger_$P.json --out-dir outputs
done

# 3) Pareto 前沿与推荐（exit 0；前沿={P1,P2}，P3 被 P1 支配，
#    按 case rubric 权重推荐 P2，rule_source=case_rubric）
python3 ../scripts/pareto.py --case case.example.json --out-dir outputs \
  --plan P1:outputs/ledger_P1.json:outputs/time_P1.json \
  --plan P2:outputs/ledger_P2.json:outputs/time_P2.json \
  --plan P3:outputs/ledger_P3.json:outputs/time_P3.json

# 4) booby-trap 负例（均应 exit 3，且产物仍写出到 outputs/）
python3 ../scripts/cost_ledger.py --plan plan_record_bad_missing_price.json --out-dir outputs
#   -> exit 3，缺陷：条目[微量滤膜（缺单价陷阱）] 缺 unit_price
python3 ../scripts/cost_ledger.py --plan plan_record_bad_overbudget.json --out-dir outputs   # exit 0
python3 ../scripts/time_model.py --plan plan_record_bad_overbudget.json \
  --case case.example.json --ledger outputs/ledger_BADBUDGET.json --out-dir outputs
#   -> exit 3，GATE_TRIGGERED: over_budget（30000 > 20000）
python3 ../scripts/cost_ledger.py --plan plan_record_bad_probability.json --out-dir outputs  # exit 0
python3 ../scripts/time_model.py --plan plan_record_bad_probability.json \
  --case case.example.json --ledger outputs/ledger_BADPROB.json --out-dir outputs
#   -> exit 3，缺陷：rework_probability 必须在 [0,1]: 1.4

# 5) 端到端自查（应 exit 0）
python3 ../scripts/selfcheck.py
```

## Decimal 精确性演示（易错算例）

P1 的「微量滤膜」条目 `unit_price=0.1, quantity=7`：

- float 运算：`0.1 * 7 = 0.7000000000000001`（有尾差）；
- 本引擎：`outputs/ledger_P1.json` 中该条目 `line_total` 恰为字符串 `"0.7"`，
  耗材小计恰为 `"480.9"`（0.7 + 0.2 + 480），全链路 `decimal.Decimal`，
  `parse_float=Decimal` 从源头杜绝 float。`selfcheck.py` 对这两个值做精确断言。

## 双跑字节一致

完整流程（好例三方案 + pareto）在任意两个不同输出目录各跑一遍后
`diff -r` 无差异；`selfcheck.py` 内置该校验（产物不含绝对路径、不含时间戳）。
