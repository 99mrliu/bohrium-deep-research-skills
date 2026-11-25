#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claim_align.py — 两个权利要求切分结果的要素级对齐（仅用 Python 标准库 difflib）。

输入：claim_segment.py 生成的两份切分 JSON（版本 A 与版本 B）。
方法：
  1. 权利要求先按编号配对；未配对的记为整项 新增/删除；
  2. 每对权利要求内部，对 preamble/transition/elements 做贪婪最优相似度配对，
     相似度为 difflib.SequenceMatcher 在归一化文本上的 ratio；
  3. 相似度 < 阈值（默认 0.60，可用 --threshold 调整）的候选配对只列入
     candidates，绝不强制配对；
  4. 归一化文本完全一致 -> unchanged；配对成功但文本不同 -> modified；
     配对成功且文本一致但相对次序变化 -> reordered；
     A 侧未配对 -> removed；B 侧未配对 -> added；
  5. statistics 一律由本脚本根据生成的对应表重新统计，不信任调用方计数；
  6. 仅提供 --a 时输出单侧清单（one_sided_inventory），status 恒为 partial；
     任一侧切分降级或跨越 OCR 合并边界时，status 亦为 partial 并在 limits
     中说明具体位置。

退出码：0 = 正常完成（含 partial）；2 = 用法/输入错误。
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys

TOOL = "claim_align.py"
VERSION = "1.0.0"
DEFAULT_THRESHOLD = 0.60


def norm(s: str) -> str:
    return " ".join(s.lower().split())


def sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def collect_items(claim: dict):
    items = []
    if claim.get("preamble"):
        items.append(
            {
                "kind": "preamble",
                "index": 0,
                "span": claim["preamble"]["span"],
                "quote": claim["preamble"]["quote"],
            }
        )
    if claim.get("transition"):
        items.append(
            {
                "kind": "transition",
                "index": 0,
                "span": claim["transition"]["span"],
                "quote": claim["transition"]["quote"],
            }
        )
    for el in claim.get("elements", []):
        items.append(
            {"kind": el["kind"], "index": el["index"], "span": el["span"], "quote": el["quote"]}
        )
    return items


def align_items(items_a, items_b, threshold):
    """贪婪最优相似度配对；返回 (element_pairs, candidates)。"""
    scored = []
    for i, ia in enumerate(items_a):
        for j, ib in enumerate(items_b):
            r = sim(norm(ia["quote"]), norm(ib["quote"]))
            scored.append((r, i, j))
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))

    used_a, used_b = set(), set()
    pairs = []
    for r, i, j in scored:
        if r < threshold:
            break
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        cls = "unchanged" if norm(items_a[i]["quote"]) == norm(items_b[j]["quote"]) else "modified"
        pairs.append(
            {
                "i": i,
                "j": j,
                "similarity": round(r, 4),
                "classification": cls,
                "reordered": False,
            }
        )

    # 重排检测：按 A 侧顺序排列后，B 侧序号的相对次序若变化则标记。
    pairs_sorted = sorted(pairs, key=lambda p: p["i"])
    b_rank = {j: k for k, j in enumerate(sorted(p["j"] for p in pairs_sorted))}
    for k, p in enumerate(pairs_sorted):
        if b_rank[p["j"]] != k:
            p["reordered"] = True
            if p["classification"] == "unchanged":
                p["classification"] = "reordered"

    # 低于阈值的最佳候选：只列出，不强制配对。
    candidates = []
    for i, ia in enumerate(items_a):
        if i in used_a:
            continue
        best = None
        for j, ib in enumerate(items_b):
            if j in used_b:
                continue
            r = sim(norm(ia["quote"]), norm(ib["quote"]))
            if best is None or r > best[0]:
                best = (r, j)
        if best is not None and best[0] > 0.0:
            candidates.append(
                {
                    "i": i,
                    "j": best[1],
                    "similarity": round(best[0], 4),
                    "note": "below_threshold_not_forced",
                }
            )

    def _side(items, idx):
        it = items[idx]
        return {"kind": it["kind"], "index": it["index"], "span": it["span"], "quote": it["quote"]}

    element_pairs = []
    for p in pairs_sorted:
        element_pairs.append(
            {
                "classification": p["classification"],
                "similarity": p["similarity"],
                "reordered": p["reordered"],
                "a": _side(items_a, p["i"]),
                "b": _side(items_b, p["j"]),
            }
        )
    for i, ia in enumerate(items_a):
        if i not in used_a:
            element_pairs.append(
                {
                    "classification": "removed",
                    "similarity": None,
                    "reordered": False,
                    "a": _side(items_a, i),
                    "b": None,
                }
            )
    for j, ib in enumerate(items_b):
        if j not in used_b:
            element_pairs.append(
                {
                    "classification": "added",
                    "similarity": None,
                    "reordered": False,
                    "a": None,
                    "b": _side(items_b, j),
                }
            )

    cand_out = [
        {
            "similarity": c["similarity"],
            "note": c["note"],
            "a": _side(items_a, c["i"]),
            "b": _side(items_b, c["j"]),
        }
        for c in candidates
    ]
    return element_pairs, cand_out


def _claim_brief(claim):
    return {"number": claim["number"], "span": claim["span"], "quote": claim["quote"]}


