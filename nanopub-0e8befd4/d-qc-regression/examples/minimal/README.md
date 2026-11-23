# 最小调用示例（合成示例，非正式案例结果）

同一合成来源（synthetic_source.txt）配两份台账：

- `ledger.good.json`：4 条干净断言 → 预期 `gate=pass`、`status_cap=success`；
- `ledger.bad.json`：9 条含已知缺陷（改写引文、代词主语、抄错数值、抹掉模态、
  重复、未决冲突、缺检索范围）→ 预期 `gate=fail`、逐条 reject/review、
  `status_cap=partial`。

## 运行

```
python3 SKILL_DIR/scripts/qc_gate.py --ledger ledger.good.json --out /tmp/qc-good.json
python3 SKILL_DIR/scripts/qc_gate.py --ledger ledger.bad.json  --out /tmp/qc-bad.json
```

`expected/` 为本机真实运行产物（合成示例）。bad 台账退出码为 1 是预期行为
（有 reject）。缺陷的构造理由写在每条断言的 rationale 中，便于教学复用。
