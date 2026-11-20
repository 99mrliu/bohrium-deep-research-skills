#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_corpus.py — 防御式解析 case.json / task.md，发现文献材料并抽取分页文本。

产物（写入 --work）：
  pages/<doc_id>.jsonl   每行 {"page": n, "text": ...}
  anchors/<doc_id>.json  段落锚点表 {"doc_id":..., "anchors":[{"anchor":"p1.¶1","page":1,"para":1,"preview":...}]}
  docs.jsonl             每行一篇文献元数据（doc_id/source_path/sha256/word_count/tier/method/title/note）
并在 --output 下尽早写入部分 result.json（status=in_progress），失败点之前保证文件存在。

仅使用 Python3 标准库；PDF 文本抽取通过 subprocess 调用 pdftotext，失败回退 pypdf（若可导入）。
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

DOC_LIST_KEYS = ["documents", "papers", "references", "files",
                 "literature", "corpus", "materials"]
CONTRACT_KEYS = ["output_contract", "contract", "output_fields", "required_fields"]
CASE_ID_KEYS = ["case_id", "id", "caseId"]
PATH_KEYS = ["path", "file", "pdf", "url", "filepath", "file_path", "filename"]
WORD_MIN_FULLTEXT = 500  # 低于该词数的正文按 abstract_only 处理（启发式）


def log(msg):
    print("[extract_corpus] %s" % msg, file=sys.stderr)


def safe_read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        log("无法读取 %s: %s" % (path, e))
        return None


def safe_read_json(path):
    text = safe_read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except Exception as e:
        log("JSON 解析失败 %s: %s" % (path, e))
        return None


def find_first_key(obj, keys):
    """在嵌套 dict/list 中按键名优先级递归查找第一个命中的值。"""
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and obj[k] is not None:
                return obj[k]
        for v in obj.values():
            r = find_first_key(v, keys)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_first_key(v, keys)
            if r is not None:
                return r
    return None


def sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        log("sha256 失败 %s: %s" % (path, e))
        return None


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def word_count(text):
    return len(re.findall(r"\w+", text or ""))


def split_pages(text):
    """按换页符分页；无换页符则整篇为第 1 页。"""
    raw = text.split("\f")
    pages = []
    for i, t in enumerate(raw):
        if i == len(raw) - 1 and not t.strip():
            continue  # pdftotext 末尾常带空页
        pages.append({"page": i + 1, "text": t})
    if not pages:
        pages = [{"page": 1, "text": ""}]
    return pages


