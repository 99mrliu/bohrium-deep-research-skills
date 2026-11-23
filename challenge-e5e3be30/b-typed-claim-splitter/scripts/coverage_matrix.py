#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
coverage_matrix.py — 覆盖矩阵与遗漏/重叠机检（纯标准库）

输入 cue_scan.py 产出的 atoms.json，对每条论断：
  1. 构建 子判断 × 槽位 覆盖矩阵（1 = 该子判断认领该槽位）；
  2. 机检遗漏（omission）：任何槽位未被任何子判断认领 → 拆漏了，必须返工，exit 1；
  3. 机检重叠（overlap）：两个子判断 covers 完全相同槽位集且谓词主干相同
     （谓词主干取 atom.predicate_stem，缺失时用最长大中文串/英文单词启发式重算）
     → 只警告，不阻断；
  4. 一致性交叉检查：槽位字符位置落在某子判断区间内但未被其 covers_slots 认领，
     记为 mapping_mismatch（视为遗漏的预警，计入 omission）；
  5. 不可判定项提示：无槽位、无谓词线索的 fact 子判断，其边界需人工确认。

退出码：0 通过（可有 overlap 警告）；1 存在 omission（必须返工）；2 输入/运行错误。

用法：
  python3 coverage_matrix.py --atoms atoms.json [--out report.json]
  python3 coverage_matrix.py --help
