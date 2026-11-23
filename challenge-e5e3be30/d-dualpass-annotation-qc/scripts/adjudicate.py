#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adjudicate.py — 双通道合并与保守仲裁。

输入 passA.json、passB.json（格式同 agreement.py，建议含 evidence_quote /
rationale 以便日志并列双方原话）与 agreement-report.json，输出：
  - adjudicated.json：每条论断的最终/临时判定记录；
  - adjudication-log.md：人类可读仲裁日志。

仲裁规则（保守默认，详见 references/adjudication-protocol.md）：
  * 两通道 verdict 一致且页码有重合 → 直接采纳，needs_review=false；
  * verdict 一致但页码无重合 → 采纳 verdict，页码取并集，needs_review=true
    （理由 location_divergence）；
  * {supported, partially_supported} → partially_supported；
  * {supported, insufficient_evidence} → partially_supported；
  * {partially_supported, insufficient_evidence} → insufficient_evidence；
  * contradicted 与其他任何判定分歧 → provisional=partially_supported，
    conflict=true，双方原话并列，不强行选边；
  * 所有分歧项 needs_review=true 并附仲裁理由。

schema/输入错误 exit 1；用法错误 exit 2；正常 exit 0。
"""
import argparse
import json
import sys
from collections import Counter

VERDICTS = ["supported", "partially_supported", "contradicted", "insufficient_evidence"]
# 悲观方向序：沿箭头取更不乐观者（contradicted 走冲突特例，不在序内）
PESSIMIZE = {
    frozenset(["supported", "partially_supported"]): "partially_supported",
    frozenset(["supported", "insufficient_evidence"]): "partially_supported",
    frozenset(["partially_supported", "insufficient_evidence"]): "insufficient_evidence",
}


def fail(msg):
    print(f"[adjudicate] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load_records(path, tag):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        fail(f"{tag}: 文件不存在: {path}")
    except json.JSONDecodeError as e:
        fail(f"{tag}: JSON 解析失败: {path}: {e}")
    if isinstance(data, dict) and "records" in data:
        data = data["records"]
    if not isinstance(data, list):
        fail(f"{tag}: 顶层必须是标注记录数组（或含 records 数组的对象）")
    out = {}
    for i, r in enumerate(data):
        where = f"{tag}[{i}]"
        if not isinstance(r, dict):
            fail(f"{where}: 记录必须是对象")
        for field in ("claim_id", "verdict", "evidence_pages"):
            if field not in r:
                fail(f"{where}: 缺少必需字段 '{field}'")
        cid = r["claim_id"]
        if cid in out:
            fail(f"{where}: claim_id 重复: {cid}")
        v = r["verdict"]
        if v not in VERDICTS:
            fail(f"{where}: verdict '{v}' 非法")
        pages = r["evidence_pages"]
        if not isinstance(pages, list) or any(
            not isinstance(p, int) or isinstance(p, bool) or p < 0 for p in pages
        ):
            fail(f"{where}: evidence_pages 必须是非负整数数组")
        out[cid] = {
            "verdict": v,
            "pages": sorted(set(pages)),
            "quote": str(r.get("evidence_quote", "")),
            "rationale": str(r.get("rationale", "")),
        }
    return out


def adjudicate_one(cid, a, b):
    """返回该论断的合并记录。"""
    va, vb = a["verdict"], b["verdict"]
    sa, sb = set(a["pages"]), set(b["pages"])
    pages_union = sorted(sa | sb)
    base = {
        "claim_id": cid,
        "pass_a": {"verdict": va, "evidence_pages": a["pages"],
                   "evidence_quote": a["quote"], "rationale": a["rationale"]},
        "pass_b": {"verdict": vb, "evidence_pages": b["pages"],
                   "evidence_quote": b["quote"], "rationale": b["rationale"]},
        "evidence_pages_merged": pages_union,
        "conflict": False,
    }
    if va == vb:
        if sa & sb or (not sa and not sb):
            base.update(final_verdict=va, provisional=False, needs_review=False,
                        adjudication_reason="两通道判定与定位一致，直接采纳")
        else:
            base.update(final_verdict=va, provisional=False, needs_review=True,
                        adjudication_reason="判定一致但证据页码无重合（location_divergence），"
                                            "页码取并集，建议复核定位")
        return base
    # verdict 分歧
    pair = frozenset([va, vb])
    if "contradicted" in pair:
        base.update(final_verdict="partially_supported", provisional=True,
                    needs_review=True, conflict=True,
                    adjudication_reason=f"contradicted 冲突（A={va}, B={vb}）：按协议不降"
                                        "为 contradicted 也不采信对方，双方原话并列，"
                                        "临时判 partially_supported，必须人工/仲裁复核")
        return base
    if pair in PESSIMIZE:
        final = PESSIMIZE[pair]
        base.update(final_verdict=final, provisional=True, needs_review=True,
                    adjudication_reason=f"保守默认：分歧对 ({va}, {vb}) 取更不乐观判定 "
                                        f"→ {final}")
        return base
    # 理论上不可达（四值两两组合已穷举）
    base.update(final_verdict="insufficient_evidence", provisional=True,
                needs_review=True,
                adjudication_reason=f"未预设的分歧对 ({va}, {vb})，兜底取 "
                                    f"insufficient_evidence")
    return base


def main(argv=None):
    ap = argparse.ArgumentParser(description="双通道标注保守合并与仲裁。")
    ap.add_argument("pass_a", help="Pass A 标注 JSON")
    ap.add_argument("pass_b", help="Pass B 标注 JSON")
    ap.add_argument("agreement_report", help="agreement.py 输出的报告 JSON")
    ap.add_argument("-o", "--output", default="adjudicated.json",
                    help="合并结果输出路径（默认 adjudicated.json）")
    ap.add_argument("--log", default="adjudication-log.md",
                    help="仲裁日志 Markdown 路径（默认 adjudication-log.md）")
    args = ap.parse_args(argv)

    A = load_records(args.pass_a, "passA")
    B = load_records(args.pass_b, "passB")
    try:
        with open(args.agreement_report, "r", encoding="utf-8") as f:
            report = json.load(f)
    except FileNotFoundError:
        fail(f"agreement 报告不存在: {args.agreement_report}（请先运行 agreement.py）")
    except json.JSONDecodeError as e:
        fail(f"agreement 报告解析失败: {e}")
    if not isinstance(report, dict) or "verdict_agreement" not in report:
        fail("agreement 报告缺少 verdict_agreement 字段，疑似非 agreement.py 产物")

    if set(A) != set(B):
        fail(f"两通道 claim_id 集合不一致：仅A={sorted(set(A) - set(B))}；"
             f"仅B={sorted(set(B) - set(A))}")
    claim_ids = sorted(A)

    results = [adjudicate_one(c, A[c], B[c]) for c in claim_ids]
    n_review = sum(1 for r in results if r["needs_review"])
    n_conflict = sum(1 for r in results if r["conflict"])
    final_counts = Counter(r["final_verdict"] for r in results)

    kappa = report["verdict_agreement"].get("cohens_kappa")
    payload = {
        "quality": {
            "cohens_kappa": kappa,
            "kappa_note": report["verdict_agreement"].get("kappa_note"),
            "mean_page_jaccard": report["location_agreement"]["mean_page_jaccard"],
            "exact_overlap_ratio": report["location_agreement"]["exact_overlap_ratio"],
            "n_claims": len(results),
            "n_needs_review": n_review,
            "n_conflict": n_conflict,
            "final_verdict_counts": dict(final_counts),
        },
        "records": results,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # 仲裁日志（Markdown，人类可读）
    lines = [
        "# 双通道标注仲裁日志",
        "",
        f"- 论断总数：{len(results)}",
        f"- Cohen's kappa：{kappa if kappa is not None else '无定义（完全一致单类别）'}",
        f"- 平均页码 Jaccard：{report['location_agreement']['mean_page_jaccard']}",
        f"- 至少一页精确重合比例：{report['location_agreement']['exact_overlap_ratio']}",
        f"- 需复核（needs_review）：{n_review} 条；其中冲突标记（conflict）：{n_conflict} 条",
        "",
        "## 终判分布",
        "",
    ]
    for v in VERDICTS:
        lines.append(f"- {v}: {final_counts.get(v, 0)}")
    lines += ["", "## 逐条仲裁明细", ""]
    for r in results:
        lines.append(f"### {r['claim_id']} → {r['final_verdict']}"
                     + ("（provisional，needs_review）" if r["needs_review"] else "（一致采纳）")
                     + (" ⚠️CONFLICT" if r["conflict"] else ""))
        lines.append("")
        lines.append(f"- 仲裁理由：{r['adjudication_reason']}")
        lines.append(f"- 合并证据页码：{r['evidence_pages_merged']}")
        lines.append("")
        lines.append("| 通道 | 判定 | 证据页 | 原文引句 | 理由 |")
        lines.append("|---|---|---|---|---|")
        for tag in ("pass_a", "pass_b"):
            p = r[tag]
            q = p["evidence_quote"].replace("|", "\\|").replace("\n", " ") or "（无）"
            ra = p["rationale"].replace("|", "\\|").replace("\n", " ") or "（无）"
            lines.append(f"| {tag} | {p['verdict']} | {p['evidence_pages']} | {q} | {ra} |")
        lines.append("")
    with open(args.log, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[adjudicate] 共 {len(results)} 条：一致采纳 {len(results) - n_review}，"
          f"needs_review {n_review}（含 conflict {n_conflict}）")
    print(f"[adjudicate] 终判分布: {dict(final_counts)}")
    for r in results:
        if r["needs_review"]:
            print(f"  [复核] {r['claim_id']} → {r['final_verdict']}"
                  f"{' [CONFLICT]' if r['conflict'] else ''}：{r['adjudication_reason']}")
    print(f"[adjudicate] 已写出 {args.output} 与 {args.log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
