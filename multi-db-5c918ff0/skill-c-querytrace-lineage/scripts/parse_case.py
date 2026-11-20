#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parse_case.py — 解析多数据库联合检索案例输入，生成 case_summary.json。

读取 case.json 与 task.md（路径可用参数覆盖），完成：
  - case_id / output_contract / 研究问题（缺失时回退 task.md 并标 needs_confirmation）
  - 材料发现：先取 case.json 的 materials/files/data/attachments 字段，
    再对材料目录做扩展名扫描兜底，去重；
  - 逐文件格式嗅探（sniff）归类为：
      crossref / europepmc / publisher / recordlist / jsonl / csv /
      reference_graph / import_state / query_ledger / unknown
    嗅探失败的文件降级 unknown 并逐文件留痕，绝不静默吞掉；
  - 汇总已发现来源库集合、引用图 / 导入状态 / 组织方查询台账的定位。

退出码：0=解析成功（允许带 warning）；2=输入/材料不足；3=输入存在但非法（如 JSON 损坏）。
顶层未捕获异常一律汇总打印并以 exit 2 诚实降级，绝不 crash 留 traceback。

用法：
  python3 parse_case.py [--case /input/case.json] [--task /input/task.md]
                        [--materials-dir /input] [--out /app/work/case_summary.json]
