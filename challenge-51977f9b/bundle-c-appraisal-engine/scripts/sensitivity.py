#!/usr/bin/env python3
"""sensitivity.py —— 结论敏感性分析：剔除高风险研究后重算论断支撑。

claims.jsonl 行：{claim_id, text, supporting:[record_id...]}

规则：
  S1 每条 claim 至少 1 条支撑（无支撑论断不许进入综述，exit 3）；
  S2 supporting 中的 record_id 必须存在于评价报告（exit 3）。
判定（剔除 --exclude-grade 指定等级的研究后）：
  stable      支撑集不变（未失去任何支撑）；
  weakened    失去部分支撑，但剩余支撑数仍 ≥ --min-support；
  unsupported 支撑清零或剩余 < --min-support。

纪律：unsupported 的 claim 必须改写或移入 result.json 的 uncertainty
（见 references/sensitivity_guide.md）。

退出码：0=通过；2=输入不足；3=校验失败。
"""
import argparse
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--appraisal", required=True, help="appraisal_report.json 路径")
    ap.add_argument("--claims", required=True, help="claims.jsonl 路径")
    ap.add_argument("--min-support", type=int, default=1,
                    help="论断成立所需的最少剩余支撑研究数（默认 1）")
    ap.add_argument("--exclude-grade", action="append", default=None,
                    help="要剔除的风险等级，可多次指定（默认 high）")
    ap.add_argument("--out", required=True, help="输出 sensitivity_report.json 路径")
    args = ap.parse_args()

    exclude_grades = args.exclude_grade if args.exclude_grade else ["high"]

    for p, tag in ((args.appraisal, "appraisal"), (args.claims, "claims")):
        if not os.path.isfile(p):
            print(f"[E2] 输入缺失：{tag} 文件不存在：{p}", file=sys.stderr)
            return 2
    try:
        with open(args.appraisal, "r", encoding="utf-8") as f:
            appraisal = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[E3] appraisal JSON 解析失败：{e}", file=sys.stderr)
        return 3

    grade_map = {s["record_id"]: s["grade"] for s in appraisal.get("studies", [])}
    if not grade_map:
        print("[E3] appraisal 报告中无研究记录。", file=sys.stderr)
        return 3

    claims, errors = [], []
    with open(args.claims, "r", encoding="utf-8") as f:
        for ln, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                c = json.loads(raw)
            except json.JSONDecodeError as e:
                errors.append(("E3", f"第 {ln} 行 JSON 解析失败：{e}"))
                continue
            cid = c.get("claim_id")
            supporting = c.get("supporting")
            if not cid:
                errors.append(("E3", f"第 {ln} 行缺 claim_id。"))
                continue
            if not isinstance(supporting, list) or len(supporting) < 1:
                errors.append(("S1", f"论断 {cid} 无支撑研究："
                                     "无支撑论断不许进入综述。"))
                continue
            for rid in supporting:
                if rid not in grade_map:
                    errors.append(("S2", f"论断 {cid} 的支撑记录 {rid} "
                                         "不在评价报告中。"))
            claims.append(c)
    if errors:
        print(f"[校验失败] 共 {len(errors)} 处违规：", file=sys.stderr)
        for code, msg in errors:
            print(f"  [{code}] {msg}", file=sys.stderr)
        return 3

    results = []
    for c in claims:
        original = list(c["supporting"])
        excluded = [r for r in original if grade_map[r] in exclude_grades]
        remaining = [r for r in original if r not in excluded]
        if not excluded:
            status = "stable"
        elif len(remaining) >= args.min_support:
            status = "weakened"
        else:
            status = "unsupported"
        results.append({
            "claim_id": c["claim_id"],
            "text": c.get("text", ""),
            "original_support": original,
            "excluded": excluded,
            "remaining": remaining,
            "status": status,
        })

    summary = {"stable": 0, "weakened": 0, "unsupported": 0}
    for r in results:
        summary[r["status"]] += 1

    report = {
        "excluded_grades": exclude_grades,
        "min_support": args.min_support,
        "scale_id": appraisal.get("scale_id"),
        "claims": results,
        "summary": summary,
        "discipline": "unsupported 论断必须改写或移入 result.json 的 uncertainty；"
                      "weakened 论断在正文中标注'剔除高风险研究后支撑减弱'。",
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    md_path = os.path.splitext(args.out)[0] + ".md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# 结论敏感性分析报告\n\n")
        f.write(f"剔除等级：{', '.join(exclude_grades)}；min_support = "
                f"{args.min_support}\n\n")
        f.write("| claim_id | 论断 | 原支撑 | 剔除 | 剩余 | 判定 |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in results:
            f.write(f"| {r['claim_id']} | {r['text']} | "
                    f"{len(r['original_support'])}（{', '.join(r['original_support'])}） | "
                    f"{', '.join(r['excluded']) or '无'} | "
                    f"{len(r['remaining'])}（{', '.join(r['remaining']) or '无'}） | "
                    f"{r['status']} |\n")
        f.write(f"\n汇总：stable {summary['stable']} 条，weakened "
                f"{summary['weakened']} 条，unsupported {summary['unsupported']} 条。\n")

    print(f"[OK] 敏感性报告已生成：{args.out}（markdown 表：{md_path}）")
    for r in results:
        print(f"  {r['claim_id']}: {r['status']}（剩余支撑 {len(r['remaining'])} 条）")
    if summary["unsupported"]:
        print(f"  [警告] {summary['unsupported']} 条论断 unsupported，"
              "必须改写或移入 uncertainty。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
