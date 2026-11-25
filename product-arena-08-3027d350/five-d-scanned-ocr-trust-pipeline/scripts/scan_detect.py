#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan_detect.py — 纯标准库字节级扫描页判定 + OCR 移交清单生成。

做法：正则扫描 PDF 间接对象，zlib 解压内容流（支持 FlateDecode 与
ASCIIHexDecode 及其链式组合），对每页统计：
  - 图像 XObject 个数与像素量（/Width x /Height 之和，不解码像素数据）
  - 内容流 BT..ET 块内文本绘制操作（Tj/TJ 字符串）的字符数
据此给出 page_class:
  born_digital / scanned / mixed / empty；截尾或解析失败页标 unknown。
若环境提供 PyMuPDF / pdftotext，则做交叉验证并把分歧写入报告
（仅作旁证，不改变主判定；缺失时降级并在 engine 字段说明）。

输出（--outdir 下）：
  scan_report.json   逐页判定报告
  handoff_ocr.json   扫描/混合/未知页移交清单（page, suggest_dpi,
                     suggest_preprocess, reason）

退出码：0=成功，2=部分（存在 unknown 页或截尾告警），3=失败。
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import zlib
from pathlib import Path

# ---- 阈值（与 SKILL.md「方法要点」一致，改动需同步文档） ----
MIN_TEXT_CHARS = 100          # 每页可绘制文本字符数低于此值视为文字极少
FULLPAGE_PIXELS = 100_000     # 单页图像像素总量达到此值视为存在整页位图
SUGGEST_DPI = 300
SUGGEST_PREPROCESS = ["deskew", "binarize"]

EXIT_OK, EXIT_PARTIAL, EXIT_FAIL = 0, 2, 3

OBJ_RE = re.compile(rb"(\d+)\s+(\d+)\s+obj\b(.*?)\bendobj", re.S)
PAGE_RE = re.compile(rb"/Type\s*/Page(?![A-Za-z])")
PAGES_RE = re.compile(rb"/Type\s*/Pages(?![A-Za-z])")
CATALOG_RE = re.compile(rb"/Type\s*/Catalog(?![A-Za-z])")


def parse_objects(data: bytes):
    """{(num, gen): body_bytes}"""
    objs = {}
    for m in OBJ_RE.finditer(data):
        objs[(int(m.group(1)), int(m.group(2)))] = m.group(3)
    return objs


def resolve_ref(body: bytes, key: bytes):
    """在对象体内找 /key N G R，返回 (N, G) 或 None。"""
    m = re.search(rb"/" + key + rb"\s+(\d+)\s+(\d+)\s+R", body)
    return (int(m.group(1)), int(m.group(2))) if m else None


def page_order(objs):
    """按 /Pages 树的 /Kids 顺序返回页对象 key 列表；失败返回 None。"""
    root_ref = None
    expected = None
    for key, body in objs.items():
        if CATALOG_RE.search(body):
            root_ref = resolve_ref(body, b"Pages")
            break
    if root_ref is None:
        return None, None
    pages_body = objs.get(root_ref)
    if pages_body is None:
        return None, None
    m = re.search(rb"/Count\s+(\d+)", pages_body)
    if m:
        expected = int(m.group(1))

    order = []

    def walk(ref, depth=0):
        if depth > 64:
            return
        body = objs.get(ref)
        if body is None:
            return
        if PAGE_RE.search(body):
            order.append(ref)
            return
        km = re.search(rb"/Kids\s*\[(.*?)\]", body, re.S)
        if km:
            for rm in re.finditer(rb"(\d+)\s+(\d+)\s+R", km.group(1)):
                walk((int(rm.group(1)), int(rm.group(2))), depth + 1)

    walk(root_ref)
    return (order or None), expected


def ascii_hex_decode(raw: bytes) -> bytes:
    hexchars = re.sub(rb"\s+", b"", raw.split(b">")[0])
    if len(hexchars) % 2:
        hexchars += b"0"
    return bytes.fromhex(hexchars.decode("ascii"))


