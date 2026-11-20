#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_corpus.py — 防御式解析 case.json / task.md，发现文献材料并抽取分页全文。

产出（--work-dir 下）：
  pages/<doc_id>.jsonl    每行 {"page": int, "text": str}（按页）
  anchors/<doc_id>.json   文档锚点元数据（来源、哈希、页数、是否仅摘要）
  docs.jsonl              每篇文档一行汇总（含抽取状态）
并在 --output-dir 尽早（解析完 case.json 后、PDF 抽取前）写入部分 result.json
（status="in_progress"），保证任何后续失败点之前已有部分交付。

仅 Python3 标准库（>=3.8）；PDF 经 subprocess 调 pdftotext -layout，
失败回退 pypdf（若环境恰好提供），再失败标记 failed，绝不 crash。
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

DOC_LIST_KEYS = ["documents", "papers", "references", "files",
                 "literature", "corpus", "materials"]
CONTRACT_KEYS = ["output_contract", "contract", "output_fields", "required_fields"]
CASE_ID_KEYS = ["case_id", "id", "caseId"]
PATH_KEYS = ["path", "file", "filepath", "file_path", "filename",
             "local_path", "source", "src"]
TITLE_KEYS = ["title", "name", "label"]


# ---------------------------------------------------------------- 工具

def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def find_key_recursive(obj, keys, want_type=None):
    """在嵌套 dict/list 中深度优先查找任一 key；可限定值类型。"""
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and (want_type is None or isinstance(obj[k], want_type)):
                return obj[k]
        for v in obj.values():
            r = find_key_recursive(v, keys, want_type)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_key_recursive(v, keys, want_type)
            if r is not None:
                return r
    return None


def get_case_id(case):
    if isinstance(case, dict):
        for k in CASE_ID_KEYS:
            if isinstance(case.get(k), str) and case[k].strip():
                return case[k].strip()
    r = find_key_recursive(case, CASE_ID_KEYS, want_type=str)
    return r.strip() if isinstance(r, str) and r.strip() else "unknown_case"


def get_contract(case):
    c = find_key_recursive(case, CONTRACT_KEYS)
    return c if c is not None else {}


def contract_field_names(contract):
    if isinstance(contract, dict):
        return list(contract.keys())
    if isinstance(contract, list):
        out = []
        for it in contract:
            if isinstance(it, str):
                out.append(it)
            elif isinstance(it, dict):
                for k in ("name", "field", "key"):
                    if isinstance(it.get(k), str):
                        out.append(it[k])
                        break
        return out
    return []


# ---------------------------------------------------------------- 文档发现

def resolve_path(p, input_dir):
    if not isinstance(p, str) or not p.strip():
        return None
    p = p.strip()
    if os.path.isabs(p) and os.path.isfile(p):
        return p
    cand = os.path.join(input_dir, p)
    if os.path.isfile(cand):
        return cand
    base = os.path.basename(p)
    for root, _dirs, files in os.walk(input_dir):
        if base in files:
            return os.path.join(root, base)
    return None


def collect_doc_items(case, input_dir, uncertainties):
    """从 case.json 递归查找文献清单；不命中则回退扫描 input_dir。"""
    items = []
    doc_list = find_key_recursive(case, DOC_LIST_KEYS, want_type=list)
    if doc_list:
        for it in doc_list:
            rec = {"path": None, "title": None, "raw": it}
            if isinstance(it, str):
                rec["path"] = resolve_path(it, input_dir)
                if rec["path"] is None and not re.search(r"\.\w{1,5}$", it):
                    rec["title"] = it  # 可能是标题而非路径
            elif isinstance(it, dict):
                for k in PATH_KEYS:
                    if isinstance(it.get(k), str):
                        rec["path"] = resolve_path(it[k], input_dir)
                        if rec["path"]:
                            break
                for k in TITLE_KEYS:
                    if isinstance(it.get(k), str):
                        rec["title"] = it[k]
                        break
            items.append(rec)
    # 回退：扫描 /input 下的材料文件
    have = {r["path"] for r in items if r["path"]}
    fallback = []
    for root, _dirs, files in os.walk(input_dir):
        for fn in sorted(files):
            low = fn.lower()
            if low in ("case.json", "task.md"):
                continue
            if low.endswith((".pdf", ".txt", ".md", ".json")):
                fp = os.path.join(root, fn)
                if fp not in have:
                    fallback.append({"path": fp, "title": None, "raw": fn})
    if not doc_list:
        uncertainties.append("case.json 中未找到文献清单键（documents/papers/...），"
                             "已回退扫描输入目录下的 *.pdf/*.txt/*.md/*.json。")
        items = fallback
    else:
        items.extend(fallback)
    if not items:
        uncertainties.append("未发现任何文献材料。")
    return items


