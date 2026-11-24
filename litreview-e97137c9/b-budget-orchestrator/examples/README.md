# 合成示例（SYNTHETIC EXAMPLE）

本示例为**合成演示**，所有文献与研究问题均为虚构，不冒充正式案例结果。

## 运行

```bash
python3 examples/make_example.py /tmp/cfo-demo
```

## 演示内容

- 5 篇虚构短文：D1 全文（支持合成对照臂）、D2 全文（反对，与 D1 冲突）、D3 全文
  （监管视角）、D4 是 D1 的换题近重复（预印本版）、D5 仅摘要。
- `run_case.py init` 真实执行：ingest（解析/分级/近重复分组）→ contract_probe
  （contract_map.json + status=in_progress 的 partial result.json + requirements.md）
  → budget_ledger plan（run_plan.json + state.json，D4 被判 skip/duplicate_of D1）。
- `budget_ledger.py status` 打印剩余预算与阶段 checkpoint。
- **中断恢复演示**：在写入任何模型产物之前先运行一次 `check`，consistency_report
  指出全部阶段"未完成且产物缺失"（退出码 1）；随后写入标注 simulated 的模拟模型
  产物（screening/digests/themes/evidence_ledger/draft，摘录从 pages/*.jsonl 程序化
  抽取保证逐字），逐阶段 `budget_ledger.py mark` 登记，再次 `check` 通过。
- `finalize` 真实组装 result.json，最后再过一次 `check` 确认契约字段全部就位。

## 查看点

- `/tmp/cfo-demo/output/result.json`：初看 init 后的 partial（全 null），终看 finalize
  后的完整版（含 output_contract 全部 9 个字段与 budget_summary）。
- `/tmp/cfo-demo/work/run_plan.json`：预算分配、每篇文献的阅读深度与重叠得分、降级留痕。
- `/tmp/cfo-demo/work/state.json`：阶段账本（pending/completed、产物路径、实耗请求）。
- `/tmp/cfo-demo/output/consistency_report.json`：阶段-产物一致性、契约完备性、
  change_log 覆盖的校验明细。
- `/tmp/cfo-demo/work/contract_map.json` 与 `requirements.md`：契约字段产出计划与
  task.md 硬性要求提取结果。
