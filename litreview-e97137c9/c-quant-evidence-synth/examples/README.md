# 合成示例（SYNTHETIC EXAMPLE）

本示例为**合成演示**，所有文献与研究问题均为虚构，不冒充正式案例结果。

## 运行

```bash
python3 examples/make_example.py /tmp/qes-demo
```

## 演示内容

- 4 篇虚构短文：
  - **D1** 全文：recall@10 = 0.74（95% CI [0.68, 0.80]，n = 480，p < 0.01）、延迟 350 ms。
  - **D2** 全文：recall@10 = 0.52（与 D1 相对差异 >20% 且 CI 不重叠 → **演示数值冲突检测**）；
    延迟 0.31 s（与 D1 的 ms **单位不一致 → 演示归一化后比较**）。
  - **D3** 仅摘要（abstract_only）：precision 0.81（单源）、RMSE 4.2（无单位 → **演示 unnormalized**）。
  - **D4** 为 D1 的换题近重复（**演示冲突检测只取代表篇**）。
- `run_case.py init` 真实执行：解析、数值候选抽取、单位归一化、冲突检测。
- 模拟模型阶段产物（标注 simulated）写入后，`verify` 真实执行数字回链门控：
  草稿与证据表中的数字全部由脚本从 quant candidates 程序化取值（含 81%≡0.81
  与 350 ms≡0.35 s 的等价写法），保证回链通过；`finalize` 组装 result.json。

## 查看点

- `/tmp/qes-demo/work/quant_candidates.jsonl`：数值候选（含 p<页>.¶<段> 定位与指标名）。
- `/tmp/qes-demo/work/quant_normalized.jsonl`：归一化后的 canonical 值与量纲。
- `/tmp/qes-demo/work/numeric_conflicts.json`：数值冲突候选（供模型裁决，不调和）。
- `/tmp/qes-demo/output/quant_gate_report.json`：数字回链门控明细。
- `/tmp/qes-demo/output/result.json`：终版结构化结果（含 output_contract 全部字段）。
