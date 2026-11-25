#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_index.py — 发现文档并建立 p<页>.¶<段> 锚点索引。

用法:
    python3 build_index.py --input-dir /input [--case /input/case.json] \
        --workdir /app/work [--output-dir /app/output]

产物:
    <workdir>/pages/<doc_id>.jsonl   每行 {"anchor","page","para","text"}
    <workdir>/index.json             文档清单、页/段数、text_layer 标志、sha256
    <output-dir>/result.json         骨架 (status=in_progress)，仅在给定 --output-dir 时

退出码: 0 = 正常（含零文档/部分文档失败的诚实降级）; 1 = 致命错误; 2 = argparse 用法错误。
仅依赖 Python 3 标准库；PDF 文本抽取调用系统 pdftotext，缺失时标记 no_text_layer 并继续。
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

DOC_KEYS = ("documents", "papers", "references", "files",
            "literature", "corpus", "materials")
PATH_KEYS = ("path", "file", "filepath", "file_path", "filename", "local_path")
TEXT_EXT = (".txt", ".md", ".markdown")
PDF_EXT = (".pdf",)


def eprint(*a):
    print(*a, file=sys.stderr)


def recursive_find_documents(node, found):
    """防御式递归：在任意嵌套 JSON 中找文档清单键。"""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and k.lower() in DOC_KEYS and isinstance(v, list):
                for item in v:
                    found.append(item)
            else:
                recursive_find_documents(v, found)
    elif isinstance(node, list):
        for item in node:
            recursive_find_documents(item, found)


def entry_to_path(entry):
    """清单条目可能是字符串路径或元数据对象；返回 (path_or_none, meta)。"""
    if isinstance(entry, str):
        return entry, {"raw": entry}
    if isinstance(entry, dict):
        for k in PATH_KEYS:
            v = entry.get(k)
            if isinstance(v, str) and v.strip():
                return v, dict(entry)
        return None, dict(entry)
    return None, {"raw": repr(entry)}


def sanitize_doc_id(name):
    stem = os.path.splitext(os.path.basename(name))[0] or "doc"
    sid = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_")
    return sid or "doc"


def resolve_path(p, input_dir, case_dir):
    """相对路径依次相对 case.json 所在目录与 input-dir 解析。"""
    if os.path.isabs(p):
        return p
    for base in (case_dir, input_dir):
        cand = os.path.normpath(os.path.join(base, p))
        if os.path.exists(cand):
            return cand
    return os.path.normpath(os.path.join(input_dir, p))


def extract_pdf_text(path):
    """pdftotext -layout；返回 (text_or_none, note)。"""
    try:
        proc = subprocess.run(
            ["pdftotext", "-layout", path, "-"],
            capture_output=True, timeout=120)
    except FileNotFoundError:
        return None, "pdftotext not found on PATH"
    except subprocess.TimeoutExpired:
        return None, "pdftotext timed out"
    if proc.returncode != 0:
        return None, "pdftotext exit %d: %s" % (
            proc.returncode, proc.stderr.decode("utf-8", "replace")[:200])
    text = proc.stdout.decode("utf-8", "replace")
    if not text.strip():
        return None, "pdftotext produced empty text (scanned/image PDF?)"
    return text, None


def split_pages(text):
    """按换页符分页；无换页符则整体为一页。"""
    pages = text.split("\f")
    # 去掉末尾纯空白页（pdftotext 常以 \f 结尾）
    while len(pages) > 1 and not pages[-1].strip():
        pages.pop()
    return pages


def split_paragraphs(page_text):
    """按一个或多个空行分段，段内保留原始换行。"""
    chunks = re.split(r"\n[ \t]*\n(?:[ \t]*\n)*", page_text)
    return [c.strip("\n") for c in chunks if c.strip()]


