# 20 条断言样例（合成示例，非正式案例结果）

`source_excerpt.txt` 为虚构论文片段（含摘要、方法、结果、局限四节）；`claims.jsonl`
是对它的 20 条原子断言拆解，覆盖：并列功能拆分（T-004/005）、多基准比较拆分
（T-007/008、T-016）、方向相反的混合比较句拆分（T-017/018）、参数逐条化（T-010/011）、
模态保留（T-009 proposed）、无显著差异 ≠ 等价（T-019）、否定极性编码（T-020）。

可直接复用为拆解风格的参照，或用 lint 自检：

```
python3 SKILL_DIR/scripts/atomize_lint.py --claims claims.jsonl --out lint-20.json
```

预期 `summary.gate=pass`（本机实跑产物见 expected/lint-report.json）。
样例是接口与粒度示范，不是目标条数，也不是正式案例输出。
