#!/usr/bin/env python3
"""corpus_build.py — 由案例材料构建带页码定位的文本语料库。

扫描 --materials 目录（默认 /input）中的 .pdf / .txt / .md：
  * .pdf  -> 调 pdftotext -layout 抽取文本；失败则重试不带 -layout；
             再失败则标记 unparseable 并记录原因。
  * .txt/.md -> 直接读取，按单页模拟。
为每篇文档生成 doc_id（文件名派生）、源文件 SHA-256、页数与每页字符区间
（pdftotext 以 \\f 分页），并从首页文本抽取文献身份候选
（标题首行、DOI 正则、四位年份、作者行启发式）。

产物（写入 <workdir>/corpus/）：
  text/<doc_id>.txt        每篇文档的纯文本
  corpus_index.json        语料索引（页结构与定位区间）
  identity_candidates.json 每篇文档的身份候选

退出码：0 通过；1 门控违例（stdout 逐项失败清单）；2 用法/IO 错误。
仅依赖 Python3 标准库与系统 pdftotext。
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>)\]}]+")
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
TEXT_EXT = (".txt", ".md")
NAME_LINE_RE = re.compile(
    r"^[A-Z][A-Za-z\-']+(?:\s+[A-Z]\.?)*(?:\s+[A-Z][A-Za-z\-']+)+"
)


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


def pdftotext_extract(pdf_path, out_txt):
    """先 -layout，失败重试普通模式。返回 (ok, method_or_error)。"""
    for args, tag in ((["-layout"], "layout"), ([], "plain")):
        try:
            r = subprocess.run(
                ["pdftotext"] + args + [pdf_path, out_txt],
                capture_output=True, text=True, timeout=180,
            )
        except FileNotFoundError:
            return False, "pdftotext not found in PATH"
        except subprocess.TimeoutExpired:
            return False, "pdftotext timeout"
        if r.returncode == 0 and os.path.exists(out_txt):
            return True, tag
        err = (r.stderr or "").strip().splitlines()
        last = err[-1] if err else "unknown pdftotext error"
    return False, last


def page_spans(text):
    """按 \\f 分页，返回 (pages, spans)；spans 给出每页在 text 中的字符区间。"""
    raw_pages = text.split("\f")
    spans = []
    pos = 0
    for i, pg in enumerate(raw_pages):
        start = pos
        end = pos + len(pg)
        spans.append({"page": i + 1, "start": start, "end": end,
                      "chars": len(pg)})
        pos = end + 1  # 跳过 \f 本身
    # 去掉末尾空白页（pdftotext 常在文末多输出一个 \f）
    while len(spans) > 1 and raw_pages[spans[-1]["page"] - 1].strip() == "":
        spans.pop()
    return spans


def extract_identity(first_page_text):
    lines = [l.strip() for l in first_page_text.splitlines()]
    nonempty = [l for l in lines if l]
    title = nonempty[0] if nonempty else None
    doi = None
    m = DOI_RE.search(first_page_text)
    if m:
        doi = m.group(0).rstrip(".,;:")
    year = None
    ym = YEAR_RE.search(first_page_text)
    if ym:
        year = int(ym.group(1))
    authors = None
    for l in nonempty[1:9]:
        if DOI_RE.search(l):
            continue
        has_multi = ("," in l) or (" and " in l) or ("&" in l)
        if NAME_LINE_RE.match(l) and (has_multi or len(l.split()) <= 8):
            if not re.search(r"\d{4}", l) and len(l) <= 120:
                authors = l
                break
    return {"title_candidate": title, "doi_candidate": doi,
            "year_candidate": year, "author_line_candidate": authors}


def main():
    ap = argparse.ArgumentParser(
        description="构建带页码定位的文献语料库（corpus index + identity candidates）")
    ap.add_argument("--materials", default="/input",
                    help="材料目录（默认 /input）")
    ap.add_argument("--workdir", default="/app/work",
                    help="工作目录（默认 /app/work），语料写入 <workdir>/corpus/")
    args = ap.parse_args()

    materials = args.materials
    if not os.path.isdir(materials):
        print(f"[IO ERROR] 材料目录不存在: {materials}")
        return 2
    corpus_dir = os.path.join(args.workdir, "corpus")
    text_dir = os.path.join(corpus_dir, "text")
    os.makedirs(text_dir, exist_ok=True)

    failures = []
    docs = []
    identities = {}
    seen_ids = set()

    entries = sorted(os.listdir(materials))
    for fname in entries:
        path = os.path.join(materials, fname)
        if not os.path.isfile(path):
            continue
        lower = fname.lower()
        if not (lower.endswith(".pdf") or lower.endswith(TEXT_EXT)):
            continue
        stem = os.path.splitext(fname)[0]
        doc_id = re.sub(r"[^A-Za-z0-9_\-]+", "_", stem).strip("_") or "doc"
        base = doc_id
        n = 2
        while doc_id in seen_ids:
            doc_id = f"{base}_{n}"
            n += 1
        seen_ids.add(doc_id)

        sha = sha256_file(path)
        out_txt = os.path.join(text_dir, doc_id + ".txt")
        if lower.endswith(".pdf"):
            ok, info = pdftotext_extract(path, out_txt)
            if not ok:
                failures.append(
                    f"UNPARSEABLE {fname}: pdftotext 两次尝试均失败 ({info})")
                docs.append({"doc_id": doc_id, "source_file": fname,
                             "sha256": sha, "kind": "pdf",
                             "parse_status": "unparseable",
                             "parse_method": None, "pages": 0,
                             "text_file": None, "page_spans": [],
                             "error": info})
                continue
            kind, method = "pdf", "pdftotext-" + info
            text = read_text_file(out_txt)
        else:
            text = read_text_file(path)
            with open(out_txt, "w", encoding="utf-8") as f:
                f.write(text)
            kind, method = "text", "direct-read"
            # txt/md 模拟单页：整篇即一页
            text = text if text.endswith("\f") else text  # 保持原样
        spans = page_spans(text)
        first_page = text[spans[0]["start"]:spans[0]["end"]] if spans else ""
        ident = extract_identity(first_page)
        identities[doc_id] = ident
        docs.append({"doc_id": doc_id, "source_file": fname,
                     "sha256": sha, "kind": kind,
                     "parse_status": "ok", "parse_method": method,
                     "pages": len(spans),
                     "text_file": os.path.relpath(out_txt, corpus_dir),
                     "page_spans": spans})

    index = {"materials_dir": os.path.abspath(materials),
             "doc_count": len(docs),
             "parse_ok": sum(1 for d in docs if d["parse_status"] == "ok"),
             "docs": docs}
    with open(os.path.join(corpus_dir, "corpus_index.json"), "w",
              encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    with open(os.path.join(corpus_dir, "identity_candidates.json"), "w",
              encoding="utf-8") as f:
        json.dump(identities, f, ensure_ascii=False, indent=2)

    ok_count = index["parse_ok"]
    print(f"[corpus_build] 材料目录: {materials}")
    print(f"[corpus_build] 索引文档 {len(docs)} 篇，解析成功 {ok_count} 篇；"
          f"产物: {corpus_dir}")
    if ok_count == 0:
        failures.append("GATE 无任何可解析文档，语料为空")
    if failures:
        print("[corpus_build] 失败清单:")
        for item in failures:
            print("  - " + item)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
