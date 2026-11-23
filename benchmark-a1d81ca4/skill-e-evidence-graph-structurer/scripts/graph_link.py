#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""graph_link.py — 将 agent 起草的 claims/items 接入证据图谱并核验。

功能：
1. 逐字核验每条 evidence（NFKC 归一化、fi/fl 连字还原、断词连字符
   接合、空白折叠）是否落在其声称锚点内，supports 边记 verdict
   pass / fail / degraded；
2. 跨锚点冲突检测：同一属性（名称后缀匹配）同一单位数值不一致 ->
   numeric_mismatch；同值但极性相反 -> negation；产出 ConflictEdge；
3. 孤儿检测：无 supports 边且未标诚实的 claim 列入 orphans。

确定性：重跑同输入得同输出。本脚本幂等——先清除旧的
Claim/Evidence/RubricRule 节点、answers/supports/derived_from/
governed_by 边与 conflicts，再重新挂接。

用法：
  python3 graph_link.py --graph /app/work/graph.json \
      --answers /app/work/agent_answers.json \
      --report /app/work/link_report.json
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata

LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff",
             "ﬃ": "ffi", "ﬄ": "ffl"}
UNITS = ["mV/dec", "kJ/mol", "J/mol", "mA/cm2", "mA/cm^2",
         "eV", "mV", "MPa", "kPa", "Pa", "nm", "μm", "µm", "mm",
         "mA", "V", "K", "%", "℃", "°C", "倍", "Ω", "ohm"]
UNIT_ALT = "|".join(re.escape(u) for u in UNITS)
NUM_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(%s)?(?![\w/])"
                    % UNIT_ALT)
ATTR_TAIL_RE = re.compile(
    r"([一-鿿A-Za-z][一-鿿A-Za-z·\- ]{0,14}?)\s*"
    r"(?:为|是|达|约为|约|of|is|was|=|:|：)?\s*$")
CLEAN_RE = re.compile(r"[|\[\]()（）【】,，、;；。.:：@#*>「」『』\"'`·]")
NEG_RE = re.compile(r"(不|未|无|并非|不是|没有|not|never|no )")


