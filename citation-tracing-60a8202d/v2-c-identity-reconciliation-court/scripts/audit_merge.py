#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_merge.py — 交付前自查（第三步）。

检查项：
  1. 去重干净：任意两个实体不共享规范化 DOI，也不共享规范化标题键；
  2. 合并证据完整：多成员组的 merge_evidence 含成对打分与裁决理由，
     且每个成员都有 locator（file + pointer）；冲突字段未丢失；
  3. 存疑队列交代：review_queue 非空时，result.json 的 uncertainty 中有明确说明；
  4. 残缺记录交代：flags 含 incomplete_record 的实体在 uncertainty 中说明；
  5. 契约镜像：result.json 含 case_id 与 case.json output_contract 的全部字段。

输出：逐检查 ok=true/false 与总判定；退出码 0 表示全部通过。
"""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from identity_merge import norm_doi, norm_title  # noqa: E402


def check_unique_ids(entities, ledger):
    doi_owner, title_owner = {}, {}
    problems = []
    # 台账已标注的「同名不同文」对：标题键共享为合法情形
    dst_entity_pairs = set()
    dst_map = {g["entity_id"]: set(g.get("members") or []) for g in ledger.get("groups", [])}
    rec2ent = {rid: eid for eid, rids in dst_map.items() for rid in rids}
    for d in ledger.get("distinct_same_title", []) or []:
        ea, eb = rec2ent.get(d.get("rec_a")), rec2ent.get(d.get("rec_b"))
        if ea and eb:
            dst_entity_pairs.add(frozenset((ea, eb)))
    for e in entities:
        for d in e.get("dois") or []:
            nd = norm_doi(d)
            if not nd:
                continue
            if nd in doi_owner:
                problems.append(f"DOI 冲突：{nd} 同时属于 {doi_owner[nd]} 与 {e['entity_id']}")
            else:
                doi_owner[nd] = e["entity_id"]
        for m in e.get("members") or []:
            for t in {norm_title(m.get("title")), norm_title(e.get("title"))}:
                if not t:
                    continue
                if t in title_owner and title_owner[t] != e["entity_id"]:
                    if frozenset((title_owner[t], e["entity_id"])) not in dst_entity_pairs:
                        problems.append(f"标题键共享且未被台账标注为同名不同文：{t[:40]}… 由 "
                                        f"{title_owner[t]} 与 {e['entity_id']} 共享")
                else:
                    title_owner[t] = e["entity_id"]
    return not problems, problems


def check_merge_evidence(entities):
    problems = []
    for e in entities:
        if e.get("member_count", 1) <= 1:
            continue
        ev = e.get("merge_evidence") or {}
        if ev.get("singleton"):
            problems.append(f"{e['entity_id']} 是多成员组却标注 singleton")
        if not ev.get("pair_scores"):
            problems.append(f"{e['entity_id']} 缺少成对打分 pair_scores")
        if not ev.get("reasons"):
            problems.append(f"{e['entity_id']} 缺少裁决理由 reasons")
        for m in e.get("members") or []:
            loc = m.get("locator") or {}
            if not loc.get("file") or not loc.get("pointer"):
                problems.append(f"{e['entity_id']} 成员 {m.get('rec_id')} 缺 locator")
        if e.get("member_count", 1) > 1 and not any(m.get("title") for m in e.get("members") or []):
            problems.append(f"{e['entity_id']} 成员全部无标题（身份证据不足）")
    return not problems, problems


def check_ledger_consistency(entities, ledger):
    problems = []
    member_count = {e["entity_id"]: len(e.get("members") or []) for e in entities}
    ledger_counts = {g["entity_id"]: len(g.get("members") or []) for g in ledger.get("groups", [])}
    if member_count != ledger_counts:
        problems.append(f"entities.jsonl 与 merge_ledger.json 的组/成员数不一致："
                        f"{member_count} vs {ledger_counts}")
    return not problems, problems


def check_uncertainty_coverage(result, entities, ledger):
    problems = []
    unc = json.dumps(result.get("uncertainty") or [], ensure_ascii=False)
    if ledger.get("review_queue") and "review_queue" not in unc:
        problems.append("review_queue 非空但 result.json uncertainty 未交代")
    incomplete = [e["entity_id"] for e in entities if "incomplete_record" in (e.get("flags") or [])]
    if incomplete and "残缺" not in unc:
        problems.append("存在残缺记录但 result.json uncertainty 未交代")
    if result.get("status") == "ok" and not result.get("candidates"):
        problems.append("status=ok 但 candidates 为空")
    if not result.get("case_id") or result.get("case_id") == "unknown-case":
        problems.append("result.json 缺有效 case_id")
    return not problems, problems


def check_contract(result, case):
    problems = []
    contract = case.get("output_contract") or {}
    if not isinstance(contract, dict) or not contract:
        return True, ["case.json 无 output_contract，跳过契约镜像检查"]
    for key in contract:
        if key not in result:
            problems.append(f"result.json 缺 output_contract 字段: {key}")
    return not problems, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description="身份合并交付自查")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    args = ap.parse_args(argv)

    results = []
    entities = []
    ent_path = Path(args.workdir) / "entities.jsonl"
    if ent_path.exists():
        for line in ent_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entities.append(json.loads(line))
    else:
        results.append(("entities_exists", False, [f"缺少 {ent_path}"]))

    ledger = {}
    led_path = Path(args.workdir) / "merge_ledger.json"
    if led_path.exists():
        ledger = json.loads(led_path.read_text(encoding="utf-8"))

    result = {}
    res_path = Path(args.out) / "result.json"
    if res_path.exists():
        result = json.loads(res_path.read_text(encoding="utf-8"))
    else:
        results.append(("result_exists", False, [f"缺少 {res_path}"]))

    case = {}
    case_path = Path(args.case)
    if case_path.exists():
        case = json.loads(case_path.read_text(encoding="utf-8"))
    else:
        results.append(("case_exists", False, [f"缺少 {case_path}（契约镜像检查跳过）"]))

    if ent_path.exists():
        ok, probs = check_unique_ids(entities, ledger)
        results.append(("unique_doi_and_title_keys", ok, probs))
        ok, probs = check_merge_evidence(entities)
        results.append(("merge_evidence_complete", ok, probs))
        ok, probs = check_ledger_consistency(entities, ledger)
        results.append(("ledger_consistency", ok, probs))
    if res_path.exists() and ent_path.exists():
        ok, probs = check_uncertainty_coverage(result, entities, ledger)
        results.append(("uncertainty_coverage", ok, probs))
    if res_path.exists() and case_path.exists():
        ok, probs = check_contract(result, case)
        results.append(("contract_mirror", ok, probs))

    overall = all(ok for _, ok, _ in results) and bool(results)
    report = {
        "ok": overall,
        "checks": [
            {"check": name, "ok": ok, "problems": probs}
            for name, ok, probs in results
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
