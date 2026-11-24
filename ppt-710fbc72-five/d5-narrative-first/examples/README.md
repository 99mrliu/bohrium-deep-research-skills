# examples — 合成示例（非正式测试案例）

本目录脚本演示 narrative-first-deck 的完整接口。**所有案例数据均为合成**
（`scripts/make_synthetic_case.py` 现场生成的 LeafNet-S 虚拟论文，无真实科研结论），
仅用于说明接口与流程，不冒充正式案例结果。所有产物写入 `$(mktemp -d)` 临时目录，
**绝不写回 bundle**。

## run_example.sh — 端到端正例

```bash
bash examples/run_example.sh
```

流程（非交互）：
1. `make_synthetic_case.py --outdir $TMP/input`：生成 template.pptx（python-pptx 默认
   母版/版式/占位符）、paper.pdf（4 个文本页 + Figure 1/2 两个图页）、case.json
   （case_id=`synthetic-demo-05`）、task.md（audience: 研究生组会；duration: 8 minutes；
   slides: 6-8）。
2. `run_case.py prepare`：PyMuPDF 抽取论文（全文、图、表、数字候选句）→ 解剖模板 →
   立即写 partial result.json → 预填 storyline.json / slide_plan.json 骨架。
3. `fill_example_plan.py`：代替 Agent 完成创作步骤，自动写齐 storyline（7 条 claim
   的依赖图）与 7 页 slide_plan，notes 长短不一以真实触发计时预算计算。
4. `run_case.py finish`：plan_lint 七条规则全过（含 8min±15% 计时表）→ 构建
   deck.pptx（模板版式 + 等比图 + 备注计时行）→ soffice 导出 deck.pdf → pdftoppm
   导出 preview/slide-*.png → qa_report 页数一致 → 最终 result.json。

脚本结尾打印产物清单与计时表。

## lint_negative_demo.sh — 顺序违规负例

```bash
bash examples/lint_negative_demo.sh
```

在临时目录的计划副本中对调 method 页与 results 页（results 先于 method 讲），
`plan_lint.py` 必须 fail 并在 R5_order 中精确指出违规 slide 编号与 claim id，
退出码非零、构建被拒绝。脚本在门禁按预期失败时打印违规详情并返回 0。
