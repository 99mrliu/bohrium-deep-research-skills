# examples — 合成示例（SYNTHETIC DEMO）

**本目录示例全部为合成数据，非正式测试案例、非预制答案。**
`make_synthetic_case.py` 生成的论文是虚构的（"Adaptive Grid Refinement for
Shallow-Water Solvers"，作者 A. Synthetic / B. Demo），模板主题也是演示用的
定制主题（major=Georgia / minor=Trebuchet MS / ea=SimHei，accent1=#8E44AD）。

## 运行

```bash
bash examples/run_example.sh
```

脚本在 `$(mktemp -d)` 中执行，**不会写回 bundle**：

1. `[0/4]` 生成合成案例到 `$TMP/input`：`template.pptx`（真母版/版式/占位符 +
   XML 级定制主题）、`starting_deck.pptx`（同模板 + 2 页待删旧页）、
   `paper.pdf`（4 页文本 + Figure 1/2 两页图）、`case.json`、`task.md`。
2. `[1/4]` `run_case.py prepare`：解剖模板 → `template_inventory.json`，
   抽取论文文本与页面渲染，预填 `slide_plan.json`，写 partial 骨架 result.json。
3. `[2/4]` `fill_example_plan.py` 自动把 plan 填完（代替 Agent 的创作步骤，
   版式名全部取自 inventory）。
4. `[3/4]` `run_case.py finish`：严格从起始稿/模板构建 `deck.pptx`（删除 2 页
   旧页并记录），跑 XML 级继承审计 → `inheritance_report.json`
   （期望 `overall_pass=true`、`theme_preserved=true`），导出 `deck.pdf` +
   `preview/slide-N.png` + `qa_report.json`，定稿 `result.json`。
5. `[4/4]` **负向主题指纹测试**：另用 python-pptx 默认主题做一个外来 deck，
   对其跑同一审计，验证 `theme_preserved=false`、`overall_pass=false` ——
   证明指纹确实能区分"真继承"与"换了主题"。

## 接口

- 输入：`--input`（case.json + task.md + 材料）、`--work`、`--output`。
- 产物（在 `$TMP/output`）：`deck.pptx`、`deck.pdf`、`preview/slide-*.png`、
  `inheritance_report.json`、`qa_report.json`、`result.json`。
- 中间件（在 `$TMP/work`）：`template_inventory.json`、`slide_plan.json`、
  `build_report.json`、`plan_lint.json`、`paper/`（text + figs）。

运行结束后脚本打印 tmpdir 路径，产物保留供人工检查。