def decode_stream_body(body: bytes):
    """返回 (decoded_bytes|None, note|None)。支持 Flate/ASCIIHex 及链式组合。"""
    sm = re.search(rb"stream\r?\n(.*?)endstream", body, re.S)
    if not sm:
        return None, "no_stream"
    data = sm.group(1).rstrip(b"\r\n")
    head = body[: sm.start()]
    filters = []
    fm = re.search(rb"/Filter\s*(\[[^\]]*\]|/[A-Za-z0-9]+)", head)
    if fm:
        filters = re.findall(rb"/([A-Za-z0-9]+)", fm.group(1))
    for f in filters:
        try:
            if f in (b"FlateDecode", b"Fl"):
                try:
                    data = zlib.decompress(data)
                except zlib.error:
                    d = zlib.decompressobj()
                    data = d.decompress(data) + d.flush()
            elif f in (b"ASCIIHexDecode", b"AHx"):
                data = ascii_hex_decode(data)
            elif f in (b"ASCII85Decode", b"A85"):
                import base64
                data = base64.a85decode(data.split(b"~>")[0], adobe=False)
            else:
                return None, "unsupported_filter:%s" % f.decode("ascii", "replace")
        except Exception as exc:  # 解压失败如实上报
            return None, "decode_error:%s:%s" % (f.decode("ascii", "replace"), exc)
    return data, None


PAREN_RE = re.compile(rb"\((?:\\.|[^\\()])*\)")
HEXSTR_RE = re.compile(rb"(?<!<)<([0-9A-Fa-f\s]+)>(?!>)")
BT_RE = re.compile(rb"BT(.*?)ET", re.S)


def count_text_chars(content: bytes) -> int:
    """近似统计文本绘制操作字符数：BT..ET 内括号字符串与十六进制串。

    这是字节级近似（不解析字体编码），对「有无文字层」的判定足够，
    但对 CJK/复合字体的字符数可能低估，报告中以 text_chars_approx 标注。
    """
    n = 0
    for blk in BT_RE.findall(content):
        for pm in PAREN_RE.finditer(blk):
            inner = pm.group(0)[1:-1]
            inner = re.sub(rb"\\(.)", rb"\1", inner)  # 转义字符按 1 字符计
            n += len(inner)
        for hm in HEXSTR_RE.finditer(blk):
            n += len(re.sub(rb"\s+", b"", hm.group(1))) // 2
    return n


def image_stats_for_page(objs, page_body: bytes):
    """返回 (n_images, total_pixels, notes)。解析页内联或间接 /XObject 资源。"""
    notes = []
    bodies = [page_body]
    rref = resolve_ref(page_body, b"Resources")
    if rref and rref in objs:
        bodies.append(objs[rref])
    xobj_refs = []
    for b in bodies:
        xm = re.search(rb"/XObject\s*<<(.*?)>>", b, re.S)
        if xm:
            for rm in re.finditer(rb"/[A-Za-z0-9]+\s+(\d+)\s+(\d+)\s+R", xm.group(1)):
                xobj_refs.append((int(rm.group(1)), int(rm.group(2))))
    n_img, pixels = 0, 0
    for ref in xobj_refs:
        body = objs.get(ref)
        if body is None:
            notes.append("xobject_missing:%d" % ref[0])
            continue
        if not re.search(rb"/Subtype\s*/Image(?![A-Za-z])", body):
            continue
        n_img += 1
        wm = re.search(rb"/Width\s+(\d+)", body)
        hm = re.search(rb"/Height\s+(\d+)", body)
        if wm and hm:
            pixels += int(wm.group(1)) * int(hm.group(1))
        else:
            notes.append("image_no_dims:%d" % ref[0])
    return n_img, pixels, notes


def classify(text_chars, image_pixels):
    fullpage = image_pixels >= FULLPAGE_PIXELS
    if text_chars == 0 and image_pixels == 0:
        return "empty", fullpage
    if text_chars == 0:
        return "scanned", fullpage
    if text_chars < MIN_TEXT_CHARS:
        return ("scanned" if fullpage else "mixed"), fullpage
    return ("mixed" if fullpage else "born_digital"), fullpage


def cross_validate_pymupdf(pdf_path):
    """可选引擎：PyMuPDF 逐页文本字符数与图像像素量。缺失返回 None。"""
    try:
        import pymupdf  # type: ignore
    except Exception:
        try:
            import fitz as pymupdf  # type: ignore
        except Exception:
            return None
    try:
        doc = pymupdf.open(str(pdf_path))
        pages = []
        for i in range(doc.page_count):
            pg = doc[i]
            text_chars = len(pg.get_text("text").strip())
            px = 0
            n_img = 0
            try:
                for info in pg.get_image_info():
                    n_img += 1
                    px += int(info.get("width", 0)) * int(info.get("height", 0))
            except Exception:
                for img in pg.get_images(full=True):
                    n_img += 1
                    try:
                        pix = doc.extract_image(img[0])
                        px += int(pix.get("width", 0)) * int(pix.get("height", 0))
                    except Exception:
                        pass
            cls, _ = classify(text_chars, px)
            pages.append({"page": i + 1, "text_chars": text_chars,
                          "image_xobjects": n_img, "image_pixels": px,
                          "page_class": cls})
        ver = getattr(pymupdf, "__doc__", "pymupdf") or "pymupdf"
        doc.close()
        return {"engine": ver.split(":")[0], "pages": pages}
    except Exception as exc:
        return {"engine": "pymupdf", "error": str(exc), "pages": []}


