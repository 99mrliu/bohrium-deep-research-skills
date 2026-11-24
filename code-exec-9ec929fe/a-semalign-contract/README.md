# semalign-contract（challenge-9ec929fe 作品 A）

上游契约与字段语义对齐门禁：把 `output_contract` 编译成机检契约、把数据字典
字段与实际列名归一化对齐、先落盘诚实 result.json 骨架、交付前契约门拦截
"看起来完成了"。纯 Python 标准库，零第三方依赖。

## 使用

```bash
python3 scripts/semalign.py inspect --input /input --work /app/work --output /app/output
# ... Agent 完成真实计算，填充 /app/output/result.json ...
python3 scripts/semalign.py gate --input /input --output /app/output
```

## 合成示例

`bash examples/run_example.sh` —— 端到端跑通 inspect → 计算填充 → gate，
数据为人工合成（见 `examples/synthetic_case/`），输出仅为接口演示。

详见 [SKILL.md](SKILL.md) 与 [references/contract_protocol.md](references/contract_protocol.md)。
