#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parse_case.py — 读取 case.json/task.md，发现材料文件并嗅探归类。

按 SHARED_CONTRACT 第 2/5 节：案例真实 schema 未知，先嗅探归类
（crossref / europepmc / publisher / recordlist / jsonl / csv /
reference_graph / import_state / unknown），再交由 map_fields.py 提取。

输出 /app/work/case_summary.json：
  {case_id, output_contract, research_question(含 needs_confirmation),
   task_excerpt, materials:[{path, sniff, detail, size_bytes, usable, notes}],
   sources_found, reference_graph, import_state, unparsed_files, warnings}

纪律：本脚本不联网；坏 JSON/不可解码文件降级为 unknown 并逐文件留痕，
绝不静默吞掉，绝不崩溃（顶层 try/except 汇总 exit 2）。

退出码：0=解析完成（部分 unknown 也算完成）；2=case.json 缺失或可用材料为零；
        3=case.json 为非法 JSON（校验失败）。
"""
import argparse
import csv
import io
import json
import os
import re
import sys

SNIFF_TYPES = ("crossref", "europepmc", "publisher", "recordlist", "jsonl",
               "csv", "reference_graph", "import_state", "unknown")
MATERIAL_EXTS = (".json", ".jsonl", ".csv", ".tsv", ".html", ".htm", ".txt", ".xml")

IMPORT_KEYS = ("imported_records", "import_state", "local_library", "already_imported")

FNAME_HINTS = (
    ("crossref", ("crossref", "cr_")),
    ("europepmc", ("europepmc", "europe_pmc", "eupmc", "europe-pmc")),
    ("publisher", ("publisher", "elsevier", "springer", "wiley", "nature", "tandf", "sage")),
    ("reference_graph", ("reference_graph", "citation_graph", "refgraph")),
    ("import_state", ("import_state", "local_state", "library_state", "already_imported")),
)


def fname_hint(base):
    b = base.lower()
    for sniff, keys in FNAME_HINTS:
        if any(k in b for k in keys):
            return sniff
    return None


def read_text(path):
    """返回 (text, note)；不可读/不可解码时 note 留痕。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read(), None
    except UnicodeDecodeError:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read(), "UTF-8 解码失败，已按 errors=replace 降级读取"
        except OSError as e:
            return None, "文件不可读: %s" % e
    except OSError as e:
        return None, "文件不可读: %s" % e


def classify_json(obj, hint):
    """按内容签名 + 文件名提示归类 JSON 结构。返回 (sniff, detail)。"""
    if isinstance(obj, dict):
        msg = obj.get("message")
        if isinstance(msg, dict) and (isinstance(msg.get("items"), list) or
                                      "DOI" in msg or "title" in msg):
            return "crossref", "dict.message 结构（works 列表或单条 work）"
        if isinstance(obj.get("resultList"), dict):
            return "europepmc", "resultList 结构"
        if any(k in obj for k in IMPORT_KEYS):
            return "import_state", "含导入状态键 %s" % ",".join(
                k for k in IMPORT_KEYS if k in obj)
        if isinstance(obj.get("nodes"), list) and isinstance(obj.get("edges"), list):
            return "reference_graph", "nodes/edges 结构"
        for k in ("records", "items", "results", "works"):
            if isinstance(obj.get(k), list):
                if hint == "publisher":
                    return "publisher", "含 %s 数组 + 文件名提示 publisher" % k
                if hint == "import_state":
                    return "import_state", "含 %s 数组 + 文件名提示 import_state" % k
                return "recordlist", "含 %s 数组（无来源签名，按通用记录列表）" % k
        if "DOI" in obj and "title" in obj:
            return "crossref", "单条 work 形状（DOI+title）"
        if ("pmid" in obj or "journalInfo" in obj) and "title" in obj:
            return "europepmc", "单条结果形状（pmid/journalInfo+title）"
        if hint:
            return hint, "内容无签名，按文件名提示归类"
        return "unknown", "无法识别的 dict 结构"
    if isinstance(obj, list):
        dicts = [x for x in obj if isinstance(x, dict)]
        if obj and len(dicts) == len(obj):
            if any("imported_at" in x or "local_id" in x for x in dicts):
                return "import_state", "记录含 imported_at/local_id 字段"
            if hint == "publisher":
                return "publisher", "dict 列表 + 文件名提示 publisher"
            return "recordlist", "dict 列表（无来源签名）"
        return "unknown", "JSON 列表元素非对象"
    return "unknown", "JSON 标量，无记录语义"


