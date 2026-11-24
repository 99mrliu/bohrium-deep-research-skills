#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""finalize.py — 装配 /app/output 并生成契约归一化的 result.json（仅标准库）。

读取工作目录中的诊断产物（citeaudit / citebuild 输出），生成：
  citation_map.md  —— 正文每个引用点 ↔ bib 条目 file:line ↔ 最终状态
  result.json      —— case_id 原样复制；output_contract 逐字段镜像；
                      status / sources / uncertainty / artifacts 据实填写

output_contract 四种历史方言的归一化：
  1. {字段: {type, required}}  2. 自然语言描述（提取 `反引号` 或行首字段名）
  3. JSON Schema（type=object + properties/required）  4. 字段名列表
缺材料的字段给诚实的 null，绝不填充编造值。

用法：
  python3 finalize.py [--case /input/case.json] [--input-root /input]
      --work /app/work --out /app/output [--project <工程目录>] [--banner "标注"]
退出码：0 装配完成（status 字段自身表达 complete/partial/blocked）；1 运行错误
（也会尽力先落盘一份 failed 的 result.json）。
"""
import argparse
import json
import os
import re
import shutil
import sys


def normalize_contract(oc):
    """四种方言 → [(field, required, type_hint)]。无法识别时返回 []。"""
    if isinstance(oc, dict):
        if oc.get("type") == "object" and isinstance(oc.get("properties"), dict):
            req = set(oc.get("required") or [])
            return [(k, k in req,
                     v.get("type") if isinstance(v, dict) else None)
                    for k, v in oc["properties"].items()]
        out = []
        for k, v in oc.items():
            if isinstance(v, dict):
                out.append((k, bool(v.get("required", True)), v.get("type")))
            elif isinstance(v, str):
                out.append((k, True, None))
        return out
    if isinstance(oc, list):
        return [(str(x), True, None) for x in oc]
    if isinstance(oc, str):
        fields = re.findall(r"`([A-Za-z_][\w]*)`", oc)
        if not fields:
            fields = re.findall(r"^\s*[-*]\s*([A-Za-z_][\w]*)\s*[:：]", oc, re.M)
        return [(f, True, None) for f in dict.fromkeys(fields)]
    return []


def load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def fill_field(name, type_hint, ctx):
    """按字段名启发式填充；无可靠数据来源时返回 (None, 原因)。"""
    n = name.lower()
    has_rounds = ctx.get("rounds") is not None and \
        ctx["rounds"].get("status") == "ok"
    if "map" in n or "mapping" in n:
        if os.path.isfile(os.path.join(ctx["out"], "citation_map.md")):
            return "citation_map.md", None
        return None, "citation_map.md 未生成"
    if "report" in n:
        if os.path.isfile(os.path.join(ctx["out"], "citation_report.md")):
            return "citation_report.md", None
        return None, "citation_report.md 未生成"
    if "round" in n or "curve" in n:
        if has_rounds or os.path.isfile(os.path.join(ctx["out"], "rounds.json")):
            return "rounds.json", None
        return None, "多轮编译未执行或工具不可用"
    if "unresolved" in n:
        if has_rounds:
            return sorted(ctx["rounds"]["final"].get(
                "unresolved_citations", {})), None
        if ctx.get("graph"):
            return ctx["graph"].get("undefined_citations", []), \
                "未经编译验证（静态结果）"
        return None, "无诊断数据"
    if "resolved" in n and (type_hint or "").lower() in (
            "number", "integer", "int"):
        if has_rounds:
            ks = ctx["rounds"]["final"].get("key_status", {})
            return sum(1 for v in ks.values() if v == "resolved"), None
        return None, "未经编译验证"
    if "graph" in n:
        if os.path.isfile(os.path.join(ctx["out"], "citation_graph.json")):
            return "citation_graph.json", None
        return None, "citation_graph.json 未生成"
    return None, "无可对应的数据来源，诚实置空"


def build_citation_map(graph, rounds, banner=None):
    L = []
    if banner:
        L += [banner, ""]
    L.append("# 引用映射表（citation map）")
    L.append("")
    verified = rounds is not None and rounds.get("status") == "ok"
    if verified:
        L.append("最终状态来源：citebuild 多轮编译（已验证）。")
    else:
        L.append("最终状态来源：citeaudit 静态解析（**未经编译验证**"
                 + ("；编译工具不可用" if rounds is not None else "；未执行编译")
                 + "）。")
    L.append("")
    L.append("| 引用点（file:line） | 命令 | 键 | bib 条目（file:line） | 最终状态 |")
    L.append("| --- | --- | --- | --- | --- |")
    key_status = (rounds or {}).get("final", {}).get("key_status", {}) \
        if verified else {}
    unresolved_reason = (rounds or {}).get("final", {}).get(
        "unresolved_citations", {}) if verified else {}
    if graph:
        for c in graph.get("citations", []):
            site = f"`{c['file']}:{c['line']}`"
            bib = (f"`{c['bib']['file']}:{c['bib']['line']}`"
                   if c.get("bib") else "—（无对应条目）")
            key = c["key"]
            if verified:
                st = key_status.get(key)
                if st is None:
                    st = ("unresolved（%s）" % unresolved_reason[key]) \
                        if key in unresolved_reason else \
                        "resolved" if c["resolved"] else \
                        "unresolved（未进入 .aux，可能位于未编译分支）"
            else:
                st = "static-resolved（未编译验证）" if c["resolved"] \
                    else "static-undefined（未编译验证）"
            L.append(f"| {site} | \\{c['command']} | `{key}` | {bib} | {st} |")
    else:
        L.append("| — | — | — | — | 无静态图谱数据 |")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="装配 /app/output 与 result.json")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--input-root", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--project", default=None)
    ap.add_argument("--banner", default=None)
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)

    uncertainty, sources, notes = [], [], []

    # ---- 输入：case.json 缺失时遍历 /input 并如实降级 ----
    case = load_json(args.case)
    if case is None:
        case = {}
        notes.append(f"case.json 缺失或不可解析（{args.case}），已降级")
        if os.path.isdir(args.input_root):
            listing = []
            for dirpath, _d, files in os.walk(args.input_root):
                for f in files:
                    listing.append(os.path.relpath(
                        os.path.join(dirpath, f), args.input_root))
            notes.append("遍历 /input 发现文件：" + ("、".join(sorted(listing))
                                                   if listing else "（空）"))
            sources.extend(sorted(listing))
        uncertainty.append("case_id 不可得（case.json 缺失）")
    else:
        sources.append(os.path.abspath(args.case))
    case_id = case.get("case_id")
    contract = normalize_contract(case.get("output_contract"))
    if case and not contract:
        uncertainty.append("output_contract 缺失或方言无法识别，契约字段全部置空")

    # ---- 收集工作产物 ----
    graph = load_json(os.path.join(args.work, "citation_graph.json"))
    rounds = load_json(os.path.join(args.work, "rounds.json"))
    if graph is None:
        uncertainty.append("缺少 citation_graph.json（未运行 citeaudit）")
    if rounds is None:
        uncertainty.append("缺少 rounds.json（未运行 citebuild，未做编译验证）")
    elif rounds.get("status") == "compile_unavailable":
        notes.append("编译验证不可用：" + rounds.get("status_note", ""))

    # ---- 生成 citation_map.md 并复制产物 ----
    with open(os.path.join(args.out, "citation_map.md"), "w",
              encoding="utf-8") as fh:
        fh.write(build_citation_map(graph, rounds, banner=args.banner))
    for fname in ("citation_report.md", "citation_graph.json",
                  "rounds.json", "citebuild_report.md"):
        src = os.path.join(args.work, fname)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(args.out, fname))
            sources.append(os.path.abspath(src))

    # ---- 契约字段镜像 ----
    ctx = {"out": args.out, "rounds": rounds, "graph": graph}
    result = {"case_id": case_id}
    unfilled_required = 0
    for field, required, thint in contract:
        value, why = fill_field(field, thint, ctx)
        result[field] = value
        if value is None:
            uncertainty.append(f"契约字段 `{field}` 置空：{why or '无数据'}")
            if required:
                unfilled_required += 1

    # ---- status 判定（据实） ----
    compile_ok = rounds is not None and rounds.get("status") == "ok"
    unresolved = 0
    if compile_ok:
        unresolved = len(rounds["final"].get("unresolved_citations", {})) + \
            len(rounds["final"].get("unresolved_references", []))
    if not case and graph is None:
        status = "blocked"
        notes.append("无 case.json 且无诊断产物，无法开展工作")
    elif not case:
        status = "partial"
        notes.append("case.json 缺失，无法核对 output_contract，降级为 partial")
    elif compile_ok and unresolved == 0 and unfilled_required == 0:
        status = "complete"
    else:
        status = "partial"
        if not compile_ok:
            uncertainty.append("编译验证未完成或不可用，引用状态未经多轮编译确认")
        if unresolved:
            uncertainty.append(f"仍有 {unresolved} 个未解析引用/交叉引用")
    result.update({
        "status": status,
        "sources": sources,
        "uncertainty": uncertainty,
        "artifacts": sorted(f for f in os.listdir(args.out)
                            if os.path.isfile(os.path.join(args.out, f))
                            and f != "result.json"),
        "notes": notes,
    })
    out_path = os.path.join(args.out, "result.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(f"[finalize] status={status}，case_id={case_id}，"
          f"契约字段 {len(contract)} 个（置空必填 {unfilled_required}），"
          f"产物 {len(result['artifacts'])} 个 → {out_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # 先交付再改进：失败也尽早落盘
        out = "/app/output"
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as fh:
            json.dump({"case_id": None, "status": "failed",
                       "sources": [], "artifacts": [],
                       "uncertainty": [f"finalize 异常：{exc}"],
                       "notes": []}, fh, ensure_ascii=False, indent=2)
        print(f"[finalize] 失败（已落盘 result.json）：{exc}", file=sys.stderr)
        sys.exit(1)