def normalize(s):
    """核验用归一化：NFKC、连字、断词连字符、空白折叠。"""
    s = unicodedata.normalize("NFKC", s or "")
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s)  # 断词连字符接合
    s = re.sub(r"-\s*\n\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def atomic_write_json(path, obj):
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


def short_hash(s):
    return hashlib.sha1(normalize(s).encode("utf-8")).hexdigest()[:8]


def index_nodes(graph):
    return {n["id"]: n for n in graph.get("nodes", [])}


def reset_graph(graph):
    """幂等重置：移除上一轮挂接的节点、边与冲突。"""
    drop_types = {"Claim", "Evidence", "RubricRule"}
    graph["nodes"] = [n for n in graph.get("nodes", [])
                      if n.get("type") not in drop_types]
    drop_edges = {"answers", "supports", "derived_from", "governed_by"}
    graph["edges"] = [e for e in graph.get("edges", [])
                      if e.get("type") not in drop_edges]
    graph["conflicts"] = []


def attr_of(prefix):
    """从数值前缀文本中抽取属性名：清洗后取尾部短串。"""
    cleaned = CLEAN_RE.sub(" ", prefix)
    cleaned = re.sub(r"\s+", " ", cleaned)
    m = ATTR_TAIL_RE.search(cleaned)
    if not m:
        return ""
    return re.sub(r"\s+", "", m.group(1)).lower()


def common_suffix_len(a, b):
    n = 0
    for x, y in zip(reversed(a), reversed(b)):
        if x != y:
            break
        n += 1
    return n


def same_attr(a, b):
    return bool(a) and bool(b) and (a == b or common_suffix_len(a, b) >= 2)


def extract_numeric(text):
    """抽取 (attr, value, unit, polarity) 记录。"""
    records = []
    for m in NUM_RE.finditer(text):
        value = m.group(1)
        unit = m.group(2) or ""
        prefix = text[max(0, m.start() - 32):m.start()]
        attr = attr_of(prefix)
        if not attr:
            continue
        polarity = "neg" if NEG_RE.search(prefix[-12:]) else "pos"
        records.append({"attr": attr, "value": value, "unit": unit,
                        "polarity": polarity})
    return records


def verify_evidence(quote, anchor_node):
    """逐字核验，返回 (verdict, reason)。"""
    if anchor_node is None:
        return "fail", "anchor_not_found"
    q = normalize(quote)
    a = normalize(anchor_node["attrs"].get("text", ""))
    if not q:
        return "fail", "empty_quote"
    if not a:
        return "degraded", "anchor_text_unavailable"
    if q in a:
        return "pass", "verbatim_match"
    return "fail", "verbatim_mismatch"


def link_answers(graph, answers):
    nodes_by_id = index_nodes(graph)
    report = {"added": {"claims": 0, "evidences": 0, "rubrics": 0},
              "verdicts": {"pass": 0, "fail": 0, "degraded": 0},
              "fails": [], "orphans": [], "conflicts": []}
    new_nodes, new_edges = [], []

    def add_claim(task_id, text, honest, honest_reason, extra_attrs):
        seq = sum(1 for n in new_nodes if n["type"] == "Claim"
                  and n["attrs"].get("task") == task_id) + 1
        cid = "c.%s.%d.%s" % (task_id, seq, short_hash(text))
        attrs = {"task": task_id, "text": text,
                 "honest": bool(honest)}
        if honest_reason:
            attrs["honest_reason"] = honest_reason
        attrs.update(extra_attrs or {})
        new_nodes.append({"id": cid, "type": "Claim", "attrs": attrs})
        new_edges.append({"type": "answers", "src": cid,
                          "dst": task_id, "attrs": {}})
        return cid

    def add_evidences(cid, ev_list):
        for k, ev in enumerate(ev_list or [], 1):
            anchor_id = str(ev.get("anchor", ""))
            quote = str(ev.get("quote", ""))
            eid = "e.%s.%d" % (cid, k)
            anchor_node = nodes_by_id.get(anchor_id)
            verdict, reason = verify_evidence(quote, anchor_node)
            new_nodes.append({"id": eid, "type": "Evidence", "attrs": {
                "claim": cid, "anchor": anchor_id, "quote": quote,
                "verdict": verdict, "reason": reason}})
            new_edges.append({"type": "supports", "src": eid, "dst": cid,
                              "attrs": {"verdict": verdict,
                                        "reason": reason}})
            new_edges.append({"type": "derived_from", "src": eid,
                              "dst": anchor_id, "attrs": {}})
            report["added"]["evidences"] += 1
            report["verdicts"][verdict] += 1
            if verdict == "fail":
                report["fails"].append({"claim": cid, "anchor": anchor_id,
                                        "quote": quote, "reason": reason})

    for item in answers.get("claims", []) or []:
        task_id = str(item.get("task", ""))
        if task_id not in nodes_by_id:
            report["fails"].append({"claim": None, "anchor": None,
                                    "quote": item.get("text", ""),
                                    "reason": "task_not_found:" + task_id})
            continue
        cid = add_claim(task_id, str(item.get("text", "")),
                        item.get("honest", False),
                        item.get("honest_reason", ""),
                        {"kind": "claim"})
        add_evidences(cid, item.get("evidence"))
        report["added"]["claims"] += 1

    for item in answers.get("items", []) or []:
        task_id = str(item.get("task", ""))
        if task_id not in nodes_by_id:
            report["fails"].append({"claim": None, "anchor": None,
                                    "quote": item.get("question", ""),
                                    "reason": "task_not_found:" + task_id})
            continue
        cid = add_claim(task_id, str(item.get("question", "")),
                        item.get("honest", False),
                        item.get("honest_reason", ""),
                        {"kind": "item",
                         "reference_answer": str(
                             item.get("reference_answer", "")),
                         "difficulty": str(item.get("difficulty", "")),
                         "license": str(item.get("license", ""))})
        for r, rule in enumerate(item.get("rubric", []) or [], 1):
            rid = "r.%s.%d" % (task_id, r)
            new_nodes.append({"id": rid, "type": "RubricRule",
                              "attrs": {"task": task_id,
                                        "text": str(rule)}})
            new_edges.append({"type": "governed_by", "src": cid,
                              "dst": rid, "attrs": {}})
            report["added"]["rubrics"] += 1
        add_evidences(cid, item.get("evidence"))
        report["added"]["claims"] += 1

    graph["nodes"].extend(new_nodes)
    graph["edges"].extend(new_edges)

    # ---- 跨锚点冲突检测（仅基于 pass 证据引文） ----
    records = []
    for n in new_nodes:
        if n["type"] != "Evidence" or n["attrs"]["verdict"] != "pass":
            continue
        norm_quote = normalize(n["attrs"]["quote"])
        for rec in extract_numeric(norm_quote):
            records.append({"anchor": n["attrs"]["anchor"],
                            "evidence": n["id"], **rec})
    seen = set()
    seq = 0
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            a, b = records[i], records[j]
            if a["anchor"] == b["anchor"]:
                continue
            if a["unit"] != b["unit"]:
                continue
            if not same_attr(a["attr"], b["attr"]):
                continue
            try:
                diff_value = float(a["value"]) != float(b["value"])
            except ValueError:
                diff_value = a["value"] != b["value"]
            if diff_value:
                kind = "numeric_mismatch"
            elif a["polarity"] != b["polarity"]:
                kind = "negation"
            else:
                continue
            key = (kind, tuple(sorted([a["anchor"], b["anchor"]])),
                   tuple(sorted([a["value"], b["value"]])))
            if key in seen:
                continue
            seen.add(key)
            seq += 1
            attr_name = a["attr"] if len(a["attr"]) >= len(b["attr"]) \
                else b["attr"]
            conflict = {
                "id": "conf-%d" % seq, "kind": kind,
                "node_a": a["anchor"], "node_b": b["anchor"],
                "attr": attr_name, "unit": a["unit"],
                "values": {a["anchor"]: a["value"],
                           b["anchor"]: b["value"]},
                "detail": "%s：%s=%s%s vs %s=%s%s" % (
                    kind, a["anchor"], a["value"], a["unit"],
                    b["anchor"], b["value"], b["unit"])}
            graph["conflicts"].append(conflict)
            report["conflicts"].append(conflict)

    # ---- 孤儿检测 ----
    supported = {e["dst"] for e in graph["edges"]
                 if e["type"] == "supports"}
    for n in graph["nodes"]:
        if n["type"] == "Claim" and not n["attrs"].get("honest") \
                and n["id"] not in supported:
            report["orphans"].append({
                "claim": n["id"], "task": n["attrs"].get("task"),
                "text": n["attrs"].get("text", "")})
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="挂接 claims/items：逐字核验、冲突检测、孤儿检测")
    ap.add_argument("--graph", default="/app/work/graph.json")
    ap.add_argument("--answers", required=True)
    ap.add_argument("--report", default="/app/work/link_report.json")
    args = ap.parse_args(argv)

    try:
        with open(args.graph, "r", encoding="utf-8") as fh:
            graph = json.load(fh)
    except Exception as exc:
        print("[graph_link] ERROR: 无法读取 graph: %s" % exc,
              file=sys.stderr)
        return 1
    try:
        with open(args.answers, "r", encoding="utf-8") as fh:
            answers = json.load(fh)
        if not isinstance(answers, dict):
            raise ValueError("answers 须为 JSON object")
    except Exception as exc:
        print("[graph_link] ERROR: 无法解析 answers: %s" % exc,
              file=sys.stderr)
        return 1

    try:
        reset_graph(graph)
        report = link_answers(graph, answers)
        atomic_write_json(args.graph, graph)
        atomic_write_json(args.report, report)
        v = report["verdicts"]
        print("[graph_link] claims=%d evidences=%d pass=%d fail=%d "
              "degraded=%d orphans=%d conflicts=%d"
              % (report["added"]["claims"], report["added"]["evidences"],
                 v["pass"], v["fail"], v["degraded"],
                 len(report["orphans"]), len(report["conflicts"])))
        for o in report["orphans"]:
            print("[graph_link] ORPHAN %s (task=%s): %s"
                  % (o["claim"], o["task"], o["text"][:60]))
        for f in report["fails"]:
            print("[graph_link] FAIL %s anchor=%s reason=%s"
                  % (f["claim"], f["anchor"], f["reason"]))
        for c in report["conflicts"]:
            print("[graph_link] CONFLICT %s %s"
                  % (c["id"], c["detail"]))
        return 0
    except Exception as exc:
        print("[graph_link] ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
