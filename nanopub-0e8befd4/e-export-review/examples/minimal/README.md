# 最小调用示例（合成示例，非正式案例结果）

`claims.json` 为虚构冷链传感论文 CryoMesh 的 20 条断言（同时充当本技能的 20 条
断言样例），含 asserted / not_reported（E-18，带检索范围）/ conflict（E-19↔E-20，
正文内部版本表述冲突）三种状态，用于演示导出与复核单的分组渲染。

## 运行

```
python3 SKILL_DIR/scripts/export_bundle.py --claims claims.json --outdir out
python3 SKILL_DIR/scripts/check_exports.py --claims claims.json --export-dir out --out out/export-check.json
```

预期：导出 gate=pass；回读 verdict=PASS（JSONL/CSV 条数与 ID 集合一致、列序一致、
manifest 哈希一致、review.md/html 覆盖全部 ID）。`expected/` 为本机真实运行产物
（合成示例）。正式案例中 claims.json 由 Agent 从真实论文拆解产生。
