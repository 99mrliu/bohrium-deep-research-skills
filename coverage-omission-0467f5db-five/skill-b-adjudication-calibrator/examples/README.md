# 最小调用示例（合成示例，非正式测试案例）

`input/` 为**合成数据**：10 条参考题录（1 条无标识符）、3 条查询的命中结果、8 对带标签的标定片段（含灰区样本与标识符冲突样本）。

## 运行

```bash
python3 scripts/adjudication_engine.py \
  --input examples/input --work examples/run/work --output examples/run/output
```

## 预期产物（合成示例输出）

- `examples/run/work/calibration_report.json`：8 对样本在 8 个阈值下的混淆矩阵与 Wilson95 区间；标定片段小于 10 对，因此只给建议、不改写冻结阈值；
- `examples/run/work/adjudication_ledger.json`：逐条裁决——6 条 hit（5 条 L1、1 条 L2），R007 落入灰区 [0.65,0.80) 进 L3 队列并保守计 miss；
- `examples/run/output/coverage_report.md`：分母 10、命中 6、漏检 4（含 1 条 L3 待裁），覆盖率 0.6000 附 Wilson95 区间；
- `examples/run/output/result.json`：含 case_id 与契约全部 7 个字段。

`examples/run/` 下产物为真实执行生成，仅作接口对照，不代表正式案例成绩。
