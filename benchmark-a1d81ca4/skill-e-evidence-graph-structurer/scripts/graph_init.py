#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""graph_init.py — 解析案例输入并初始化证据图谱 graph.json。

仅使用 Python 标准库（3.8+）。pdftotext 可选，缺失时 PDF 源优雅降级为
无锚点的 Source 节点（status=degraded），绝不因畸形输入崩溃。

确定性：同一组输入文件必产出逐字节一致的 graph.json（无时间戳、无随机
序、对象键排序、列表顺序仅由输入顺序决定）。所有写盘均为原子写
（同目录临时文件 + os.replace）。

用法：
  python3 graph_init.py --case /input/case.json --task /input/task.md \
      --materials /input --out /app/work/graph.json \
      [--init-result --result-out /app/output/result.json]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

GRAPH_VERSION = 1
SOURCE_EXTS = (".txt", ".md", ".json", ".pdf")
EXCLUDE_BASENAMES = {"case.json", "task.md"}
EXCLUDE_RES = [re.compile(p) for p in (
    r"^agent_answers", r"^graph", r"^result", r"^link_report",
    r"^query_report", r"^failure_analysis", r"^evidence_graph",
    r"^graph_map")]
T2_KEYWORDS = ("出题", "题卡", "benchmark", "DRAFT", "草拟",
               "4 道", "4道", "四道")
TASK_LINE_RE = re.compile(
    r"^\s*(?:第\s*\d+\s*[题问]|\d+\s*[\.、\)）:：]|[（(]\d+[)）])\s*"
    r"(\S.*?)\s*$")


