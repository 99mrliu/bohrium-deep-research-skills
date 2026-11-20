#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parse_case.py — 解析多数据库联合检索案例输入，嗅探归类材料，生成 case_summary.json。

读取 case.json 与 task.md（路径可用参数覆盖），提取：
  - case_id / output_contract / 研究问题（task.md 回退提取时标 needs_confirmation）
  - 材料清单：先按 case.json 的 materials/files/data/attachments 字段发现，
    再对 case.json 所在目录做扫描兜底；逐文件格式嗅探归类：
    crossref / europepmc / publisher / recordlist / jsonl / csv /
    reference_graph / import_state / unknown
  - 已发现的来源库集合 source_dbs、引用图与导入状态文件定位
  - 解析失败或无法归类的文件记入 unparsed_files（留痕，绝不静默吞掉）

退出码：0=解析成功（允许带 warning 与 unknown 文件）；
2=case/task 均缺失或未发现任何材料文件（材料不足，诚实降级）；
3=case.json 存在但 JSON 非法（校验失败）。
顶层兜底：任何未预期异常汇总后以 exit 2 结束，绝不 crash。

用法：
  python3 parse_case.py [--case /input/case.json] [--task /input/task.md]
                        [--out /app/work/case_summary.json]
"""
import argparse
import json
import os
import re
import sys

QUESTION_KEYS = {"research_question", "review_question", "question",
                 "objective", "objectives", "aim", "aims", "task", "goal"}
CASE_ID_KEYS = {"case_id", "caseid", "id"}
CONTRACT_KEYS = {"output_contract", "contract", "required_fields"}
MATERIAL_KEYS = {"materials", "files", "data", "attachments", "inputs"}
PATH_KEYS = ("path", "file", "filepath", "file_path", "name", "filename")
RECORD_EXTS = {".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".html", ".htm",
               ".txt", ".xml", ".ris", ".bib"}
EXCLUDE_BASENAMES = {"case.json", "task.md", "result.json"}

GRAPH_KEYS = {"edges", "citations", "links", "aliases", "adjacency", "graph",
              "id_map", "mappings", "same_work", "equivalences"}
IMPORT_KEYS = {"imported_records", "import_state", "local_db", "existing_records",
               "already_imported", "imported", "import_log"}


def deep_find(obj, keys):
    """在嵌套 dict/list 中按候选键名（小写）深度优先找第一个非空值。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in keys and v not in (None, "", [], {}):
                return v
        for v in obj.values():
            r = deep_find(v, keys)
            if r not in (None, "", [], {}):
                return r
    elif isinstance(obj, list):
        for it in obj:
            r = deep_find(it, keys)
            if r not in (None, "", [], {}):
                return r
    return None


def collect_material_refs(obj):
    """从 case.json 的 materials/files/data/attachments 等字段收集文件引用。"""
    refs = []
    if not isinstance(obj, dict):
        return refs
    for key, val in obj.items():
        if isinstance(key, str) and key.lower() in MATERIAL_KEYS:
            items = val if isinstance(val, list) else [val]
            if isinstance(val, dict):  # {name: path} 形式
                items = [{"path": v, "name": k} for k, v in val.items()]
            for it in items:
                if isinstance(it, str):
                    refs.append({"path": it, "role": None})
                elif isinstance(it, dict):
                    p = None
                    for pk in PATH_KEYS:
                        if isinstance(it.get(pk), str) and it[pk]:
                            p = it[pk]
                            break
                    if p:
                        refs.append({"path": p,
                                     "role": it.get("role") or it.get("type")})
    return refs


def name_hint(name):
    """文件名提示，用于内容无法确定时的归类仲裁（不作硬假设）。"""
    n = name.lower()
    if "crossref" in n:
        return "crossref"
    if "europepmc" in n or "europe_pmc" in n or "europe-pmc" in n or "epmc" in n:
        return "europepmc"
    if "publisher" in n or "press" in n or "vendor" in n:
        return "publisher"
    if "graph" in n or "citation" in n or "refgraph" in n:
        return "reference_graph"
    if "import" in n or "local_db" in n or "state" in n:
        return "import_state"
    if "record" in n or "bibliograph" in n or "metadata" in n:
        return "recordlist"
    return None


def looks_graph(obj):
    return isinstance(obj, dict) and any(
        k in obj and isinstance(obj[k], (list, dict)) for k in GRAPH_KEYS)


def looks_import_state(obj):
    return isinstance(obj, dict) and any(k in obj for k in IMPORT_KEYS)


