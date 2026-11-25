#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_scan_pdf.py — 纯标准库生成 1 页"类扫描"PDF（合成示例输入）。

产物 scan_like.pdf 特征：
  - 1 页，/MediaBox [0 0 612 792]
  - 整页 DeviceGray 8bpc 位图（400x300 = 120000 像素），
    图像数据 ASCIIHexDecode 编码（保证整个 PDF 为纯 ASCII/UTF-8 文本）
  - 内容流同样 ASCIIHexDecode，只绘制图像，无任何文字（无 BT..ET）
用途：验证 scan_detect.py 将其判为 scanned 并产出 OCR 移交清单。
"""
from pathlib import Path

W, H = 400, 300
PAGE_W, PAGE_H = 612, 792


def hex_wrap(data: bytes, width: int = 64) -> bytes:
    hexs = data.hex().encode("ascii")
    lines = [hexs[i:i + width] for i in range(0, len(hexs), width)]
    return b"\n".join(lines)


def make_bitmap() -> bytes:
    """确定性的灰度渐变+条纹图案（无需随机数）。"""
    buf = bytearray()
    for y in range(H):
        for x in range(W):
            buf.append((x * 7 + y * 13 + (x * y) // 11) % 256)
    return bytes(buf)


def build_pdf() -> bytes:
    bitmap_hex = hex_wrap(make_bitmap()) + b">"
    content = b"q\n%d 0 0 %d 0 0 cm\n/Im1 Do\nQ\n" % (PAGE_W, PAGE_H)
    content_hex = hex_wrap(content) + b">"

    objects = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        b"<< /Type /Page /Parent 2 0 R\n"
        b"   /MediaBox [0 0 %d %d]\n"
        b"   /Resources << /XObject << /Im1 4 0 R >> >>\n"
        b"   /Contents 5 0 R\n>>" % (PAGE_W, PAGE_H))
    objects.append(
        b"<< /Type /XObject /Subtype /Image\n"
        b"   /Width %d /Height %d\n"
        b"   /ColorSpace /DeviceGray /BitsPerComponent 8\n"
        b"   /Filter /ASCIIHexDecode\n"
        b"   /Length %d\n>>\nstream\n%s\nendstream" % (W, H, len(bitmap_hex), bitmap_hex))
    objects.append(
        b"<< /Length %d /Filter /ASCIIHexDecode >>\nstream\n%s\nendstream"
        % (len(content_hex), content_hex))

    out = bytearray(b"%PDF-1.4\n% synthetic scan-like PDF (ASCII only)\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\n"
            b"startxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_pos))
    return bytes(out)


def main():
    out_path = Path(__file__).resolve().parent / "scan_like.pdf"
    pdf = build_pdf()
    out_path.write_bytes(pdf)
    # 自查：整个文件必须可按 UTF-8 解码（纯 ASCII）
    pdf.decode("utf-8")
    print("written %s (%d bytes, ascii-only)" % (out_path, len(pdf)))


if __name__ == "__main__":
    main()