# ---------------------------------------------------------------- 文本抽取

def extract_pdf(src):
    """返回 (text_with_formfeeds, extractor) 或 (None, 'failed')。"""
    try:
        r = subprocess.run(["pdftotext", "-layout", src, "-"],
                           capture_output=True, timeout=180)
        if r.returncode == 0 and r.stdout:
            return r.stdout.decode("utf-8", "replace"), "pdftotext"
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        import pypdf  # 环境若提供则回退；不属于依赖
        reader = pypdf.PdfReader(src)
        texts = [(p.extract_text() or "") for p in reader.pages]
        if any(t.strip() for t in texts):
            return "\f".join(texts), "pypdf"
    except Exception:
        pass
    return None, "failed"


_TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(s):
    return _TAG_RE.sub(" ", s or "")


def extract_json_snapshot(obj):
    """从 Crossref / EuropePMC 风格 JSON 快照中抽取标题与摘要。"""
    title, abstract = None, None
    node = obj
    if isinstance(obj, dict) and isinstance(obj.get("message"), dict):
        node = obj["message"]  # Crossref API 包装
    if isinstance(node, dict):
        t = node.get("title")
        if isinstance(t, list) and t:
            title = str(t[0])
        elif isinstance(t, str):
            title = t
        abstract = node.get("abstract") or node.get("abstractText")
        if isinstance(abstract, dict):  # EuropePMC 偶见 {"p": ...}
            abstract = " ".join(str(v) for v in abstract.values())
        res = node.get("result")
        if isinstance(res, dict):  # EuropePMC 包装
            title = title or res.get("title")
            abstract = abstract or res.get("abstractText")
    if title or abstract:
        text = (str(title or "") + "\n\n" + strip_tags(str(abstract or ""))).strip()
        return title or "(untitled snapshot)", text
    return None, None


# ---------------------------------------------------------------- 主流程

