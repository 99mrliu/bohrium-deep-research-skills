#!/usr/bin/env python3
"""md2docx.py -- render a Markdown manuscript to a real, editable .docx.

Pure Python 3 stdlib: writes a minimal but valid OOXML package (the same
format Word, LibreOffice and Pages open). A Markdown file renamed .docx is
not a docx; this script produces the genuine container with
[Content_Types].xml, _rels, word/document.xml and word/styles.xml.

Supported Markdown subset (deliberately small and documented):
  # / ## / ### headings        -> Heading 1/2/3 styles
  paragraphs                   -> Normal style, blank-line separated
  - / * bullet lines           -> ListParagraph with a bullet glyph
  **bold**, *italic*, `code`   -> run properties b / i / monospace
Everything else is emitted as literal text (never dropped).

Usage:
  python3 md2docx.py --md introduction.md --out introduction.docx [--title T]

With --verify the script re-opens the produced package and checks the
required members and that document.xml parses as XML.

Exit codes: 0 ok, 2 usage/IO error, 3 produced file failed self-verification.
"""
import argparse
import re
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>
<w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>
<w:pPr><w:outlineLvl w:val="0"/><w:spacing w:before="240" w:after="120"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>
<w:pPr><w:outlineLvl w:val="1"/><w:spacing w:before="200" w:after="100"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/>
<w:pPr><w:outlineLvl w:val="2"/><w:spacing w:before="160" w:after="80"/></w:pPr>
<w:rPr><w:b/><w:i/><w:sz w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/>
<w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:style>
</w:styles>"""

INLINE = re.compile(r"(\*\*.+?\*\*|\*[^*]+?\*|`[^`]+?`)")


def runs_xml(text):
    out = []
    for tok in INLINE.split(text):
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**"):
            out.append('<w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">%s</w:t></w:r>'
                       % escape(tok[2:-2]))
        elif tok.startswith("*") and tok.endswith("*") and len(tok) > 2:
            out.append('<w:r><w:rPr><w:i/></w:rPr><w:t xml:space="preserve">%s</w:t></w:r>'
                       % escape(tok[1:-1]))
        elif tok.startswith("`") and tok.endswith("`") and len(tok) > 2:
            out.append('<w:r><w:rPr><w:rFonts w:ascii="Courier New" w:hAnsi="Courier New"/></w:rPr>'
                       '<w:t xml:space="preserve">%s</w:t></w:r>' % escape(tok[1:-1]))
        else:
            out.append('<w:r><w:t xml:space="preserve">%s</w:t></w:r>' % escape(tok))
    return "".join(out)


def para(text, style=None):
    ppr = '<w:pPr><w:pStyle w:val="%s"/></w:pPr>' % style if style else ""
    return "<w:p>%s%s</w:p>" % (ppr, runs_xml(text))


def md_to_body(md):
    blocks, buf = [], []

    def flush():
        if buf:
            blocks.append(("p", " ".join(x.strip() for x in buf)))
            buf.clear()

    for ln in md.splitlines():
        s = ln.rstrip()
        if not s.strip():
            flush()
            continue
        m = re.match(r"^(#{1,3})\s+(.*)", s)
        if m:
            flush()
            blocks.append(("h%d" % len(m.group(1)), m.group(2).strip()))
            continue
        m = re.match(r"^\s*[-*]\s+(.*)", s)
        if m:
            flush()
            blocks.append(("li", m.group(1).strip()))
            continue
        buf.append(s)
    flush()
    xml = []
    for kind, text in blocks:
        if kind == "h1":
            xml.append(para(text, "Heading1"))
        elif kind == "h2":
            xml.append(para(text, "Heading2"))
        elif kind == "h3":
            xml.append(para(text, "Heading3"))
        elif kind == "li":
            xml.append(para("\u2022  " + text, "ListParagraph"))
        else:
            xml.append(para(text))
    return "".join(xml)


def build_docx(md_text, out_path):
    body = md_to_body(md_text)
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body>%s"
                '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
                '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>'
                "</w:body></w:document>") % body
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/document.xml", document)


def verify_docx(path):
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        need = {"[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml"}
        missing = need - names
        if missing:
            return False, "missing members: %s" % sorted(missing)
        ET.fromstring(z.read("word/document.xml"))
        ET.fromstring(z.read("word/styles.xml"))
        n_words = len(re.findall(r"<w:t[ >]", z.read("word/document.xml").decode("utf-8")))
    return (n_words > 0), ("document.xml parses; %d text runs" % n_words)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--md", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    try:
        md = Path(args.md).read_text(encoding="utf-8")
    except Exception as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if args.title:
        md = "# %s\n\n%s" % (args.title, md)
    build_docx(md, args.out)
    size = Path(args.out).stat().st_size
    print("docx written: %s (%d bytes, real OOXML zip container)" % (args.out, size))
    if args.verify:
        ok, detail = verify_docx(args.out)
        print("self-verify: %s (%s)" % ("PASS" if ok else "FAIL", detail))
        if not ok:
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