def sniff_file(path):
    """嗅探单个文件，返回 (sniff_type, detail)。失败不抛异常。"""
    base = os.path.basename(path)
    ext = os.path.splitext(base)[1].lower()
    hint = name_hint(base)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            head = f.read(65536)
    except OSError as e:
        return "unknown", "read_error: %s" % e

    stripped = head.lstrip()
    if not stripped:
        return "unknown", "empty_file"
    if stripped.startswith("<"):
        return (hint if hint in ("publisher",) else "publisher"), "html_fragment"
    if ext in (".csv", ".tsv"):
        return "csv", "ext=%s" % ext
    if ext in (".jsonl", ".ndjson"):
        return "jsonl", "ext=%s" % ext

    # 尝试整体 JSON
    obj = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            obj = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        obj = None

    if obj is not None:
        if isinstance(obj, dict):
            msg = obj.get("message")
            if isinstance(msg, dict) and (isinstance(msg.get("items"), list)
                                          or msg.get("DOI") or msg.get("title")):
                return "crossref", "message.items|message-work"
            rl = obj.get("resultList")
            if isinstance(rl, dict) and isinstance(rl.get("result"), list):
                return "europepmc", "resultList.result"
            if {"pmid", "authorString"} & set(obj.keys()) or \
                    ("journalInfo" in obj and ("title" in obj or "id" in obj)):
                return "europepmc", "single_result_like"
            if looks_graph(obj) and hint != "import_state":
                return "reference_graph", "keys=%s" % sorted(
                    k for k in GRAPH_KEYS if k in obj)[:4]
            if looks_import_state(obj):
                return "import_state", "keys=%s" % sorted(
                    k for k in IMPORT_KEYS if k in obj)[:4]
            for lk in ("records", "items", "results", "data", "entries"):
                if isinstance(obj.get(lk), list):
                    return (hint or "recordlist"), "list_under:%s" % lk
            if hint:
                return hint, "name_hint_only"
            return "unknown", "json_dict_unrecognized"
        if isinstance(obj, list):
            if obj and all(isinstance(x, dict) for x in obj[:5]):
                return (hint or "recordlist"), "json_list_of_dicts"
            return "unknown", "json_list_unrecognized"

    # 非整体 JSON：尝试 NDJSON
    lines = [l for l in head.splitlines() if l.strip()]
    if lines:
        ok = 0
        for l in lines[:10]:
            try:
                json.loads(l)
                ok += 1
            except json.JSONDecodeError:
                pass
        if ok and ok >= max(1, min(len(lines), 10)) // 2:
            return "jsonl", "ndjson_detected"
    if stripped.startswith("{") or stripped.startswith("["):
        return "unknown", "json_decode_error"
    if hint:
        return hint, "name_hint_only_nonjson"
    return "unknown", "unrecognized_content"


def extract_question_from_task(task_text):
    if not task_text:
        return None
    paras = [p.strip() for p in re.split(r"\n\s*\n", task_text) if p.strip()]
    for p in paras:
        plain = re.sub(r"^#+\s*", "", p)
        if re.search(r"(研究问题|任务|research question|objective|问题[:：])", p, re.I) \
                and len(plain) >= 10:
            return plain
    for p in paras:
        plain = re.sub(r"^#+\s*", "", p)
        if len(plain) >= 20 and not plain.startswith(("- ", "* ", "|")):
            return plain
    return None


