#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_sample.py — 纯标准库生成合成单栏三页 PDF + case.json（合成示例，非真实论文）。

约束：不联网、不 pip、只用标准库；输出 PDF 仅含 ASCII 字节（可 UTF-8 解码），
且能被 pdftotext 与 pymupdf 真实读取。

用法：python3 make_sample.py [输出目录]   （默认：脚本所在目录）
产物：sample.pdf, case.json
"""
import json
import os
import sys

PAGE_W, PAGE_H = 612, 792  # US Letter, pt
MARGIN_X, TOP_Y, BOTTOM_Y = 72, 740, 72


def esc(s):
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def wrap(text, size, max_width):
    """按 Helvetica 平均字宽 ~0.5em 近似折行（仅用于合成示例排版）。"""
    max_chars = max(10, int(max_width / (0.5 * size)))
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def para(text, size, bold=False, space_before=6):
    return {"text": text, "size": size, "bold": bold, "space_before": space_before}


def render_page(items):
    """把段落渲染为 PDF 内容流（BT/ET 文本操作），返回 (stream, next_y)。"""
    ops, y = [], TOP_Y
    for it in items:
        size = it["size"]
        font = "F2" if it["bold"] else "F1"
        leading = size * 1.35
        y -= it.get("space_before", 6)
        for ln in wrap(it["text"], size, PAGE_W - 2 * MARGIN_X):
            if y < BOTTOM_Y:
                break  # 本合成示例内容量已手工控制在三页内
            ops.append(f"BT /{font} {size} Tf {MARGIN_X} {y:.1f} Td ({esc(ln)}) Tj ET")
            y -= leading
    return "\n".join(ops) + "\n", y


PAGE1 = [
    para("Synthetic Study of Document Structure Extraction", 20, bold=True, space_before=0),
    para("Alice Smith, Bob Jones, Carol White", 11, space_before=14),
    para("Department of Examples, Demo University", 10, space_before=4),
    para("Abstract", 13, bold=True, space_before=16),
    para("We present a synthetic document used to test structure extraction. "
         "It contains numbered sections, captions, and references. "
         "This file is generated for testing and is not a real paper.", 10),
    para("1 Introduction", 14, bold=True, space_before=16),
    para("This synthetic paper demonstrates hierarchical section detection. "
         "The numbering scheme follows a standard decimal style used in many "
         "scientific articles.", 10),
    para("1.1 Background", 12, bold=True, space_before=10),
    para("Prior synthetic work is summarized in Figure 1. Additional detail "
         "appears in Figure 3, which is intentionally left without a caption "
         "so that the structure audit can flag it.", 10),
]

PAGE2 = [
    para("2 Methods", 14, bold=True, space_before=0),
    para("The method section of this synthetic document contains two "
         "subsections with generated placeholder text.", 10),
    para("2.1 Data", 12, bold=True, space_before=10),
    para("All data in this document are synthetic and were produced by a "
         "deterministic generator script using only the standard library.", 10),
    para("2.2 Setup", 12, bold=True, space_before=10),
    para("The setup uses a single column layout with Helvetica and "
         "Helvetica-Bold at several sizes to mimic a real article.", 10),
    para("3 Results", 14, bold=True, space_before=16),
    para("The main synthetic outcome is shown in Figure 1 and Table 1. "
         "Both captions below are real text lines in the PDF.", 10),
    para("Figure 1: Synthetic results overview generated for testing.", 9, space_before=8),
    para("Table 1: Synthetic measurements with placeholder values.", 9, space_before=6),
    para("Further synthetic discussion refers back to Figure 1 for context "
         "and mentions Figure 3 again even though no such caption exists.", 10),
]

PAGE3 = [
    para("References", 14, bold=True, space_before=0),
    para("[1] Smith, A. Example citation one for the synthetic reference "
         "list. Journal of Demos, 2020.", 10, space_before=10),
    para("[2] Jones, B. and White, C. A rather long second example title "
         "that wraps onto a second line inside the PDF layout for testing "
         "continuation. Proc. Testing, 2021.", 10, space_before=6),
    para("[3] Brown, D. Third example entry. Demo Letters, 2019.", 10, space_before=6),
    para("[4] Miller, E. Fourth example entry. Annals of Samples, 2022.", 10, space_before=6),
    para("Acknowledgments", 14, bold=True, space_before=16),
    para("The authors thank nobody in particular; this is a synthetic file.", 10),
]


def build_pdf(pages_streams, out_path):
    """组装最小 PDF：Catalog/Pages/Page×N/Font×2/Content×N，全 ASCII。"""
    n = len(pages_streams)
    # 对象编号：1 Catalog, 2 Pages, 3..3+n-1 Page, 3+n F1, 4+n F2, 5+n.. content
    page_ids = [3 + i for i in range(n)]
    font1_id, font2_id = 3 + n, 4 + n
    content_ids = [5 + n + i for i in range(n)]
    max_id = 4 + n + n  # 最大对象编号

    objs = {}

    objs[1] = "<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{p} 0 R" for p in page_ids)
    objs[2] = f"<< /Type /Pages /Kids [{kids}] /Count {n} >>"
    for i, pid in enumerate(page_ids):
        objs[pid] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Resources << /Font << /F1 {font1_id} 0 R /F2 {font2_id} 0 R >> >> "
            f"/Contents {content_ids[i]} 0 R >>"
        )
    objs[font1_id] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    objs[font2_id] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"
    for i, cid in enumerate(content_ids):
        stream = pages_streams[i].encode("ascii")
        objs[cid] = (b"<< /Length " + str(len(stream)).encode("ascii")
                     + b" >>\nstream\n" + stream + b"endstream")

    buf = bytearray(b"%PDF-1.4\n")
    offsets = {0: 0}
    for oid in range(1, max_id + 1):
        offsets[oid] = len(buf)
        body = objs[oid]
        buf += f"{oid} 0 obj\n".encode("ascii")
        buf += body if isinstance(body, bytes) else body.encode("ascii")
        buf += b"\nendobj\n"
    xref_pos = len(buf)
    buf += f"xref\n0 {max_id + 1}\n".encode("ascii")
    buf += b"0000000000 65535 f \n"
    for oid in range(1, max_id + 1):
        buf += f"{offsets[oid]:010d} 00000 n \n".encode("ascii")
    buf += (f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n").encode("ascii")
    with open(out_path, "wb") as f:
        f.write(bytes(buf))


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    os.makedirs(out_dir, exist_ok=True)
    streams = []
    for items in (PAGE1, PAGE2, PAGE3):
        s, y = render_page(items)
        assert y >= BOTTOM_Y, f"内容溢出页面（y={y}），请精简合成文本"
        streams.append(s)
    pdf_path = os.path.join(out_dir, "sample.pdf")
    build_pdf(streams, pdf_path)

    case = {
        "case_id": "synth-minimal-001",
        "note": "合成示例（非正式案例、非真实论文）：PDF 由 make_sample.py 纯标准库生成。",
        "pdf": "sample.pdf",
        "output_contract": {
            "fields": ["document_tree", "section_spans", "references",
                       "reference_count", "structure_audit", "engine"]
        },
    }
    case_path = os.path.join(out_dir, "case.json")
    with open(case_path, "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)

    print(f"[make_sample] wrote {pdf_path} ({os.path.getsize(pdf_path)} bytes, 3 pages)")
    print(f"[make_sample] wrote {case_path}")


if __name__ == "__main__":
    main()
