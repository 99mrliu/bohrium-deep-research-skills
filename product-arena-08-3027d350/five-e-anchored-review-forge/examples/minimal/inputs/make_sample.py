#!/usr/bin/env python3
"""make_sample.py — 纯标准库生成合成单栏 PDF（inputs/sample.pdf）。

合成示例（非正式案例、非真实论文）：2 页 Letter（612×792 pt），内含
title、heading、body、一条 "Figure 1:" caption、一条公式行。
直接手写 PDF 对象与 xref 表，字体用 Base-14 Helvetica/Helvetica-Bold，
无需嵌入字体。所有坐标在源码中以"距页顶"标注（y 向下），写入内容流时
换算为 PDF 的左下原点 y 向上坐标。
"""

import os

PAGE_W, PAGE_H = 612.0, 792.0
MARGIN = 72.0


def esc_pdf(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_op(font, size, x, y_top, s):
    """返回一条绝对定位文本操作；y_top 为距页顶的基线上方距离（pt）。"""
    y = PAGE_H - (y_top + size)  # 基线 = y_top + 字号（近似）
    return f"BT /{font} {size} Tf 1 0 0 1 {x:.1f} {y:.1f} Tm ({esc_pdf(s)}) Tj ET"


# 版式约定：段内行距（y 差）14 pt，块间断档 >= 26 pt，让最小提取器的
# 行距阈值（1.5 x 基准行距）能干净切出 title/heading/equation/caption 独立块。
PAGE1 = [
    ("F2", 18, 72,  "Anchored Rendering of Parsed Documents"),
    ("F1", 11, 112, "This synthetic two-page document exists only to feed the"),
    ("F1", 11, 126, "minimal extractor of the anchored-review-forge skill."),
    ("F1", 11, 140, "Every sentence is fabricated and carries no real claims."),
    ("F2", 13, 170, "1. Introduction"),
    ("F1", 11, 198, "Anchored rendering draws one colored rectangle per block"),
    ("F1", 11, 212, "so that a reviewer can trace each line back to the PDF."),
    ("F1", 11, 240, "The equation below is a stand-in with no derivation:"),
    ("F1", 11, 268, "E = m c^2 + 1/2 k_B T    (1)"),
    ("F1", 11, 296, "The caption below belongs to a figure that is not drawn,"),
    ("F1", 11, 310, "which is fine for a geometry-only smoke test."),
    ("F1", 11, 338, "Figure 1: Schematic of the anchored review pipeline."),
    ("F1", 11, 366, "A trailing paragraph closes the first synthetic page"),
    ("F1", 11, 380, "so that body blocks outnumber every other kind."),
]

PAGE2 = [
    ("F2", 13, 72,  "2. Method"),
    ("F1", 11, 100, "Words are clustered into lines by vertical proximity"),
    ("F1", 11, 114, "and lines merge into blocks while the gap stays small."),
    ("F1", 11, 128, "The kind of each block is assigned by simple rules."),
    ("F1", 11, 156, "Rendering is one-to-one in PDF points with no scaling,"),
    ("F1", 11, 170, "which keeps every rectangle easy to audit by eye."),
    ("F1", 11, 198, "End of the synthetic sample document."),
]


def content_stream(lines):
    return "\n".join(text_op(f, s, MARGIN, y, t) for f, s, y, t in lines) + "\n"


def build_pdf(path):
    streams = [content_stream(PAGE1), content_stream(PAGE2)]
    objects = []

    def add(body):
        objects.append(body)
        return len(objects)  # 1-based 对象号

    font1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    contents = [add(("<< /Length %d >>\nstream\n" % len(s.encode("latin-1"))).encode("latin-1")
                    + s.encode("latin-1") + b"endstream") for s in streams]
    kids = []
    for c in contents:
        kids.append(add(
            f"<< /Type /Page /Parent 0 0 R /MediaBox [0 0 {PAGE_W:.0f} {PAGE_H:.0f}] "
            f"/Resources << /Font << /F1 {font1} 0 R /F2 {font2} 0 R >> >> "
            f"/Contents {c} 0 R >>".encode("latin-1")))
    pages_obj = add(("<< /Type /Pages /Kids [" +
                     " ".join(f"{k} 0 R" for k in kids) +
                     f"] /Count {len(kids)} >>").encode("latin-1"))
    # 回填 Page 的 /Parent
    for k in kids:
        objects[k - 1] = objects[k - 1].replace(b"/Parent 0 0 R",
                                                f"/Parent {pages_obj} 0 R".encode("latin-1"))
    catalog = add(f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode("latin-1"))

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n").encode("latin-1")

    with open(path, "wb") as f:
        f.write(bytes(out))
    return len(out)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "sample.pdf")
    n = build_pdf(path)
    print(f"wrote {path} ({n} bytes, 2 pages, synthetic)")


if __name__ == "__main__":
    main()
