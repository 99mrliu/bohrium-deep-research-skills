#!/usr/bin/env python3
"""make_sample.py — 纯标准库合成 PDF 生成器(math-symbol-fidelity-lab 合成示例)

生成 2 页 ASCII-clean PDF(sample_math.pdf):
- Helvetica(/F1)正文;
- /Symbol 标准字体(/F2)写 Greek:内容流里字节 a b g 经 Symbol 编码渲染为 α β γ;
- 小字号 + Tm 文本位移构造上标(x 后 7pt 升起 6pt 的 2)与下标(E 后 7pt 降 3pt 的 i);
- 三条右端独立编号公式 (1) (2) (3);
- 一个 /ZapfDingbats 生僻码位(0xA6,内容流写八进制转义 \\246)用于真实触发
  unmapped 台账。

仅使用 Python 标准库;整个 PDF 只含 ASCII 字节,便于以纯文本形式入库。
退出码: 0 成功, 3 失败。
"""

import io
import os
import sys


def esc(s: str) -> str:
    """PDF 字面字符串转义(反斜杠与括号)。"""
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text(font: str, size: float, x: float, y: float, s: str) -> str:
    """一条绝对定位文本绘制操作(BT ... Tm ... Tj ET)。"""
    return f"BT /{font} {size} Tf 1 0 0 1 {x} {y} Tm ({esc(s)}) Tj ET"


def raw_text(font: str, size: float, x: float, y: float, raw: str) -> str:
    """与 text() 相同,但字符串内容按原样写入(用于八进制转义码位)。"""
    return f"BT /{font} {size} Tf 1 0 0 1 {x} {y} Tm ({raw}) Tj ET"


def page1_content() -> str:
    ops = []
    # 标题与正文(纯 Helvetica,无数学信号)
    ops.append(text("F1", 16, 72, 740, "Math Symbol Fidelity Demo (Synthetic)"))
    ops.append(text("F1", 12, 72, 712, "Body text in Helvetica: plain words, no math here."))
    # 公式 1: Symbol 字体 Greek: a + b = g  =>  α + β = γ        (1)
    ops.append(text("F2", 12, 72, 650, "a + b = g"))
    ops.append(text("F1", 12, 520, 650, "(1)"))
    # 公式 2: E_i = x^2 + chi psi  =>  E_i = x^2 + χψ            (2)
    ops.append(text("F1", 12, 72, 610, "E"))
    ops.append(text("F1", 7, 81, 605, "i"))        # 下标: 字号 ≤0.8×12, 基线下降 3pt
    ops.append(text("F1", 12, 90, 610, " = x"))
    ops.append(text("F1", 7, 121, 616, "2"))       # 上标: 字号 ≤0.8×12, 基线升起 6pt
    ops.append(text("F1", 12, 129, 610, " + "))
    ops.append(text("F2", 12, 158, 610, "cy"))     # χ ψ (Symbol 编码 c=chi, y=psi)
    ops.append(text("F1", 12, 520, 610, "(2)"))
    # 未映射字符行: ZapfDingbats 码位 0xA6(不在脚本内嵌常见映射表内)
    ops.append(text("F1", 12, 72, 570, "Marker: "))
    ops.append(raw_text("F3", 12, 125, 570, r"\246"))
    # 行内数学(无编号): Sum: α + β
    ops.append(text("F1", 12, 72, 530, "Sum: "))
    ops.append(text("F2", 12, 108, 530, "a + b"))
    return "\n".join(ops) + "\n"


def page2_content() -> str:
    ops = []
    ops.append(text("F1", 12, 72, 740, "Second page."))
    # 公式 3: Σ f(x) = Ω                                                (3)
    ops.append(text("F2", 12, 72, 700, "S f(x) = W"))  # text() 内部已做转义, 勿重复转义
    ops.append(text("F1", 12, 520, 700, "(3)"))
    ops.append(text("F1", 12, 72, 660, "End of synthetic sample."))
    return "\n".join(ops) + "\n"


def build_pdf() -> bytes:
    pages = [page1_content(), page2_content()]
    objects: list[bytes] = []

    def obj(body: str | bytes) -> int:
        if isinstance(body, str):
            body = body.encode("latin-1")
        objects.append(body)
        return len(objects)  # 1-based object number

    catalog = obj("<< /Type /Catalog /Pages 2 0 R >>")
    assert catalog == 1
    obj("<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>")
    font_res = "<< /Font << /F1 5 0 R /F2 6 0 R /F3 7 0 R >> >>"
    obj(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        f"/Resources {font_res} /Contents 8 0 R >>")
    obj(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        f"/Resources {font_res} /Contents 9 0 R >>")
    obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    obj("<< /Type /Font /Subtype /Type1 /BaseFont /Symbol >>")
    obj("<< /Type /Font /Subtype /Type1 /BaseFont /ZapfDingbats >>")
    for content in pages:
        data = content.encode("latin-1")
        obj(f"<< /Length {len(data)} >>\nstream\n".encode("latin-1") + data + b"endstream")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode("latin-1"))
        out.write(body)
        out.write(b"\nendobj\n")
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode("latin-1"))
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
              f"startxref\n{xref_pos}\n%%EOF\n".encode("latin-1"))
    return out.getvalue()


def main() -> int:
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_math.pdf")
    data = build_pdf()
    # 自查: 全部字节必须在 ASCII 范围内, 保证文件本身是合法 UTF-8 文本
    assert all(b < 128 for b in data), "PDF 必须 ASCII-clean"
    with open(out_path, "wb") as f:
        f.write(data)
    print(f"wrote {out_path} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
