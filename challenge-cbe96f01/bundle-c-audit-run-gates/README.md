# audit-run-gates

引用与事实核验的**过程质量控制**门控协议：五阶段 checkpoint 流水线 + G0–G9 机器门控 + 确定性重放，保证"换一个人按记录复核能得到同一批结论"。详见 [SKILL.md](SKILL.md)。

## 布局

- `SKILL.md` — Skill 本体（运行契约、五阶段门控流水线、交付契约、异常处理）
- `scripts/ingest.py` — 确定性材料解析（同输入同输出，无时间戳）
- `scripts/anchor_index.py` — 段落/图表/参考文献锚点表
- `scripts/gate_check.py` — 交付总门 G1–G8（身份、契约、覆盖、结构、位置真实、词表、诚实一致、日志）
- `scripts/replay_diff.py` — 门 G9：确定性产物重放比对
- `references/` — 门的语义基准与诚实 partial 规则
- `examples/` — **合成示例**（`bash examples/run_example.sh`）

## 快速自检

```bash
bash examples/run_example.sh
# 期望：replay_diff 通过（exit 0）；
# 诚实的 partial result 过门（exit 0）；
# 埋雷 result 被拦下（exit 1：G2 缺契约字段 / G5 编造摘录 / G6 非法词表 / G7 completed 却有 unchecked 覆盖）
```

无第三方依赖：Python ≥3.8 标准库；PDF 用系统 `pdftotext`（可回退纯文本）。
