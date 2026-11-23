# 最小调用示例（合成示例，非正式案例结果）

演示「索引 → 锚定」接口，含三种定位形态：常规唯一匹配（B-001）、跨行连字符修复
（B-002，transpira-\ntion）、重复短语歧义消解（B-003，page_hint=2）。

## 运行

```
python3 SKILL_DIR/scripts/index_source.py \
  --input synthetic_source.txt --source-id SYNTXT --out /tmp/src-index.json

python3 SKILL_DIR/scripts/verify_anchors.py \
  --source /tmp/src-index.json --claims claims.jsonl --out /tmp/anchor-report.json
```

预期：退出码 0；B-001/B-002/B-003 均 `verified`；B-002 产生 `dehyphenation`
change_record；B-003 带 `W_PAGE_HINT` 提示。`expected/` 为本机真实运行产物
（合成示例）。正式案例中材料为真实论文文件，索引与断言由 Agent 现场生成。