"""
import argparse
import csv
import io
import json
import os
import re
import sys

QUESTION_KEYS = ["research_question", "review_question", "question",
                 "objective", "objectives", "aim", "aims"]
CASE_ID_KEYS = ["case_id", "caseid", "id"]
CONTRACT_KEYS = ["output_contract", "contract", "required_fields"]
MATERIAL_KEYS = ["materials", "files", "data", "attachments", "inputs"]

SCAN_EXTS = (".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".html", ".htm",
             ".xml", ".txt", ".md")

HINT_GRAPH = ("reference_graph", "reference-graph", "citation_graph",
              "citation-graph", "refgraph")
HINT_IMPORT = ("import_state", "import-state", "imported_records",
               "local_import", "import_status")
HINT_QLEDGER = ("query_ledger", "query-ledger", "query_log", "query-log",
                "search_log", "search-log")
HINT_PUBLISHER = ("publisher", "elsevier", "springer", "wiley", "taylor",
                  "ieee", "nature", "science_direct", "sciencedirect", "oup",
                  "acs", "rsc", "aip", "iop")


def deep_find(obj, keys):
    """在嵌套 dict/list 中按候选键名深度优先查找第一个非空值。"""
    keys = set(k.lower() for k in keys)
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


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def try_json(text):
    return json.loads(text)


def try_jsonl(text):
    """全文 JSON 失败时尝试逐行 JSON；全部非空行可解析则返回对象列表。"""
    rows = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        rows.append(json.loads(ln))
    return rows or None


def looks_like_csv(text):
    head = "\n".join(text.splitlines()[:5])
    if "," not in head and "\t" not in head:
        return False
    try:
        rows = list(csv.reader(io.StringIO(head)))
        return len(rows) >= 1 and len(rows[0]) >= 2
    except csv.Error:
        return False


def is_query_ledger_rows(rows):
    if not isinstance(rows, list) or not rows:
        return False
    hit = 0
    for r in rows[:10]:
        if isinstance(r, dict) and ("source_db" in r or "db" in r) and (
                "query_text" in r or "query" in r or "query_id" in r):
            hit += 1
    return hit >= max(1, len(rows[:10]) // 2)


def is_import_state_obj(obj, base):
    if any(h in base for h in HINT_IMPORT):
        return True
    if isinstance(obj, dict):
        recs = obj.get("records") or obj.get("imported") or []
        if isinstance(recs, list) and recs and isinstance(recs[0], dict):
            if any("imported_at" in r or "import_date" in r or "local_id" in r
                   for r in recs[:5]):
                return True
    return False


def is_reference_graph_obj(obj, base):
    if any(h in base for h in HINT_GRAPH):
        return True
    if isinstance(obj, dict) and isinstance(obj.get("edges"), list):
        return True
    if isinstance(obj, dict) and isinstance(obj.get("nodes"), list) and (
            "citations" in obj or "links" in obj):
        return True
    return False


def sniff_file(path):
    """嗅探单个材料文件，返回 (sniff_type, notes, item_count)。绝不抛异常。"""
    notes = []
    base = os.path.basename(path).lower()
    try:
        text = read_text(path)
    except OSError as e:
        return "unknown", ["read_error: %s" % e], None
    stripped = text.lstrip()

    obj, rows = None, None
    parsed_kind = None  # json / jsonl / csv / html / text
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            obj = try_json(text)
            parsed_kind = "json"
        except (json.JSONDecodeError, ValueError):
            try:
                rows = try_jsonl(text)
                parsed_kind = "jsonl"
            except (json.JSONDecodeError, ValueError):
                if looks_like_csv(text):
                    parsed_kind = "csv"
                else:
                    notes.append("json_decode_failed: 既非合法 JSON 亦非 JSONL")
                    return "unknown", notes, None
    elif stripped.startswith("<"):
        parsed_kind = "html"
    elif looks_like_csv(text):
        parsed_kind = "csv"
    else:
        parsed_kind = "text"

    # ---- 强文件名线索（特殊用途文件优先）----
    if any(h in base for h in HINT_QLEDGER) and parsed_kind in ("jsonl", "json"):
        data = rows if rows is not None else obj
        n = len(data) if isinstance(data, list) else None
        return "query_ledger", notes + ["name_hint:query_ledger"], n
    if any(h in base for h in HINT_GRAPH) and parsed_kind == "json":
        return "reference_graph", notes + ["name_hint:reference_graph"], None
    if any(h in base for h in HINT_IMPORT) and parsed_kind == "json":
        recs = obj.get("records") if isinstance(obj, dict) else None
        return "import_state", notes + ["name_hint:import_state"], \
            len(recs) if isinstance(recs, list) else None

    # ---- 内容嗅探 ----
    if parsed_kind == "jsonl":
        if is_query_ledger_rows(rows):
            return "query_ledger", notes, len(rows)
        return "jsonl", notes, len(rows)
    if parsed_kind == "csv":
        n = max(0, len(text.splitlines()) - 1)
        return "csv", notes, n
    if parsed_kind == "html":
        if any(h in base for h in HINT_PUBLISHER):
            return "publisher", notes + ["html_content:name_hint_publisher"], None
        return "unknown", notes + ["html_content: 无出版商文件名线索，降级 unknown"], None
    if parsed_kind == "text":
        return "unknown", notes + ["plain_text: 无法归类，降级 unknown"], None

    # parsed_kind == json
    if isinstance(obj, dict):
        if is_reference_graph_obj(obj, base):
            return "reference_graph", notes, None
        if is_import_state_obj(obj, base):
            recs = obj.get("records") or obj.get("imported") or []
            return "import_state", notes, \
                len(recs) if isinstance(recs, list) else None
        msg = obj.get("message")
        if isinstance(msg, dict):
            if isinstance(msg.get("items"), list):
                return "crossref", notes, len(msg["items"])
            if "DOI" in msg or "title" in msg:
                return "crossref", notes + ["single_work_response"], 1
        rl = obj.get("resultList")
        if isinstance(rl, dict) and isinstance(rl.get("result"), list):
            return "europepmc", notes, len(rl["result"])
        if is_query_ledger_rows([obj]):
            return "query_ledger", notes, 1
        for k in ("items", "records", "results"):
            if isinstance(obj.get(k), list):
                tag = "publisher" if any(h in base for h in HINT_PUBLISHER) \
                    else "recordlist"
                return tag, notes, len(obj[k])
        notes.append("json_dict_unrecognized: 未命中任何已知 schema")
        return "unknown", notes, None
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj):
            tag = "publisher" if any(h in base for h in HINT_PUBLISHER) \
                else "recordlist"
            return tag, notes, len(obj)
        return "unknown", notes + ["json_array_non_dict"], len(obj)
    return "unknown", notes + ["json_scalar"], None


def discover_materials(case_obj, materials_dir, exclude):
    """从 case.json 字段 + 目录扫描兜底发现材料文件，返回有序去重路径列表。"""
    found = []

    def add(p, origin):
        if not p or not isinstance(p, str):
            return
        p2 = p if os.path.isabs(p) else os.path.join(materials_dir, p)
        p2 = os.path.normpath(p2)
        if os.path.isfile(p2) and p2 not in [x[0] for x in found]:
            found.append((p2, origin))

    raw = deep_find(case_obj, MATERIAL_KEYS) if case_obj else None
    if isinstance(raw, dict):
        raw = list(raw.values())
    if isinstance(raw, list):
        for it in raw:
            if isinstance(it, str):
                add(it, "case_json")
            elif isinstance(it, dict):
                for k in ("path", "file", "name", "location", "filename"):
                    if it.get(k):
                        add(str(it[k]), "case_json")
                        break
    if os.path.isdir(materials_dir):
        for fn in sorted(os.listdir(materials_dir)):
            p = os.path.join(materials_dir, fn)
            if os.path.isfile(p) and fn.lower().endswith(SCAN_EXTS) \
                    and os.path.normpath(p) not in exclude:
                add(p, "dir_scan")
    return found


def extract_question_from_task(task_text):
    if not task_text:
        return None
    paras = [p.strip() for p in re.split(r"\n\s*\n", task_text) if p.strip()]
    for p in paras:
        plain = re.sub(r"^#+\s*", "", p)
        if re.search(r"(研究问题|research question|review question|问题[:：])", p, re.I) \
                and len(plain) >= 20:
            return plain
    for p in paras:
        plain = re.sub(r"^#+\s*", "", p)
        if len(plain) >= 40 and not plain.startswith(("- ", "* ", "|")):
            return plain
    return None


def main_inner(args):
    warnings = []
    case_obj, task_text = None, ""

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
        task_text = read_text(args.task)
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
        warnings.append("output_contract_missing: 未找到 output_contract，"
                        "scaffold_result.py 将使用默认字段")

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
                            "需在 change_records 中二次确认")
    if not question:
        warnings.append("question_missing: 未提取到研究问题（本 bundle 不强依赖，留痕继续）")

    mdir = args.materials_dir or os.path.dirname(os.path.abspath(args.case))
    exclude = {os.path.normpath(os.path.abspath(args.case)),
               os.path.normpath(os.path.abspath(args.task))}
    found = discover_materials(case_obj, mdir, exclude)

    materials, unparsed = [], []
    source_dbs = set()
    ref_graph = import_state = qledger = None
    for path, origin in found:
        sniff, notes, n = sniff_file(path)
        rel = os.path.basename(path)
        materials.append({"file": rel, "path": path, "sniff": sniff,
                          "origin": origin, "item_count": n, "notes": notes})
        if sniff in ("crossref", "europepmc", "publisher"):
            source_dbs.add(sniff)
        if sniff == "reference_graph" and ref_graph is None:
            ref_graph = path
        if sniff == "import_state" and import_state is None:
            import_state = path
        if sniff == "query_ledger" and qledger is None:
            qledger = path
        if sniff == "unknown":
            unparsed.append(rel)
            warnings.append("unparsed_file: %s 嗅探失败降级 unknown (%s)"
                            % (rel, "; ".join(notes) or "无细节"))
    if not materials:
        warnings.append("materials_empty: 未发现任何材料文件")

    summary = {
        "case_id": str(case_id),
        "output_contract": [str(c) for c in (contract or [])],
        "research_question": question,
        "question_source": q_source,
        "needs_confirmation": needs_confirm,
        "task_text_excerpt": (task_text or "")[:300],
        "materials": materials,
        "source_dbs": sorted(source_dbs),
        "reference_graph": ref_graph,
        "import_state": import_state,
        "query_ledger_material": qledger,
        "unparsed_files": unparsed,
        "warnings": warnings,
    }
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("OK: case_summary 已写出 -> %s (materials=%d, dbs=%s, warnings=%d)"
          % (args.out, len(materials), ",".join(sorted(source_dbs)) or "-",
             len(warnings)))
    for w in warnings:
        print("WARN: " + w, file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="解析 case.json + task.md 并嗅探材料，输出 case_summary.json"
                    "（exit 0/2/3）。")
    ap.add_argument("--case", default="/input/case.json", help="case.json 路径")
    ap.add_argument("--task", default="/input/task.md", help="task.md 路径")
    ap.add_argument("--materials-dir", default=None,
                    help="材料目录（默认取 case.json 所在目录）")
    ap.add_argument("--out", default="/app/work/case_summary.json", help="输出路径")
    args = ap.parse_args()
    try:
        return main_inner(args)
    except Exception as e:  # 顶层兜底：不 crash，诚实降级
        print("ERROR: 未捕获异常，诚实降级 exit 2: %r" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
