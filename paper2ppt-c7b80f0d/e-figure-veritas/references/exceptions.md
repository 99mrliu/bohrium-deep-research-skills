# 图表异常处置（exceptions）

| 异常 | 检测点 | 处置 |
|---|---|---|
| 矢量图抽不出位图 | fig_harvest：caption 页无嵌入位图 | 整页渲染兜底，`extraction="page-render"`，manifest warnings 留痕；provenance 仍可标 original-crop 但须在 uncertainties 说明 |
| 扫描件 PDF（无文本层） | fig_harvest：text_engine=none 或全文为空 | captions 索引为空 → exceptions 记 `scanned_pdf`；deck 只能引用人工裁决的图；status 至多 partial |
| caption 缺失 | fig_harvest：无 caption 命中 | 该图不进 manifest → deck 引用即 unknown-figure error；Agent 可在 manifest 手工补条目并记入 change_records |
| 图片加密/权限位 | pymupdf 打开失败 | stderr 明确报错，exit 2；result.json exceptions 记 `encrypted_pdf`，不中断其余流程 |
| matplotlib 缺失 | chart_redraw | exit 3，stderr `tool_missing`；honest missing，不伪造图；改用 original-crop |
| python-pptx 缺失 | build_deck | exit 3，`tool_missing`；交付 deck.json + 全部报告作为 partial |
| soffice / pdftoppm 缺失 | make_result --render | `export_artifact.rendered=false`，exceptions 记 `tool_missing`；禁止声称渲染通过 |
| 数值漂移 | redraw_verify exit 1 | 阻断该图入 deck；修正 spec 后重跑；不得"大概差不多"放行 |
| results 页误挂示意图 | fig_binding_lint exit 1 | 换图或改页角色；重跑 lint 至 error=0 |
| unknown 种类 | fig_classify | Agent 裁决，结果写回 manifest 并记入 change_records；裁决前禁用该图 |