def write_partial_result(output_dir, case_id, contract, status, extra=None):
    os.makedirs(output_dir, exist_ok=True)
    fields = contract_field_names(contract)
    result = {
        "case_id": case_id,
        "status": status,
        "output_contract": contract,          # 原样镜像
        "contract_fields": {k: None for k in fields},
        "uncertainties": [],
        "change_log": [],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if extra:
        result.update(extra)
    tmp = os.path.join(output_dir, "result.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(output_dir, "result.json"))
    return result


def main():
    ap = argparse.ArgumentParser(description="解析 case.json 并抽取文献分页全文")
    ap.add_argument("--input-dir", default="/input")
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args()

    uncertainties = []
    change_log = []
    for d in ("pages", "anchors"):
        os.makedirs(os.path.join(args.work_dir, d), exist_ok=True)

    # 1. 解析 case.json（防御式）
    case_path = os.path.join(args.input_dir, "case.json")
    case = read_json(case_path)
    if case is None:
        case = {}
        uncertainties.append("case.json 缺失或无法解析，已按空配置继续。")
    case_id = get_case_id(case)
    contract = get_contract(case)
    if not contract:
        uncertainties.append("未找到 output_contract/contract/output_fields/required_fields，"
                             "contract_fields 为空。")

    # 2. 尽早写部分 result.json（在任何重活之前）
    result = write_partial_result(args.output_dir, case_id, contract, "in_progress",
                                  {"uncertainties": list(uncertainties)})
    change_log.append({"event": "partial_result_written", "status": "in_progress",
                       "at": result["updated_at"]})

    # 3. task.md 优先作为任务说明来源
    task_path = os.path.join(args.input_dir, "task.md")
    task_text = ""
    if os.path.isfile(task_path):
        try:
            with open(task_path, "r", encoding="utf-8") as f:
                task_text = f.read()
            with open(os.path.join(args.work_dir, "task.md"), "w", encoding="utf-8") as f:
                f.write(task_text)
        except OSError:
            uncertainties.append("task.md 存在但读取失败。")

    # 4. 发现文献
    items = collect_doc_items(case, args.input_dir, uncertainties)

    # 5. 逐篇抽取
    docs_summary = []
    for i, rec in enumerate(items, 1):
        doc_id = "doc_%03d" % i
        src = rec["path"]
        kind = "unknown"
        title = rec["title"]
        abstract_only = False
        extractor = "none"
        status = "failed"
        pages = []
        if src is None:
            uncertainties.append("%s：文献条目无可用路径（title=%s），标记 failed。"
                                 % (doc_id, title))
        elif not os.path.isfile(src):
            uncertainties.append("%s：文件不存在 %s。" % (doc_id, src))
        else:
            low = src.lower()
            try:
                if low.endswith(".pdf"):
                    kind = "pdf"
                    text, extractor = extract_pdf(src)
                    if text is not None:
                        pages = text.split("\f")
                        status = "ok"
                elif low.endswith((".txt", ".md")):
                    kind = "text"
                    with open(src, "r", encoding="utf-8", errors="replace") as f:
                        text = f.read()
                    pages = text.split("\f")
                    extractor = "direct"
                    status = "ok"
                    title = title or os.path.basename(src)
                elif low.endswith(".json"):
                    kind = "json_snapshot"
                    obj = read_json(src)
                    if obj is not None:
                        title2, text = extract_json_snapshot(obj)
                        if text:
                            title = title or title2
                            pages = [text]
                            abstract_only = True
                            extractor = "snapshot"
                            status = "ok"
                        else:
                            uncertainties.append("%s：JSON 快照中未找到标题/摘要字段。" % doc_id)
                    else:
                        uncertainties.append("%s：JSON 快照无法解析。" % doc_id)
                else:
                    uncertainties.append("%s：不支持的文件类型 %s。" % (doc_id, src))
            except Exception as e:  # 防御式：任何单篇失败不拖垮整体
                uncertainties.append("%s：抽取异常 %r。" % (doc_id, e))
                status = "failed"

        # 写 pages / anchors
        pages = [p for p in pages] or []
        all_text = "\f".join(pages)
        if status == "ok":
            pj = os.path.join(args.work_dir, "pages", doc_id + ".jsonl")
            with open(pj, "w", encoding="utf-8") as f:
                for pi, ptext in enumerate(pages, 1):
                    f.write(json.dumps({"page": pi, "text": ptext},
                                       ensure_ascii=False) + "\n")
        anchor = {
            "doc_id": doc_id,
            "source_path": src,
            "source_sha256": sha256_file(src) if src else None,
            "kind": kind,
            "title": title,
            "abstract_only": abstract_only,
            "num_pages": len(pages),
            "text_sha256": sha256_text(all_text) if status == "ok" else None,
            "extractor": extractor,
            "status": status,
        }
        with open(os.path.join(args.work_dir, "anchors", doc_id + ".json"),
                  "w", encoding="utf-8") as f:
            json.dump(anchor, f, ensure_ascii=False, indent=2)
        docs_summary.append(anchor)

    with open(os.path.join(args.work_dir, "docs.jsonl"), "w", encoding="utf-8") as f:
        for d in docs_summary:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    # 6. 更新部分 result.json（仍为 in_progress，终版由 build_result.py 写）
    ok_n = sum(1 for d in docs_summary if d["status"] == "ok")
    fail_n = len(docs_summary) - ok_n
    if fail_n:
        uncertainties.append("%d 篇文献抽取失败（详见 docs.jsonl）。" % fail_n)
    change_log.append({"event": "corpus_extracted", "docs_ok": ok_n,
                       "docs_failed": fail_n,
                       "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    write_partial_result(args.output_dir, case_id, contract, "in_progress", {
        "uncertainties": uncertainties,
        "change_log": change_log,
        "task_source": "task.md" if task_text else None,
        "documents": docs_summary,
    })
    print(json.dumps({"case_id": case_id, "docs_ok": ok_n, "docs_failed": fail_n},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
