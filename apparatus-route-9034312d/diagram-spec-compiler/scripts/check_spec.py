#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_spec.py — figure_spec.json 静态校验（纯 Python 标准库）。

用法:
    python3 check_spec.py figure_spec.json [--report validation_report.json]

校验项（errors，退出码 1）:
  * JSON 无法解析 / kind 非法 / title 为空 / nodes 为空
  * 节点 id 重复、label 为空、kind 未知、边 id 重复
  * 边端点未知、flow_type 未定义、自环
  * stepflow：num 缺失/非整数、S1..Sn 编号不连续
  * roadmap：stages 缺失/id 重复、节点 stage 引用未知
警告（warnings，不阻塞）:
  * 节点/边缺少 source 溯源字段、孤立节点、重复边(from,to,flow_type)
"""
import argparse
import json
import sys

VALID_KINDS = ("apparatus", "stepflow", "roadmap")
VALID_NODE_KINDS = ("unit", "step", "stage", "data", "note")
DEFAULT_FLOW_TYPES = ("material", "energy", "information")


def check(spec):
    errors, warnings = [], []

    kind = spec.get("kind")
    if kind not in VALID_KINDS:
        errors.append("kind 必须为 %s 之一，当前: %r" % (VALID_KINDS, kind))
    if not str(spec.get("title") or "").strip():
        errors.append("title 为空")

    styles = spec.get("styles") or {}
    flow_types = set(DEFAULT_FLOW_TYPES) | set((styles.get("flow_types") or {}).keys())

    nodes = spec.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        errors.append("nodes 为空或不是数组")
        nodes = []
    edges = spec.get("edges") or []
    if not isinstance(edges, list):
        errors.append("edges 不是数组")
        edges = []

    ids = []
    seen = set()
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            errors.append("nodes[%d] 不是对象" % i)
            continue
        nid = n.get("id")
        if not nid:
            errors.append("nodes[%d] 缺少 id" % i)
            continue
        if nid in seen:
            errors.append("节点 id 重复: %s" % nid)
        seen.add(nid)
        ids.append(nid)
        if not str(n.get("label") or "").strip():
            errors.append("节点 %s 的 label 为空" % nid)
        kd = n.get("kind")
        if kd is None:
            warnings.append("节点 %s 未指定 kind，编译时按 unit 处理" % nid)
        elif kd not in VALID_NODE_KINDS:
            errors.append("节点 %s 的 kind 未知: %r（可选 %s）"
                          % (nid, kd, VALID_NODE_KINDS))
        src = n.get("source") or {}
        if not (src.get("locator") and src.get("quote")):
            warnings.append("节点 %s 缺少完整 source{locator,quote} 溯源字段" % nid)

    # stepflow 编号连续性（仅 step 类节点参与编号；data/note 等不需要 num）
    if kind == "stepflow":
        nums = []
        for n in nodes:
            kd = n.get("kind") or "step"
            if kd != "step":
                continue
            num = n.get("num")
            if not isinstance(num, int) or isinstance(num, bool):
                errors.append("stepflow 步骤节点 %s 缺少整数 num" % n.get("id"))
            else:
                nums.append(num)
        if nums and sorted(nums) != list(range(1, len(nums) + 1)):
            errors.append("stepflow 编号不连续: 期望 S1..S%d，实际 %s"
                          % (len(nums), sorted(nums)))

    # roadmap 泳道引用
    stage_ids = set()
    if kind == "roadmap":
        stages = spec.get("stages") or []
        if not stages:
            errors.append("roadmap 缺少 stages 数组")
        for s in stages:
            sid = s.get("id")
            if not sid:
                errors.append("stages 中存在缺少 id 的阶段")
            elif sid in stage_ids:
                errors.append("stage id 重复: %s" % sid)
            stage_ids.add(sid)
        for n in nodes:
            st = n.get("stage")
            if not st:
                warnings.append("roadmap 节点 %s 未指定 stage，将落入第一泳道"
                                % n.get("id"))
            elif st not in stage_ids:
                errors.append("节点 %s 引用了未知 stage: %s" % (n.get("id"), st))

    idset = set(ids)
    edge_ids = set()
    edge_keys = set()
    for i, e in enumerate(edges):
        if not isinstance(e, dict):
            errors.append("edges[%d] 不是对象" % i)
            continue
        eid = e.get("id") or "e%02d" % i
        if eid in edge_ids:
            errors.append("边 id 重复: %s" % eid)
        edge_ids.add(eid)
        u, v = e.get("from"), e.get("to")
        if u not in idset:
            errors.append("边 %s 的 from 未知: %r" % (eid, u))
        if v not in idset:
            errors.append("边 %s 的 to 未知: %r" % (eid, v))
        if u is not None and u == v:
            errors.append("边 %s 为自环(%s→%s)，不支持" % (eid, u, v))
        ft = e.get("flow_type") or "material"
        if ft not in flow_types:
            errors.append("边 %s 的 flow_type 未定义: %r（已定义: %s）"
                          % (eid, ft, sorted(flow_types)))
        if not str(e.get("label") or "").strip():
            warnings.append("边 %s 的 label 为空" % eid)
        src = e.get("source") or {}
        if not (src.get("locator") and src.get("quote")):
            warnings.append("边 %s 缺少完整 source{locator,quote} 溯源字段" % eid)
        key = (u, v, ft)
        if key in edge_keys:
            warnings.append("重复边(from,to,flow_type): %s→%s/%s" % (u, v, ft))
        edge_keys.add(key)

    deg = {i: 0 for i in ids}
    for e in edges:
        if isinstance(e, dict):
            if e.get("from") in deg:
                deg[e["from"]] += 1
            if e.get("to") in deg:
                deg[e["to"]] += 1
    for nid in ids:
        if deg[nid] == 0 and nodes and kind != "roadmap":
            warnings.append("孤立节点（无任何连线）: %s" % nid)

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {"nodes": len(ids), "edges": len(edges),
                   "flow_types_defined": sorted(flow_types)},
    }


def main(argv):
    ap = argparse.ArgumentParser(description="校验 figure_spec.json")
    ap.add_argument("spec")
    ap.add_argument("--report", default="validation_report.json")
    args = ap.parse_args(argv[1:])

    try:
        with open(args.spec, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        report = {"ok": False, "errors": ["spec 无法解析: %s" % exc],
                  "warnings": [], "counts": {}}
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
        print("[check_spec] FAIL: %s" % exc, file=sys.stderr)
        return 1

    report = check(spec)
    with open(args.report, "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
    status = "OK" if report["ok"] else "FAIL"
    print("[check_spec] %s errors=%d warnings=%d -> %s"
          % (status, len(report["errors"]), len(report["warnings"]), args.report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
