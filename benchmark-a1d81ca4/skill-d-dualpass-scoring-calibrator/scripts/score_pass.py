#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通道 1：机判确定项，并接收带书面理由的语义档位。"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

RESERVED = {"case_id", "status", "status_reason", "sources", "uncertainty", "change_records", "scores", "agreement"}
CORE_T2 = {
    "task": ["task", "question", "prompt", "任务"],
    "material_scope": ["material_scope", "source_scope", "scope", "材料范围"],
    "reference_answer": ["reference_answer", "answer_key", "answer", "参考答案"],
    "scoring_rules": ["scoring_rules", "rubric", "grading", "评分规则"],
    "evidence_anchors": ["evidence_anchors", "evidence", "anchors", "证据锚点"],
}
BOUNDARY_KEYS = ["boundary_notes", "unreported_aspects", "conflicts", "limitations", "uncertainty", "边界说明"]

def atomic_write_text(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", dir=str(target.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp_name, str(target))
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)

def atomic_write_json(path, payload):
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        if isinstance(default, dict):
            payload = dict(default)
            payload["_load_error"] = "{}: {}".format(type(exc).__name__, exc)
            return payload
        if default is not None:
            return default
        return {"_load_error": "{}: {}".format(type(exc).__name__, exc)}

def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

def normalize_text(value):
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\ufb00", "ff").replace("\ufb01", "fi").replace("\ufb02", "fl")
    text = re.sub(r"[-‐‑‒–—]\s*\n\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def extract_pdf(path):
    exe = shutil.which("pdftotext")
    if not exe:
        return "", "pdftotext_missing"
    try:
        proc = subprocess.run([exe, "-layout", str(path), "-"], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=30, check=False)
        if proc.returncode != 0:
            return "", "pdftotext_failed:" + proc.stderr.decode("utf-8", "replace")[:200]
        return proc.stdout.decode("utf-8", "replace"), None
    except Exception as exc:
        return "", "pdftotext_error:{}".format(type(exc).__name__)

def load_sources(root):
    base = Path(root)
    docs = {}
    if not base.exists():
        return docs
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(base))
        suffix = path.suffix.lower()
        error = None
        if suffix in {".txt", ".md", ".text"}:
            text = read_text(path)
        elif suffix == ".pdf":
            text, error = extract_pdf(path)
        else:
            continue
        docs[rel] = {"path": rel, "text": text, "lines": text.splitlines(), "extraction_error": error}
    return docs

def contract_fields(case):
    spec = case.get("output_contract", {}) if isinstance(case, dict) else {}
    fields = []
    if isinstance(spec, dict):
        fields = [str(k) for k in spec]
    elif isinstance(spec, list):
        for entry in spec:
            if isinstance(entry, str):
                fields.append(entry)
            elif isinstance(entry, dict):
                name = entry.get("name") or entry.get("field") or entry.get("key")
                if name:
                    fields.append(str(name))
    return fields

def init_result(case_path, output_dir):
    case = load_json(case_path, {})
    if not isinstance(case, dict):
        case = {}
    result = {
        "case_id": str(case.get("case_id") or "unknown"),
        "status": "部分完成",
        "status_reason": "已按契约初始化；评分与裁决尚未完成，contract 字段暂为 null。",
        "sources": [],
        "uncertainty": ["初始化结果仅保证结构合法，不代表实质任务已完成。"],
        "change_records": [{"step": 0, "actor": "score_pass.py --init", "change": "创建合法部分 result.json"}],
    }
    for field in contract_fields(case):
        if field not in RESERVED:
            result[field] = None
    out_path = Path(output_dir) / "result.json"
    atomic_write_json(out_path, result)
    return out_path

