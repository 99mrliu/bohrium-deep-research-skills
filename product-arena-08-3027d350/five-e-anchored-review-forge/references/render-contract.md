# 渲染契约（render contract）

本契约规定"坐标映射、转义、锚点命名、清单哈希"四条不可变规则；
`render_overlay.py` 与 `render_review.py` 共用 `svg_common.py` 实现，
任何改动必须三处同步（代码 / 本文档 / SKILL.md）。

## 1. 坐标映射

- 输入 `bbox` 为 PDF 点（pt），原点左上，y 向下（与 PyMuPDF 的
  `page.get_text("dict")`、`pdftotext -bbox` 的输出一致）。
- SVG 坐标系同为左上原点、y 向下，因此**直写 1:1，不翻转、不缩放、
  不偏移**。这是本 bundle 刻意的简化：变换越少，可复核性越强。
- 每页 SVG：`<svg width="{W}pt" height="{H}pt" viewBox="0 0 {W} {H}">`，
  W/H 取自 page_meta.json；数值统一保留两位小数。
- 页面底框：`<rect id="page-frame" x="0" y="0" width="W" height="H">`。
- 块矩形直接以 bbox 四值渲染；越界块不裁剪，渲染并记 warning。
- review.html 中用 CSS `max-width:100%; height:auto` 缩放显示，仅影响
  显示尺寸，不改变 SVG 内部坐标（viewBox 保证比例）。

## 2. 转义规则

- **SVG（XML）**：所有进入 SVG 的文本（`<title>` 摘要、锚点标签、id 属性）
  经 `xml.sax.saxutils.escape` 并附加 `"` 与 `'` 的转义
  （`&` `<` `>` `&quot;` `&apos;`）。`<title>` 元素内容 = 块文本前 80 字符。
- **HTML**：所有进入 review.html 的动态文本与属性经
  `html.escape(s, quote=True)`（`&` `<` `>` `"` `'` 五字符全覆盖）。
  块文本置于 `white-space:pre-wrap` 的 `<p>` 中，`\n` 原样保留。
- 颜色值、页码、坐标等由程序生成的数值不拼接用户输入。
- 每份 SVG 写出前用 `xml.etree.ElementTree.fromstring` 做良构自检；
  review.html 写出前用 `html.parser.HTMLParser` 跑全文解析自检，
  任一失败即退出码 3，不交付半成品。

## 3. 锚点命名

- 锚点 id = 块 `id`，格式 `p{page}.b{n}`（如 `p1.b3`），来自 blocks.jsonl，
  渲染端不重新编号，保证与上游索引逐字一致。
- SVG 侧元素 id = `blk-` + 锚点（如 `blk-p1.b3`），加前缀避免与页面
  锚、HTML 元素撞名；含 `.` 的 id 合法，JS 一律用 `getElementById`，
  不用 `querySelector('#...')`。
- review.html 右栏块卡片 id = `card-` + 锚点；徽章 `data-anchor` 属性
  持有裸锚点。JS 双向联动：hover/点击徽章 ↔ 高亮/滚动到 SVG 矩形，
  hover/点击 SVG 分组 ↔ 高亮/滚动到右栏卡片。
- 高亮方式：矩形 `stroke-width` 1.2 → 3；不改填充，避免遮挡文字。

## 4. 颜色表（kind → 描边色；填充为同色 0.18 透明度）

| kind | 色值 | | kind | 色值 |
|---|---|---|---|---|
| title | `#1f77b4` | | equation | `#9467bd` |
| heading | `#2ca02c` | | reference | `#8c564b` |
| body | `#7f7f7f` | | header / footer | `#17becf` |
| caption | `#ff7f0e` | | （未知 kind 兜底） | `#d62728` |

## 5. 清单哈希算法（manifest.json）

- 算法：SHA-256（十六进制小写），逐文件对**字节内容**计算。
- 覆盖范围：产物根目录递归遍历的全部文件，**排除 `manifest.json` 与
  `result.json` 自身**（避免自引用与写入顺序悖论）；各脚本的
  `*.report.json` 属于普通产物，计入清单。
- `files[]` 每项：`{path（相对产物根目录，POSIX 分隔）, bytes, sha256}`，
  按 path 排序。
- `input_hashes`：blocks.jsonl、page_meta.json（及可选 PDF）的 sha256，
  与 review.html 头部注释中的哈希一致。
- 复核命令：`shasum -a 256 <file>`（或 `sha256sum`）输出应等于
  manifest 中对应条目的 `sha256`。