def sniff_file(path):
    """返回 (sniff, notes[list])；任何异常都降级 unknown 并留痕。"""
    notes = []
    text, note = read_text(path)
    if note:
        notes.append(note)
    if text is None:
        return "unknown", notes or ["文件不可读"]
    s = text.lstrip()
    if not s:
        return "unknown", ["空文件"] + notes
    hint = fname_hint(os.path.basename(path))
    if s[0] in "{[":
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            # 回退 JSONL：逐行可解析则按 jsonl 归类，否则 unknown（坏 JSON 已留痕）
            lines = [ln for ln in s.splitlines() if ln.strip()]
            ok = 0
            for ln in lines:
                try:
                    json.loads(ln)
                    ok += 1
                except json.JSONDecodeError:
                    pass
            if lines and ok == len(lines):
                return "jsonl", ["整文件 JSON 解析失败，但 %d 行均可独立解析，按 JSONL 归类" % ok] + notes
            return "unknown", ["JSON 解析失败（坏 JSON，已逐文件留痕，map_fields 将跳过）"] + notes
        sniff, detail = classify_json(obj, hint)
        return sniff, [detail] + notes
    low = text.lower()
    if "<html" in low or "citation_" in low or "<meta" in low:
        return "publisher", ["HTML/元数据片段（出版商落盘）"] + notes
    first = s.splitlines()[0] if s.splitlines() else ""
    if "," in first and not first.lstrip().startswith(("{", "[")):
        try:
            csv.Sniffer().sniff(text[:4096])
            return "csv", ["CSV 表头嗅探成功: %s" % first[:80]] + notes
        except csv.Error:
            pass
    if hint:
        return hint, ["内容无签名，按文件名提示归类"] + notes
    return "unknown", ["无法归类的文本内容（前 80 字符: %r）" % s[:80]] + notes


def collect_case_paths(case_obj, input_dir, case_path):
    """从 case.json 的 materials/files/data/attachments 字段收集材料相对路径。"""
    paths = []
    for key in ("materials", "files", "data", "attachments"):
        val = case_obj.get(key)
        if isinstance(val, str):
            val = [val]
        if isinstance(val, dict):
            val = list(val.values())
        if not isinstance(val, list):
            continue
        for item in val:
            if isinstance(item, str):
                paths.append(item)
            elif isinstance(item, dict):
                for kk in ("path", "file", "filename", "name", "href"):
                    if isinstance(item.get(kk), str):
                        paths.append(item[kk])
                        break
    resolved = []
    for p in paths:
        if os.path.isabs(p):
            if os.path.isfile(p):
                resolved.append(p)
            continue
        cand = os.path.join(input_dir, p)
        if os.path.isfile(cand):
            resolved.append(cand)
        else:
            # 路径未命中：留待目录扫描兜底
            pass
    return resolved


def extract_research_question(case_obj, task_text):
    for key in ("research_question", "question", "query", "research_goal"):
        v = case_obj.get(key)
        if isinstance(v, str) and v.strip():
            return {"text": v.strip(), "source": "case.json:%s" % key,
                    "needs_confirmation": False}
    if task_text:
        for ln in task_text.splitlines():
            t = ln.strip().lstrip("#").strip()
            if t:
                return {"text": t[:500], "source": "task.md 首行（回退提取）",
                        "needs_confirmation": True}
    return {"text": None, "source": None, "needs_confirmation": False}