def extract_items(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("item_bank", "items", "answers", "cards"):
        if isinstance(payload.get(key), list):
            return payload[key]
    return []

def first_value(obj, aliases):
    for key in aliases:
        if isinstance(obj, dict) and key in obj:
            return obj.get(key)
    return None

def nonempty(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True

def find_doc(docs, claimed):
    claimed = str(claimed or "")
    if claimed in docs:
        return claimed, docs[claimed]
    base = os.path.basename(claimed)
    matches = [name for name in docs if os.path.basename(name) == base]
    if len(matches) == 1:
        return matches[0], docs[matches[0]]
    return claimed, None

def heading_segment(doc, heading):
    lines = doc.get("lines", [])
    needle = normalize_text(heading)
    start = None
    for idx, line in enumerate(lines):
        if needle and needle in normalize_text(line):
            start = idx
            break
    if start is None:
        return None
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("#") and idx > start:
            end = idx
            break
    return "\n".join(lines[start:end])

def anchor_segment(doc, locator):
    if isinstance(locator, str) and locator.strip():
        return heading_segment(doc, locator)
    if not isinstance(locator, dict):
        return None
    lines = doc.get("lines", [])
    try:
        if "line_start" in locator or "line_end" in locator:
            start = int(locator.get("line_start", 1))
            end = int(locator.get("line_end", start))
            if start < 1 or end < start or start > len(lines):
                return None
            return "\n".join(lines[start - 1:min(end, len(lines))])
        start_text = locator.get("start") or locator.get("start_text")
        end_text = locator.get("end") or locator.get("end_text")
        if start_text:
            full = normalize_text(doc.get("text", ""))
            start_norm = normalize_text(start_text)
            begin = full.find(start_norm)
            if begin < 0:
                return None
            finish = len(full)
            if end_text:
                end_norm = normalize_text(end_text)
                found = full.find(end_norm, begin + len(start_norm))
                if found >= 0:
                    finish = found + len(end_norm)
            return full[begin:finish]
    except Exception:
        return None
    return None

def evidence_entries(item):
    value = first_value(item, ["evidence_anchors", "evidence", "anchors", "证据锚点"])
    if isinstance(value, list):
        return [entry for entry in value if isinstance(entry, dict)]
    return []

def check_evidence(item, docs):
    entries = evidence_entries(item)
    checks = []
    if not entries:
        return 0, checks, "未提供任何证据锚点。"
    valid = 0
    for idx, entry in enumerate(entries, 1):
        quote = entry.get("quote") or entry.get("text") or entry.get("citation")
        locator = entry.get("locator") or entry.get("anchor") or entry.get("section")
        source_name, doc = find_doc(docs, entry.get("source") or entry.get("file") or entry.get("path"))
        reason = []
        ok = False
        if doc is None:
            reason.append("source_not_found")
        elif doc.get("extraction_error"):
            reason.append(doc["extraction_error"])
        elif not normalize_text(quote):
            reason.append("empty_quote")
        elif locator in (None, "", {}):
            reason.append("missing_claimed_anchor")
        else:
            segment = anchor_segment(doc, locator)
            if segment is None:
                reason.append("claimed_anchor_not_found")
            elif normalize_text(quote) in normalize_text(segment):
                ok = True
                reason.append("quote_verified_within_claimed_anchor")
            else:
                reason.append("quote_not_within_claimed_anchor")
        valid += 1 if ok else 0
        checks.append({"index": idx, "source": source_name, "ok": ok, "verdict": ";".join(reason)})
    score = 2 if valid == len(entries) else (1 if valid else 0)
    return score, checks, "机检引文 {}/{} 通过；归一化含 NFKC、连字、断词连字符与空白折叠。".format(valid, len(entries))

def completeness_score(item, task_type):
    if task_type == "T2":
        missing = [name for name, aliases in CORE_T2.items() if not nonempty(first_value(item, aliases))]
        metadata_missing = [key for key in ("difficulty", "license") if not nonempty(item.get(key))]
        count = len(CORE_T2) - len(missing)
        score = 2 if count == 5 else (1 if count >= 3 else 0)
        return score, {"core_present": count, "core_missing": missing, "metadata_missing": metadata_missing}, "五个核心字段齐备 {}/5。".format(count)
    present = [nonempty(first_value(item, ["response", "answer", "答案"])), bool(evidence_entries(item)), any(key in item for key in BOUNDARY_KEYS)]
    count = sum(1 for value in present if value)
    score = 2 if count == 3 else (1 if count >= 2 else 0)
    return score, {"answer_evidence_boundary_present": count}, "答案/证据/边界说明齐备 {}/3。".format(count)

def boundary_score(item):
    present = [key for key in BOUNDARY_KEYS if isinstance(item, dict) and key in item]
    if not present:
        return 0, {"present_keys": []}, "未提供未报告/冲突/限制/不确定性标记。"
    weak = []
    for key in present:
        value = item.get(key)
        if isinstance(value, str) and not value.strip():
            weak.append(key)
    score = 1 if weak else 2
    return score, {"present_keys": present, "weak_keys": weak}, "显式边界标记 {} 个。".format(len(present))

def semantic_entry(semantic, item_id, dimension):
    root = semantic.get("items", semantic) if isinstance(semantic, dict) else {}
    entry = root.get(item_id, {}) if isinstance(root, dict) else {}
    data = entry.get(dimension, {}) if isinstance(entry, dict) else {}
    if not isinstance(data, dict):
        data = {"score": data, "justification": ""}
    score = data.get("score")
    justification = str(data.get("justification") or "").strip()
    if score not in (0, 1, 2) or not justification:
        raise ValueError("语义评分缺少 0/1/2 分或非空 justification: {}.{}".format(item_id, dimension))
    return int(score), justification

def build_scores(case, rubric, items_payload, semantic, docs, pass_id):
    task_type = rubric.get("task_type", "T1")
    items = extract_items(items_payload)
    records = []
    for pos, raw in enumerate(items, 1):
        item = raw if isinstance(raw, dict) else {"response": raw}
        item_id = str(item.get("item_id") or item.get("id") or "item-{}".format(pos))
        dims = {}
        ev_score, ev_checks, ev_reason = check_evidence(item, docs)
        comp_score, comp_detail, comp_reason = completeness_score(item, task_type)
        bound_score, bound_detail, bound_reason = boundary_score(item)
        sem_score, sem_reason = semantic_entry(semantic, item_id, "correctness")
        dims["correctness"] = {"score": sem_score, "justification": sem_reason, "source": "semantic", "machine_verdict": {"status": "not_machine_decidable"}}
        dims["evidence_anchoring"] = {"score": ev_score, "justification": ev_reason, "source": "machine", "machine_verdict": {"checks": ev_checks}}
        dims["completeness"] = {"score": comp_score, "justification": comp_reason, "source": "machine", "machine_verdict": comp_detail}
        dims["boundary_honesty"] = {"score": bound_score, "justification": bound_reason, "source": "machine", "machine_verdict": bound_detail}
        total = sum(dims[key]["score"] for key in dims)
        records.append({"item_id": item_id, "dimensions": dims, "total_score": total, "max_score": 8})
    return {
        "pass_id": pass_id,
        "case_id": str(case.get("case_id", rubric.get("case_id", "unknown"))),
        "task_type": task_type,
        "expected_item_count": rubric.get("expected_item_count"),
        "item_count": len(records),
        "items": records,
        "warnings": [] if len(records) == rubric.get("expected_item_count") else ["提交项数与 rubric 预期不一致。"],
    }

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="通道 1 评分；--init 先写合法部分 result.json")
    parser.add_argument("--init", action="store_true", help="仅初始化 result.json")
    parser.add_argument("--case", required=True)
    parser.add_argument("--task")
    parser.add_argument("--rubric")
    parser.add_argument("--items")
    parser.add_argument("--semantic")
    parser.add_argument("--source-root")
    parser.add_argument("--output")
    parser.add_argument("--output-dir", help="--init 的结果目录")
    parser.add_argument("--pass-id", default="pass1")
    return parser.parse_args(argv)

def main(argv=None):
    args = parse_args(argv)
    try:
        if args.init:
            if not args.output_dir:
                raise ValueError("--init 需要 --output-dir")
            path = init_result(args.case, args.output_dir)
            print(json.dumps({"ok": True, "result": str(path)}, ensure_ascii=False))
            return 0
        required = ["task", "rubric", "items", "semantic", "source_root", "output"]
        missing = [name for name in required if not getattr(args, name)]
        if missing:
            raise ValueError("缺少参数: " + ",".join(missing))
        case = load_json(args.case, {})
        rubric = load_json(args.rubric, {})
        items = load_json(args.items, {})
        semantic = load_json(args.semantic, {})
        if not isinstance(case, dict) or not isinstance(rubric, dict) or not isinstance(items, (dict, list)) or not isinstance(semantic, dict):
            raise ValueError("case/rubric/semantic 必须为对象，items 须为对象或数组。")
        for name, payload in (("case", case), ("rubric", rubric), ("items", items), ("semantic", semantic)):
            if isinstance(payload, dict) and "_load_error" in payload:
                raise ValueError(name + " JSON 畸形: " + payload["_load_error"])
        result = build_scores(case, rubric, items, semantic, load_sources(args.source_root), args.pass_id)
        atomic_write_json(args.output, result)
        print(json.dumps({"ok": True, "output": args.output, "items": result["item_count"], "warnings": result["warnings"]}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "{}: {}".format(type(exc).__name__, exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
