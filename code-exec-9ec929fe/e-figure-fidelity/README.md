# figure-fidelity（challenge-9ec929fe 作品 E）

下游渲染工程重心：每张图强制三件套（PNG + .data.csv + .receipt.json），
lint 机检列名/PNG 哈希/值域/单位-字典/轴标签一致性，check 核对
result.json figures 字段；无 matplotlib 时诚实降级，绝不交付不存在或
内容不符的图。lint/check 纯标准库。

## 使用

```bash
python3 scripts/figkit.py render --table clean.csv --kind hist --x strength \
  --xlabel "strength (MPa)" --title "..." --out /app/output/fig1.png
python3 scripts/figkit.py lint --receipts /app/output/*.receipt.json \
  --dictionary /input/data_dictionary.json
python3 scripts/figkit.py check --result /app/output/result.json
```

## 合成示例

`bash examples/run_example.sh` —— 渲染两图并通过 lint → 演示单位写错被
lint 拦截 → `FIGKIT_NO_MPL=1` 降级演示 → check 通过。数据人工合成。

详见 [SKILL.md](SKILL.md) 与 [references/figure_checklist.md](references/figure_checklist.md)。