def split_paragraphs(text):
    """与 match_evidence.py / verify_quotes.py 保持一致的段落切分逻辑。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    if len(paras) <= 1 and (text or "").strip():
        lines = [l.rstrip() for l in text.splitlines() if l.strip()]
        paras, buf = [], []
        for l in lines:
            buf.append(l)
            if len(buf) >= 6:
                paras.append("\n".join(buf))
                buf = []
        if buf:
            paras.append("\n".join(buf))
    return paras


def build_anchors(doc_id, pages):
    anchors = []
    for pg in pages:
        for k, para in enumerate(split_paragraphs(pg["text"])):
            preview = re.sub(r"\s+", " ", para)[:80]
            anchors.append({
                "anchor": "p%d.¶%d" % (pg["page"], k + 1),
                "page": pg["page"],
                "para": k + 1,
                "preview": preview,
            })
    return {"doc_id": doc_id, "anchors": anchors}


def strip_markup(s):
    """去除 Crossref JATS/HTML 标签。"""
    return re.sub(r"<[^>]+>", " ", s or "")


def find_meta_text(obj, keys):
    v = find_first_key(obj, keys)
    if isinstance(v, list):
        v = " ".join(str(x) for x in v if x)
    if isinstance(v, str):
        return strip_markup(v).strip()
    return None


def extract_pdf(path):
    """返回 (pages, method, error)。"""
    try:
        p = subprocess.run(["pdftotext", "-layout", path, "-"],
                           capture_output=True, timeout=180)
        if p.returncode == 0:
            text = p.stdout.decode("utf-8", "replace")
            if text.strip():
                return split_pages(text), "pdftotext", None
        log("pdftotext 返回空或失败(%s): rc=%s" % (path, p.returncode))
    except FileNotFoundError:
        log("pdftotext 不可用，尝试 pypdf 回退")
    except Exception as e:
        log("pdftotext 异常(%s): %s" % (path, e))
    try:
        import pypdf  # noqa
        reader = pypdf.PdfReader(path)
        pages = [{"page": i + 1, "text": (pg.extract_text() or "")}
                 for i, pg in enumerate(reader.pages)]
        if any(pg["text"].strip() for pg in pages):
            return pages, "pypdf", None
    except Exception as e:
        log("pypdf 回退失败(%s): %s" % (path, e))
    return None, "failed", "pdftotext 与 pypdf 均失败或不可用"


def extract_snapshot_json(obj):
    """从 Crossref / EuropePMC JSON 快照提取 title/abstract，组成单页 abstract_only 文档。"""
    title = find_meta_text(obj, ["title"])
    abstract = find_meta_text(obj, ["abstractText", "abstract", "Abstract"])
    if not title and not abstract:
        return None, None
    parts = []
    if title:
        parts.append("Title: " + title)
    if abstract:
        parts.append("Abstract: " + abstract)
    return [{"page": 1, "text": "\n\n".join(parts)}], title


def normalize_entry(entry, base_dir):
    """把清单元素归一化为 {'path':...} 或 {'inline':...} 或 {'invalid':原因}。"""
    if isinstance(entry, str):
        p = entry if os.path.isabs(entry) else os.path.join(base_dir, entry)
        return {"path": p}
    if isinstance(entry, dict):
        for k in PATH_KEYS:
            v = entry.get(k)
            if isinstance(v, str) and v.strip():
                if v.lower().startswith(("http://", "https://", "doi:")):
                    # 离线环境不可访问 URL：若有内联摘要则降级使用，否则记录
                    if find_meta_text(entry, ["abstractText", "abstract"]):
                        return {"inline": entry, "note": "仅有 URL，离线不可达；使用内联摘要"}
                    return {"invalid": "仅有 URL(%s)，离线环境不可访问" % v}
                p = v if os.path.isabs(v) else os.path.join(base_dir, v)
                return {"path": p}
        if find_meta_text(entry, ["title", "abstractText", "abstract"]):
            return {"inline": entry}
        return {"invalid": "字典条目无 path/file/pdf/url/title 等可用字段"}
    return {"invalid": "不支持的清单元素类型: %s" % type(entry).__name__}


def discover_documents(case_obj, input_dir, uncertainties):
    """返回归一化文献条目列表。"""
    entries = []
    lst = find_first_key(case_obj, DOC_LIST_KEYS)
    if isinstance(lst, list):
        for e in lst:
            entries.append(normalize_entry(e, input_dir))
    elif isinstance(lst, dict):
        for key, v in lst.items():
            e = normalize_entry(v, input_dir)
            e.setdefault("list_key", key)
            entries.append(e)
    if not entries:
        log("case.json 未提供文献清单，扫描输入目录 %s" % input_dir)
        found = []
        for root, _dirs, files in os.walk(input_dir):
            for fn in sorted(files):
                low = fn.lower()
                if low in ("case.json", "task.md"):
                    continue
                ext = os.path.splitext(low)[1]
                if ext in (".pdf", ".txt", ".md", ".json"):
                    prio = {".pdf": 0, ".txt": 1, ".md": 2, ".json": 3}[ext]
                    found.append((prio, os.path.join(root, fn)))
        for _prio, p in sorted(found):
            entries.append({"path": p})
        if not entries:
            uncertainties.append("输入目录下未发现任何 *.pdf/*.txt/*.md/*.json 文献材料")
    return entries


def apply_contract(result, contract, uncertainties):
    """把 output_contract 原样镜像进 result，并为其字段预置顶层键。"""
    if contract is None:
        uncertainties.append("case.json 中未找到 output_contract/contract/output_fields/required_fields")
        return
    result["output_contract"] = contract
    if isinstance(contract, dict):
        for k in contract:
            if k not in result:
                result[k] = None
    elif isinstance(contract, list):
        for k in contract:
            if isinstance(k, str) and k not in result:
                result[k] = None


def write_result_partial(output_dir, result):
    os.makedirs(output_dir, exist_ok=True)
    tmp = os.path.join(output_dir, "result.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(output_dir, "result.json"))


def process_entry(doc_id, entry, work_dir):
    """抽取单篇文献，返回 docs.jsonl 记录。"""
    pages_dir = os.path.join(work_dir, "pages")
    anchors_dir = os.path.join(work_dir, "anchors")
    os.makedirs(pages_dir, exist_ok=True)
    os.makedirs(anchors_dir, exist_ok=True)
    rec = {"doc_id": doc_id, "source_path": None, "sha256": None,
           "word_count": 0, "n_pages": 0, "tier": "failed",
           "method": "none", "title": None, "note": None}

    pages, method, err, title = None, None, None, None

    if "invalid" in entry:
        rec["note"] = entry["invalid"]
        return rec, None, None

    if "inline" in entry:
        obj = entry["inline"]
        pages, title = extract_snapshot_json(obj)
        rec["sha256"] = sha256_text(json.dumps(obj, ensure_ascii=False, sort_keys=True))
        rec["source_path"] = "(inline entry)"
        method = "inline_snapshot"
        if pages is None:
            rec["note"] = "内联条目无法提取 title/abstract"
            return rec, None, None
    else:
        path = entry["path"]
        rec["source_path"] = path
        if not os.path.isfile(path):
            rec["note"] = "文件不存在: %s" % path
            return rec, None, None
        rec["sha256"] = sha256_file(path)
        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            pages, method, err = extract_pdf(path)
            if err:
                rec["note"] = err
                return rec, None, None
        elif ext in (".txt", ".md"):
            text = safe_read_text(path)
            if text is None:
                rec["note"] = "文本读取失败"
                return rec, None, None
            pages, method = split_pages(text), "direct_read"
        elif ext == ".json":
            obj = safe_read_json(path)
            if obj is None:
                rec["note"] = "JSON 快照解析失败"
                return rec, None, None
            pages, title = extract_snapshot_json(obj)
            method = "json_snapshot"
            if pages is None:
                rec["note"] = "JSON 快照中未找到 title/abstract 字段"
                return rec, None, None
        else:
            rec["note"] = "不支持的文件类型: %s" % ext
            return rec, None, None

    full_text = "\n".join(pg["text"] for pg in pages)
    wc = word_count(full_text)
    rec["word_count"] = wc
    rec["n_pages"] = len(pages)
    rec["method"] = method
    rec["title"] = title
    if entry.get("note"):
        rec["note"] = entry["note"]
    if method in ("json_snapshot", "inline_snapshot"):
        rec["tier"] = "abstract_only"
    else:
        rec["tier"] = "fulltext" if wc >= WORD_MIN_FULLTEXT else "abstract_only"
        if rec["tier"] == "abstract_only":
            rec["note"] = (rec["note"] or "") + "；正文词数 %d < %d，按仅摘要处理" % (wc, WORD_MIN_FULLTEXT)

    with open(os.path.join(pages_dir, doc_id + ".jsonl"), "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    with open(os.path.join(anchors_dir, doc_id + ".json"), "w", encoding="utf-8") as f:
        json.dump(build_anchors(doc_id, pages), f, ensure_ascii=False, indent=2)
    return rec, pages, None


def main():
    ap = argparse.ArgumentParser(description="解析 case.json 并抽取文献分页文本")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--task", default="/input/task.md")
    ap.add_argument("--input-dir", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    uncertainties = []
    sources = []

    case_obj = safe_read_json(args.case) or {}
    if not case_obj:
        uncertainties.append("case.json 缺失或无法解析: %s" % args.case)
    task_text = safe_read_text(args.task)
    if task_text is None:
        uncertainties.append("task.md 缺失或无法读取: %s" % args.task)

    case_id = find_first_key(case_obj, CASE_ID_KEYS) or "unknown_case"
    contract = find_first_key(case_obj, CONTRACT_KEYS)

    result = {
        "case_id": case_id,
        "status": "in_progress",
        "stage": "extract_corpus",
        "skill": "design-typed-itembank-assessor",
        "sources": sources,
        "uncertainties": uncertainties,
        "change_records": [],
    }
    apply_contract(result, contract, uncertainties)
    # 10 秒内先落盘部分结果
    write_result_partial(args.output, result)
    log("已写入部分 result.json (case_id=%s)" % case_id)

    entries = discover_documents(case_obj, args.input_dir, uncertainties)
    docs_path = os.path.join(args.work, "docs.jsonl")
    n_ok = 0
    with open(docs_path, "w", encoding="utf-8") as f:
        for i, entry in enumerate(entries):
            doc_id = "doc_%03d" % (i + 1)
            rec, _pages, _ = process_entry(doc_id, entry, args.work)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            sources.append({"doc_id": doc_id, "source_path": rec["source_path"],
                            "tier": rec["tier"], "method": rec["method"],
                            "sha256": rec["sha256"]})
            if rec["tier"] != "failed":
                n_ok += 1
            if rec["note"]:
                uncertainties.append("%s: %s" % (doc_id, rec["note"]))
    log("共处理 %d 篇文献，成功 %d 篇" % (len(entries), n_ok))

    result["stage"] = "extract_done"
    result["n_documents"] = len(entries)
    result["n_extracted"] = n_ok
    write_result_partial(args.output, result)
    print(json.dumps({"case_id": case_id, "n_documents": len(entries),
                      "n_extracted": n_ok}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
