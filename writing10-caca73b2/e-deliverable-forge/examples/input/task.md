# 任务说明(合成示例)

本示例为合成示例, 数据与结论均为虚构, 仅用于演示交付流程, 不构成任何科学主张。

## 目标

对 `manuscript.md`(已定稿的结果与讨论章节, 科学内容由上游保证)执行下游交付工程:

1. 运行 `xref_check.py` 审计图表交叉引用, 若有错误先修复;
2. 运行 `build_docx.py` 生成可编辑 `.docx` 并自验;
3. 运行 `render_preview.py` 生成 SVG 预览页;
4. 按 `case.json` 的 `output_contract` 组装 `result.json` 并用 `result_contract.py check` 校验。

## 契约

- `result.json` 必须包含 `case_id`(原样照抄)与 `output_contract` 的全部键,
  外加诚实的 `status` / `sources` / `uncertainty`。
- 渲染/打包环节不得改动任何科学内容(数值、结论、比较关系)。
- docx 构建或预览失败时, `status` 记为 `partial` 并保留 md/html 降级产物。
