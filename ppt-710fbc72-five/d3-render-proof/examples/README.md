# 合成示例（synthetic-demo-03）

**这是合成示例，不是正式评测案例，不冒充任何真实结果。**
论文、模板、数字全部由 `scripts/make_synthetic_case.py` 现场生成。

## 运行

```bash
bash examples/run_example.sh
```

脚本在 `$(mktemp -d)` 临时目录中非交互执行全流程，**绝不写回 bundle**：

1. `make_synthetic_case.py --out $T/input`
   生成 case.json（case_id=synthetic-demo-03）、task.md、
   `materials/template.pptx`（python-pptx 默认母版/版式/占位符）、
   `materials/paper.pdf`（4 页文字 + 2 页图，matplotlib PdfPages）。
2. `run_case.py prepare`：依赖自检 → PyMuPDF 抽取论文（全文/页文本/页图/
   图候选）→ 立即写 partial 骨架 result.json → 预填 slide_plan.json
   （含 `_candidates`：章节/图/数字候选）→ 打印 NEXT ACTION。
3. `fill_example_plan.py`：代替 Agent 创作步，自动填出 7 页计划。
   **故意把 results 页塞入 12 条长要点**，导出后必然触发 OVERFLOW。
4. `run_case.py finish`：构建 deck.pptx → soffice 导出 deck.pdf →
   pdftoppm 逐页 PNG → 像素 QA → **自动修复闭环**（溢出页 18pt→16pt
   降字号重渲，必要时阶梯继续/拆续页）→ 最终报告。

## 预期观察点

- `render_proof.json`：逐页 ink 覆盖率、overflow/images/empty 检查状态、
  页数一致性、字体替换清单、`fix_log` 修复留痕。
- 第 4 页（故意过载页）在首轮渲染 overflow=fail，修复后 pass；
  `fix_log` 至少 1 条 `font_step_down` 记录。
- `preview/slide-4.png` 修复前后对比可见：修复前最后一行被页面底边裁切。
- `result.json`：status=success（字体 warn 不影响）；重跑 finish 不产生新
  修复（幂等）。

临时目录路径会在结尾打印，用完可 `rm -rf`。
