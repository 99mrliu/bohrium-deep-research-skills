# examples/minimal — 修复闭环合成演示

**这是合成示例**：虚构的"微型藻类光生物反应器流程"（源文本 `sources/excerpt.txt`
开头已标注"合成示例"），用于端到端演示 render→QC→修 IR→re-QC 闭环。全部 JSON/SVG
报告均为脚本真实输出，非手写。

## 剧情

- `figure_ir.v1.json` — 预埋 4 处缺陷：
  1. 边 e2 指向不存在的节点 `n9`（→ DANGLING_EDGE，IR 级 + 几何级各报一条）
  2. 步骤编号 order = 1,2,4 跳号（→ NUMBERING_GAP）
  3. IR legend 把"物料流"色块写成 #e37702，与边实际用的 #1f77b4 不符（→ LEGEND_MISMATCH）
  4. n2 标签"光照恒温培养光生物反应器（内置LED阵列）"超长（→ TEXT_OVERFLOW）
- 复现 round 1：
  `python3 ../../scripts/repair_loop.py --ir figure_ir.v1.json --workdir . --source-dir sources --out-dir /tmp/c_qc_out`
  → 退出码 2（needs_repair），`qc_report.round1.json` 记录 5 error / 1 warn
  （额外 warn 是 LABEL_SOURCE_MISMATCH：超长标签词元在源文本中找不到，符合预期）。
- `figure_ir.v2.json` — agent 修复：e2.to 改为 n3；order 重排 1,2,3；删除显式 legend
  （改自动图例）；标签缩短为源文本原词"光照恒温培养反应器"。
- 复现 round 2：同上命令换 `--ir figure_ir.v2.json` → 退出码 0（clean），
  `qc_report.round2.json` 为 0 error / 0 warn。

## 文件清单

| 文件 | 说明 |
|---|---|
| figure_ir.v1.json / figure_ir.v2.json | 修复前/后 IR |
| sources/excerpt.txt | 虚构源文本（合成示例） |
| figure.round1.svg / figure.round2.svg | 两轮渲染的 SVG（before/after） |
| figure.svg | 最终交付 SVG（= round2，可复制编辑） |
| qc_report.round1.json | round1 质检报告：4 个预埋代码全部检出 |
| qc_report.round2.json | round2 质检报告：干净 |
| loop_log.json | 两轮记账：errors 5→0，status=clean |
| export_report.json | 导出报告（本机测试时 PDF/PNG 输出到 /tmp，回退链 cairosvg→rsvg→inkscape→chrome-headless） |

注：导出产物（figure.pdf/figure.png）按仓库约定不进 skill 目录，测试中生成于 /tmp；
`export_report.json` 记录了当时的真实路径与回退过程。
