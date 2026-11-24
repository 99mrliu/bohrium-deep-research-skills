#!/usr/bin/env python3
"""make_fixtures.py — 生成合成示例夹具（非正式测试案例材料）。

写出两份纯 ASCII 的最小 PDF（不依赖任何第三方库，手工拼装 PDF 对象与
xref 表），供 ingest 流程真实解析。内容为虚构论文，仅作演示：
  - synth_paper_alpha.pdf：2 页虚构论文（含两段"结果"文本）；
  - synth_paper_beta.pdf：1 页虚构论文 + 1 个空白页（演示 QC 对空页的检出）。
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUT = HERE / "input"


def pdf_escape(text):
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_pdf(pages_text):
    """pages_text: List[str]，每页一段 ASCII 文本；空串 = 空白页。"""
    objects = []

    def stream_obj(body):
        return ("<< /Length %d >>\nstream\n%s\nendstream"
                % (len(body.encode("latin-1")), body))

    page_objs, content_objs = [], []
    for text in pages_text:
        if text:
            lines = text.split("\n")
            ops = ["BT", "/F1 12 Tf", "72 740 Td", "14 TL"]
            for i, ln in enumerate(lines):
                if i:
                    ops.append("T*")
                ops.append("(%s) Tj" % pdf_escape(ln))
            ops.append("ET")
            content_objs.append(stream_obj("\n".join(ops)))
        else:
            content_objs.append(stream_obj(""))
        page_objs.append(None)  # 占位，稍后填

    # 对象编号规划：1=Catalog 2=Pages 3=Font；之后每页两个对象（page, content）
    objs = {1: "<< /Type /Catalog /Pages 2 0 R >>",
            3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"}
    n_pages = len(pages_text)
    kids = []
    next_id = 4
    for i in range(n_pages):
        page_id, content_id = next_id, next_id + 1
        next_id += 2
        kids.append("%d 0 R" % page_id)
        objs[page_id] = ("<< /Type /Page /Parent 2 0 R "
                         "/MediaBox [0 0 612 792] "
                         "/Resources << /Font << /F1 3 0 R >> >> "
                         "/Contents %d 0 R >>" % content_id)
        objs[content_id] = content_objs[i]
    objs[2] = ("<< /Type /Pages /Kids [%s] /Count %d >>"
               % (" ".join(kids), n_pages))

    out = ["%PDF-1.4"]
    offsets = {}
    pos = len(out[0]) + 1
    for oid in sorted(objs):
        body = "%d 0 obj\n%s\nendobj" % (oid, objs[oid])
        offsets[oid] = pos
        out.append(body)
        pos += len(body.encode("latin-1")) + 1
    xref_pos = pos
    max_id = max(objs)
    xref = ["xref", "0 %d" % (max_id + 1), "0000000000 65535 f "]
    for oid in range(1, max_id + 1):
        xref.append("%010d 00000 n " % offsets[oid])
    trailer = ["trailer",
               "<< /Size %d /Root 1 0 R >>" % (max_id + 1),
               "startxref", str(xref_pos), "%%EOF"]
    return "\n".join(out + xref + trailer) + "\n"


def main():
    INPUT.mkdir(parents=True, exist_ok=True)
    alpha = build_pdf([
        "SYNTHETIC PAPER (demo fixture, not a real paper)\n"
        "Alpha et al. 2024. On synthetic dataset D, baseline B achieves\n"
        "metric X = 0.71. Our improved pipeline raises X to 0.74.",
        "Page 2. Limitations: single synthetic dataset, no significance\n"
        "test was performed. All numbers in this fixture are invented.",
    ])
    beta = build_pdf([
        "SYNTHETIC PAPER (demo fixture, not a real paper)\n"
        "Beta et al. 2025. Method M reaches X = 0.80 on benchmark P,\n"
        "but was never evaluated on dataset D. Training needs 200 GPUh.",
        "",  # 故意留一个空白页，演示 QC 检出
    ])
    (INPUT / "synth_paper_alpha.pdf").write_text(alpha, encoding="ascii")
    (INPUT / "synth_paper_beta.pdf").write_text(beta, encoding="ascii")
    print("wrote", INPUT / "synth_paper_alpha.pdf")
    print("wrote", INPUT / "synth_paper_beta.pdf")


if __name__ == "__main__":
    main()
