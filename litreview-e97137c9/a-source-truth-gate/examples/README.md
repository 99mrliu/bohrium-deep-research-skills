# 合成示例（SYNTHETIC EXAMPLE）

本示例为**合成演示**，所有文献与研究问题均为虚构，不冒充正式案例结果。

## 运行

```bash
python3 examples/make_example.py /tmp/stg-demo
```

## 演示内容

- 4 篇虚构短文：D1 全文、D2 全文（结论与 D1 冲突，且 case 元数据年份故意写错）、
  D3 仅摘要、D4 是 D1 的换题近重复。
- `run_case.py init` 真实执行：解析、分级、近重复检测，并由 `source_forensics.py`
  检出 D2 元数据冲突（降级 T2）、裁定 D4 为 duplicate_of D1。
- 模拟模型阶段产物（标注 simulated）写入后，`verify` 真实执行引用门控：
  逐字摘录校验 + 信任强制；`finalize` 组装 result.json。

## 查看点

- `/tmp/stg-demo/work/forensics_report.md`：信任分层与身份核验结果。
- `/tmp/stg-demo/output/gate_report.json`：门控明细。
- `/tmp/stg-demo/output/result.json`：终版结构化结果（含 output_contract 全部字段）。
