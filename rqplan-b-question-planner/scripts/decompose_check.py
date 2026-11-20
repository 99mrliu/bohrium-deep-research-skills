#!/usr/bin/env python3
"""decompose_check.py — 校验(或引导生成)子问题拆解 decomposition.json。

用法:
  python3 decompose_check.py --case /input/case.json --input-dir /input \
      --decomposition /app/work/decomposition.json [--auto]

--auto: 若 decomposition 不存在,从 research_question 做一个机械起点(仅含
        对象/时间窗/证据要求三个 SQ),Agent 仍需人工补全机制/方法/比较 SQ。

校验规则(全部输出逐项诊断):
  R1 2<=len(sqs)<=12; 每个 SQ 必须有 id/question/acceptance/queries/facet
  R2 acceptance 非空且含可判据(数字/类型词); queries 中英各>=1 条
  R3 depends_on 引用必须存在且无环
  R4 时间窗检索式最多出现在 1 个 SQ
  R5 facet 取值必须在六要素集合内
"""
import argparse, json, os, re, sys

FACETS = {"object", "mechanism", "method", "timeframe", "comparator", "evidence"}
TIME_PAT = re.compile(r"(19|20)\d{2}")

def template(case):
    q = case.get("research_question", "")
    ys = sorted(set(TIME_PAT.findall(q)))
    win = ("%s-%s" % (ys[0], ys[-1])) if ys else "未在问题中检出,需人工确认"
    return {
        "_guide": "按 resources/decomposition_schema.md 补全;questions 必须可独立检索",
        "research_question": q,
        "time_window": win,
        "sqs": [
            {"id": "SQ-1", "facet": "object",
             "question": "<研究对象是什么:替换为具体可检索的问句>",
             "acceptance": "≥3 条记录/文献明确涉及该对象",
             "queries": {"zh": ["<中文检索式>"], "en": ["<english query>"]},
             "depends_on": []},
            {"id": "SQ-2", "facet": "evidence",
             "question": "<证据要求对应的子问题>",
             "acceptance": "<可判定标准,如:≥2 篇原始研究给出定量结果>",
             "queries": {"zh": ["<中文检索式>"], "en": ["<english query>"]},
             "depends_on": ["SQ-1"]},
        ]}

def check_cycles(sqs):
    ids = {s["id"] for s in sqs}
    deps = {s["id"]: [d for d in s.get("depends_on", [])] for s in sqs}
    for s in sqs:
        for d in s.get("depends_on", []):
            if d not in ids:
                return "悬空依赖: %s -> %s" % (s["id"], d)
    color, stack = {}, []
    def dfs(u):
        color[u] = 1
        for v in deps.get(u, []):
            if color.get(v) == 1:
                return True
            if color.get(v, 0) == 0 and dfs(v):
                return True
        color[u] = 2
        return False
    for s in sqs:
        if color.get(s["id"], 0) == 0 and dfs(s["id"]):
            return "依赖成环,请合并或删除子问题"
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--decomposition", required=True)
    ap.add_argument("--auto", action="store_true")
    args = ap.parse_args()
    case = {}
    if os.path.exists(args.case):
        case = json.load(open(args.case, encoding="utf-8"))
    if not os.path.exists(args.decomposition):
        if args.auto:
            os.makedirs(os.path.dirname(args.decomposition), exist_ok=True)
            json.dump(template(case), open(args.decomposition, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            print(json.dumps({"ok": False, "error": "decomposition 不存在",
                              "action": "已生成机械起点模板,请按六要素补全后重跑本校验"},
                             ensure_ascii=False))
        else:
            print(json.dumps({"ok": False, "error": "decomposition 不存在",
                              "action": "请按 resources/decomposition_schema.md 编写后重跑",
                              "schema_hint": template(case)}, ensure_ascii=False))
        sys.exit(1)
    d = json.load(open(args.decomposition, encoding="utf-8"))
    sqs = d.get("sqs")
    errors = []
    if not isinstance(sqs, list) or not sqs:
        errors.append("R1: 缺少 sqs 列表")
        sqs = []
    if not (2 <= len(sqs) <= 12):
        errors.append("R1: 子问题数 %d 不在 [2,12]" % len(sqs))
    ids = set()
    for s in sqs:
        sid = s.get("id", "?")
        ids.add(sid)
        for field in ("id", "question", "acceptance", "queries", "facet"):
            if not s.get(field):
                errors.append("%s: 缺少必填字段 %s" % (sid, field))
        if s.get("facet") and s["facet"] not in FACETS:
            errors.append("%s: facet=%s 不在六要素集合" % (sid, s["facet"]))
        acc = str(s.get("acceptance", ""))
        if acc and not (re.search(r"\d", acc) or re.search(r"≥|篇|条|类|type|original|review", acc)):
            errors.append("%s: acceptance 无可判据(%s)" % (sid, acc[:40]))
        q = s.get("queries") or {}
        if q and (not q.get("zh") or not q.get("en")):
            errors.append("%s: queries 需中英各>=1 条" % sid)
    if len(ids) != len(sqs):
        errors.append("R1: SQ id 重复")
    cyc = check_cycles(sqs)
    if cyc:
        errors.append("R3: %s" % cyc)
    n_time = sum(1 for s in sqs if TIME_PAT.search(json.dumps(s.get("queries", {}), ensure_ascii=False)))
    if n_time > 1:
        errors.append("R4: %d 个 SQ 的检索式含年份窗,只允许 1 个" % n_time)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False))
        sys.exit(1)
    layers = {}
    deps = {s["id"]: set(s.get("depends_on", [])) for s in sqs}
    depth = {}
    def dep_d(sid):
        if sid in depth:
            return depth[sid]
        depth[sid] = 1 + max([dep_d(x) for x in deps[sid]], default=-1)
        return depth[sid]
    for s in sqs:
        layers.setdefault(dep_d(s["id"]), []).append(s["id"])
    print(json.dumps({"ok": True, "sqs": len(sqs), "dag_layers": len(layers),
                      "layer_map": layers}, ensure_ascii=False))

if __name__ == "__main__":
    main()
