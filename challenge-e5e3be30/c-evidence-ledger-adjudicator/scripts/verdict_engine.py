#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verdict_engine.py — 确定性裁决核心：按 references/verdict-rules.md 的公开规则，
从证据台账确定性地计算四级判定。同一份台账永远得到同一个 verdict。

用法:
    python3 verdict_engine.py LEDGER [LEDGER ...] [--explain] [--update] [--json]

  LEDGER    台账 JSON 文件或目录（目录时扫描 ledger-*.json）
  --explain 打印逐步推导（命中的规则编号、中间量）
  --update  把 adjudication 字段写回台账文件
  --json    以 JSON 汇总全部结果到 stdout

退出码: 0 裁决完成; 1 台账 schema 错误（裁决被阻塞）; 2 IO/用法错误。
规则文本见 references/verdict-rules.md（R1–R7），本文件是其唯一实现依据。
纯 Python3 标准库。
"""
import argparse
import glob
import json
import os
import sys

RANK = {"direct": 3, "indirect": 2, "topical": 1}
VERDICTS = ("supported", "partially_supported", "contradicted",
            "insufficient_evidence")
DOWNGRADE = {
    "supported": "partially_supported",
    "contradicted": "partially_supported",
    "partially_supported": "insufficient_evidence",
    "insufficient_evidence": "insufficient_evidence",
}
ENGINE_VERSION = "1.0"


def iter_ledger_paths(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out.extend(sorted(glob.glob(os.path.join(p, "ledger-*.json"))))
        elif os.path.isfile(p):
            out.append(p)
        else:
            print("ERROR: 路径不存在: %s" % p, file=sys.stderr)
            sys.exit(2)
    if not out:
        print("ERROR: 未找到任何台账文件", file=sys.stderr)
        sys.exit(2)
    return out


def check_minimal_schema(ledger):
    """裁决前的最小 schema 检查；返回错误列表（空=通过）。"""
    errs = []
    if not isinstance(ledger.get("anchors"), list):
        errs.append("anchors 缺失或不是列表")
    if not isinstance(ledger.get("evidence"), list):
        errs.append("evidence 缺失或不是列表")
        return errs
    anchor_ids = {a.get("id") for a in ledger.get("anchors", [])
                  if isinstance(a, dict)}
    for i, e in enumerate(ledger["evidence"]):
        if not isinstance(e, dict):
            errs.append("evidence[%d] 不是对象" % i)
            continue
        for k in ("evidence_id", "side", "strength", "polarity", "covers",
                  "quote"):
            if k not in e:
                errs.append("evidence[%d] 缺少字段 '%s'" % (i, k))
        if e.get("side") not in ("pro", "con"):
            errs.append("evidence[%d] side 非法" % i)
        if e.get("strength") not in RANK:
            errs.append("evidence[%d] strength 非法" % i)
        if e.get("polarity") not in ("same", "opposite"):
            errs.append("evidence[%d] polarity 非法" % i)
        for aid in (e.get("covers") or []):
            if aid not in anchor_ids:
                errs.append("evidence[%d] covers 引用不存在的锚点 %s" % (i, aid))
    return errs


def adjudicate(ledger):
    """核心裁决函数。返回 adjudication 字典与推导步骤列表。"""
    steps = []
    anchors = ledger["anchors"]
    evidence = ledger["evidence"]
    all_ids = {a["id"] for a in anchors}
    core_ids = {a["id"] for a in anchors if a.get("core")}

    pro_same = [e for e in evidence
                if e["side"] == "pro" and e["polarity"] == "same"]
    con_opp = [e for e in evidence
               if e["side"] == "con" and e["polarity"] == "opposite"]
    pro_direct = [e for e in pro_same if e["strength"] == "direct"]
    con_direct = [e for e in con_opp if e["strength"] == "direct"]

    pro_rank = max((RANK[e["strength"]] for e in pro_same), default=0)
    con_rank = max((RANK[e["strength"]] for e in con_opp), default=0)

    def union_covers(evs):
        s = set()
        for e in evs:
            s.update(e.get("covers") or [])
        return s

    pro_covers = union_covers(pro_same)
    condir_covers = union_covers(con_direct)
    pro_full = bool(pro_direct) and all_ids <= pro_covers
    con_core = bool(con_direct) and core_ids <= condir_covers

    conflict_pairs = []
    for ep in pro_direct:
        for ec in con_direct:
            shared = sorted(set(ep.get("covers") or [])
                            & set(ec.get("covers") or []))
            if shared:
                conflict_pairs.append({
                    "pro_evidence": ep["evidence_id"],
                    "con_evidence": ec["evidence_id"],
                    "shared_anchors": shared,
                })
    conflict = bool(conflict_pairs)

    steps.append("S1 证据分组: pro_same=%d (direct=%d), con_opp=%d (direct=%d)"
                 % (len(pro_same), len(pro_direct),
                    len(con_opp), len(con_direct)))
    steps.append("S2 强度: pro_rank=%d, con_rank=%d (direct=3/indirect=2/topical=1)"
                 % (pro_rank, con_rank))
    steps.append("S3 覆盖: 锚点全集=%s, 核心锚点=%s; pro 覆盖=%s → pro_full=%s; "
                 "con_direct 覆盖=%s → con_core=%s" % (
                     sorted(all_ids), sorted(core_ids), sorted(pro_covers),
                     pro_full, sorted(condir_covers), con_core))
    steps.append("S4 冲突: conflict=%s（pro_direct × con_direct 锚点重叠对 %d 组）"
                 % (conflict, len(conflict_pairs)))

    # ---- 决策树 R1–R6（顺序求值，先命中先生效）----
    rule = None
    if not evidence:
        base, rule = "insufficient_evidence", "R1"
    elif pro_full and not con_core:
        base, rule = "supported", "R2"
    elif con_core and not pro_full and con_rank >= pro_rank:
        base, rule = "contradicted", "R3"
    elif pro_full and con_core:
        base, rule = "supported", "R4"  # 对撞基准档，通常经 R7 降级
    elif pro_same and (pro_rank >= 2 or pro_direct):
        base, rule = "partially_supported", "R5"
    else:
        base, rule = "insufficient_evidence", "R6"
    steps.append("S5 命中规则 %s → 基准判定 base=%s" % (rule, base))

    verdict = base
    downgraded = False
    if conflict:
        verdict = DOWNGRADE[base]
        downgraded = verdict != base
        steps.append("S6 R7 冲突降级: %s → %s" % (base, verdict))
    else:
        steps.append("S6 R7 不适用（无 direct 对撞），verdict=base=%s" % verdict)

    if rule == "R6" and pro_same:
        steps.append("S7 备注: 存在 pro 证据但最高仅 topical —— 主题相关≠支持，"
                     "按 R6 判 insufficient_evidence")
    elif rule == "R5" and pro_direct and not pro_full:
        uncovered = sorted(all_ids - pro_covers)
        steps.append("S7 备注: direct 证据未覆盖锚点 %s → 按 R5 降半档" % uncovered)

    anchor_table = []
    covered_by = {}
    for e in evidence:
        for aid in (e.get("covers") or []):
            covered_by.setdefault(aid, []).append(
                "%s(%s/%s/%s)" % (e["evidence_id"], e["side"],
                                  e["strength"], e["polarity"]))
    for a in anchors:
        anchor_table.append({
            "anchor_id": a["id"],
            "type": a["type"],
            "text": a["text"],
            "core": bool(a.get("core")),
            "covered": a["id"] in covered_by,
            "covered_by": covered_by.get(a["id"], []),
        })

    reasons = [
        "%s → base=%s" % (rule, base),
        "pro_full=%s (PRO_D=%d, 覆盖 %d/%d 锚点)" % (
            pro_full, len(pro_direct), len(pro_covers & all_ids), len(all_ids)),
        "con_core=%s (CON_D=%d, 核心锚点覆盖 %d/%d)" % (
            con_core, len(con_direct), len(condir_covers & core_ids),
            len(core_ids)),
    ]
    if conflict:
        reasons.append("R7 conflict 降级: %s → %s（对撞 %d 组）" % (
            base, verdict, len(conflict_pairs)))

    adjudication = {
        "verdict": verdict,
        "base_verdict": base,
        "base_rule": rule,
        "downgraded": downgraded,
        "conflict": conflict,
        "conflict_pairs": conflict_pairs,
        "anchor_table": anchor_table,
        "reasons": reasons,
        "engine": "verdict_engine.py v%s" % ENGINE_VERSION,
        "rules_doc": "references/verdict-rules.md",
    }
    return adjudication, steps


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="按公开规则（references/verdict-rules.md）从证据台账确定性计算四级判定。")
    ap.add_argument("ledgers", nargs="+", help="台账 JSON 文件或目录")
    ap.add_argument("--explain", action="store_true", help="打印逐步推导")
    ap.add_argument("--update", action="store_true",
                    help="把 adjudication 写回台账文件")
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="以 JSON 汇总输出")
    args = ap.parse_args(argv)

    results = []
    rc = 0
    for path in iter_ledger_paths(args.ledgers):
        try:
            with open(path, "r", encoding="utf-8") as f:
                ledger = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print("ERROR: 无法读取 %s: %s" % (path, e), file=sys.stderr)
            return 2
        errs = check_minimal_schema(ledger)
        if errs:
            for e_ in errs:
                print("ERROR [%s] %s" % (os.path.basename(path), e_),
                      file=sys.stderr)
            print("ERROR [%s] 台账存在 schema 错误，裁决被阻塞"
                  "（请先通过 ledger_validate.py 修正）"
                  % os.path.basename(path), file=sys.stderr)
            rc = 1
            continue
        adj, steps = adjudicate(ledger)
        results.append({"claim_id": ledger.get("claim_id"),
                        "verdict": adj["verdict"],
                        "base_verdict": adj["base_verdict"],
                        "base_rule": adj["base_rule"],
                        "conflict": adj["conflict"]})
        if args.explain:
            print("=" * 70)
            print("CLAIM %s: %s" % (ledger.get("claim_id"),
                                      ledger.get("claim_text", "")[:80]))
            for s in steps:
                print("  " + s)
            print("  ⇒ VERDICT: %s (base=%s via %s, conflict=%s)" % (
                adj["verdict"], adj["base_verdict"], adj["base_rule"],
                adj["conflict"]))
        else:
            print("%s\tverdict=%s\tbase=%s(%s)\tconflict=%s" % (
                ledger.get("claim_id"), adj["verdict"], adj["base_verdict"],
                adj["base_rule"], adj["conflict"]))
        if args.update:
            ledger["adjudication"] = adj
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(ledger, f, ensure_ascii=False, indent=2)
            except OSError as e:
                print("ERROR: 写回 %s 失败: %s" % (path, e), file=sys.stderr)
                return 2
    if args.as_json:
        print(json.dumps({"results": results,
                          "engine": "verdict_engine.py v%s" % ENGINE_VERSION},
                         ensure_ascii=False, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())
