#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adjudicate.py — 校验模型仲裁记录并生成终判标签与计数。

用法:
    python3 adjudicate.py [--work /app/work] [--arb /app/work/arbitrations.json]

输入:
    <work>/disagreements.json     分歧清单（agreement.py 产物）
    <work>/arbitrations.json      模型仲裁记录，逐条 {record_id, final_decision,
      disagreement_type(D1-D4), arbitration_basis, criteria_interpretation(D1必填),
      evidence_quote(可选)}

校验（任一失败 exit 3）:
    1. 每条分歧都有且仅有一条仲裁；
    2. disagreement_type ∈ {D1,D2,D3,D4}；
    3. arbitration_basis 非空，且含锚定引用（evidence_quote 锚定 / basis 中 >=8 字符
       片段命中题录）或明确的元数据缺失声明（缺失/未提供/无摘要/missing 等）；
    4. D1 型必须给出 criteria_interpretation，供全批一致适用。

输出:
    <work>/final_labels.jsonl  全部筛选记录终判 {record_id, final_decision
      (include/exclude/needs_human), source(agreement/arbitration), reason_code,
      evidence_quote, human_confirmation_required, note}
    <work>/final_counts.json   {screened, included, excluded, needs_human}

人工确认门（rules/human_gates.md）: D3 型 / basis 声明元数据缺失 / 最终 uncertain /
记录 abstract_missing → final_decision 一律记为 needs_human 且
human_confirmation_required=true；这些是「待复核建议」，绝不伪造人工复核结论。

