#!/usr/bin/env python3
"""source_index.py — 把案例上游材料"焊"成一份可定位、可复核的源索引。

扫描 --materials 目录（默认 /input）中的 .pdf / .txt / .md：
  * .pdf     -> 调 pdftotext -layout 抽文本；失败则去掉 -layout 重试；
                再失败则标记 unparseable 并记录原因。
                PATH 中不存在 pdftotext 且目录里确有 PDF 时，直接 exit 2。
  * .txt/.md -> 直接读取；按换页符 \\f 切页（与 pdftotext 输出同约定）。

产物 source_index.json（默认 /app/work/source_index.json）按文档记录：
  pages[]     逐页文本 span（page / char_start / char_end / text）
  captions[]  Figure/Table 题注重册表（label、所在页、题注全文）
  sections[]  节标题注册表（所在页、标题行）
  numbers[]   数字注册表（数值 token、可选单位、所在页、上下文片段）

退出码：0 成功；1 门控违例（stdout 逐项失败清单，如无可解析文档）；
2 用法/IO/工具缺失错误。仅依赖 Python3 标准库与系统 pdftotext。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

TEXT_EXT = (".txt", ".md")

# 题注行：Figure 2 / Fig. 3 / Table 1（允许行首空白）
CAPTION_RE = re.compile(r"^\s*((?:Figure|Fig\.?|Table)\s*\d+)[.:]?\s*(.*)$")
# 节标题：编号节（"2. Methods"、"3.1 Data"，标题部分仅字母/空格/连字符，
# 以免把 "178 Wh/kg under ..." 这类正文行误判为标题）或常见无编号节名单
NUMBERED_SECTION_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)*)\.?\s+([A-Za-z][A-Za-z\-& ]{1,70})$")
NAMED_SECTIONS = (
    "abstract", "introduction", "background", "methods", "materials and methods",
    "results", "results and discussion", "discussion", "conclusion",
    "conclusions", "references", "acknowledgments", "supplementary",
)
# 数字 token：不被字母/点/符号紧贴前缀；允许小数；右侧不得再跟数字或点
NUMBER_RE = re.compile(r"(?<![\w.+-])(\d+(?:,\d{3})*(?:\.\d+)?)(?![\d.])")
# 数字后的可选单位 token（% 紧贴或一个词）
UNIT_RE = re.compile(r"\s*(%|[A-Za-zμ°Ω][\wμ°/%²³.-]{0,15})")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text_file(path):
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def pdftotext_extract(pdf_path):
    """先 -layout，失败重试普通模式。返回 (text_or_None, method_or_error)。"""
    for args, tag in ((["-layout"], "pdftotext-layout"),
                      ([], "pdftotext-plain")):
        try:
            r = subprocess.run(
                ["pdftotext"] + args + [pdf_path, "-"],
                capture_output=True, timeout=180,
            )
        except FileNotFoundError:
            return None, "pdftotext not found in PATH"
        except subprocess.TimeoutExpired:
            return None, "pdftotext timeout"
        if r.returncode == 0 and r.stdout:
            for enc in ("utf-8", "latin-1"):
                try:
                    return r.stdout.decode(enc), tag
                except UnicodeDecodeError:
                    continue
            return r.stdout.decode("utf-8", errors="replace"), tag
        err = (r.stderr or b"").decode("utf-8", errors="replace").strip()
        last = err.splitlines()[-1] if err else "unknown pdftotext error"
    return None, last


def split_pages(text):
    """按 \\f 切页；去掉末尾空白页。返回 [{page, char_start, char_end, text}]。"""
    raw_pages = text.split("\f")
    while len(raw_pages) > 1 and raw_pages[-1].strip() == "":
        raw_pages.pop()
    pages = []
    pos = 0
    for i, pg in enumerate(raw_pages):
        pages.append({"page": i + 1, "char_start": pos,
                      "char_end": pos + len(pg), "chars": len(pg),
                      "text": pg})
        pos += len(pg) + 1
    return pages


def harvest_captions(doc_id, pages):
    caps = []
    for pg in pages:
        lines = pg["text"].splitlines()
        i = 0
        while i < len(lines):
            m = CAPTION_RE.match(lines[i])
            if m:
                label = re.sub(r"\s+", " ", m.group(1)).strip()
                body = m.group(2).strip()
                # 题注可能折行：合并后续非空行，直到空行或新题注/新节
                j = i + 1
                while j < len(lines) and lines[j].strip() \
                        and not CAPTION_RE.match(lines[j]) \
                        and not NUMBERED_SECTION_RE.match(lines[j]):
                    body += " " + lines[j].strip()
                    j += 1
                caps.append({"doc_id": doc_id, "label": label,
                             "page": pg["page"], "text": body[:400]})
                i = j
            else:
                i += 1
    return caps


def harvest_sections(doc_id, pages):
    secs = []
    for pg in pages:
        for line in pg["text"].splitlines():
            s = line.strip()
            if not s or len(s) > 90:
                continue
            m = NUMBERED_SECTION_RE.match(s)
            if m:
                secs.append({"doc_id": doc_id, "page": pg["page"],
                             "heading": s})
                continue
            if s.rstrip(".:").lower() in NAMED_SECTIONS:
                secs.append({"doc_id": doc_id, "page": pg["page"],
                             "heading": s})
    return secs


def harvest_numbers(doc_id, pages):
    nums = []
    for pg in pages:
        text = pg["text"]
        for m in NUMBER_RE.finditer(text):
            value = m.group(1).replace(",", "")
            um = UNIT_RE.match(text, m.end(1))
            unit = um.group(1).rstrip(".") if um and um.group(1) else None
            if unit == "":
                unit = None
            lo = max(0, m.start(1) - 30)
            hi = min(len(text), m.end(1) + 30)
            context = re.sub(r"\s+", " ", text[lo:hi]).strip()
            nums.append({"doc_id": doc_id, "value": value,
                         "unit": unit, "page": pg["page"],
                         "context": context})
    return nums


def main():
    ap = argparse.ArgumentParser(
        description="把上游材料焊成源索引（页级 span + 题注/节标题/数字注册表）")
    ap.add_argument("--materials", default="/input",
                    help="材料目录（默认 /input）")
    ap.add_argument("--out", default="/app/work/source_index.json",
                    help="源索引输出路径（默认 /app/work/source_index.json）")
    args = ap.parse_args()

    materials = args.materials
    if not os.path.isdir(materials):
        print(f"[IO ERROR] 材料目录不存在: {materials}")
        return 2

    entries = sorted(
        f for f in os.listdir(materials)
        if os.path.isfile(os.path.join(materials, f))
        and f.lower().endswith((".pdf",) + TEXT_EXT))
    if not entries:
        print(f"[IO ERROR] 材料目录中没有 .pdf/.txt/.md: {materials}")
        return 2

    has_pdf = any(f.lower().endswith(".pdf") for f in entries)
    if has_pdf and shutil.which("pdftotext") is None:
        print("[IO ERROR] 目录含 PDF 但 PATH 中找不到 pdftotext，"
              "无法建立可信索引（禁止凭文件名臆测内容）")
        return 2

    failures = []
    docs = []
    seen_ids = set()

    for fname in entries:
        path = os.path.join(materials, fname)
        stem = os.path.splitext(fname)[0]
        doc_id = re.sub(r"[^A-Za-z0-9_\-]+", "_", stem).strip("_") or "doc"
        base, n = doc_id, 2
        while doc_id in seen_ids:
            doc_id = f"{base}_{n}"
            n += 1
        seen_ids.add(doc_id)
        sha = sha256_file(path)

        if fname.lower().endswith(".pdf"):
            text, method = pdftotext_extract(path)
            if text is None:
                failures.append(
                    f"UNPARSEABLE {fname}: pdftotext 两级尝试均失败 ({method})")
                docs.append({"doc_id": doc_id, "source_file": fname,
                             "sha256": sha, "kind": "pdf",
                             "parse_status": "unparseable",
                             "parse_method": None, "page_count": 0,
                             "pages": [], "captions": [], "sections": [],
                             "numbers": [], "error": method})
                continue
            kind = "pdf"
        else:
            text = read_text_file(path)
            kind, method = "text", "direct-read"

        pages = split_pages(text)
        docs.append({
            "doc_id": doc_id, "source_file": fname, "sha256": sha,
            "kind": kind, "parse_status": "ok", "parse_method": method,
            "page_count": len(pages), "pages": pages,
            "captions": harvest_captions(doc_id, pages),
            "sections": harvest_sections(doc_id, pages),
            "numbers": harvest_numbers(doc_id, pages),
        })

    index = {
        "index_version": 1,
        "materials_dir": os.path.abspath(materials),
        "doc_count": len(docs),
        "parse_ok": sum(1 for d in docs if d["parse_status"] == "ok"),
        "docs": docs,
    }
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"[source_index] 材料目录: {materials}")
    for d in docs:
        print(f"[source_index]   {d['doc_id']}: kind={d['kind']} "
              f"parse_method={d['parse_method']} pages={d['page_count']} "
              f"captions={len(d['captions'])} sections={len(d['sections'])} "
              f"numbers={len(d['numbers'])}")
    print(f"[source_index] 索引写出: {args.out}")
    if index["parse_ok"] == 0:
        failures.append("GATE 无任何可解析文档，索引为空")
    if failures:
        print("[source_index] 失败清单:")
        for item in failures:
            print("  - " + item)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
