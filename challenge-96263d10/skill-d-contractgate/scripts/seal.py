#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seal.py -- 交付封印：独立裁决 result.json 是否够格出门。

seal 不读 Agent 的解释，只核对证据。八项裁决（S1–S8）：
  S1 result.json 可解析
  S2 case_id 与 case.json 一致
  S3 output_contract 全部字段存在且非空
  S4 status 合法且与证据一致（complete ⇒ limits/manual_confirm/uncertainties 全空，
     有未了事项只许 partial/failed）
  S5 artifacts 全部在盘上且 sha256 匹配
  S6 sources 非空（来源可回溯）
  S7 changes 非空，或 status=failed（什么都没做也要有交代）
  S8 /app/output 里除 result.json 外存在真实交付物（或渲染缺失声明）

退出码: 0 SEALED; 1 SEAL REFUSED（逐项列出）; 2 用法/输入错误。
用法: python3 seal.py --case /input/case.json --output /app/output --work /app/work
"""
import argparse, hashlib, json, os, sys, time

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def contract_fields(case):
    oc = case.get("output_contract") or case.get("outputContract") or {}
    if isinstance(oc, dict):
        return sorted(oc.keys())
    if isinstance(oc, list):
        return [(x if isinstance(x, str) else x.get("name") or x.get("field") or "")
                for x in oc]
    return []

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--work", default=None)
    a = ap.parse_args()

    checks = []
    def add(cid, ok, detail):
        checks.append({"check": cid, "pass": bool(ok), "detail": detail})

    # S1
    rj_path = os.path.join(a.output, "result.json")
    try:
        rj = json.load(open(rj_path, encoding="utf-8"))
        add("S1-parse", True, "result.json parses")
    except (OSError, json.JSONDecodeError) as e:
        add("S1-parse", False, str(e))
        return finish(a, checks, 1)

    # S2
    try:
        case = json.load(open(a.case, encoding="utf-8"))
        want_id = case.get("case_id") or case.get("id")
        add("S2-case-id", rj.get("case_id") == want_id,
            "result=%r case=%r" % (rj.get("case_id"), want_id))
    except (OSError, json.JSONDecodeError) as e:
        case = {}
        add("S2-case-id", False, "case.json unreadable: %s" % e)

    # S3
    fields = contract_fields(case)
    missing = [f for f in fields if not str(rj.get(f, "")).strip()]
    add("S3-contract-fields", not missing,
        "fields=%d missing=%s" % (len(fields), missing or "[]"))

    # S4
    status = rj.get("status")
    open_items = (rj.get("limits") or []) + (rj.get("manual_confirm") or []) + (rj.get("uncertainties") or [])
    if status == "complete":
        add("S4-status-consistency", not open_items,
            "status=complete but open items: %s" % (open_items[:3] or "[]") if open_items else "complete, no open items")
    elif status in ("partial", "failed"):
        add("S4-status-consistency", True, "status=%s, open items declared: %d" % (status, len(open_items)))
    else:
        add("S4-status-consistency", False, "illegal status %r" % (status,))

    # S5
    bad = []
    for art in rj.get("artifacts", []):
        p, want = art.get("path"), art.get("sha256")
        if not p or not os.path.isfile(p):
            bad.append("missing: %s" % p)
        elif want and sha256_of(p) != want:
            bad.append("hash mismatch: %s" % p)
    add("S5-artifacts", not bad, "; ".join(bad) if bad else "%d artifacts verified" % len(rj.get("artifacts", [])))

    # S6
    add("S6-sources", bool(rj.get("sources")), "%d sources" % len(rj.get("sources") or []))

    # S7
    add("S7-changes", bool(rj.get("changes")) or status == "failed",
        "%d change records" % len(rj.get("changes") or []))

    # S8
    others = [f for f in os.listdir(a.output) if f != "result.json" and os.path.isfile(os.path.join(a.output, f))]
    render_declared = any("渲染" in str(x) or "render" in str(x).lower() for x in (rj.get("limits") or []))
    add("S8-deliverables", bool(others) or render_declared,
        "%d files besides result.json" % len(others) if others else "no deliverable files; render-missing declared" if render_declared else "nothing delivered")

    finish(a, checks, 0 if all(c["pass"] for c in checks) else 1)

def finish(a, checks, code):
    report = {"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "output": a.output,
              "verdict": "SEALED" if code == 0 else "SEAL REFUSED", "checks": checks}
    dst = os.path.join(a.work or a.output, "seal_report.json")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    json.dump(report, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(report["verdict"])
    for c in checks:
        print("  [%s] %s: %s" % ("PASS" if c["pass"] else "FAIL", c["check"], c["detail"]))
    sys.exit(code)

if __name__ == "__main__":
    main()
