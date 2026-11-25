# 任务说明（合成示例）

将上游解析产物 `inputs/blocks.jsonl`（20 个合成块，2 页，覆盖全部 8 种 kind，
含 2 个 unresolved 与 1 个 bbox=null 的 body 块）渲染为交付物并完成对账：

1. `anchor_map.py`：校验 schema，分配稳定锚点；
2. `render_preview.py`：产出 `deliverable.md` 与自包含 `preview.html`；
3. `render_qc.py`：对账并产出 `render_qc.json` 与 `result.json`。

验收标准：QC status 为 pass；20 blocks in == 20 anchors out（md、html 各 20）；
warnings 中正确披露 p1-b6 的 bbox=null 与 2 个 unresolved 块；
`result.json` 回传 `case_id` 且 `output_contract` 五个字段齐全。

> 合成声明：所有块均为编造，仅用于演示。
