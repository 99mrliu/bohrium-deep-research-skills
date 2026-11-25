#!/usr/bin/env python3
"""validate.py — 独立契约门禁：pipeline 的产物不过此门不得交付（本技能的核心）。

用法:
  python3 validate.py --case /input/case.json --work /app/work --out /app/output

检查（全部可复算，任一 FAIL 则 exit=1）:
  C1 result.json 存在且为合法 JSON 对象
  C2 case_id 存在且与 case.json 一致
  C3 output_contract 每个字段都在 result.json 中出现（null 视为缺失）
  C4 空容器字段（[]/""）必须在 uncertainty 中有对应说明
  C5 status ∈ {complete, partial, blocked}；complete 时 uncertainty 必须为空
  C6 sources 中 kind=file 的条目指向 /input 内真实存在的文件
  C7 candidates 每条含 rid/title/source，且 rid 可回溯到 ledger 记录
  C8 uncertainty 为字符串列表，且不含空串
"""
import argparse, json, os, sys


def contract_fields(case):
    c = case.get("output_contract")
    if isinstance(c, list):
        return [str(x) for x in c]
    if isinstance(c, dict):
        for k in ("fields", "required"):
            if isinstance(c.get(k), list):
                return [str(x) for x in c[k]]
        return sorted(c.keys())
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    checks = []

    def check(cid, ok, detail):
        checks.append({"id": cid, "verdict": "PASS" if ok else "FAIL", "detail": detail})
        return ok

    case = {}
    if os.path.isfile(args.case):
        try:
            case = json.load(open(args.case, encoding="utf-8"))
        except Exception:
            pass
    rp = os.path.join(args.out, "result.json")
    result = None
    if os.path.isfile(rp):
        try:
            result = json.load(open(rp, encoding="utf-8"))
        except Exception:
            result = None
    check("C1", isinstance(result, dict), "result.json 存在且为 JSON 对象")
    if not isinstance(result, dict):
        report = {"gate": "fail", "checks": checks}
        json.dump(report, open(os.path.join(args.out, "validate-report.json"), "w"),
                  ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=False))
        sys.exit(1)

    check("C2", bool(result.get("case_id")) and result.get("case_id") == case.get("case_id"),
          "case_id=%r（case.json: %r）" % (result.get("case_id"), case.get("case_id")))

    fields = contract_fields(case)
    missing = [f for f in fields if result.get(f) is None]
    check("C3", not missing, "契约字段 %d 个，缺失: %s" % (len(fields), missing or "无"))

    uncert_text = " ".join(str(u) for u in (result.get("uncertainty") or []))
    notes = result.get("field_notes") or {}
    empty_unexplained = [f for f in fields
                         if result.get(f) in ([], "", {}) and f not in uncert_text
                         and f not in notes
                         and f not in ("uncertainty", "sources")]
    check("C4", not empty_unexplained, "空容器但未说明: %s" % (empty_unexplained or "无"))

    st = result.get("status")
    ok5 = st in ("complete", "partial", "blocked") and not (
        st == "complete" and result.get("uncertainty"))
    check("C5", ok5, "status=%r，uncertainty 项数=%d"
          % (st, len(result.get("uncertainty") or [])))

    bad_src = []
    for s in result.get("sources") or []:
        if isinstance(s, dict) and s.get("kind") == "file":
            p = s.get("path", "")
            base = os.path.dirname(os.path.abspath(args.case))
            if not (os.path.isfile(os.path.join(base, p)) or os.path.isfile(p)):
                bad_src.append(p)
    check("C6", not bad_src, "sources 中失效文件引用: %s" % (bad_src or "无"))

    ledger_rids = set()
    lp = os.path.join(args.out, "ledger.jsonl")
    if os.path.isfile(lp):
        for line in open(lp, encoding="utf-8"):
            if line.strip():
                try:
                    ledger_rids.add(json.loads(line).get("rid"))
                except Exception:
                    pass
    cands = result.get("candidates") or []
    bad_c = [c for c in cands if not isinstance(c, dict)
             or not all(k in c for k in ("rid", "title", "source"))]
    orphan = [c.get("rid") for c in cands if isinstance(c, dict)
              and ledger_rids and c.get("rid") not in ledger_rids]
    check("C7", not bad_c and not orphan,
          "candidates %d 条；字段缺失 %d；台账外 rid %s"
          % (len(cands), len(bad_c), orphan or "无"))

    u = result.get("uncertainty")
    check("C8", isinstance(u, list) and all(isinstance(x, str) and x.strip() for x in u),
          "uncertainty 为非空字符串列表")

    gate = "pass" if all(c["verdict"] == "PASS" for c in checks) else "fail"
    report = {"gate": gate, "checks": checks,
              "note": "gate=pass 才可交付；fail 时按 FAIL 项修复后重跑 pipeline.py 与本脚本"}
    with open(os.path.join(args.out, "validate-report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"gate": gate,
                      "failed": [c["id"] for c in checks if c["verdict"] == "FAIL"]},
                     ensure_ascii=False))
    sys.exit(0 if gate == "pass" else 1)


if __name__ == "__main__":
    main()
