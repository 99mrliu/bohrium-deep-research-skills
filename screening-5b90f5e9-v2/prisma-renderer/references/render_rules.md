# 渲染工程规则

## 确定性

- 布局坐标、盒尺寸、字号全部来自固定参数与计数文本长度，不引入
  随机或环境相关因素；同一份 counts.json 两次渲染的 flow.svg
  逐字节一致；
- 文本宽度估算：ASCII 6.6px/字符（12px Helvetica）、CJK 12px/字符，
  仅用于盒宽估算，不影响内容；
- 时间戳不进 SVG——可复现性优先于"生成时间"装饰。

## 转义与注入

- 所有进 SVG 的文本经 xml.sax.saxutils.escape；理由码、数据库名等
  若含 `&<>'"` 不会破坏文档结构（R4 well-formed 门兜底）；
- Mermaid 文本中的引号用 `<br/>` 与转义处理，节点标签一律双引号包裹。

## 降级与边界

- exclusion_reasons 为空：Excluded 盒只显示总数，R3 跳过；
- databases/search_date 缺失：Identification 盒显示 n/a 与"未登记"，
  并在 render_check.json 外由报告层标缺失；
- 计数全零的合法空结果：允许渲染（0 是事实，不是错误），
  但 build_report 会在相应节保留 0 值而非缺失标注。

## 交付清单

/app/output 下应同时存在：flow.svg（图形）、flow.md（Mermaid+计数表）、
render_check.json（闭合门与 well-formed 证据）、screening_report.md。
四者同源生成；任何手工编辑都违背同源原则，应改输入产物后重跑。