"""
import argparse
import json
import re
import sys


def stem_of(atom):
    stem = atom.get("predicate_stem")
    if stem:
        return stem
    text = atom.get("text", "")
    runs = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    if runs:
        return max(runs, key=len)
    words = re.findall(r"[A-Za-z]{3,}", text)
    return max(words, key=len) if words else text.strip()[:16]


def check_claim(claim):
    claim_id = claim.get("id", "?")
    slots = claim.get("slots", [])
    atoms = claim.get("atoms", [])
    slot_ids = [s["slot_id"] for s in slots]
    known = set(slot_ids)

    covered = {}
    for a in atoms:
        for sid in a.get("covers_slots", []):
            covered.setdefault(sid, []).append(a["atom_id"])

    omissions, mismatch_notes, infos, overlaps = [], [], [], []

    # 1) 遗漏：槽位无人认领
    for s in slots:
        if s["slot_id"] not in covered:
            omissions.append({
                "slot_id": s["slot_id"], "category": s["category"], "text": s["text"],
                "reason": "槽位未被任何子判断认领（拆解遗漏，必须返工）",
            })

    # 2) 交叉检查：区间包含但未认领
    for s in slots:
        for a in atoms:
            span = a.get("span", [0, 0])
            if span[0] <= s["start"] and s["end"] <= span[1]:
                if s["slot_id"] not in a.get("covers_slots", []):
                    mismatch_notes.append(
                        "槽位 %s 位于子判断 %s 区间 [%d,%d) 内但未列入其 covers_slots" % (
                            s["slot_id"], a["atom_id"], span[0], span[1]))
                    if s["slot_id"] not in covered:
                        pass  # 已计入 omissions
                    else:
                        omissions.append({
                            "slot_id": s["slot_id"], "category": s["category"], "text": s["text"],
                            "reason": "区间归属与 covers_slots 不一致（mapping_mismatch）",
                        })
    # covers_slots 引用了不存在的槽位
    for a in atoms:
        for sid in a.get("covers_slots", []):
            if sid not in known:
                infos.append("子判断 %s 认领了不存在的槽位 %s（atoms.json 可能被手工改坏）"
                             % (a["atom_id"], sid))

    # 3) 重叠：covers 集合完全相同 且 谓词主干相同
    for i in range(len(atoms)):
        for j in range(i + 1, len(atoms)):
            a, b = atoms[i], atoms[j]
            if set(a.get("covers_slots", [])) == set(b.get("covers_slots", [])) \
                    and stem_of(a) == stem_of(b):
                overlaps.append({
                    "atoms": [a["atom_id"], b["atom_id"]],
                    "shared_slots": sorted(set(a.get("covers_slots", []))),
                    "predicate_stem": stem_of(a),
                    "reason": "两个子判断覆盖相同槽位集且谓词主干相同，疑似重复核验或循环论证",
                })

    # 4) 不可判定项提示
    for a in atoms:
        if a.get("type") == "fact" and not a.get("covers_slots"):
            infos.append("子判断 %s 无任何线索槽位且类型为 fact：边界与谓词需人工确认。" % a["atom_id"])

    matrix_rows = []
    for a in atoms:
        row = {"atom_id": a["atom_id"], "type": a.get("type"), "predicate_stem": stem_of(a)}
        for s in slots:
            row[s["slot_id"]] = 1 if s["slot_id"] in a.get("covers_slots", []) else 0
        matrix_rows.append(row)

    return {
        "claim_id": claim_id,
        "n_slots": len(slots),
        "n_atoms": len(atoms),
        "matrix": {"slot_order": slot_ids, "rows": matrix_rows},
        "omissions": omissions,
        "overlaps": overlaps,
        "mismatch_notes": mismatch_notes,
        "infos": infos,
        "passed": not omissions,
    }


def print_matrix(rep):
    slot_order = rep["matrix"]["slot_order"]
    header = ["atom_id", "type"] + [s.split("#")[-1] for s in slot_order]
    print("\n论断 %s：覆盖矩阵（子判断 × 槽位）" % rep["claim_id"])
    print("  " + " | ".join("%-14s" % h for h in header))
    for row in rep["matrix"]["rows"]:
        cells = ["%-14s" % row["atom_id"], "%-14s" % row["type"]]
        for s in slot_order:
            cells.append("%-14s" % ("1" if row[s] else "."))
        print("  " + " | ".join(cells))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="覆盖矩阵与遗漏/重叠机检。输入 atoms.json，输出机检报告。有 omission 时 exit 1。")
    ap.add_argument("--atoms", required=True, help="cue_scan.py 产出的 atoms.json 路径")
    ap.add_argument("--out", default=None, help="机检报告 JSON 输出路径（默认仅打印摘要到标准输出）")
    args = ap.parse_args(argv)

    try:
        with open(args.atoms, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("错误：无法读取 atoms.json：%s" % e, file=sys.stderr)
        return 2
    if not isinstance(data, dict) or not isinstance(data.get("claims"), list):
        print("错误：atoms.json 结构不符（应为含 claims 数组的对象）。", file=sys.stderr)
        return 2

    reports = [check_claim(c) for c in data["claims"]]
    n_omit = sum(len(r["omissions"]) for r in reports)
    n_overlap = sum(len(r["overlaps"]) for r in reports)

    for r in reports:
        print_matrix(r)
        for o in r["omissions"]:
            print("  [OMISSION] %s (%s '%s')：%s" % (o["slot_id"], o["category"], o["text"], o["reason"]))
        for ov in r["overlaps"]:
            print("  [OVERLAP-警告] %s 与 %s：谓词主干 '%s'，共享槽位 %s"
                  % (ov["atoms"][0], ov["atoms"][1], ov["predicate_stem"], ov["shared_slots"]))
        for msg in r["infos"]:
            print("  [INFO] %s" % msg)
        print("  → %s" % ("通过" if r["passed"] else "未通过：存在遗漏，拆解必须返工"))

    print("\n总计：%d 条论断，omission=%d，overlap 警告=%d" % (len(reports), n_omit, n_overlap))
    report = {"meta": {"tool": "coverage_matrix.py", "version": "1.0.0"},
              "summary": {"claims": len(reports), "omissions": n_omit, "overlaps": n_overlap,
                          "passed": n_omit == 0},
              "claims": reports}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("报告已写入 %s" % args.out)
    return 1 if n_omit else 0


if __name__ == "__main__":
    sys.exit(main())
