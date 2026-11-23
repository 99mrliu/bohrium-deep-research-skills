# 最小调用示例（合成示例，非正式案例结果）

演示「草稿 → lint → 修复」接口。材料为虚构论文片段（见 source_excerpt.txt 首部声明）。

## 运行

```
python3 SKILL_DIR/scripts/atomize_lint.py \
  --claims claims.draft.jsonl \
  --out lint-report.json
```

预期：退出码 0，报告含 8 条断言的逐条 verdict（pass 为主，允许 W_* 待审项），
`expected/lint-report.json` 为本机真实运行产物（标注：合成示例）。

## 接口说明

- 输入 `claims.draft.jsonl`：每行一条断言，字段见 ../../references/field-dictionary.md。
- 输出 lint 报告：`summary.gate=pass|fail`；`E_*` 需修复，`W_*` 需人工判读留痕。
- 本示例不依赖网络与第三方库；正式案例中 claims 由 Agent 从真实论文拆解产生。
