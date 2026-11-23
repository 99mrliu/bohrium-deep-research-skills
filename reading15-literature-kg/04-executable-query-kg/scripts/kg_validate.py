#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kg_validate.py — 候选图谱校验：结构 + 证据原文精确核验（仅标准库）。

两层校验：
  1) 结构校验：复用 kg_loader.Graph（字段、id 唯一、端点存在、证据字段、quote 长度）。
  2) 证据核验（evidence verifier）：
     - 从 /input 风格的材料文件（material.json / primary-material.json /
       secondary-material.json，或 --materials 指定的任意 JSON）递归抽取
       「paragraph_id → 原文文本」索引；
     - 每条节点/边证据要求：source_id 已在 sources 声明、paragraph_id 在材料
       索引中存在、quote 是该段落原文的【精确子串】（不做任何改写/规范化，
       不允许把自建页码当证据：出现 page/页码 字段直接报错）；
     - 若来源声明了 file 且材料可定位，则核验证据段落确实出自该来源文件，
       防止把 secondary 的段落挂到 primary 的 source_id 上。

退出码：0 通过；2 校验未通过（报告逐条列出问题）；3 用法/材料错误。
报告写 validation_report.json（--report 指定），供 result.json 引用。
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kg_loader import GraphLoadError, load_graph, sha256_text  # noqa: E402

PID_KEYS = ("paragraph_id", "pid", "para_id", "paragraphId", "id")
TEXT_KEYS = ("text", "content", "paragraph", "sentence", "value")
FORBIDDEN_EVIDENCE_KEYS = ("page", "page_no", "pdf_page", "页码")


def extract_paragraphs(obj, file_tag, index, problems):
    """递归抽取段落索引：index[paragraph_id] = {"text":..., "file":...}。"""
    if isinstance(obj, dict):
        pid = None
        text = None
        for k in PID_KEYS:
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                pid = v.strip()
                break
        for k in TEXT_KEYS:
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                text = v
                break
        if pid and text is not None:
            if pid in index and index[pid]["text"] != text:
                problems.append("段落 id 冲突: %s 在多个材料中出现且文本不同（保留先见者: %s）"
                                % (pid, index[pid]["file"]))
            else:
                index.setdefault(pid, {"text": text, "file": file_tag})
        for v in obj.values():
            extract_paragraphs(v, file_tag, index, problems)
    elif isinstance(obj, list):
        for v in obj:
            extract_paragraphs(v, file_tag, index, problems)


def build_material_index(material_paths):
    index = {}
    problems = []
    for p in material_paths:
        if not os.path.isfile(p):
            problems.append("材料文件不存在: %s" % p)
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            problems.append("材料文件无法解析为 UTF-8 JSON: %s（%s）" % (p, exc))
            continue
        extract_paragraphs(data, os.path.basename(p), index, problems)
    return index, problems


def validate(graph_path, material_paths, report_path=None, require_materials=True):
    """执行两层校验，返回 (ok, report_dict)。"""
    report = {"graph": graph_path, "structural_ok": False,
              "evidence_ok": None, "errors": [], "warnings": [],
              "checked_evidence": 0, "material_paragraphs": 0}
    # 第一层：结构
    try:
        graph = load_graph(graph_path)
    except GraphLoadError as exc:
        report["errors"].append(str(exc))
        _write(report_path, report)
        return False, report
    report["structural_ok"] = True
    report["counts"] = graph.counts()

    # 材料索引
    index, mat_problems = build_material_index(material_paths)
    report["material_paragraphs"] = len(index)
    report["material_files"] = sorted({v["file"] for v in index.values()})
    if require_materials and not index:
        report["errors"].append("未建立任何材料段落索引（材料缺失或全部解析失败），"
                                "证据无法核验；" + "；".join(mat_problems))
        _write(report_path, report)
        return False, report
    for w in mat_problems:
        report["warnings"].append(w)

    # 来源声明 → 文件 映射（若 candidate 里声明了 file 字段）
    src_file = {}
    for sid, s in graph.sources.items():
        if isinstance(s.get("file"), str) and s["file"]:
            src_file[sid] = s["file"]

    # 第二层：逐条证据精确核验
    errors = []
    checked = 0
    items = [("node", n["id"], n.get("evidence", [])) for n in
             sorted(graph.nodes.values(), key=lambda n: n["id"])]
    items += [("edge", e["id"], e.get("evidence", [])) for e in
              sorted(graph.edges.values(), key=lambda e: e["id"])]
    for kind, iid, evs in items:
        for j, ev in enumerate(evs):
            tag = "%s %s 证据#%d" % (kind, iid, j + 1)
            checked += 1
            for fk in FORBIDDEN_EVIDENCE_KEYS:
                if fk in ev:
                    errors.append("%s 含有禁用字段 %s（本包无 PDF 页码，位置必须是 JATS paragraph_id）"
                                  % (tag, fk))
            sid = ev.get("source_id")
            if sid not in graph.sources:
                errors.append("%s 的 source_id=%s 未在 sources 中声明" % (tag, sid))
                continue
            pid = ev.get("paragraph_id")
            quote = str(ev.get("quote", ""))
            if not index:
                errors.append("%s 无法核验（无材料索引）" % tag)
                continue
            if pid not in index:
                errors.append("%s 的 paragraph_id=%s 在材料中不存在" % (tag, pid))
                continue
            para = index[pid]
            if quote not in para["text"]:
                errors.append("%s 的 quote 不是 %s 段落 %s 原文的精确子串：quote=%r"
                              % (tag, sid, pid, quote[:60]))
                continue
            expected_file = src_file.get(sid)
            if expected_file and os.path.basename(expected_file) != para["file"]:
                errors.append("%s 声称来源 %s（文件 %s），但段落 %s 实际出自 %s"
                              % (tag, sid, expected_file, pid, para["file"]))
    report["checked_evidence"] = checked
    report["errors"].extend(errors)
    report["evidence_ok"] = not errors
    ok = report["structural_ok"] and report["evidence_ok"]
    report["ok"] = ok
    _write(report_path, report)
    return ok, report


def _write(path, report):
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="候选图谱结构+证据校验")
    ap.add_argument("--graph", required=True, help="graph.candidate.json 路径")
    ap.add_argument("--materials", nargs="*", default=[],
                    help="材料 JSON 文件（material/primary/secondary 等）")
    ap.add_argument("--report", default=None, help="validation_report.json 输出路径")
    ap.add_argument("--allow-no-materials", action="store_true",
                    help="无材料时仅做结构校验（evidence_ok=null，报告如实标注未核验）")
    args = ap.parse_args(argv)
    ok, report = validate(args.graph, args.materials, args.report,
                          require_materials=not args.allow_no_materials)
    if ok:
        print("校验通过：结构 OK，%d 条证据全部命中原文精确子串。" % report["checked_evidence"])
        return 0
    print("校验未通过，共 %d 个问题：" % len(report["errors"]), file=sys.stderr)
    for e in report["errors"]:
        print(" - " + e, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