def run(args):
    warnings, unparsed = [], []
    case_obj, task_text = None, ""
    case_dir = os.path.dirname(os.path.abspath(args.case)) or "."

    if os.path.isfile(args.case):
        try:
            with open(args.case, "r", encoding="utf-8") as f:
                case_obj = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print("ERROR: case.json 解析失败（校验失败）: %s" % e, file=sys.stderr)
            return 3
    else:
        warnings.append("case_json_missing: %s 不存在" % args.case)

    if os.path.isfile(args.task):
        with open(args.task, "r", encoding="utf-8") as f:
            task_text = f.read()
    else:
        warnings.append("task_md_missing: %s 不存在" % args.task)

    if case_obj is None and not task_text:
        print("ERROR: case.json 与 task.md 均缺失，材料不足，诚实降级。", file=sys.stderr)
        return 2

    case_id = deep_find(case_obj, CASE_ID_KEYS) if case_obj else None
    if not case_id:
        case_id = "unknown-case"
        warnings.append("case_id_missing: 未找到 case_id，使用占位 unknown-case")

    contract = deep_find(case_obj, CONTRACT_KEYS) if case_obj else None
    if isinstance(contract, dict):
        contract = list(contract.keys())
    if contract and not isinstance(contract, list):
        contract = [str(contract)]
    if not contract:
        warnings.append("output_contract_missing: scaffold_result.py 将使用 SPEC 默认字段")

    question, q_source, needs_confirm = None, None, False
    if case_obj:
        q = deep_find(case_obj, QUESTION_KEYS)
        if isinstance(q, list):
            q = "；".join(str(x) for x in q)
        if q:
            question, q_source = str(q), "case_json"
    if not question and task_text:
        question = extract_question_from_task(task_text)
        if question:
            q_source, needs_confirm = "task_md", True
            warnings.append("question_from_task_md: 已从 task.md 提取研究问题，"
                            "需在 change_records 做二次确认")

    # ---- 材料发现：case.json 引用 + 目录扫描兜底 ----
    refs, seen = [], set()
    if case_obj:
        refs.extend(collect_material_refs(case_obj))
    resolved = []
    for r in refs:
        p = r["path"]
        if not os.path.isabs(p):
            p = os.path.join(case_dir, p)
        p = os.path.normpath(p)
        if p in seen:
            continue
        seen.add(p)
        resolved.append({"path": p, "role": r.get("role"), "origin": "case_json"})
    if os.path.isdir(case_dir):
        for fn in sorted(os.listdir(case_dir)):
            if fn in EXCLUDE_BASENAMES or fn.startswith("."):
                continue
            if "expected" in fn.lower() or fn.lower().startswith("readme"):
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext not in RECORD_EXTS:
                continue
            p = os.path.normpath(os.path.join(case_dir, fn))
            if p in seen or not os.path.isfile(p):
                continue
            seen.add(p)
            resolved.append({"path": p, "role": None, "origin": "dir_scan"})

    # ---- 逐文件嗅探 ----
    materials, source_dbs, graph_files, import_files = [], set(), [], []
    for r in resolved:
        path = r["path"]
        entry = {"path": path, "name": os.path.basename(path),
                 "role": r.get("role"), "origin": r["origin"]}
        if not os.path.isfile(path):
            entry["sniff_type"] = "unknown"
            entry["detail"] = "file_not_found"
            unparsed.append({"path": path, "reason": "file_not_found"})
            materials.append(entry)
            continue
        stype, detail = sniff_file(path)
        entry["sniff_type"] = stype
        entry["detail"] = detail
        try:
            entry["size_bytes"] = os.path.getsize(path)
        except OSError:
            pass
        if stype in ("crossref", "europepmc", "publisher",
                     "recordlist", "jsonl", "csv"):
            source_dbs.add(stype)
        elif stype == "reference_graph":
            graph_files.append(path)
        elif stype == "import_state":
            import_files.append(path)
        else:
            unparsed.append({"path": path,
                             "reason": "sniff_unknown: %s" % detail})
            warnings.append("unparsed_file: %s 归类为 unknown（%s），"
                            "已记入 unparsed_files，不做内容假设"
                            % (entry["name"], detail))
        materials.append(entry)

    if not materials:
        print("ERROR: 未发现任何材料文件（case.json 引用与目录扫描均为空），"
              "材料不足，诚实降级。", file=sys.stderr)
        return 2
    if not source_dbs:
        warnings.append("no_record_source: 未嗅探到任何记录型来源，"
                        "normalize_records.py 将 exit 2 诚实降级")

    summary = {
        "case_id": str(case_id),
        "output_contract": contract or [],
        "research_question": question,
        "question_source": q_source,
        "needs_confirmation": needs_confirm,
        "task_excerpt": (task_text or "")[:500],
        "materials": materials,
        "source_dbs": sorted(source_dbs),
        "reference_graph_files": graph_files,
        "import_state_files": import_files,
        "unparsed_files": unparsed,
        "warnings": warnings,
    }
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("OK: case_summary 已写出 -> %s (材料=%d, 来源库=%s, 引用图=%d, "
          "导入状态=%d, 未解析=%d, 警告=%d)"
          % (args.out, len(materials), sorted(source_dbs) or "无",
             len(graph_files), len(import_files), len(unparsed), len(warnings)))
    for w in warnings:
        print("WARN: " + w, file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="解析 case.json + task.md，嗅探归类材料，输出 case_summary.json"
                    "（exit 0/2/3）。")
    ap.add_argument("--case", default="/input/case.json", help="case.json 路径")
    ap.add_argument("--task", default="/input/task.md", help="task.md 路径")
    ap.add_argument("--out", default="/app/work/case_summary.json", help="输出路径")
    args = ap.parse_args()
    try:
        return run(args)
    except Exception as e:  # 顶层兜底：绝不 crash
        print("ERROR: parse_case 未预期异常（降级 exit 2）: %r" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
