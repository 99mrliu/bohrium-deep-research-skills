# 最小调用示例（合成示例，非正式测试案例）

`input/` 为**合成数据**：7 条参考题录、2 条查询。

## 运行

```bash
python3 scripts/governance_forge.py \
  --input examples/input --work examples/run/work --output examples/run/output
python3 scripts/governance_forge.py \
  --input examples/input --work examples/run/work --output examples/run/output --replay
```

## 预期产物（合成示例输出）

- 覆盖：分母 7、命中 5、漏检 2（R003、R007），覆盖率 0.7143；
- `examples/run/work/audit_report.json`：确定性抽样 3 条（R001/R004/R007），独立包含度匹配复核，一致率 1.0、无分歧；
- `examples/run/work/run_manifest.json`：脚本哈希 + 4 份输入哈希 + 4 个阶段哈希；
- 第二条命令（`--replay`）输出 `{"replay_ok": true, "drifted_stages": []}`，退出码 0；
- `examples/run/output/coverage_report.md`：关键数字带 [B1]–[B6] 绑定号；`coverage_chart.svg` 为同数据文本渲染图；
- `examples/run/output/result.json`：含 case_id 与契约全部 7 个字段。

`examples/run/` 下产物为真实执行生成，仅作接口对照，不代表正式案例成绩。