退出码: 0=成功, 2=用法或IO错误, 3=校验失败
"""
import argparse
import json
import re
import sys
import traceback
import unicodedata
from pathlib import Path

TYPES = {"D1", "D2", "D3", "D4"}
DECISIONS = {"include", "exclude", "uncertain", "needs_human"}
MISSING_KEYS = ("缺失", "未提供", "无摘要", "摘要为空", "信息不足", "missing",
                "not provided", "no abstract", "empty abstract", "unavailable")


def eprint(*a):
    print(*a, file=sys.stderr)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"\s+", " ", s).strip()


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def declares_missing(text: str) -> bool:
    low = (text or "").lower()
    return any(k in low or k in (text or "") for k in MISSING_KEYS)


def basis_anchored(arb, rec_text_norm):
    """返回 (是否通过, 方式)。"""
    basis = str(arb.get("arbitration_basis", "")).strip()
    if not basis:
        return False, "basis_empty"
    quote = str(arb.get("evidence_quote", "")).strip()
    if quote:
        return (norm(quote) in rec_text_norm), "evidence_quote"
    for seg in re.split(r"[，。；,.;、\n:：\"'“”‘’「」()（）\[\]【】]", basis):
        ns = norm(seg)
        if len(ns) >= 8 and ns in rec_text_norm:
            return True, "basis_segment"
    if declares_missing(basis):
        return True, "missing_declaration"
    return False, "no_anchor"


def main():
    ap = argparse.ArgumentParser(description="校验仲裁记录并生成终判标签与计数")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--arb", default=None)
    args = ap.parse_args()
    work = Path(args.work)

    dis_path = work / "disagreements.json"
    arb_path = Path(args.arb) if args.arb else work / "arbitrations.json"
    dedup_path = work / "records_dedup.jsonl"
    s1_path = work / "annotations_s1.jsonl"
    for p in (dis_path, arb_path, dedup_path, s1_path):
        if not p.exists():
            eprint(f"[adjudicate] 缺少 {p}")
            return 2

    disagreements = json.loads(dis_path.read_text(encoding="utf-8"))
    arbitrations = json.loads(arb_path.read_text(encoding="utf-8"))
    records = {r["record_id"]: r for r in load_jsonl(dedup_path)}
    s1 = {r["record_id"]: r for r in load_jsonl(s1_path)}
    texts = {rid: norm(r.get("title", "") + " " + r.get("abstract", ""))
             for rid, r in records.items()}

    if not isinstance(arbitrations, list):
        eprint("[adjudicate] arbitrations.json 必须是列表")
        return 3
    arb_map, errors = {}, []
    for i, a in enumerate(arbitrations, 1):
        rid = str(a.get("record_id", "")).strip()
        if rid in arb_map:
            errors.append({"record_id": rid, "error": "重复仲裁"})
        arb_map[rid] = a

    dis_ids = {d["record_id"] for d in disagreements}
    for rid in sorted(dis_ids):
        a = arb_map.get(rid)
        if a is None:
            errors.append({"record_id": rid, "error": "分歧缺少仲裁记录"})
            continue
        fd = str(a.get("final_decision", "")).strip()
        dt = str(a.get("disagreement_type", "")).strip()
        basis = str(a.get("arbitration_basis", "")).strip()
        if fd not in DECISIONS:
            errors.append({"record_id": rid, "error": f"final_decision 非法: '{fd}'"})
        if dt not in TYPES:
            errors.append({"record_id": rid, "error": f"disagreement_type 非法: '{dt}'"})
        ok, how = basis_anchored(a, texts.get(rid, ""))
        if not ok:
            errors.append({"record_id": rid,
                           "error": f"arbitration_basis 无锚定引用且无元数据缺失声明 ({how})"})
        if dt == "D1" and not str(a.get("criteria_interpretation", "")).strip():
            errors.append({"record_id": rid,
                           "error": "D1 型仲裁必须给出 criteria_interpretation"})
    extra = sorted(set(arb_map) - dis_ids)
    if extra:
        errors.append({"record_id": ",".join(extra), "error": "仲裁了不存在的分歧记录"})

    if errors:
        err_path = work / "adjudication_errors.json"
        err_path.write_text(json.dumps(errors, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        eprint(f"[adjudicate] 校验失败 {len(errors)} 处 -> {err_path}")
        return 3

    final_rows = []
    for rid in sorted(records):
        rec = records[rid]
        abs_missing = "abstract_missing" in rec.get("field_status", [])
        if rid in dis_ids:
            a = arb_map[rid]
            fd = a["final_decision"]
            human = (a["disagreement_type"] == "D3"
                     or fd in ("uncertain", "needs_human")
                     or declares_missing(str(a.get("arbitration_basis", "")))
                     or abs_missing)
            if human:
                fd = "needs_human"
            final_rows.append({
                "record_id": rid,
                "final_decision": fd,
                "source": "arbitration",
                "disagreement_type": a["disagreement_type"],
                "reason_code": f"ARB-{a['disagreement_type']}",
                "evidence_quote": str(a.get("evidence_quote", "")),
                "human_confirmation_required": bool(human),
                "note": ("待复核建议：未经人工复核确认" if human
                         else "经仲裁判定（模型仲裁，依据见 arbitration_basis）"),
            })
        else:
            a1 = s1[rid]
            fd = a1["decision"]
            human = fd == "uncertain" or (abs_missing and fd != "exclude")
            if human:
                fd = "needs_human"
            final_rows.append({
                "record_id": rid,
                "final_decision": fd,
                "source": "agreement",
                "disagreement_type": None,
                "reason_code": a1.get("reason_code", ""),
                "evidence_quote": a1.get("evidence_quote", ""),
                "human_confirmation_required": bool(human),
                "note": ("待复核建议：双方一致 uncertain 或元数据缺失，未经人工复核确认"
                         if human else "S1/S2 一致"),
            })

    counts = {
        "screened": len(final_rows),
        "included": sum(1 for r in final_rows if r["final_decision"] == "include"),
        "excluded": sum(1 for r in final_rows if r["final_decision"] == "exclude"),
        "needs_human": sum(1 for r in final_rows
                           if r["final_decision"] == "needs_human"),
        "human_confirmation_required_ids": [r["record_id"] for r in final_rows
                                            if r["human_confirmation_required"]],
    }
    with (work / "final_labels.jsonl").open("w", encoding="utf-8") as f:
        for r in final_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (work / "final_counts.json").write_text(
        json.dumps(counts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[adjudicate] 仲裁 {len(dis_ids)} 条全部通过；终判 include={counts['included']} "
          f"exclude={counts['excluded']} needs_human={counts['needs_human']}")
    print("[adjudicate] 提醒: needs_human 记录仅为待复核建议，禁止表述为已经人工复核。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        eprint("[adjudicate] 未捕获异常:")
        traceback.print_exc()
        sys.exit(2)
