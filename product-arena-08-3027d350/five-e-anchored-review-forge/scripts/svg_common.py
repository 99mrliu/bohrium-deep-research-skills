"""svg_common.py — 逐页锚点叠加 SVG 的共享构建器（纯标准库）。

被 render_overlay.py 与 render_review.py 共同 import，保证
overlays/page-N.svg 与 review.html 内嵌 SVG 逐字节同源。

坐标约定（与 references/render-contract.md 一致）：
  bbox 为 PDF 点（pt），原点左上，y 向下；SVG 坐标系同为左上原点 y 向下，
  因此 1:1 直写，不做任何翻转或缩放；viewBox = "0 0 width height"。
"""

from xml.sax.saxutils import escape

# kind -> 颜色（描边/文字用实色，填充用同色 0.18 透明度）。
# 与 references/render-contract.md 的颜色表逐项一致。
KIND_COLORS = {
    "title":     "#1f77b4",
    "heading":   "#2ca02c",
    "body":      "#7f7f7f",
    "caption":   "#ff7f0e",
    "equation":  "#9467bd",
    "reference": "#8c564b",
    "header":    "#17becf",
    "footer":    "#17becf",
}
DEFAULT_COLOR = "#d62728"  # 未知 kind 的醒目兜底色

TITLE_SNIPPET_LEN = 80     # <title> 元素保留块文本的前 80 个字符
LABEL_FONT_SIZE = 7        # 锚点标签字号（pt）
STROKE_WIDTH = 1.2         # 常态描边宽度；review.html 高亮时改 3


def xesc(s):
    """XML 转义：& < > 以及两种引号（属性安全）。"""
    return escape(str(s), {'"': "&quot;", "'": "&apos;"})


def fmt(v):
    """坐标数值格式：两位小数，避免 72.0 / 72.00 不稳定写法。"""
    return f"{float(v):.2f}"


def build_page_svg(width, height, blocks):
    """构建单页叠加 SVG（纯文本，无外部引用）。

    width/height: 页宽页高（PDF 点）。
    blocks: 该页的块列表，每块含 id/kind/bbox/text。
    返回 SVG 字符串（不带 <?xml?> 声明，便于 inline 进 HTML）。
    """
    w, h = float(width), float(height)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(w)}pt" '
        f'height="{fmt(h)}pt" viewBox="0 0 {fmt(w)} {fmt(h)}">',
        f'<rect id="page-frame" x="0" y="0" width="{fmt(w)}" height="{fmt(h)}" '
        f'fill="#ffffff" stroke="#333333" stroke-width="1"/>',
    ]
    for b in blocks:
        anchor = str(b["id"])
        kind = str(b.get("kind", "body"))
        color = KIND_COLORS.get(kind, DEFAULT_COLOR)
        x0, y0, x1, y1 = (float(v) for v in b["bbox"])
        snippet = xesc(str(b.get("text", ""))[:TITLE_SNIPPET_LEN])
        # 标签优先放在块顶上方；贴近页顶时改放块内，避免越出页面。
        ty = y0 - 2.0 if y0 >= LABEL_FONT_SIZE + 3 else y0 + LABEL_FONT_SIZE + 1.0
        ty = min(ty, h - 1.0)
        parts.append(f'<g id="blk-{xesc(anchor)}" data-kind="{xesc(kind)}">')
        parts.append(f'<title>{snippet}</title>')
        parts.append(
            f'<rect x="{fmt(x0)}" y="{fmt(y0)}" width="{fmt(x1 - x0)}" '
            f'height="{fmt(y1 - y0)}" fill="{color}" fill-opacity="0.18" '
            f'stroke="{color}" stroke-width="{STROKE_WIDTH}"/>'
        )
        parts.append(
            f'<text x="{fmt(x0 + 2.0)}" y="{fmt(ty)}" font-size="{LABEL_FONT_SIZE}" '
            f'font-family="monospace" fill="{color}">{xesc(anchor)}</text>'
        )
        parts.append('</g>')
    parts.append('</svg>')
    return "\n".join(parts) + "\n"
