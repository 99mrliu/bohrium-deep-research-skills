#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""docx_spec.py -- 从模板/稿件 DOCX 抽取可逐项核对的格式规格（上游取证）。

每条规格带溯源指针（文件 + OOXML 位置），绝不凭经验猜测。
纯 Python 3 标准库。退出码：0 成功；2 输入不是可读 DOCX。

用法:
  python3 docx_spec.py TEMPLATE.docx --out spec.json [--role template|manuscript]
"""
import argparse, hashlib, json, sys, zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

def twips2cm(v):
    return round(int(v) / 567.0, 3)

def halfpt2pt(v):
    return round(int(v) / 2.0, 2)

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def read_xml(zf, name):
    try:
        return ET.fromstring(zf.read(name))
    except KeyError:
        return None

def item(item_id, category, prop, value, unit, status, src_file, pointer, quote=""):
    return {"id": item_id, "category": category, "property": prop,
            "value": value, "unit": unit, "status": status,
            "source": {"file": src_file, "pointer": pointer, "quote": quote[:120]}}

def extract(docx_path, role):
    items = []
    try:
        zf = zipfile.ZipFile(docx_path)
        bad = zf.testzip()
        if bad:
            raise ValueError("corrupt member: %s" % bad)
        names = set(zf.namelist())
        if "word/document.xml" not in names:
            raise ValueError("not a wordprocessingml package")
    except (zipfile.BadZipFile, ValueError) as e:
        print("ERROR: %s 不是可读 DOCX: %s" % (docx_path, e), file=sys.stderr)
        sys.exit(2)
    src = docx_path

    # ---- 1. 页面几何（sectPr：页面尺寸/页边距/栏数/页眉页脚引用）----
    doc = read_xml(zf, "word/document.xml")
    sects = doc.findall(".//%ssectPr" % W)
    if sects:
        sect = sects[-1]  # 最终节决定整体页面几何
        ptr = "word/document.xml#body/sectPr"
        pgSz = sect.find("%spgSz" % W)
        if pgSz is not None:
            w, h = pgSz.get("%sw" % W), pgSz.get("%sh" % W)
            if w: items.append(item("page.size.width", "page", "page_width", twips2cm(w), "cm", "measured", src, ptr + "/pgSz@w", "w=%s twips" % w))
            if h: items.append(item("page.size.height", "page", "page_height", twips2cm(h), "cm", "measured", src, ptr + "/pgSz@h", "h=%s twips" % h))
            orient = pgSz.get("%sorient" % W)
            if orient: items.append(item("page.orientation", "page", "orientation", orient, "", "measured", src, ptr + "/pgSz@orient", orient))
        pgMar = sect.find("%spgMar" % W)
        if pgMar is not None:
            for side in ("top", "bottom", "left", "right", "header", "footer", "gutter"):
                v = pgMar.get("%s%s" % (W, side))
                if v is not None:
                    items.append(item("page.margin.%s" % side, "page", "margin_%s" % side, twips2cm(v), "cm", "measured", src, ptr + "/pgMar@%s" % side, "%s=%s twips" % (side, v)))
        cols = sect.find("%scols" % W)
        if cols is not None:
            num = cols.get("%snum" % W, "1")
            items.append(item("page.columns", "page", "columns", int(num), "栏", "measured", src, ptr + "/cols@num", "num=%s" % num))
        items.append(item("page.section_count", "page", "section_count", len(sects), "节", "measured", src, "word/document.xml", "sectPr x%d" % len(sects)))
        hdrs = sect.findall("%sheaderReference" % W)
        ftrs = sect.findall("%sfooterReference" % W)
        items.append(item("page.header_footer_refs", "page", "header_footer_refs",
                          {"headers": len(hdrs), "footers": len(ftrs)}, "", "measured", src, ptr, ""))

    # ---- 2. 样式表（字号/字体/行距/段距/对齐/大纲层级）----
    styles = read_xml(zf, "word/styles.xml")
    if styles is not None:
        for st in styles.findall("%sstyle" % W):
            sid = st.get("%sstyleId" % W)
            styp = st.get("%stype" % W)
            name_el = st.find("%sname" % W)
            sname = name_el.get("%sval" % W) if name_el is not None else sid
            ptr = "word/styles.xml#style[@styleId=%s]" % sid
            pPr, rPr = st.find("%spPr" % W), st.find("%srPr" % W)
            if rPr is not None:
                rf = rPr.find("%srFonts" % W)
                if rf is not None:
                    for attr, label in (("ascii", "font_latin"), ("eastAsia", "font_eastasia")):
                        v = rf.get("%s%s" % (W, attr))
                        if v: items.append(item("style.%s.%s" % (sid, label), "style", "%s.%s" % (sname, label), v, "", "measured", src, ptr + "/rPr/rFonts@%s" % attr, v))
                sz = rPr.find("%ssz" % W)
                if sz is not None and sz.get("%sval" % W):
                    items.append(item("style.%s.size" % sid, "style", "%s.size" % sname, halfpt2pt(sz.get("%sval" % W)), "pt", "measured", src, ptr + "/rPr/sz@val", "half-points=%s" % sz.get("%sval" % W)))
                if rPr.find("%sb" % W) is not None:
                    items.append(item("style.%s.bold" % sid, "style", "%s.bold" % sname, True, "", "measured", src, ptr + "/rPr/b", ""))
                if rPr.find("%si" % W) is not None:
                    items.append(item("style.%s.italic" % sid, "style", "%s.italic" % sname, True, "", "measured", src, ptr + "/rPr/i", ""))
            if pPr is not None:
                sp = pPr.find("%sspacing" % W)
                if sp is not None:
                    line, rule = sp.get("%sline" % W), sp.get("%slineRule" % W)
                    if line:
                        if rule in (None, "auto"):
                            val, unit = round(int(line) / 240.0, 3), "倍"
                        else:
                            val, unit = halfpt2pt(line), "pt(%s)" % rule
                        items.append(item("style.%s.line_spacing" % sid, "style", "%s.line_spacing" % sname, val, unit, "measured", src, ptr + "/pPr/spacing@line", "line=%s lineRule=%s" % (line, rule)))
                    for a, label in (("before", "space_before"), ("after", "space_after")):
                        v = sp.get("%s%s" % (W, a))
                        if v: items.append(item("style.%s.%s" % (sid, label), "style", "%s.%s" % (sname, label), halfpt2pt(v), "pt", "measured", src, ptr + "/pPr/spacing@%s" % a, "twentieths=%s" % v))
                jc = pPr.find("%sjc" % W)
                if jc is not None and jc.get("%sval" % W):
                    items.append(item("style.%s.align" % sid, "style", "%s.align" % sname, jc.get("%sval" % W), "", "measured", src, ptr + "/pPr/jc@val", jc.get("%sval" % W)))
                ol = pPr.find("%soutlineLvl" % W)
                if ol is not None and ol.get("%sval" % W) is not None:
                    items.append(item("style.%s.outline_level" % sid, "style", "%s.outline_level" % sname, int(ol.get("%sval" % W)) + 1, "级", "measured", src, ptr + "/pPr/outlineLvl@val", "outlineLvl=%s" % ol.get("%sval" % W)))

    # ---- 3. 题注/编号/页眉页脚文本线索 ----
    if doc is not None:
        caps = 0
        for p in doc.findall(".//%sp" % W):
            st = p.find("%spPr/%spStyle" % (W, W))
            if st is not None and st.get("%sval" % W, "").lower() in ("caption", "captionchar"):
                caps += 1
        if caps:
            items.append(item("content.caption_paragraphs", "content", "caption_paragraphs", caps, "段", "measured", src, "word/document.xml", "pStyle=Caption x%d" % caps))
    hdr_txt = []
    for n in sorted(names):
        if n.startswith("word/header") or n.startswith("word/footer"):
            r = read_xml(zf, n)
            if r is not None:
                t = "".join(t.text or "" for t in r.findall(".//%st" % W)).strip()
                if t:
                    hdr_txt.append({"part": n, "text": t[:80]})
    if hdr_txt:
        items.append(item("page.header_footer_text", "page", "header_footer_text", hdr_txt, "", "measured", src, "word/header*.xml", ""))

    return {"spec_version": "1.0", "generator": "docx_spec.py",
            "sources": [{"file": docx_path, "sha256": sha256_of(docx_path),
                         "kind": "docx-%s" % role}],
            "items": items}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("docx")
    ap.add_argument("--out", required=True)
    ap.add_argument("--role", default="template", choices=["template", "manuscript"])
    a = ap.parse_args()
    spec = extract(a.docx, a.role)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    print("spec items: %d -> %s" % (len(spec["items"]), a.out))

if __name__ == "__main__":
    main()
