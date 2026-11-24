# 最小调用示例（合成示例，非正式案例结果）

本示例的全部输入为虚构合成数据，仅用于演示接口与流程，不冒充正式案例结果。
`examples/output/` 下的产物是上述合成输入在本地真实执行脚本得到的真实输出。

## 输入（examples/input/）

- `case.json`：合成案例，case_id=`SYNTH-DEMO-0002`，output_contract
  声明 `deliverable`（必需）与 `evidence_map`（可选）两键；
- `result_parts/`：部件目录。`deliverable.md`、`status.txt`（partial）、
  `limits.md`、`uncertainty.md`、`change_log.md`、`sources.json` 齐备；
  **`evidence_map` 部件刻意缺失**，用于演示诚实 partial 的组装行为。

## 调用

```bash
python3 scripts/contract_inspect.py examples/input/case.json /tmp/cc-contract.json
python3 scripts/assemble_result.py /tmp/cc-contract.json \
    examples/input/result_parts /tmp/cc-out/result.json
python3 scripts/validate_output.py /tmp/cc-out \
    --case examples/input/case.json --report /tmp/cc-out/validation_report.md
```

## 输出（examples/output/，本地真实运行所得）

- `contract.json`：编译出的 2 个契约键（含 required/expected_kind 推断）；
- `result.json`：`status=partial`，`missing` 列出 `evidence_map`，
  该键值为 null（组装器不造内容）；`case_id` 与 case.json 一致；
- `validation_report.md`：终验 10 项全 PASS（partial + limits 非空
  即合规）。

退出码：inspect=0、assemble=0、validate=0。负向对照（本地已验证）：
把 result.json 中 deliverable 改成不存在的文件名后重跑终验，
"引用文件存在"与"存在可编辑交付物"两项 FAIL、退出码 1——悬空引用
无法通过终验。
