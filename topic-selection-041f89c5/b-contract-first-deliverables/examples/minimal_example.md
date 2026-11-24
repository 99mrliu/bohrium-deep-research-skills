# 最小调用示例（合成示例，非正式案例结果）

全部输入为**虚构合成数据**，仅演示接口与流程。

## 输入

- `input/case.json`：虚构案例，`case_id=SYNTH-DEMO-001`，`output_contract` 声明 4 个字段；
- `input/payload.json`：虚构的结构化评估载荷。

## 调用与预期输出（真实运行产生，已目检）

```bash
# 1. 契约编译 → 骨架
python3 scripts/contract_scaffold.py --case examples/input/case.json \
    --out examples/output/result_skeleton.json \
    --report examples/output/contract_fields.md
# stdout: {"case_id": "SYNTH-DEMO-001", "contract_fields": 4,
#          "runtime_fields_added": ["status", "provenance"]}

# 2. 确定性渲染 → 人读报告
python3 scripts/render_review_pack.py --payload examples/input/payload.json \
    --out examples/output

# 3. 契约校验：合规回填 → 通过
python3 scripts/contract_validate.py --case examples/input/case.json \
    --result examples/output/result_filled.json --out examples/output/check_filled
# 退出码 0，fill_rate=1.0

# 4. 契约校验：故意违约（缺 novelty_assessment 且 status=success）→ 拦下
python3 scripts/contract_validate.py --case examples/input/case.json \
    --result examples/output/result_bad.json --out examples/output/check_bad
# 退出码 1，硬失败："契约字段缺失: novelty_assessment"
```

产物见 `examples/output/`：`result_skeleton.json`、`contract_fields.md`、`evaluation_report.md`、`evidence_matrix.md`、`check_filled.{json,md}`、`check_bad.{json,md}`。