def index_document(doc_id, path, pages_dir):
    """返回 (doc_record, rows_or_none)。"""
    rec = {"doc_id": doc_id, "path": path, "sha256": None,
           "text_layer": False, "pages": 0, "paragraphs": 0, "note": None}
    if not os.path.exists(path):
        rec["note"] = "missing: file not found"
        return rec, None
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        rec["note"] = "unreadable: %s" % exc
        return rec, None
    rec["sha256"] = hashlib.sha256(raw).hexdigest()

    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXT:
        text = raw.decode("utf-8", "replace")
        if not text.strip():
            rec["note"] = "empty text file"
            return rec, None
    elif ext in PDF_EXT:
        text, note = extract_pdf_text(path)
        if text is None:
            rec["note"] = "no_text_layer: %s" % note
            return rec, None
    else:
        # 未知扩展名按文本尝试，失败则标记
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            rec["note"] = "unsupported extension %s and not valid UTF-8" % ext
            return rec, None
        if not text.strip():
            rec["note"] = "empty file"
            return rec, None

    rows = []
    pages = split_pages(text)
    n_par = 0
    for pno, ptext in enumerate(pages, start=1):
        for qno, para in enumerate(split_paragraphs(ptext), start=1):
            rows.append({"anchor": "p%d.¶%d" % (pno, qno),
                         "page": pno, "para": qno, "text": para})
            n_par += 1
    if not rows:
        rec["note"] = "no_text_layer: no extractable paragraphs"
        return rec, None

    rec["text_layer"] = True
    rec["pages"] = len(pages)
    rec["paragraphs"] = n_par
    os.makedirs(pages_dir, exist_ok=True)
    out = os.path.join(pages_dir, doc_id + ".jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    rec["pages_file"] = os.path.join("pages", doc_id + ".jsonl")  # 相对 workdir
    return rec, rows


def write_skeleton_result(output_dir, case_id, docs):
    skeleton = {
        "case_id": case_id,
        "status": "in_progress",
        "evidence_records": [],
        "abstentions": [],
        "anchor_coverage": {d["doc_id"]: {"paragraphs_indexed": d["paragraphs"],
                                          "claims_anchored": 0}
                            for d in docs},
        "uncertainties": ["skeleton written by build_index.py; "
                          "judgment and gate stages not run yet"],
        "change_records": [],
        "limits": ["partial skeleton: indexing complete, gating pending"],
    }
    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, "result.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(skeleton, f, ensure_ascii=False, indent=2)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="build p<page>.¶<para> anchor index")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--case", default=None, help="可选 case.json 路径")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--output-dir", default=None)
    args = ap.parse_args(argv)

    input_dir = args.input_dir
    workdir = args.workdir
    pages_dir = os.path.join(workdir, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    case_id = None
    candidates = []   # (path, meta)
    case_dir = None
    if args.case:
        case_dir = os.path.dirname(os.path.abspath(args.case))
        try:
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
            case_id = case.get("case_id") or case.get("id")
            found = []
            recursive_find_documents(case, found)
            for item in found:
                p, meta = entry_to_path(item)
                if p:
                    candidates.append((p, meta))
        except (OSError, json.JSONDecodeError) as exc:
            eprint("warning: cannot read case.json: %s" % exc)

    # 兜底：直接扫描 input-dir 顶层（不递归，避免吸入无关文件）
    if os.path.isdir(input_dir):
        for name in sorted(os.listdir(input_dir)):
            ext = os.path.splitext(name)[1].lower()
            if ext in TEXT_EXT + PDF_EXT:
                candidates.append((name, {"source": "input-dir scan"}))

    # 去重（按解析后的绝对路径）
    seen, resolved = set(), []
    for p, meta in candidates:
        rp = resolve_path(p, input_dir, case_dir or input_dir)
        key = os.path.abspath(rp)
        if key in seen:
            continue
        seen.add(key)
        resolved.append((rp, meta))

    docs, used_ids = [], {}
    for path, meta in resolved:
        base_id = sanitize_doc_id(meta.get("id") if isinstance(meta, dict)
                                  and isinstance(meta.get("id"), str) else path)
        n = used_ids.get(base_id, 0)
        used_ids[base_id] = n + 1
        doc_id = base_id if n == 0 else "%s_%d" % (base_id, n + 1)
        rec, _ = index_document(doc_id, path, pages_dir)
        if isinstance(meta, dict) and meta.get("title"):
            rec["title"] = meta["title"]
        docs.append(rec)
        eprint("indexed: %s -> %s (text_layer=%s pages=%d paras=%d%s)" % (
            path, doc_id, rec["text_layer"], rec["pages"], rec["paragraphs"],
            " note=" + rec["note"] if rec["note"] else ""))

    index = {
        "case_id": case_id,
        "input_dir": os.path.abspath(input_dir),
        "documents": docs,
        "stats": {
            "documents_total": len(docs),
            "documents_with_text_layer": sum(1 for d in docs if d["text_layer"]),
            "paragraphs_total": sum(d["paragraphs"] for d in docs),
        },
    }
    os.makedirs(workdir, exist_ok=True)
    index_path = os.path.join(workdir, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print("index written: %s (%d documents, %d with text layer)" % (
        index_path, len(docs), index["stats"]["documents_with_text_layer"]))

    if args.output_dir:
        sk = write_skeleton_result(args.output_dir, case_id, docs)
        print("skeleton result written: %s" % sk)
    return 0


if __name__ == "__main__":
    sys.exit(main())
