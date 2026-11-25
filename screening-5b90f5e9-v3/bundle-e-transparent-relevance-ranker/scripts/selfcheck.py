#!/usr/bin/env python3
"""selfcheck.py — 终检：合同齐备、分数可复算、锚定可复验、分档自洽。

检查项：
  1. result.json 存在可解析；case_id 非 null；output_contract 全部字段存在；
     sources / uncertainty / change_records 非空。
  2. 分数复算：用 records.json + anchors.json + config 重新计算全部总分，
     与 scores.json 完全一致（确定性回放）。
  3. 分解自洽：每条记录 total = 覆盖小计 + 时效 + 类型 - 多样性（逐项复核）。
  4. 锚定复验：每个命中片段按 (record_id, field, start, end) 在规范化原文中
     重新切片，必须等于规范化后的 term（片段真实可追溯）。
  5. 分档自洽：tier 与阈值一致；tie_group 内分数确实相等。
  6. sensitivity.json 存在且含 rank_instability 键。

退出码：0 全部通过；2 有警告；3 有失败项。
"""
import argparse
import sys
from pathlib import Path

from common_lib import (default_config_path, eprint, load_config, load_json,
                        norm_text, round_score)
from score_records import compute_scores

FAILED = []
WARNED = []


def check(name, ok, detail="", warn_only=False):
    tag = "PASS" if ok else ("WARN" if warn_only else "FAIL")
    print(f"[selfcheck] {tag} {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        (WARNED if warn_only else FAILED).append(name)
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description="终检")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    ap.add_argument("--config", default=default_config_path())
    args = ap.parse_args(argv)

    work, out_dir = Path(args.work), Path(args.output_dir)
    cfg = load_config(args.config)
    dec = int(cfg.get("rounding_decimals", 4))

    # 1. 合同与通用字段
    result_path = out_dir / "result.json"
    if not check("result.json 存在", result_path.exists()):
        return 3
    result = load_json(result_path)
    summary = load_json(work / "case_summary.json")
    check("case_id 非 null", result.get("case_id") is not None,
          f"case_id={result.get('case_id')!r}")
    contract = summary.get("output_contract") or []
    missing = [f for f in contract if f not in result]
    check("output_contract 字段全部存在", not missing, f"缺失: {missing}")
    null_fields = [f for f in contract if result.get(f) is None]
    check("合同字段均非 null", not null_fields,
          f"置 null 字段: {null_fields}（应已在 uncertainty 说明）", warn_only=True)
    for key in ("sources", "uncertainty", "change_records"):
        check(f"{key} 非空", bool(result.get(key)))
    check("status 诚实", result.get("status") in ("success", "partial", "failed"),
          f"status={result.get('status')!r}")

    # 2. 确定性回放复算
    records = load_json(work / "records.json")
    anchors = load_json(work / "anchors.json")
    scores_doc = load_json(work / "scores.json")
    replay, _ = compute_scores(records, anchors, cfg)
    same = ([(s["record_id"], s["total_score"]) for s in replay]
            == [(s["record_id"], s["total_score"]) for s in scores_doc["scores"]])
    check("分数确定性回放一致", same)

    # 3. 分解自洽
    bad = []
    for s in scores_doc["scores"]:
        d = s["decomposition"]
        expect = round_score(d["coverage"]["subtotal"] + d["recency"]["points"]
                             + d["publication_type"]["points"] - d["diversity"]["penalty"], dec)
        if abs(expect - s["total_score"]) > 1e-9:
            bad.append(s["record_id"])
    check("分解自洽 total=覆盖+时效+类型-多样性", not bad, f"不一致: {bad}")

    # 4. 锚定复验：切片 == 规范化 term
    rec_by_id = {r["record_id"]: r for r in records}
    bad_hits, n_hits = [], 0
    for fname, fnode in anchors["facets"].items():
        for term, tnode in fnode["terms"].items():
            for rid, hits in tnode["hits_by_record"].items():
                rec = rec_by_id.get(rid)
                for h in hits:
                    n_hits += 1
                    hay = norm_text(rec.get(h["field"]) if rec else "")
                    if hay[h["start"]:h["end"]] != norm_text(term):
                        bad_hits.append((fname, term, rid))
    check(f"锚定复验 {n_hits} 处命中全部可复验", not bad_hits, f"失败: {bad_hits[:3]}")
    zero_terms = [t for fn in anchors["facets"].values() for t, tn in fn["terms"].items()
                  if tn["corpus_hit_count"] == 0]
    check("无零命中 facet 词", not zero_terms and not anchors.get("anchor_failures"))

    # 5. 分档与并列
    tiers = load_json(work / "tiers.json")
    tc = cfg["tiers"]
    bad_tier = [e["record_id"] for e in tiers["ranked"]
                if e["tier"] != ("high" if e["total_score"] >= float(tc["high_min"])
                                 else "medium" if e["total_score"] >= float(tc["medium_min"])
                                 else "low")]
    check("tier 与阈值一致", not bad_tier, f"不一致: {bad_tier}")
    bad_tie = []
    for g in tiers["tie_groups"]:
        vals = {e["total_score"] for e in tiers["ranked"] if e["record_id"] in g["members"]}
        if len(vals) != 1:
            bad_tie.append(g["tie_group"])
    check("tie_group 内分数相等", not bad_tie, f"异常: {bad_tie}")

    # 6. 敏感性产物
    sens_path = work / "sensitivity.json"
    sens = load_json(sens_path) if sens_path.exists() else None
    check("sensitivity.json 存在且含 rank_instability",
          bool(sens) and "rank_instability" in sens)

    print(f"[selfcheck] 结束: {'FAIL ' + str(len(FAILED)) if FAILED else ('WARN ' + str(len(WARNED)) if WARNED else 'ALL PASS')}")
    return 3 if FAILED else (2 if WARNED else 0)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        eprint(f"[selfcheck] 未预期异常: {exc!r}")
        sys.exit(3)
