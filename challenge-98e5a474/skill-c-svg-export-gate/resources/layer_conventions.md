# 分层 SVG 组织约定（v1）

本约定让 SVG 源文件同时满足：Inkscape / Illustrator 可直接打开逐层编辑、
文字可选中可替换、元素可被脚本按 id 精确定位。

## 1. 图层

- 用 `<g inkscape:groupmode="layer" inkscape:label="层名" id="layer-层名">`
  声明图层（同时写 `data-layer="层名"` 便于脚本识别）。
- 推荐层序（自下而上）：`background` → `groups`（分区/容器）→
  `relations`（连线/箭头）→ `entities`（节点/柱/点）→ `labels`
  （标题/边标签/注释）→ `legend`。
- 一个语义层一个组；不要把全部元素平铺在根节点下。

## 2. 元素 id

- 每个可编辑元素（实体框、文字、连线、图例项）带全局唯一、语义可读的
  id：`ent-<名称>`、`rel-<编号>`、`ann-<编号>`、`legend-<项>`。
- id 一经分配不随编辑改变；改文字不改 id，删除元素不复用其 id。
- 需要脚本校验的元素加 `data-*` 属性（如 `data-from`/`data-to`）。

## 3. 文字

- 一律用 `<text>`，禁止转曲（把文字导出成 path）、禁止用 `<image>`
  贴文字截图；特殊符号用 Unicode，不用图片。
- 每个 `<text>` 显式写 `font-family`（建议 "Helvetica, Arial, sans-serif"
  这类有通退回退的列表）与 `font-size`（用户单位，≥ 5 pt 等效）。
- 样式全部内联为属性（fill/stroke/stroke-width/...），不依赖 `<style>`
  与 CSS 类——外科式编辑与多数转换器只认内联。

## 4. 几何与画布

- 根 `<svg>` 必须同时有 `width`/`height`（用户单位，1 单位 = 1 px
  @96dpi 换算物理尺寸）和 `viewBox`。
- 线宽 ≥ 0.25 pt 等效（印刷可分辨下限）；元素避让：不重叠、不出画布。

## 5. 内容纪律

- 禁止 `<script>`、`<foreignObject>`；位图 `<image>` 仅在内容确为照片/
  扫描图时允许，并在交付说明中声明。
- 图例与实际图面元素同文件同风格；图例项与数据/实体分类一一对应
  （内容正确性由上游抽取或数据绑定流程保证，本约定只管文件工程）。

## 6. 编辑纪律

- 局部修改用 apply_edit.py 的操作单，只动目标 id 的字节区间；
  不做整文件 pretty-print 重排（破坏 diff 可核验性）。
- 每次编辑保留 edit_log.json（before/after 片段 + 理由 + 来源）。
