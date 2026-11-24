# 合成示例（synthetic example）— 非正式案例结果

本目录演示 `source-veritas-deck` 的完整接口与流程。**这是一个合成示例
（synthetic example）**：`paper.pdf` 里的"论文"、`template.pptx`、以及跑出来的
所有产物都由脚本现场生成，仅供演示接口，**不是**组织方正式案例的结果，
也不代表任何真实研究结论。

## 运行

```bash
bash examples/run_example.sh
```

脚本行为（全部在 `mktemp -d` 临时目录中，**绝不写回本 bundle**）：

1. `make_synthetic_case.py --out $EX/input` — 生成合成案例：
   - `materials/template.pptx`：python-pptx 默认模板（真实母版/版式/占位符，
     未改名），16:9；
   - `materials/paper.pdf`：matplotlib PdfPages 生成的 6 页"论文"
     （Title / Introduction / Method / Results+Limitations 四页文字 +
     Figure 1、Figure 2 两页图），含固定数字（accuracy 92.4%、n = 128、
     baseline 87.1%、p < 0.05、5.3 points、3.6 seconds、约 4%）；
   - `case.json`（`case_id: synthetic-demo-01` + `output_contract`）、
     `task.md`（受众/10 分钟/6–8 页约束）。
2. `run_case.py prepare` — 引导依赖 → 解析论文建语料台账
   （`work/corpus/corpus.jsonl` + `work/corpus/figs/`）→ 写 partial 骨架
   `result.json` → 预填 `slide_plan.json` → 打印 NEXT ACTION。
3. `fill_example_plan.py` — 代替 Agent 的创作步骤：从语料里抽取逐字句子、
   数字与图，自动填好 `slide_plan.json`（因此门禁必然通过；真实运行时由
   Agent 编辑此文件）。
4. `run_case.py finish` — **fidelity gate**（逐条核验）→ 构建 `deck.pptx`
   → soffice 导出 `deck.pdf` + `preview/slide-N.png` → `qa_report.json`
   → 定稿 `result.json`。
5. 打印 `$EX/output` 下全部产物及 sha256，以及 result.json 的 status。

## 预期产物（$EX/output）

| 文件 | 说明 |
|-|-|
| `result.json` | 含 output_contract 全部字段（case_id/status/summary/artifacts/evidence_map/sources/uncertainty/change_log） |
| `deck.pptx` | 用模板版式构建、可被 python-pptx 重新打开的可编辑文件 |
| `deck.pdf` | soffice 真实导出（缺 soffice 时记 degraded，不伪造） |
| `preview/slide-N.png` | pdftoppm 渲染的逐页预览 |
| `fidelity_report.json` | 本 skill 的标志性交付物：逐条断言核验报告 |
| `qa_report.json` | pptx 页数 vs PDF 页数、逐页渲染是否成功 |

## 负向自测（可选）

把 `$EX/work/slide_plan.json` 里某个数字改掉（例如 `92.4` → `99.9`），再跑：

```bash
python3 ../scripts/verify_fidelity.py \
  --plan $EX/work/slide_plan.json --corpus-dir $EX/work/corpus \
  --report /tmp/neg.json --out-plan /tmp/neg-plan.json --strict
```

门禁会把该 bullet 判为 `unverified`（strict 模式 gate=fail，退出码 1）。