def main():
    ap = argparse.ArgumentParser(
        description="读取 case.json/task.md，发现材料并嗅探归类（exit 0/2/3）。")
    ap.add_argument("--case", default="/input/case.json", help="case.json 路径")
    ap.add_argument("--task", default="/input/task.md", help="task.md 路径")
    ap.add_argument("--input-dir", default=None,
                    help="材料目录（默认取 --case 所在目录，再回退 /input）")
    ap.add_argument("--out", default="/app/work/case_summary.json",
                    help="case_summary.json 输出路径")
    args = ap.parse_args()

    if not os.path.isfile(args.case):
        print("ERROR: case.json 不存在（材料不足，诚实降级，exit 2）: %s"
              % args.case, file=sys.stderr)
        return 2
    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case_obj = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print("ERROR: case.json 非法 JSON（校验失败，exit 3）: %s" % e, file=sys.stderr)
        return 3
    if not isinstance(case_obj, dict):
        print("ERROR: case.json 顶层非对象（校验失败，exit 3）", file=sys.stderr)
        return 3

    input_dir = args.input_dir
    if not input_dir:
        input_dir = os.path.dirname(os.path.abspath(args.case)) or "/input"
    if not os.path.isdir(input_dir) and os.path.isdir("/input"):
        input_dir = "/input"

    task_text = ""
    if os.path.isfile(args.task):
        try:
            with open(args.task, "r", encoding="utf-8") as f:
                task_text = f.read()
        except (UnicodeDecodeError, OSError):
            task_text = ""

    warnings = []
    materials = []
    seen = set()

    def add_material(path):
        ap_ = os.path.abspath(path)
        if ap_ in seen or not os.path.isfile(path):
            return
        seen.add(ap_)
        try:
            sniff, notes = sniff_file(path)
        except Exception as e:  # 单文件异常绝不崩溃
            sniff, notes = "unknown", ["嗅探异常: %s" % e]
        try:
            size = os.path.getsize(path)
        except OSError:
            size = None
        materials.append({
            "path": path, "sniff": sniff, "detail": "; ".join(notes),
            "size_bytes": size, "usable": sniff != "unknown",
            "notes": notes,
        })

    try:
        for p in collect_case_paths(case_obj, input_dir, args.case):
            add_material(p)
        # 目录扫描兜底
        if os.path.isdir(input_dir):
            excluded = {os.path.abspath(args.case)}
            if args.task:
                excluded.add(os.path.abspath(args.task))
            for name in sorted(os.listdir(input_dir)):
                p = os.path.join(input_dir, name)
                if not os.path.isfile(p):
                    continue
                if os.path.abspath(p) in excluded:
                    continue
                if name.lower().endswith(MATERIAL_EXTS):
                    add_material(p)
    except Exception as e:  # 目录异常绝不崩溃
        warnings.append("材料发现异常: %s" % e)

    sources_found = sorted({m["sniff"] for m in materials if m["sniff"] in
                            ("crossref", "europepmc", "publisher", "recordlist",
                             "jsonl", "csv")})
    ref_graph = next((m["path"] for m in materials if m["sniff"] == "reference_graph"), None)
    import_state = next((m["path"] for m in materials if m["sniff"] == "import_state"), None)
    unparsed = [m["path"] for m in materials if m["sniff"] == "unknown"]

    summary = {
        "case_id": case_obj.get("case_id") or case_obj.get("id") or "UNKNOWN_CASE",
        "output_contract": case_obj.get("output_contract") or {},
        "research_question": extract_research_question(case_obj, task_text),
        "task_excerpt": task_text.strip()[:400],
        "materials": materials,
        "sources_found": sources_found,
        "reference_graph": ref_graph,
        "import_state": import_state,
        "unparsed_files": unparsed,
        "warnings": warnings,
        "disclaimer": "全程离线：仅解析本地材料，未执行任何真实联网查询。",
    }

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    usable = [m for m in materials if m["usable"]]
    print("OK: case 解析完成 -> %s (case_id=%s, 材料=%d, 可用=%d, unknown=%d, "
          "来源=%s, import_state=%s)"
          % (args.out, summary["case_id"], len(materials), len(usable),
             len(unparsed), ",".join(sources_found) or "无", bool(import_state)))
    if not usable:
        print("ERROR: 无可用材料（全部为 unknown 或目录为空，诚实降级，exit 2）",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # 顶层兜底：绝不 crash
        print("ERROR: parse_case 未捕获异常（诚实降级，exit 2）: %r" % e,
              file=sys.stderr)
        sys.exit(2)
