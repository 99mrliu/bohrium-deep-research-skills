# 20 条断言锚定样例（合成示例，非正式案例结果）

`synthetic_source.txt` 为虚构农艺控制器论文摘录（3 个物理页，含表格转录与跨行连字符）。
`claims.jsonl` 为 20 条断言，覆盖：跨行连字符证据（G-004）、重复短语歧义消解
（G-009，page_hint=2）、表格单元格+表头证据（G-015/016/017）、否定极性（G-018）、
计划状态保留（G-020）。

## 运行

```
python3 SKILL_DIR/scripts/index_source.py \
  --input synthetic_source.txt --source-id SYN20 --out /tmp/src20-index.json
python3 SKILL_DIR/scripts/verify_anchors.py \
  --source /tmp/src20-index.json --claims claims.jsonl --out /tmp/anchor20-report.json
```

预期 `summary: verified=20, ambiguous=0, not_found=0, gate=pass`；本机实跑产物见
`expected/`。样例用于展示批量锚定接口与证据形态，不是正式案例输出。
