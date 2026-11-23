# 最小调用示例（合成示例，非正式案例结果）

同一虚构论文的两个版本（v1/v2）+ 6 条断言，演示：指纹核验、跨版本合并
（C-03/C-04 同语义键 → 双来源绑定）、版本修订冲突（C-01 22% vs C-02 24%）、
仅旧版断言（C-05）与仅新版断言（C-06）的版本对照。

## 运行（在本目录下）

```
python3 SKILL_DIR/scripts/mint_nanopubs.py \
  --claims claims.jsonl --sources sources.json --outdir out
```

预期：`summary.unique_claims=5`、`merged_events=1`、`conflicts=1`、
`version_chains[0]` 含 only_old/only_new 各 1 个键；`gate=pass`（指纹 ok）。
`expected/` 为本机真实运行产物（合成示例）。正式案例中来源为真实论文文件，
路径用绝对路径。
