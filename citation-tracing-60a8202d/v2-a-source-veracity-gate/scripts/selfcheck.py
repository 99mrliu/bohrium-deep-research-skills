#!/usr/bin/env python3
"""selfcheck.py — 阶段三：交付自查门禁。

校验 <out>/result.json：
- case_id 非空（且与 case.json 一致，若可读）；
- output_contract 全字段在 result.json 顶层在场；
- 每条 candidate 与每条 edge 都有 source locator（{file, pointer}）；
- status 与实际内容一致（ok/partial/failed 不自相矛盾）。

打印 ok=true/false 与缺陷清单；退出码 0=通过，1=有缺陷，2=自身错误。
仅标准库，脚本位置无关。
"""
import argparse
import json
import sys
from pathlib import Path

EXPECTED_STATUS = {"ok", "partial", "failed"}


def check(out_dir, case_path):
    defects = []
    out_dir = Path(out_dir)
    rpath = out_dir / "result.json"
    if not rpath.is_file():
        return False, ["result.json 不存在：%s" % rpath]
    try:
        result = json.loads(rpath.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, ["result.json 不是合法 JSON：%s" % exc]

    # 1. case_id 非空并与 case.json 一致
    case_id = result.get("case_id")
    if not case_id or case_id == "UNKNOWN":
        defects.append("case_id 为空或为 UNKNOWN")
    case = {}
    if case_path and Path(case_path).is_file():
        try:
            case = json.loads(Path(case_path).read_text(encoding="utf-8"))
        except Exception as exc:
            defects.append("case.json 解析失败：%s" % exc)
    if case.get("case_id") and case_id and case_id != case["case_id"]:
        defects.append("case_id 与 case.json 不一致：%s != %s"
                       % (case_id, case["case_id"]))

    # 2. output_contract 全字段在场
    contract = case.get("output_contract")
    if isinstance(contract, dict):
        for key in contract:
            if key not in result:
                defects.append("output_contract 字段缺失：%s" % key)
    else:
        # 无 contract 可读时至少检查最低字段
        for key in ("case_id", "status", "seed", "candidates", "edges",
                    "sources", "evidence_records", "uncertainty"):
            if key not in result:
                defects.append("最低字段缺失：%s" % key)

    # 3. 每条 candidate 有 source locator
    for i, c in enumerate(result.get("candidates") or []):
        srcs = c.get("sources")
        ok = isinstance(srcs, list) and any(
            isinstance(s, dict) and s.get("file") and s.get("pointer") for s in srcs)
        if not ok:
            defects.append("candidate[%d] (%s) 缺少 source locator"
                           % (i, c.get("id")))

    # 4. 每条 edge 有 source locator
    for i, e in enumerate(result.get("edges") or []):
        s = e.get("source")
        if not (isinstance(s, dict) and s.get("file") and s.get("pointer")):
            defects.append("edge[%d] (%s -> %s) 缺少 source locator"
                           % (i, e.get("from"), e.get("to")))

    # 5. status 与实际一致
    status = result.get("status")
    if status not in EXPECTED_STATUS:
        defects.append("status 非法：%r（应为 ok/partial/failed）" % (status,))
    else:
        n_cand = len(result.get("candidates") or [])
        seed = result.get("seed") or {}
        if status == "ok":
            if not seed.get("found_in_corpus"):
                defects.append("status=ok 但种子未在语料中命中")
            if n_cand == 0:
                defects.append("status=ok 但 candidates 为空")
        if status == "failed" and n_cand > 0:
            defects.append("status=failed 但 candidates 非空（%d 条）" % n_cand)

    # 6. 证据记录与候选一一对应（警告级，计为缺陷但说明）
    ev_ids = {e.get("candidate_id") for e in result.get("evidence_records") or []}
    for c in result.get("candidates") or []:
        if c.get("id") not in ev_ids:
            defects.append("candidate %s 缺少对应 evidence_record" % c.get("id"))

    return (len(defects) == 0), defects


def main(argv=None):
    ap = argparse.ArgumentParser(description="result.json 交付自查门禁（阶段三）")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--case", default="/input/case.json")
    args = ap.parse_args(argv)
    try:
        ok, defects = check(args.out, args.case)
    except Exception as exc:
        print(json.dumps({"ok": False, "selfcheck_error": str(exc)},
                         ensure_ascii=False))
        return 2
    print(json.dumps({"ok": ok, "defects": defects,
                      "defect_count": len(defects)}, ensure_ascii=False, indent=2))
    print("ok=%s" % str(ok).lower())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
