# 最小调用示例（合成示例，非正式测试案例）

`input/` 为**合成数据**：9 条参考题录（1 条无标识符）、两个来源共 5 条查询（第 1 轮 2 条、第 2 轮补检 2 条、第 3 轮补检 1 条同义词重跑零收益）。

## 运行

```bash
python3 scripts/ledger_engine.py \
  --input examples/input --work examples/run/work --output examples/run/output
```

## 预期产物（合成示例输出）

- `examples/run/work/query_ledger.json`：5 行账本——第 1 轮挽回 4 条，第 2 轮挽回 3 条（Q4 仅新增 R006，R009 重复命中不计），第 3 轮 Q5 零收益（`zero_gain=true`，"补检空转"的直接证据）；
- `examples/run/work/stop_decision.json`：S1 触发（账本行 5 为证），建议停止补检；S3 声明"不可评估"；
- `examples/run/work/residual_estimate.json`：两个来源族的 Chapman 校正 LP 估计，附三条假设与下界启发式 caveat；
- 覆盖：分母 9、命中 7、漏检 2（R007、R008 逐条列出）；
- `examples/run/output/result.json`：含 case_id 与契约全部 6 个字段。

`examples/run/` 下产物为真实执行生成，仅作接口对照，不代表正式案例成绩。
