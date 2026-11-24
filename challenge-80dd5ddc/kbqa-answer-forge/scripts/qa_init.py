#!/usr/bin/env python3
"""qa_init.py — 问答生产线第 1 步：读题 + 建索引 + 保底骨架（确定性，stdlib-only）。

1. 解析 /input/case.json：case_id、问题列表（兼容 questions/searches/tasks/
   queries 等键，或退化到 task.md 的编号行）、output_contract 字段清单。
2. 对资料库建行号化索引（哈希 + 抽取文本），供检索与引文核验使用。
3. 立刻把骨架 result.json 写到 /app/output：case_id + output_contract 全部
   字段（空值占位）+ status="partial" —— 预算耗尽也有诚实可交付物。
退出码恒 0；任何子步骤失败都记录在索引/骨架的 errors 字段。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

TEXT_SUFFIX = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl",
               ".xml", ".yaml", ".yml", ".log", ".tex", ".bib", ".rst"}
SKIP_NAMES = {"case.json", "task.md"}
QUESTION_KEYS = ("questions", "searches", "queries", "tasks", "items", "prompts")
QID_KEYS = ("question_id", "qid", "id", "query_id", "task_id")
QTEXT_KEYS = ("question", "query", "prompt", "task", "text", "instruction")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_questions(case_path, task_path):
    qs, source = [], None
    try:
        with open(case_path, encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, json.JSONDecodeError):
        case = {}
    for k in QUESTION_KEYS:
        v = case.get(k)
        if isinstance(v, list) and v:
            for i, it in enumerate(v, 1):
                if isinstance(it, dict):
                    qid = next((str(it[kk]) for kk in QID_KEYS if it.get(kk)), "q%d" % i)
                    txt = next((str(it[kk]) for kk in QTEXT_KEYS if it.get(kk)), "")
                else:
                    qid, txt = "q%d" % i, str(it)
                if txt.strip():
                    qs.append({"question_id": qid, "question": txt})
            if qs:
                source = "case.json:" + k
                break
    if not qs and os.path.exists(task_path):
        with open(task_path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f.read().splitlines(), 1):
                m = re.match(r"^\s*(?:\d+[.)、]|[-*]\s+\[[ x]\]|[-*])\s*(\S.{10,})\s*$", line)
                if m and "?" in line or (m and "？" in line):
                    qs.append({"question_id": "q%d" % (len(qs) + 1), "question": m.group(1)})
        if qs:
            source = "task.md:numbered_lines"
    contract = case.get("output_contract") or case.get("outputContract") or {}
    if isinstance(contract, dict):
        fields = contract.get("fields") or list(contract.keys())
    elif isinstance(contract, list):
        fields = [str(x) for x in contract]
    else:
        fields = []
    fields = [f for f in (str(x) for x in fields) if f and f != "fields"]
    return case, qs, source, fields


def build_index(input_dir, work):
    ext_dir = os.path.join(work, "extracted")
    os.makedirs(ext_dir, exist_ok=True)
    index = {"schema": "kbqa-answer-forge/index/v1",
             "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "files": [], "errors": []}
    i = 0
    input_root = os.path.abspath(input_dir)
    for root, dirs, names in os.walk(input_root):
        dirs.sort()
        for n in sorted(names):
            if n.startswith(".") or (n in SKIP_NAMES and os.path.abspath(root) == input_root):
                continue
            p = os.path.join(root, n)
            if os.path.islink(p) or not os.path.isfile(p):
                continue
            i += 1
            fid = "F%03d" % i
            suffix = os.path.splitext(p)[1].lower()
            entry = {"file_id": fid, "relpath": os.path.relpath(p, input_root),
                     "sha256": None, "n_lines": 0, "text_status": None, "extracted": None}
            try:
                entry["sha256"] = sha256_of(p)
                text = None
                if suffix in TEXT_SUFFIX:
                    with open(p, "rb") as f:
                        text = f.read(2_000_000).decode("utf-8", errors="replace")
                elif suffix == ".pdf" and shutil.which("pdftotext"):
                    tmp = os.path.join(ext_dir, fid + ".raw")
                    r = subprocess.run(["pdftotext", "-layout", p, tmp],
                                       capture_output=True, timeout=120)
                    if r.returncode == 0 and os.path.exists(tmp):
                        with open(tmp, encoding="utf-8", errors="replace") as f:
                            text = f.read()
                        os.remove(tmp)
                if text is None:
                    entry["text_status"] = ("unsupported_type" if suffix not in TEXT_SUFFIX
                                            and suffix != ".pdf" else "extraction_unavailable")
                elif not text.strip():
                    entry["text_status"] = "empty"
                else:
                    lines = text.splitlines()
                    ext_path = os.path.join(ext_dir, fid + ".txt")
                    with open(ext_path, "w", encoding="utf-8") as f:
                        f.write("".join("L%d: %s\n" % (k + 1, l) for k, l in enumerate(lines)))
                    entry.update(text_status="ok", n_lines=len(lines),
                                 extracted=os.path.relpath(ext_path, work))
            except (OSError, PermissionError, subprocess.TimeoutExpired) as e:
                entry["text_status"] = "unreadable"
                index["errors"].append({"file_id": fid, "error": str(e)[:200]})
            index["files"].append(entry)
    with open(os.path.join(work, "kb_index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    return index


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    os.makedirs(a.out, exist_ok=True)
    case, questions, qsource, fields = load_questions(
        os.path.join(a.input, "case.json"), os.path.join(a.input, "task.md"))
    index = build_index(a.input, a.work)
    with open(os.path.join(a.work, "questions.json"), "w", encoding="utf-8") as f:
        json.dump({"source": qsource, "questions": questions,
                   "output_contract_fields": fields}, f, ensure_ascii=False, indent=2)

    skeleton = {"case_id": case.get("case_id") or case.get("id") or "unknown",
                "status": "partial",
                "answers": [{"question_id": q["question_id"], "answer": None,
                             "claims": [], "state": "pending"} for q in questions],
                "sources": [], "uncertainty": ["skeleton written at init; answers pending"],
                "change_log": [{"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "event": "init: skeleton result.json written before any answering"}]}
    for fld in fields:
        skeleton.setdefault(fld, None)
    with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(skeleton, f, ensure_ascii=False, indent=2)
    print(json.dumps({"case_id": skeleton["case_id"], "questions": len(questions),
                      "question_source": qsource, "contract_fields": fields,
                      "indexed_files": len(index["files"]),
                      "index_errors": len(index["errors"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
