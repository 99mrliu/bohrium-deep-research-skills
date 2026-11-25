# blocks.jsonl 与 page_meta.json 规范

本规范是"解析产物 → 渲染交付物"的输入契约。任何上游（pymupdf、pdftotext、
OCR、其他 bundle 的结构化产物）只要产出符合本规范的两个文件，即可直接进
`render_overlay.py` / `render_review.py` / `render_manifest.py`。

## blocks.jsonl

每行一个 JSON 对象（UTF-8，`\n` 分隔，无数组包裹），字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 锚点 id，格式 `p{page}.b{n}`，`n` 为该页内从 1 起的顺序号；全文唯一 |
| `page` | int | 页码，从 1 起 |
| `kind` | enum | `title` / `heading` / `body` / `caption` / `equation` / `reference` / `header` / `footer` |
| `bbox` | [x0, y0, x1, y1] | 外接矩形，单位 **PDF 点（pt，1/72 英寸）**，原点**左上**，**y 向下**；x0<x1，y0<y1 |
| `text` | string | 块文本；多行用 `\n`；不得含未转义控制字符（JSON 层天然转义） |
| `column` | int | 栏号，从 1 起；单栏文档恒为 1 |
| `order` | int | 全文阅读序，从 1 起单调递增；review.html 右栏按此排序 |

约束：

- `id` 必须全文唯一；渲染端不做重号检查之外的去重，重号会导致 SVG `id`
  冲突与 JS 高亮串扰。
- `bbox` 必须与 `page_meta.json` 中对应页的 `width/height` 同一坐标系；
  越界块不会被裁剪，但会在 overlay 报告中记 warning（退出码 2）。
- `kind` 取值不在枚举内时仍可渲染，使用兜底色 `#d62728`。

## page_meta.json

```json
{"pages": [{"page": 1, "width": 612.0, "height": 792.0}, ...]}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `page` | int | 页码，从 1 起，与 blocks.jsonl 的 `page` 对应 |
| `width` | float | 页宽（pt） |
| `height` | float | 页高（pt） |

`pages` 顺序即渲染顺序。blocks.jsonl 中出现而 page_meta.json 中不存在的页
会被跳过并记 warning；page_meta.json 中有而没有任何块的页照常渲染空页面框。

## 最小提取器的分类规则（mini_extract.py，仅供喂数据）

阈值与代码常量一致，改动需同步 SKILL.md「方法要点」：

1. 行归并：`|y0 差| ≤ max(2.0, 0.35 × 词高中位数)` 的 token 归同一行。
2. 块切分：相邻行 y0 差（行距）`> 1.5 × 基准行距`（全页正行距的 25
   百分位），或 x 区间不重叠（容差 2 pt）时开新块。用 y0 差而非 bbox
   间隙，规避 pymupdf/pdftotext 行框含上下留白吃掉段落间隙的问题。
3. kind 判定（按序命中即止）：
   - `caption`：文本以 `Figure` / `Fig.` / `Table` 开头（忽略大小写）；
   - `equation`：含 `=` 且字母占比 < 0.6 且长度 < 120 字符；
   - `heading`：单行、≤ 60 字符、以编号开头（正则 `^\d+(\.\d+)*[.\s]`）；
   - `title`：首页首块且最大字号 ≥ 1.25 × 全文字号中位数（pymupdf 引擎）；
     pdftotext 引擎无字号，兜底为"首页首块、单行、≤ 90 字符"并记 warning；
   - 其余为 `body`。
4. `column`：块中心 x 越过页宽中线取 2，否则 1（单栏假设下的占位实现）。
