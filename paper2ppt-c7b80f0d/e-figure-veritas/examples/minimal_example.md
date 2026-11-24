# 最小调用示例

> **合成示例，非平台案例结果。** 以下输入由 `make_synthetic_case.py` 现场生成，
> 所有文字与数值均为虚构（"Synth et al." / fictional / synthetic）。

```bash
# 1. 生成合成输入（paper.pdf / data.csv / case.json / task.md / 模板）
python3 examples/make_synthetic_case.py --out-dir /tmp/fv-demo/input

# 2. 收割 + 分类
python3 scripts/fig_harvest.py /tmp/fv-demo/input/paper.pdf \
  --out-dir /tmp/fv-demo/work/figs --manifest /tmp/fv-demo/work/figure_manifest.json
python3 scripts/fig_classify.py /tmp/fv-demo/work/figure_manifest.json \
  --report /tmp/fv-demo/work/classify_report.json
# 预期：fig1=data-figure（caption 含 measured/response），
#       fig2=schematic（caption 含 schematic），table1=table-image。

# 3. 撰写 spec.json（values 逐值抄自 data.csv），重绘并核验
python3 scripts/chart_redraw.py /tmp/fv-demo/work/spec_fig1.json \
  --data /tmp/fv-demo/input/data.csv --out /tmp/fv-demo/work/figs/redrawn_fig1.png
python3 scripts/redraw_verify.py /tmp/fv-demo/work/spec_fig1.json \
  --data /tmp/fv-demo/input/data.csv --report /tmp/fv-demo/work/redraw_report.json
# 预期：matched=12 mismatched=0，exit 0。
# 反例：把 spec 中任一数值改 0.01，redraw_verify 退出码变 1（门禁生效）。

# 4. 撰写 deck.json（results 页只挂 redrawn-from-data 的 fig1；
#    schematic 的 fig2 只能出现在 background 页，provenance=schematic-reference）
python3 scripts/fig_binding_lint.py /tmp/fv-demo/work/deck.json \
  /tmp/fv-demo/work/figure_manifest.json --report /tmp/fv-demo/work/binding_report.json
# 反例：把 results 页的 figure id 改成 fig2，lint 报 schematic-in-results，exit 1。

# 5. 构建 + 渲染 + 汇总
python3 scripts/build_deck.py /tmp/fv-demo/work/deck.json \
  --template /tmp/fv-demo/input/target-template.pptx \
  --fig-dir /tmp/fv-demo/work/figs --manifest /tmp/fv-demo/work/figure_manifest.json \
  --out /tmp/fv-demo/output/presentation.pptx --report /tmp/fv-demo/work/build_report.json
python3 scripts/make_result.py --case /tmp/fv-demo/input/case.json \
  --task /tmp/fv-demo/input/task.md --deck /tmp/fv-demo/work/deck.json \
  --pptx /tmp/fv-demo/output/presentation.pptx \
  --manifest /tmp/fv-demo/work/figure_manifest.json \
  --classify-report /tmp/fv-demo/work/classify_report.json \
  --redraw-report /tmp/fv-demo/work/redraw_report.json \
  --binding-report /tmp/fv-demo/work/binding_report.json \
  --render --render-dir /tmp/fv-demo/output --work-key demo \
  --out /tmp/fv-demo/output/result.json
```

deck.json / spec_fig1.json 是 Agent 依据真实输入撰写的结构文件，模式见
`scripts/fig_binding_lint.py` 与 `scripts/chart_redraw.py` 的 docstring。
