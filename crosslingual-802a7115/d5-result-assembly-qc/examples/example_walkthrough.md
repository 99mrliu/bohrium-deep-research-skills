# 最小调用示例（合成示例 / SYNTHETIC EXAMPLE）

> 本示例使用 `examples/data/` 的**合成玩具数据**（case_id 为 `synthetic-demo-001`，
> 不是平台正式案例），仅说明接口与产物形态。

## 输入（合成）

- `case.json`：合成案例，output_contract 点名 7 个字段（research_question、hits、
  coverage、evidence_records、sources、uncertainty、status）。
- `values.json`：Agent 汇总值——2 条 hit（pt 原文视图＋en 译文视图，归因完整，
  null 归因附 attribution_note）、3 语种 coverage（es 为证据化缺失说明）、
  去重计数说明。**刻意不供给 evidence_records**，演示契约字段 null＋留痕。

## 调用与产物（本次实际运行已目检）

```bash
python3 scripts/assemble_result.py --case examples/data/case.json \
    --values examples/data/values.json --out examples/out
# → {"status": "ok", "case_id": "synthetic-demo-001",
#    "contract_fields": 7, "nulled_fields": ["evidence_records"]}

python3 scripts/contract_check.py --case examples/data/case.json \
    --result examples/out/result.json --out examples/out/qc
# → {"overall": "pass", "fails": []}
```

`examples/out/result.json`：`evidence_records` 写为 null，且 null 在
change_records 与 uncertainty 中均有认领（C2 通过）。8 项检查全 pass
（见 `examples/out/qc/qc_report.md`）。

## 反例演示（同次验证）

把 values 改坏（删一条 hit 的 locator、coverage 加空 `de` 条目）重跑，
QC 输出 `overall: fail`，精确指出：
`C4 hit 0: no locator/source_file/evidence`、`C5 de: no hits and no note`。
fail 项修复前不得交付。

## 复核方式

对照 `qc_report.md` 逐条 verdict 与 detail；随机抽 result.json 中一条 hit，
用其 locator（`examples/data/case.json#synthetic-demo-001/w1-pt-full`）回指原始记录确认归因一致。
