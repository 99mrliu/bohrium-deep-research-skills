# 最小调用示例（合成示例，非正式案例）

输入为**手工合成的两页保版式文本**（模拟 `pdftotext -layout` 输出；数据为虚构，
仅版式模式真实）：

- `inputs/page01.txt`：空白对齐表 Table 1（4 列、一个折行单元格
  "not detected / (below 1 %)"、一个空数据格）；
- `inputs/page02.txt`：线框表 Table 2（一个空数据格）；
- `inputs/case.json`：合成契约（tables / machine_readable / provenance）。

复现：

```bash
python3 ../../scripts/extract_layout.py --layout-dir inputs --out /tmp/tg_work
python3 ../../scripts/detect_tables.py --pages /tmp/tg_work/pages --out /tmp/tg_work
python3 ../../scripts/reconstruct_grid.py --index /tmp/tg_work/tables_index.json \
  --pages /tmp/tg_work/pages --case inputs/case.json --out /tmp/tg_out
```

`outputs/` 为技能作者机器上**真实执行**产物（2026-11-23），已目检：

- Table 1 四列归属正确，折行 "(below 1 %)" 并入第 3 行 Yield 格（`wrapped: true`）；
- 两处空数据格标 `unresolved`（⚠），未填猜测值；
- `result.json` 的 `status=partial` 是**诚实状态**：歧义全部在
  `reconstruction_report.json` 与 `uncertainty` 中落盘。
