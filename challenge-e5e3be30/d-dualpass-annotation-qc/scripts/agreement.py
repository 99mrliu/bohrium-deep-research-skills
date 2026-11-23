#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agreement.py — 双通道标注一致性度量。

输入两个单通道标注 JSON（顶层为数组，每元素至少含：
  claim_id (str), verdict (四值之一), evidence_pages (int 数组)；
允许额外字段如 evidence_quote / rationale，本脚本忽略之）。

计算：
  1. verdict 的 Cohen's kappa（手写实现，输出观测一致率 po 与期望一致率 pe）；
  2. 定位一致率：每条论断两通道页码集合的 Jaccard（均值），以及
     "至少一页精确重合"的论断占比（两通道均为空页码视为一致）；
  3. 逐条分歧表：verdict 分歧清单 + 页码分歧清单。

输出 agreement-report.json；stdout 打印人类可读摘要。
kappa < 0.6 时向 stderr 打印质量警告（仍 exit 0）；schema 错误 exit 1；
用法错误（argparse）exit 2。
"""
import argparse
import json
import sys
from collections import Counter

VERDICTS = ["supported", "partially_supported", "contradicted", "insufficient_evidence"]
KAPPA_WARN_THRESHOLD = 0.6


class SchemaError(Exception):
    pass


def fail(msg):
    print(f"[agreement] SCHEMA ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load_records(path, tag):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        fail(f"{tag}: 文件不存在: {path}")
    except json.JSONDecodeError as e:
        fail(f"{tag}: JSON 解析失败: {path}: {e}")
    if isinstance(data, dict) and "records" in data:  # 容忍模板外壳
        data = data["records"]
    if not isinstance(data, list):
        fail(f"{tag}: 顶层必须是标注记录数组（或含 records 数组的对象）")
    seen = set()
    out = {}
    for i, r in enumerate(data):
        where = f"{tag}[{i}]"
        if not isinstance(r, dict):
            fail(f"{where}: 记录必须是对象")
        for field in ("claim_id", "verdict", "evidence_pages"):
            if field not in r:
                fail(f"{where}: 缺少必需字段 '{field}'")
        cid = r["claim_id"]
        if not isinstance(cid, str) or not cid:
            fail(f"{where}: claim_id 必须是非空字符串")
        if cid in seen:
            fail(f"{where}: claim_id 重复: {cid}")
        seen.add(cid)
        v = r["verdict"]
        if v not in VERDICTS:
            fail(f"{where}: verdict '{v}' 非法，须为 {VERDICTS} 之一")
        pages = r["evidence_pages"]
        if not isinstance(pages, list) or any(
            not isinstance(p, int) or isinstance(p, bool) or p < 0 for p in pages
        ):
            fail(f"{where}: evidence_pages 必须是非负整数数组")
        out[cid] = {"verdict": v, "pages": sorted(set(pages))}
    return out


def cohens_kappa(pairs):
    """pairs: list of (verdict_a, verdict_b)。返回 (kappa, po, pe)。"""
    n = len(pairs)
    if n == 0:
        return None, 0.0, 0.0
    po = sum(1 for a, b in pairs if a == b) / n
    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    pe = sum((ca[v] / n) * (cb[v] / n) for v in VERDICTS)
    if pe >= 1.0:  # 两通道完全一致且单类别，kappa 无定义
        return None, po, pe
    return (po - pe) / (1.0 - pe), po, pe


def jaccard(sa, sb):
    if not sa and not sb:
        return 1.0  # 双方均未给出页码：视为定位一致（均无证据）
    union = sa | sb
    return len(sa & sb) / len(union) if union else 1.0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="双通道标注一致性度量：Cohen's kappa + 定位一致率 + 逐条分歧表。"
    )
    ap.add_argument("pass_a", help="Pass A 标注 JSON 路径")
    ap.add_argument("pass_b", help="Pass B 标注 JSON 路径")
    ap.add_argument("-o", "--output", default="agreement-report.json",
                    help="输出报告路径（默认 agreement-report.json）")
    args = ap.parse_args(argv)

    A = load_records(args.pass_a, "passA")
    B = load_records(args.pass_b, "passB")
    ids_a, ids_b = set(A), set(B)
    if ids_a != ids_b:
        only_a = sorted(ids_a - ids_b)
        only_b = sorted(ids_b - ids_a)
        fail(f"两通道 claim_id 集合不一致：仅 Pass A 有 {only_a}；仅 Pass B 有 {only_b}")

    claim_ids = sorted(ids_a)
    pairs = [(A[c]["verdict"], B[c]["verdict"]) for c in claim_ids]
    kappa, po, pe = cohens_kappa(pairs)

    per_claim, verdict_dis, page_dis = [], [], []
    jac_sum, overlap_hits = 0.0, 0
    for c in claim_ids:
        va, vb = A[c]["verdict"], B[c]["verdict"]
        sa, sb = set(A[c]["pages"]), set(B[c]["pages"])
        jac = jaccard(sa, sb)
        exact = bool(sa & sb) or (not sa and not sb)
        jac_sum += jac
        overlap_hits += int(exact)
        entry = {
            "claim_id": c,
            "verdict_a": va, "verdict_b": vb,
            "verdict_agree": va == vb,
            "pages_a": sorted(sa), "pages_b": sorted(sb),
            "page_jaccard": round(jac, 4),
            "page_exact_overlap": exact,
        }
        per_claim.append(entry)
        if va != vb:
            verdict_dis.append({"claim_id": c, "verdict_a": va, "verdict_b": vb})
        elif not exact:  # verdict 一致但页码无重合
            page_dis.append({"claim_id": c, "pages_a": sorted(sa), "pages_b": sorted(sb)})

    n = len(claim_ids)
    report = {
        "n_claims": n,
        "verdict_agreement": {
            "observed_agreement_po": round(po, 4),
            "expected_agreement_pe": round(pe, 4),
            "cohens_kappa": round(kappa, 4) if kappa is not None else None,
            "kappa_note": (None if kappa is not None
                           else "两通道判定完全相同且集中于单一类别，kappa 无定义（po=pe=1）"),
            "marginals_a": dict(Counter(a for a, _ in pairs)),
            "marginals_b": dict(Counter(b for _, b in pairs)),
        },
        "location_agreement": {
            "mean_page_jaccard": round(jac_sum / n, 4),
            "exact_overlap_ratio": round(overlap_hits / n, 4),
        },
        "disagreements": {
            "verdict": verdict_dis,
            "location_only": page_dis,
        },
        "per_claim": per_claim,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[agreement] 论断数 n={n}")
    print(f"[agreement] verdict 观测一致率 po={po:.4f}，期望一致率 pe={pe:.4f}")
    if kappa is not None:
        print(f"[agreement] Cohen's kappa = {kappa:.4f}")
    else:
        print("[agreement] Cohen's kappa 无定义（po=pe=1）")
    print(f"[agreement] 定位：平均 Jaccard={jac_sum / n:.4f}，"
          f"至少一页精确重合比例={overlap_hits / n:.4f}")
    print(f"[agreement] verdict 分歧 {len(verdict_dis)} 条；"
          f"仅定位分歧 {len(page_dis)} 条")
    for d in verdict_dis:
        print(f"  [verdict 分歧] {d['claim_id']}: A={d['verdict_a']} vs B={d['verdict_b']}")
    for d in page_dis:
        print(f"  [定位分歧] {d['claim_id']}: A页{d['pages_a']} vs B页{d['pages_b']}")
    print(f"[agreement] 报告已写入 {args.output}")

    if kappa is not None and kappa < KAPPA_WARN_THRESHOLD:
        print(f"[agreement] 质量警告：kappa={kappa:.4f} < {KAPPA_WARN_THRESHOLD}，"
              f"判定标准不稳定，result.json 的 uncertainty 必须如实报告！", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