def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def atomic_write_json(path, obj):
    """原子写 JSON：同目录临时文件 + os.replace。"""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, sort_keys=True, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_source_text(path):
    """返回 (text, status)。PDF 依赖 pdftotext，缺失则降级。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        exe = shutil.which("pdftotext")
        if not exe:
            return None, "degraded:no-pdftotext"
        try:
            cp = subprocess.run([exe, "-layout", path, "-"],
                                capture_output=True, timeout=120)
            if cp.returncode != 0:
                return None, "degraded:pdftotext-failed"
            return cp.stdout.decode("utf-8", "replace"), "ok"
        except Exception:
            return None, "degraded:pdftotext-error"
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", "replace"), "ok"
    except Exception:
        return None, "degraded:read-error"


def split_blocks(text):
    """按空行切分段落/表格块，作为锚点单元。"""
    parts = re.split(r"\n[ \t]*\n", text)
    return [p.strip() for p in parts if p and p.strip()]


def block_kind(block):
    return "table" if "|" in block else "para"


def collect_materials(paths):
    """收集源材料文件，确定性排序（basename, 绝对路径）。"""
    files = []
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                full = os.path.join(p, name)
                if not os.path.isfile(full):
                    continue
                if name in EXCLUDE_BASENAMES:
                    continue
                if any(r.search(name) for r in EXCLUDE_RES):
                    continue
                if os.path.splitext(name)[1].lower() in SOURCE_EXTS:
                    files.append(full)
        elif os.path.isfile(p):
            files.append(p)
    seen, out = set(), []
    for f in sorted(files, key=lambda x: (os.path.basename(x),
                                          os.path.abspath(x))):
        key = os.path.abspath(f)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def detect_task_type(task_text):
    upper = task_text
    for kw in T2_KEYWORDS:
        if kw in upper:
            return "T2"
    return "T1"


def extract_tasks(task_text, task_type):
    """抽取编号任务行；无编号行时回退为单一任务。"""
    labels = []
    for line in task_text.splitlines():
        m = TASK_LINE_RE.match(line)
        if m:
            labels.append(m.group(1).strip()[:200])
    if not labels:
        labels = ["（整篇 task.md 作为单一任务）"]
    prefix = "item" if task_type == "T2" else "q"
    return [{"id": "%s%d" % (prefix, i + 1), "label": lab}
            for i, lab in enumerate(labels)]


def contract_fields(case_obj):
    """动态读取 output_contract 字段名：支持 dict、str 列表、含 name 的
    dict 列表。"""
    if not isinstance(case_obj, dict):
        return []
    oc = case_obj.get("output_contract")
    if oc is None:
        oc = case_obj.get("output-contract")
    if isinstance(oc, dict):
        return [str(k) for k in oc.keys()]
    out = []
    if isinstance(oc, list):
        for item in oc:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict) and "name" in item:
                out.append(str(item["name"]))
    return out


def build_graph(case_obj, task_text, material_files):
    task_type = detect_task_type(task_text)
    tasks = extract_tasks(task_text, task_type)
    nodes, edges = [], []
    for i, path in enumerate(material_files, 1):
        src_id = "doc%d" % i
        try:
            with open(path, "rb") as fh:
                digest = sha256_bytes(fh.read())
        except Exception:
            digest = ""
        text, status = load_source_text(path)
        nodes.append({"id": src_id, "type": "Source", "attrs": {
            "path": os.path.basename(path), "sha256": digest,
            "status": status}})
        if text:
            for k, block in enumerate(split_blocks(text), 1):
                aid = "%s.para%d" % (src_id, k)
                nodes.append({"id": aid, "type": "Anchor", "attrs": {
                    "source": src_id, "kind": block_kind(block),
                    "index": k, "text": block,
                    "sha256": sha256_text(block)}})
                edges.append({"type": "contains", "src": src_id,
                              "dst": aid, "attrs": {}})
    for t in tasks:
        nodes.append({"id": t["id"], "type": "Task",
                      "attrs": {"label": t["label"]}})
    return {
        "version": GRAPH_VERSION,
        "case_id": (case_obj.get("case_id")
                    if isinstance(case_obj, dict) else None),
        "task_type": task_type,
        "contract_fields": contract_fields(case_obj),
        "nodes": nodes,
        "edges": edges,
        "conflicts": [],
    }


def make_partial_result(graph, sources):
    """--init-result：尽早写出的合法部分 result.json。"""
    result = {"case_id": graph.get("case_id")}
    for field in graph.get("contract_fields", []):
        result[field] = None
    result["status"] = "部分完成"
    result["status_reason"] = ("graph_init --init-result 已建立图谱骨架，"
                               "output_contract 字段尚未填充")
    result["sources"] = sources
    result["uncertainty"] = ["全部 output_contract 字段待填充"]
    result["change_records"] = [{
        "seq": 1, "action": "init",
        "detail": "graph_init --init-result 创建占位 result.json"}]
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="解析 case.json + task.md + 源材料，初始化证据图谱")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--task", default="/input/task.md")
    ap.add_argument("--materials", nargs="+", default=["/input"],
                    help="源材料文件或目录（可多值）")
    ap.add_argument("--out", default="/app/work/graph.json")
    ap.add_argument("--init-result", action="store_true",
                    help="同时写出合法的部分 result.json")
    ap.add_argument("--result-out", default="/app/output/result.json")
    args = ap.parse_args(argv)

    try:
        case_obj = {}
        if os.path.isfile(args.case):
            try:
                with open(args.case, "r", encoding="utf-8") as fh:
                    case_obj = json.load(fh)
            except Exception:
                case_obj = {}
        task_text = ""
        if os.path.isfile(args.task):
            try:
                with open(args.task, "r", encoding="utf-8") as fh:
                    task_text = fh.read()
            except Exception:
                task_text = ""
        materials = collect_materials(args.materials or [])
        graph = build_graph(case_obj, task_text, materials)
        atomic_write_json(args.out, graph)
        n_src = sum(1 for n in graph["nodes"] if n["type"] == "Source")
        n_anchor = sum(1 for n in graph["nodes"] if n["type"] == "Anchor")
        n_task = sum(1 for n in graph["nodes"] if n["type"] == "Task")
        print("[graph_init] task_type=%s sources=%d anchors=%d tasks=%d -> %s"
              % (graph["task_type"], n_src, n_anchor, n_task, args.out))
        if args.init_result:
            sources = [{"id": n["id"], "path": n["attrs"]["path"],
                        "sha256": n["attrs"]["sha256"]}
                       for n in graph["nodes"] if n["type"] == "Source"]
            result = make_partial_result(graph, sources)
            atomic_write_json(args.result_out, result)
            print("[graph_init] partial result.json -> %s" % args.result_out)
        return 0
    except Exception as exc:  # 绝不因畸形输入崩溃
        print("[graph_init] ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
