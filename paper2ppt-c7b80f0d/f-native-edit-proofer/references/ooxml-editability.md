# OOXML 原生可编辑性

## 什么是"原生可编辑"

一份 PPTX 的可编辑性由它的 OOXML 内部结构决定：文字必须以 `<a:t>` 文本 run 存在于
shape 的 text body 中，表格必须是 `graphicFrame` 里的 `<a:tbl>`，图片是独立的
`pic` 部件。满足这三条，任何一台装了 PowerPoint / Keynote / WPS / LibreOffice 的
机器都能选中文字改字、改字号、增删表格行列——这才叫原生可编辑。

## 常见破坏模式

| 破坏 | 表现 | 后果 |
|---|---|---|
| text-as-image 截图贴字 | 整页一张 PNG，无文本 shape | 无法改字、无法检索、无法复制；edit_lint 以"有图无文"判嫌疑 |
| 文本转曲线/轮廓 | 字形变 freeform 路径 | 同上，且体积膨胀 |
| 图片表格 | 表格是截图 | 无法增删行列；edit_lint 对名字含 table 的 picture 给 warning |
| 整页 PDF 导出图 | 每页一张整版位图 | 完全只读 |
| 硬编码私有字体 | run 指定了本机才有的字体 | 换机替换、版式漂移；应继承主题字体 |
| 空占位符残留 | layout 克隆来的空 ph | 编辑视图满屏 "Click to add"，显得未完工 |

## python-pptx 能力边界

- **能做**：文本框/占位符、原生 table（`add_table`）、图片（`add_picture`）、
  备注（`notes_slide`）、shape 命名、字号/加粗、基于模板 layout 加页。
- **不能/不宜**：真项目符号编号 XML 微调（用 "- " 前缀代替，保持简单确定）；
  图表 chart 的复杂样式（本方向用 matplotlib 出图 + sidecar JSON 存数值代替）；
  删除模板自带 slide 需要操作 `_sldIdLst`（build_native 已实现）。
- 不设置 `run.font.name` 即继承主题字体（`+mn-lt`/`+mj-lt`），这是换机稳健的
  关键实践；edit_lint 会解析 `ppt/theme/theme1.xml` 把主题字体纳入白名单。

## 验证而非自述

可编辑性不能靠构建方自述。本方向用三层证据：edit_lint 静态门禁 →
roundtrip_check 重开校验（zip CRC、必备部件、逐页 shape/备注/图片解码）→
render_diff 真实渲染度量。三层全过才允许 result.json 里 compliance 全 pass。
