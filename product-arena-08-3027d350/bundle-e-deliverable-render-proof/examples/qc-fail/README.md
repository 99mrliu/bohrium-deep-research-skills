# qc-fail 示例：对账门捕获"静默丢块"（合成数据）

> **合成声明**：与 `examples/minimal/` 使用同一份编造的 `blocks.jsonl`；本例演示的是
> 渲染回归（交付物丢了一个块），不对应任何真实文档。

## 本例演示什么

`outputs/deliverable.md` 是先由 `render_preview.py` 真实生成、再**故意删除**块
`[[p1-b5]]`（连同其元信息行）得到的——模拟一个"静默丢块"的渲染回归。随后真实运行
`render_qc.py`，对账门必须捕获它。

## 复现

```bash
cd examples/qc-fail
MIN=../minimal
python3 ../../scripts/anchor_map.py --blocks $MIN/inputs/blocks.jsonl --out outputs/anchor_map.json
python3 ../../scripts/render_preview.py --blocks $MIN/inputs/blocks.jsonl \
    --anchor-map outputs/anchor_map.json \
    --out-md outputs/deliverable.md --out-html outputs/preview.html
# 然后手工（或脚本）从 outputs/deliverable.md 中删除 [[p1-b5]] 所在块，再运行：
python3 ../../scripts/render_qc.py --blocks $MIN/inputs/blocks.jsonl \
    --anchor-map outputs/anchor_map.json \
    --md outputs/deliverable.md --html outputs/preview.html \
    --case $MIN/inputs/case.json \
    --out-qc outputs/render_qc.json --out-result outputs/result.json --outdir .
# 预期退出码 3
```

## 预期并已被核实的输出（真实运行结果）

- `render_qc.json`：`status = "fail"`；计数 `blocks_in=20, map=20, md=19, html=20`；
  `deliverable_md.missing = ["p1-b5"]`；附 `handoff`（交还上游，禁止消费交付物）。
- `result.json`：`status = "failed"`；`case_id` 与 `output_contract` 全部字段仍在，
  但每个已存在的产物标注 `"artifact exists but QC failed; do not consume it"`；
  warnings 照旧披露（bbox=null、unresolved）。

要点：**对账失败永远不会被静默成通过**——这正是本 Skill 的存在意义。
