#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""spec_check.py -- 用规格账本机器核对输出 DOCX，逐项 PASS/FAIL/UNKNOWN。

只对可机器核对的项下结论；其余记 UNKNOWN，留给 Agent 凭渲染证据人工判定
（unknown 项必须进入 result.json 的 manual_confirm/uncertainties）。
退出码：0 全部 PASS 或仅 UNKNOWN；1 存在 FAIL；2 输出文件不可读。

用法:
  python3 spec_check.py merged_spec.json OUTPUT.docx --json check.json --md check.md
"""
import argparse, json, sys, zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

def twips2cm(v): return round(int(v) / 567.0, 3)
def halfpt2pt(v): return round(int(v) / 2.0, 2)

def load_output_geometry(docx_path):
    zf = zipfile.ZipFile(docx_path)
    doc = ET.fromstring(zf.read("word/document.xml"))
    geo = {}
    sects = doc.findall(".//%ssectPr" % W)
    if sects:
        sect = sects[-1]
        pgSz, pgMar, cols = sect.find("%spgSz" % W), sect.find("%spgMar" % W), sect.find("%scols" % W)
        if pgSz is not None:
            geo["page.size.width"] = twips2cm(pgSz.get("%sw" % W, "0"))
            geo["page.size.height"] = twips2cm(pgSz.get("%sh" % W, "0"))
        if pgMar is not None:
            for side in ("top", "bottom", "left", "right", "header", "footer", "gutter"):
                v = pgMar.get("%s%s" % (W, side))
                if v is not None:
                    geo["page.margin.%s" % side] = twips2cm(v)
        if cols is not None:
            geo["page.columns"] = int(cols.get("%snum" % W, "1"))
    geo["page.section_count"] = len(sects)
    # 样式表实测（用于 style.* 项核对）
    styles = {}
    try:
        st_root = ET.fromstring(zf.read("word/styles.xml"))
    except KeyError:
        st_root = None
    if st_root is not None:
        for st in st_root.findall("%sstyle" % W):
            sid = st.get("%sstyleId" % W)
            rPr, pPr = st.find("%srPr" % W), st.find("%spPr" % W)
            if rPr is not None:
                sz = rPr.find("%ssz" % W)
                if sz is not None and sz.get("%sval" % W):
                    styles["style.%s.size" % sid] = halfpt2pt(sz.get("%sval" % W))
                rf = rPr.find("%srFonts" % W)
                if rf is not None:
                    if rf.get("%sascii" % W):
                        styles["style.%s.font_latin" % sid] = rf.get("%sascii" % W)
                    if rf.get("%seastAsia" % W):
                        styles["style.%s.font_eastasia" % sid] = rf.get("%seastAsia" % W)
                if rPr.find("%sb" % W) is not None:
                    styles["style.%s.bold" % sid] = True
            if pPr is not None:
                sp = pPr.find("%sspacing" % W)
                if sp is not None and sp.get("%sline" % W):
                    rule = sp.get("%slineRule" % W)
                    styles["style.%s.line_spacing" % sid] = (round(int(sp.get("%sline" % W)) / 240.0, 3)
                                                             if rule in (None, "auto") else halfpt2pt(sp.get("%sline" % W)))
                jc = pPr.find("%sjc" % W)
                if jc is not None and jc.get("%sval" % W):
                    styles["style.%s.align" % sid] = jc.get("%sval" % W)
                ol = pPr.find("%soutlineLvl" % W)
                if ol is not None and ol.get("%sval" % W) is not None:
                    styles["style.%s.outline_level" % sid] = int(ol.get("%sval" % W)) + 1
    return geo, styles

def close(a, b, tol):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return a == b

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec")
    ap.add_argument("output_docx")
    ap.add_argument("--json", required=True)
    ap.add_argument("--md", required=True)
    ap.add_argument("--tolerance", type=float, default=0.06, help="数值容差（默认 0.06，单位随项）")
    a = ap.parse_args()

    with open(a.spec, encoding="utf-8") as f:
        spec = json.load(f)
    try:
        geo, styles = load_output_geometry(a.output_docx)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        print("ERROR: 输出不可读: %s" % e, file=sys.stderr)
        sys.exit(2)
    measured = dict(geo)
    measured.update(styles)

    results = []
    n_fail = 0
    for it in spec.get("items", []):
        iid, want = it["id"], it["value"]
        entry = {"id": iid, "expected": want, "unit": it.get("unit", ""),
                 "spec_source": it.get("source", {}), "spec_status": it.get("status")}
        if iid in measured:
            got = measured[iid]
            ok = close(got, want, a.tolerance) if isinstance(want, (int, float)) else (got == want)
            entry.update(verdict="PASS" if ok else "FAIL", measured=got,
                         basis="机器实测 %s" % a.output_docx)
            if not ok:
                n_fail += 1
        else:
            entry.update(verdict="UNKNOWN", measured=None,
                         basis="非机器可核对项（题注措辞/参考文献样式/版心细节等），需人工或渲染证据")
        results.append(entry)

    summary = {"total": len(results),
               "pass": sum(1 for r in results if r["verdict"] == "PASS"),
               "fail": n_fail,
               "unknown": sum(1 for r in results if r["verdict"] == "UNKNOWN")}
    report = {"spec": a.spec, "output": a.output_docx, "tolerance": a.tolerance,
              "summary": summary, "results": results}
    with open(a.json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    lines = ["# 规格核对报告（spec_check）", "",
             "输出文件：`%s`；容差 ±%s" % (a.output_docx, a.tolerance), "",
             "PASS %d / FAIL %d / UNKNOWN %d（共 %d 项）" % (
                 summary["pass"], summary["fail"], summary["unknown"], summary["total"]), "",
             "| id | 期望 | 实测 | 判定 | 规格溯源 |", "|---|---|---|---|---|"]
    for r in results:
        src = r["spec_source"]
        lines.append("| %s | %s %s | %s | %s | %s %s |" % (
            r["id"], r["expected"], r["unit"],
            r["measured"] if r["measured"] is not None else "—",
            r["verdict"], src.get("file", "?"), src.get("pointer", "")))
    with open(a.md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("PASS %d FAIL %d UNKNOWN %d -> %s" % (summary["pass"], n_fail, summary["unknown"], a.json))
    sys.exit(1 if n_fail else 0)

if __name__ == "__main__":
    main()
