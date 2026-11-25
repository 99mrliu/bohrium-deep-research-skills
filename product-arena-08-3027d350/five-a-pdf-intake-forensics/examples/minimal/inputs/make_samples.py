#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_samples.py — 纯标准库手写三个合成 PDF（合成示例，非真实论文）

产物（与本脚本同目录）:
    ok_text.pdf      2 页正常文字（Helvetica 标准字体，内容流不压缩）
    scan_like.pdf    1 页整页灰度图像 XObject（ASCIIHexDecode / DeviceGray），无任何文字
    broken_tail.pdf  ok_text.pdf 截尾后 60%（真实触发 partial/failed 路径）

验证: pdftotext 可提取 ok_text.pdf 文字；scan_like.pdf 提取为空；
      broken_tail.pdf 的取证报告如实报告 xref 损坏。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))

INFO_PRODUCER = 'pdf-intake-forensics make_samples.py'
INFO_CREATOR = 'stdlib synthetic generator'
INFO_DATE = "D:20261125090000+08'00'"


def esc(s):
    return s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


class PDFBuilder:
    """最小 PDF 写入器：经典 xref 表 + trailer，无对象流。"""

    def __init__(self):
        self.objects = []  # 1-based

    def add(self, body):
        self.objects.append(body if isinstance(body, bytes) else body.encode('latin-1'))
        return len(self.objects)

    def build(self, root_ref, info_ref):
        # 头部不放二进制注释行（%âãÏÓ），保证合成 PDF 为纯 ASCII/UTF-8 文本，
        # 满足 bundle"全部 UTF-8 文本、无二进制"的平台约束；PDF 规范对该行不作强制。
        out = bytearray(b'%PDF-1.4\n')
        offsets = []
        for i, body in enumerate(self.objects, start=1):
            offsets.append(len(out))
            out += ('%d 0 obj\n' % i).encode('latin-1') + body + b'\nendobj\n'
        xref_pos = len(out)
        n = len(self.objects) + 1
        out += ('xref\n0 %d\n' % n).encode('latin-1')
        out += b'0000000000 65535 f \n'
        for off in offsets:
            out += ('%010d 00000 n \n' % off).encode('latin-1')
        out += ('trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\n'
                'startxref\n%d\n%%%%EOF\n' % (n, root_ref, info_ref, xref_pos)).encode('latin-1')
        return bytes(out)


def text_content_stream(lines):
    ops = ['BT /F1 11 Tf 72 740 Td 15 TL']
    ops.append('(%s) Tj' % esc(lines[0]))
    for ln in lines[1:]:
        ops.append('T* (%s) Tj' % esc(ln))
    ops.append('ET')
    return ('\n'.join(ops) + '\n').encode('latin-1')


def make_ok_text():
    """2 页正常文字。"""
    # 对象编号: 1=font, 2/3=content1/page1, 4/5=content2/page2,
    # 6=pages(Kids 指向真实页对象), 7=catalog, 8=info
    pdf = PDFBuilder()
    pdf.add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica '
            '/Encoding /WinAnsiEncoding >>')
    page_refs = []
    for pageno in (1, 2):
        lines = [
            'Page %d, line %02d: the quick brown fox jumps over the lazy dog 0123456789.'
            % (pageno, i)
            for i in range(1, 13)
        ]
        stream = text_content_stream(lines)
        content = pdf.add(b'<< /Length %d >>\nstream\n' % len(stream) + stream + b'endstream')
        page = pdf.add('<< /Type /Page /Parent 6 0 R /MediaBox [0 0 612 792] '
                       '/Resources << /Font << /F1 1 0 R >> >> /Contents %d 0 R >>' % content)
        page_refs.append(page)
    pages = pdf.add('<< /Type /Pages /Kids [%s] /Count 2 >>'
                    % ' '.join('%d 0 R' % r for r in page_refs))
    assert pages == 6, pages
    catalog = pdf.add('<< /Type /Catalog /Pages 6 0 R >>')
    info = pdf.add('<< /Producer (%s) /Creator (%s) /CreationDate (%s) >>'
                   % (esc(INFO_PRODUCER), esc(INFO_CREATOR), esc(INFO_DATE)))
    return pdf.build(catalog, info)


def make_scan_like():
    """1 页整页灰度图像（ASCIIHexDecode / DeviceGray 64x64 渐变），无任何文字操作。"""
    # 对象编号: 1=image, 2=content, 3=page, 4=pages, 5=catalog, 6=info
    pdf = PDFBuilder()
    w = h = 64
    raw = bytes(((x * 255) // (w - 1) + (y * 255) // (h - 1)) // 2
                for y in range(h) for x in range(w))
    hexdata = raw.hex().encode('ascii') + b'>'
    image = pdf.add(b'<< /Type /XObject /Subtype /Image /Width %d /Height %d '
                    b'/ColorSpace /DeviceGray /BitsPerComponent 8 '
                    b'/Filter /ASCIIHexDecode /Length %d >>\nstream\n' % (w, h, len(hexdata))
                    + hexdata + b'\nendstream')
    content_str = b'q 400 0 0 400 100 200 cm /Im0 Do Q\n'
    content = pdf.add(b'<< /Length %d >>\nstream\n' % len(content_str)
                      + content_str + b'endstream')
    page = pdf.add('<< /Type /Page /Parent 4 0 R /MediaBox [0 0 612 792] '
                   '/Resources << /XObject << /Im0 %d 0 R >> >> /Contents %d 0 R >>'
                   % (image, content))
    pages = pdf.add('<< /Type /Pages /Kids [%d 0 R] /Count 1 >>' % page)
    catalog = pdf.add('<< /Type /Catalog /Pages %d 0 R >>' % pages)
    info = pdf.add('<< /Producer (%s) /Creator (%s) /CreationDate (%s) >>'
                   % (esc(INFO_PRODUCER), esc(INFO_CREATOR), esc(INFO_DATE)))
    return pdf.build(catalog, info)


def main():
    ok = make_ok_text()
    with open(os.path.join(HERE, 'ok_text.pdf'), 'wb') as fh:
        fh.write(ok)
    scan = make_scan_like()
    with open(os.path.join(HERE, 'scan_like.pdf'), 'wb') as fh:
        fh.write(scan)
    with open(os.path.join(HERE, 'broken_tail.pdf'), 'wb') as fh:
        fh.write(ok[:int(len(ok) * 0.6)])
    for name, data in (('ok_text.pdf', ok), ('scan_like.pdf', scan),
                       ('broken_tail.pdf', ok[:int(len(ok) * 0.6)])):
        print('%s: %d bytes' % (name, len(data)))


if __name__ == '__main__':
    main()
