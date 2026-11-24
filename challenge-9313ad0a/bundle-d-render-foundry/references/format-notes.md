# 格式说明与导入行为备忘

## FreeMind `.mm`（主交付格式）

`.mm` 被选为主可编辑交付物，原因：格式公开、结构简单（纯 XML）、被 FreeMind / Freeplane / XMind 三大工具直接支持，且同时承载层级、备注与跨节点关系三类信息。

- **基本结构**：`<map version="1.0.1">` 下嵌套 `<node TEXT="..." ID="...">`。子节点直接嵌套于父 `<node>` 内。XML 声明为 UTF-8。
- **节点 ID**：`ID` 属性被 FreeMind/Freeplane 保留；XMind 导入时通常重新生成内部 ID，但层级与文本完整。ID 同时是 arrowlink 的寻址基础，因此导出时务必稳定、唯一。
- **备注**：`<rich_content TYPE="NOTE"><html><head/><body><p>...</p></body></html></rich_content>`。`TYPE="NOTE"` 为 FreeMind 识别备注所必需；Freeplane 兼容同一写法。
- **关系**：`<arrowlink DESTINATION="目标节点ID"/>`，置于关系起点所在 `<node>` 内。FreeMind 与 Freeplane 均渲染为箭头连线。arrowlink 不携带类型文本（格式本身无此字段），关系类型需借助 `.md` / `.html` / 预览图查阅。XMind 对 arrowlink 的支持不稳定，导入后关系可能丢失——面向 XMind 的交付应在交付说明中声明此点。
- **转义**：属性值中的 `&`、`<`、`>`、双引号必须转义（`&amp;` `&lt;` `&gt;` `&quot;`），否则 Freeplane 解析失败。本包导出器统一处理，往返校验保证可逆。

## OPML 2.0 `.opml`

- 结构：`<opml version="2.0">` → `<head><title>` + `<body>` 内嵌套 `<outline text="...">`。
- 备注置于 `_note` 属性（OPML 2.0 约定属性）；节点类别置于 `type` 属性。部分导入方会忽略未知属性，属预期行为。
- 导入目标：OmniOutliner（直接打开）、Workflowy / Dynalist（粘贴或导入）、Logseq（OPML 导入）、部分支持 OPML 的笔记与 RSS 工具。
- OPML 无跨节点关系概念，`relations` 不进入该格式。

## Mermaid `mindmap` `.mmd`

- 语法：`mindmap` 起始行，`root((根标签))` 声明根，其余节点以缩进（本包每级 4 空格）表达层级。
- **限制**：裸标签中不得出现未转义的圆括号与方括号——`()` 与节点形状语法冲突，`[]` 在部分解析器中触发边界问题。本包导出时将其替换为全角 `（）［］`。
- 备注与 relations 均不进入 `.mmd`；该格式定位是快速嵌入渲染，不是完整数据交换。
- Mermaid 版本差异：低版本（< 9.3）无 `mindmap` 图型，渲染失败时应在支持版本中复核，而非修改源数据。

## Markmap 自包含 HTML `.html`

- 页面内嵌 `<script type="text/template">` 中的 Markdown 供 markmap-autoloader（CDN：jsDelivr）在线渲染为交互 SVG。
- **离线行为**：页面同时包含完整静态嵌套 `<ul>` 大纲，无任何网络时全部内容可读；脚本监听加载失败并在页首给出提示。在线/离线两种状态均已设计为不显式报错。
- 内嵌 `<script type="application/json">` 保存原图 JSON（`</` 已转义为 `<\/`，JSON 语义不变），供程序化复用。
- **限制**：标签中不得包含 `</` 序列（会提前闭合 script 元素）；输入数据含此序列时须先改写。

## 各格式信息承载对照

| 信息 | .mm | .opml | .md | .mmd | .html |
| --- | --- | --- | --- | --- | --- |
| 层级结构 | ✓ | ✓ | ✓ | ✓ | ✓ |
| 节点备注 | ✓ | ✓（`_note`） | ✓ | ✗ | ✓ |
| 节点类别 kind | ✗ | ✓（`type`） | ✓ | ✗ | ✓ |
| 跨节点关系 | ✓（无端点文本） | ✗ | ✓（关系节） | ✗ | ✓（JSON 内） |