def build_one_sided(seg_a: dict) -> dict:
    limits = ["仅提供单一版本（缺少 --b）：未执行双版本比对，以下为单侧清单。"]
    if seg_a.get("segmentation_degraded"):
        limits.append("版本 A 的切分结果为降级（segmentation_degraded=true）；详见其 notes。")
    for c in seg_a.get("claims", []):
        if c.get("crosses_ocr_boundary"):
            limits.append(
                "权利要求 %s 的 span %s 跨越已声明的 OCR 合并边界；边界偏移见版本 A 的 ocr_boundaries。"
                % (c["number"], c["span"])
            )
    inventory = []
    for c in seg_a.get("claims", []):
        inventory.append(
            {
                "number": c["number"],
                "type": c["type"],
                "references": c["references"],
                "span": c["span"],
                "quote": c["quote"],
                "items": collect_items(c),
            }
        )
    table = {
        "tool": TOOL,
        "tool_version": VERSION,
        "mode": "one_sided_inventory",
        "status": "partial",
        "limits": limits,
        "threshold": None,
        "a": {"source_path": seg_a.get("source_path"), "text_sha256": seg_a.get("text_sha256")},
        "b": None,
        "claim_pairs": [],
        "claims_added": [],
        "claims_removed": [],
        "one_sided_claims": inventory,
        "statistics": {
            "claims_a": len(seg_a.get("claims", [])),
            "claims_b": 0,
            "claim_pairs": 0,
            "element_pairs": {"unchanged": 0, "modified": 0, "added": 0, "removed": 0, "reordered": 0},
        },
    }
    return table


def build_two_sided(seg_a: dict, seg_b: dict, threshold: float) -> dict:
    limits = []
    if seg_a.get("segmentation_degraded"):
        limits.append("版本 A 切分降级（segmentation_degraded=true）；相关区域仅保留原文。")
    if seg_b.get("segmentation_degraded"):
        limits.append("版本 B 切分降级（segmentation_degraded=true）；相关区域仅保留原文。")
    for tag, seg in (("A", seg_a), ("B", seg_b)):
        for c in seg.get("claims", []):
            if c.get("crosses_ocr_boundary"):
                limits.append(
                    "版本 %s 权利要求 %s 的 span %s 跨越已声明的 OCR 合并边界；该处比对仅为部分结果。"
                    % (tag, c["number"], c["span"])
                )

    by_num_a = {c["number"]: c for c in seg_a.get("claims", [])}
    by_num_b = {c["number"]: c for c in seg_b.get("claims", [])}
    nums_a = sorted(by_num_a)
    nums_b = sorted(by_num_b)

    claim_pairs = []
    for n in nums_a:
        if n in by_num_b:
            ca, cb = by_num_a[n], by_num_b[n]
            eps, cands = align_items(collect_items(ca), collect_items(cb), threshold)
            claim_pairs.append(
                {
                    "number_a": ca["number"],
                    "number_b": cb["number"],
                    "type_a": ca["type"],
                    "type_b": cb["type"],
                    "pair_status": "aligned",
                    "element_pairs": eps,
                    "candidates": cands,
                }
            )
    claims_removed = [_claim_brief(by_num_a[n]) for n in nums_a if n not in by_num_b]
    claims_added = [_claim_brief(by_num_b[n]) for n in nums_b if n not in nums_a]

    # statistics 一律按已生成的对应表现场重算。
    ep_stats = {"unchanged": 0, "modified": 0, "added": 0, "removed": 0, "reordered": 0}
    for cp in claim_pairs:
        for ep in cp["element_pairs"]:
            ep_stats[ep["classification"]] += 1
    stats = {
        "claims_a": len(nums_a),
        "claims_b": len(nums_b),
        "claim_pairs": len(claim_pairs),
        "claims_added": len(claims_added),
        "claims_removed": len(claims_removed),
        "element_pairs": ep_stats,
    }

    status = "partial" if limits else "ok"
    return {
        "tool": TOOL,
        "tool_version": VERSION,
        "mode": "two_version",
        "status": status,
        "limits": limits,
        "threshold": threshold,
        "a": {"source_path": seg_a.get("source_path"), "text_sha256": seg_a.get("text_sha256")},
        "b": {"source_path": seg_b.get("source_path"), "text_sha256": seg_b.get("text_sha256")},
        "claim_pairs": claim_pairs,
        "claims_added": claims_added,
        "claims_removed": claims_removed,
        "one_sided_claims": [],
        "statistics": stats,
    }


def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise ValueError("无法读取文件 %s：%s" % (path, exc))
    except json.JSONDecodeError as exc:
        raise ValueError("文件 %s 不是合法 JSON：%s" % (path, exc))
    if not isinstance(data, dict) or "claims" not in data:
        raise ValueError("文件 %s 不是 claim_segment.py 生成的切分 JSON（缺少 claims 键）。" % path)
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="两个权利要求版本的要素级对齐（贪婪最优相似度 + difflib，阈值可声明）。"
    )
    ap.add_argument("--a", required=True, help="版本 A 的切分 JSON（claim_segment.py 输出）。")
    ap.add_argument("--b", default=None, help="版本 B 的切分 JSON；缺省时输出单侧清单。")
    ap.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="配对相似度阈值（0~1，默认 %(default)s）；低于阈值的配对只列为候选。",
    )
    ap.add_argument("--output", default=None, help="输出 JSON 路径；缺省写到标准输出。")
    args = ap.parse_args(argv)

    if not (0.0 < args.threshold <= 1.0):
        print("用法错误：--threshold 必须在 (0, 1] 区间内。", file=sys.stderr)
        return 2

    try:
        seg_a = _load(args.a)
        seg_b = _load(args.b) if args.b else None
    except ValueError as exc:
        print("用法/输入错误：%s" % exc, file=sys.stderr)
        return 2

    if seg_b is None:
        table = build_one_sided(seg_a)
    else:
        table = build_two_sided(seg_a, seg_b, args.threshold)

    payload = json.dumps(table, ensure_ascii=False, indent=2)
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(payload + "\n")
        except OSError as exc:
            print("用法/输入错误：无法写入输出文件 %s：%s" % (args.output, exc), file=sys.stderr)
            return 2
    else:
        sys.stdout.write(payload + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