def cross_validate_pdftotext(pdf_path, n_pages):
    exe = shutil.which("pdftotext")
    if not exe:
        return None
    pages = []
    try:
        for i in range(1, n_pages + 1):
            r = subprocess.run([exe, "-f", str(i), "-l", str(i), str(pdf_path), "-"],
                               capture_output=True, timeout=60)
            txt = r.stdout.decode("utf-8", "replace")
            pages.append({"page": i, "text_chars": len(txt.strip())})
        return {"engine": "pdftotext", "pages": pages}
    except Exception as exc:
        return {"engine": "pdftotext", "error": str(exc), "pages": pages}


def main(argv=None):
    ap = argparse.ArgumentParser(description="字节级扫描页判定 + OCR 移交清单")
    ap.add_argument("--pdf", required=True, help="输入 PDF 路径")
    ap.add_argument("--outdir", required=True, help="输出目录（scan_report.json / handoff_ocr.json）")
    ap.add_argument("--no-crossval", action="store_true", help="跳过可选引擎交叉验证")
    args = ap.parse_args(argv)

    pdf_path = Path(args.pdf)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    warnings, notes = [], []

    if not pdf_path.is_file():
        print(json.dumps({"error": "pdf_not_found", "pdf": str(pdf_path)}))
        return EXIT_FAIL
    data = pdf_path.read_bytes()
    if not data.startswith(b"%PDF-"):
        print(json.dumps({"error": "not_a_pdf", "pdf": str(pdf_path)}))
        return EXIT_FAIL
    truncated = b"%%EOF" not in data[-1024:]
    if truncated:
        warnings.append("truncated:文件尾部 1KB 内未见 %%EOF，判定结果可能不完整")

    objs = parse_objects(data)
    if not objs:
        print(json.dumps({"error": "no_objects_parsed", "pdf": str(pdf_path)}))
        return EXIT_FAIL
    order, expected = page_order(objs)
    if order is None:
        order = [k for k, b in sorted(objs.items()) if PAGE_RE.search(b)]
        notes.append("page_order_fallback:未能沿 /Kids 树排序，按对象号排序")
    if expected is not None and len(order) < expected:
        warnings.append("page_count_mismatch:/Count=%d 但只解析到 %d 个页对象，缺失页标 unknown"
                        % (expected, len(order)))

    pages = []
    for idx, ref in enumerate(order, start=1):
        body = objs.get(ref)
        rec = {"page": idx, "object": "%d %d" % ref,
               "page_class": "unknown", "text_chars_approx": 0,
               "image_xobjects": 0, "image_pixels": 0, "fullpage_image": False,
               "notes": []}
        try:
            n_img, pixels, img_notes = image_stats_for_page(objs, body)
            rec["image_xobjects"] = n_img
            rec["image_pixels"] = pixels
            rec["notes"].extend(img_notes)
            # 内容流（/Contents 单引用或数组）
            contents = []
            cref = resolve_ref(body, b"Contents")
            if cref:
                contents.append(cref)
            else:
                cm = re.search(rb"/Contents\s*\[(.*?)\]", body, re.S)
                if cm:
                    contents = [(int(a), int(b)) for a, b in
                                re.findall(rb"(\d+)\s+(\d+)\s+R", cm.group(1))]
            text_chars = 0
            for cr in contents:
                cbody = objs.get(cr)
                if cbody is None:
                    rec["notes"].append("contents_missing:%d" % cr[0])
                    continue
                decoded, note = decode_stream_body(cbody)
                if decoded is None:
                    rec["notes"].append("contents_" + (note or "decode_failed"))
                    continue
                text_chars += count_text_chars(decoded)
            rec["text_chars_approx"] = text_chars
            cls, fullpage = classify(text_chars, pixels)
            rec["page_class"] = cls
            rec["fullpage_image"] = fullpage
            if any(n.startswith("contents_unsupported_filter") or
                   n.startswith("contents_decode_error") for n in rec["notes"]):
                rec["page_class"] = "unknown"
                rec["notes"].append("内容流解码失败，页类标 unknown")
            elif any(n.startswith("contents_missing") or
                     n.startswith("xobject_missing") or
                     n.startswith("image_no_dims") for n in rec["notes"]):
                rec["page_class"] = "unknown"
                rec["notes"].append("引用对象缺失或不完整（疑截尾），页类标 unknown")
        except Exception as exc:
            rec["page_class"] = "unknown"
            rec["notes"].append("parse_error:%s" % exc)
        pages.append(rec)

    # /Count 与实际解析不符时补齐 unknown 页（截尾诚实路径）
    if expected is not None:
        for idx in range(len(order) + 1, expected + 1):
            pages.append({"page": idx, "object": None, "page_class": "unknown",
                          "text_chars_approx": 0, "image_xobjects": 0,
                          "image_pixels": 0, "fullpage_image": False,
                          "notes": ["page_object_missing:页对象缺失（疑截尾），标 unknown"]})

    engine = {"primary": "stdlib-regex+zlib", "cross_validation": []}
    if not args.no_crossval:
        cv = cross_validate_pymupdf(pdf_path)
        if cv is None:
            engine["cross_validation"].append(
                {"engine": "pymupdf", "status": "unavailable",
                 "reason": "未安装 PyMuPDF，跳过交叉验证（不影响主判定）"})
        else:
            for cp in cv.get("pages", []):
                mp = next((p for p in pages if p["page"] == cp["page"]), None)
                cp["agree"] = (mp is not None and mp["page_class"] == cp["page_class"])
            cv["status"] = "ok"
            engine["cross_validation"].append(cv)
        cv2 = cross_validate_pdftotext(pdf_path, len(pages))
        if cv2 is None:
            engine["cross_validation"].append(
                {"engine": "pdftotext", "status": "unavailable",
                 "reason": "PATH 中无 pdftotext，跳过文本旁证"})
        else:
            cv2["status"] = "ok"
            engine["cross_validation"].append(cv2)

    class_counts = {}
    for p in pages:
        class_counts[p["page_class"]] = class_counts.get(p["page_class"], 0) + 1
    report = {
        "pdf": str(pdf_path),
        "pdf_bytes": len(data),
        "truncated": truncated,
        "page_count": len(pages),
        "class_counts": class_counts,
        "thresholds": {"min_text_chars": MIN_TEXT_CHARS,
                       "fullpage_pixels": FULLPAGE_PIXELS},
        "engine": engine,
        "warnings": warnings,
        "notes": notes,
        "pages": pages,
    }
    (outdir / "scan_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    handoff_pages = []
    for p in pages:
        cls = p["page_class"]
        if cls in ("scanned", "mixed", "unknown"):
            if cls == "scanned":
                reason = "无文字层（text_chars=0）且存在整页位图" if p["fullpage_image"] \
                    else "无文字层（text_chars=0）且含图像"
            elif cls == "mixed":
                reason = "文本极少（<%d 字符）或文字层与整页位图并存，需 OCR 补全" % MIN_TEXT_CHARS
            else:
                reason = "页类 unknown（解析失败/截尾），保守起见一并移交 OCR"
            handoff_pages.append({
                "page": p["page"],
                "page_class": cls,
                "suggest_dpi": SUGGEST_DPI,
                "suggest_preprocess": list(SUGGEST_PREPROCESS),
                "reason": reason,
            })
    handoff = {
        "pdf": str(pdf_path),
        "generated_by": "scan_detect.py",
        "n_pages_to_ocr": len(handoff_pages),
        "pages": handoff_pages,
        "notes": ["OCR 本体移交平台 ocr-tool 执行；本清单仅给页码与建议参数"],
    }
    (outdir / "handoff_ocr.json").write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8")

    has_unknown = any(p["page_class"] == "unknown" for p in pages)
    code = EXIT_PARTIAL if (has_unknown or warnings) else EXIT_OK
    print(json.dumps({"status": "partial" if code == EXIT_PARTIAL else "ok",
                      "scan_report": str(outdir / "scan_report.json"),
                      "handoff_ocr": str(outdir / "handoff_ocr.json"),
                      "class_counts": class_counts,
                      "exit_code": code}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
