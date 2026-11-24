#!/usr/bin/env python3
"""suff_index.py — 充分性法庭第 1 步：索引 + 问题解析 + 保底骨架（确定性，stdlib-only）。

与答案生产线不同，本 bundle 的索引以"证据面"为单位：除行号化文本外，
为每个文件预抽数值事实（数字+单位+上下文键），供覆盖矩阵与冲突检测使用。
同时解析 case.json 的问题与 output_contract，立即落保底 result.json。
退出码恒 0。
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

TEXT_SUFFIX = {".txt", ".md", ".csv", ".tsv", ".json", ".log", ".tex", ".rst",
               ".markdown", ".xml", ".yaml", ".yml", ".bib"}
SKIP_NAMES = {"case.json", "task.md"}
NUM_PAT = re.compile(r"([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*"
                     r"(%|℃|°C|K|eV|keV|Ω·cm²|ohm|Ω|mV|V|mA|A|W|kWh|nm|μm|mm|cm|m|km|"
                     r"g|kg|mg|s|ms|min|h|小时|天|cycle|次|倍|ppm|M|mol|Pa|kPa|MPa|GPa)?")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_case(input_dir):
    try:
        with open(os.path.join(input_dir, "case.json"), encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, json.JSONDecodeError):
        case = {}
    questions = []
    for k in ("questions", "searches", "queries", "tasks", "items"):
        v = case.get(k)
        if isinstance(v, list) and v:
            for i, it in enumerate(v, 1):
                if isinstance(it, dict):
                    qid = str(it.get("question_id") or it.get("qid") or it.get("id") or "q%d" % i)
                    txt = str(it.get("question") or it.get("query") or it.get("task")
                              or it.get("prompt") or "")
                else:
                    qid, txt = "q%d" % i, str(it)
                if txt.strip():
                    questions.append({"question_id": qid, "question": txt})
            if questions:
                break
    contract = case.get("output_contract") or {}
    fields = contract.get("fields") if isinstance(contract, dict) else None
    if not fields and isinstance(contract, dict):
        fields = list(contract.keys())
    if not fields and isinstance(contract, list):
        fields = [str(x) for x in contract]
    return case, questions, [f for f in (fields or []) if f != "fields"]


def extract_facts(text):
    """从文本中抽数值事实：{key, value, unit, line}。key 为数值前 ≤20 字符的去噪短语。"""
    facts = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in NUM_PAT.finditer(line):
            ctx = line[max(0, m.start() - 20):m.start()].strip()
            key = re.sub(r"[\s，。；：、,.;:()（）\[\]]+", " ", ctx).strip()[-20:]
            facts.append({"key": key, "value": m.group(1), "unit": m.group(2) or "",
                          "line": i, "context": line.strip()[:160]})
    return facts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    os.makedirs(a.out, exist_ok=True)
    case, questions, fields = load_case(a.input)

    ext_dir = os.path.join(a.work, "extracted")
    os.makedirs(ext_dir, exist_ok=True)
    index = {"schema": "kbqa-abstention-court/index/v1",
             "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "files": [], "errors": []}
    i = 0
    input_root = os.path.abspath(a.input)
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
                     "sha256": None, "text_status": None, "n_lines": 0,
                     "n_facts": 0, "extracted": None}
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
                    entry["text_status"] = "extraction_unavailable" if suffix in (".pdf",) \
                        or suffix in TEXT_SUFFIX else "unsupported_type"
                elif not text.strip():
                    entry["text_status"] = "empty"
                else:
                    lines = text.splitlines()
                    facts = extract_facts(text)
                    ext_path = os.path.join(ext_dir, fid + ".txt")
                    with open(ext_path, "w", encoding="utf-8") as f:
                        f.write("".join("L%d: %s\n" % (k + 1, l) for k, l in enumerate(lines)))
                    with open(os.path.join(ext_dir, fid + ".facts.json"), "w",
                              encoding="utf-8") as f:
                        json.dump(facts, f, ensure_ascii=False, indent=1)
                    entry.update(text_status="ok", n_lines=len(lines), n_facts=len(facts),
                                 extracted=os.path.relpath(ext_path, a.work))
            except (OSError, PermissionError, subprocess.TimeoutExpired) as e:
                entry["text_status"] = "unreadable"
                index["errors"].append({"file_id": fid, "error": str(e)[:200]})
            index["files"].append(entry)
    with open(os.path.join(a.work, "suff_index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    with open(os.path.join(a.work, "questions.json"), "w", encoding="utf-8") as f:
        json.dump({"questions": questions, "output_contract_fields": fields},
                  f, ensure_ascii=False, indent=2)

    skeleton = {"case_id": case.get("case_id") or case.get("id") or "unknown",
                "status": "partial",
                "answers": [{"question_id": q["question_id"], "verdict": "pending",
                             "answer": None, "missing": None} for q in questions],
                "sources": [], "uncertainty": ["skeleton written at init"],
                "change_log": [{"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "event": "init skeleton"}]}
    for fld in fields:
        skeleton.setdefault(fld, None)
    with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(skeleton, f, ensure_ascii=False, indent=2)
    print(json.dumps({"case_id": skeleton["case_id"], "questions": len(questions),
                      "files": len(index["files"]),
                      "facts": sum(e["n_facts"] for e in index["files"])},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
