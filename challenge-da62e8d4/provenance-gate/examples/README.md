# 合成示例（synthetic），非正式案例结果

本目录中的论文、case、目标值、预期输出全部是为验证 `provenance-gate` 工具行为而构造的最小合成示例。它们不来自真实论文，不代表正式评测案例，也不能用于任何复现结论。

运行：

```bash
bash /path/to/provenance-gate/examples/run_example.sh /tmp/provenance-gate-example
```

预期命令最终退出码为 `1`：`targets.json` 前两条引文通过，第三条故意臆造的引文必须进入 `quarantined.json`，且报告首行为 `GATE: FAIL`。
