#!/usr/bin/env python3
"""run_case.py — bundle E 编排器。

用法：
  python3 run_case.py init     --case /input/case.json --task /input/task.md \
                               --input-dir /input --work /app/work --out /app/output
  python3 run_case.py gaps     --work /app/work
  python3 run_case.py appraise --work /app/work --out /app/output
  python3 run_case.py finalize --work /app/work --out /app/output

阶段划分：
  init     = ingest（防御式解析 + case_extras 探测）+ facet_scan + partial result.json
             （status=in_progress，数秒内落盘，防中断）。
  gaps     = gap_register（合并 facet 缺口与模型 claims.jsonl 的未裁决冲突）。
  appraise = appraise（候选选题评分 + 决策备忘录）。
  finalize = build_result（组装终版 result.json，镜像 output_contract）。

模型阶段（筛选/摘要/themes.json/claims.jsonl/topics.md）发生在 init 之后、
gaps 之前，全部落盘 work/。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import appraise  # noqa: E402
import build_result  # noqa: E402
import facet_scan  # noqa: E402
import gap_register  # noqa: E402
import ingest  # noqa: E402


def _append_log(work, entry):
    path = os.path.join(work, "change_log.json")
    log = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    log.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def cmd_init(args):
    profile, docs, extras = ingest.build_corpus(args.case, args.task, args.input_dir, args.work)
    matrix = facet_scan.run(args.work)
    os.makedirs(args.out, exist_ok=True)
    tiers = {}
    for d in docs:
        tiers[d["tier"]] = tiers.get(d["tier"], 0) + 1
    partial = {
        "case_id": profile["case_id"],
        "status": "in_progress",
        "note": "init 完成：解析、facet 打标已落盘；模型阶段（主题/论断/选题）进行中。",
        "docs": len(docs), "tiers": tiers,
        "candidate_topics": len(extras["candidate_topics"]),
        "constraints": len(extras["constraints"]),
        "absent_facets": len(matrix["absent_facets"]),
        "underpowered_facets": len(matrix["underpowered_facets"]),
    }
    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(partial, f, ensure_ascii=False, indent=2)
    _append_log(args.work,
                f"init: 解析 {len(docs)} 篇（{tiers}），候选选题 {len(extras['candidate_topics'])} 个、"
                f"约束 {len(extras['constraints'])} 条；absent facet {len(matrix['absent_facets'])} 个、"
                f"underpowered facet {len(matrix['underpowered_facets'])} 个")
    print(json.dumps(partial, ensure_ascii=False))


def cmd_gaps(args):
    # 模型可能已在 init 之后写入 themes.json：先刷新 facet_matrix 的 theme 段再登记空白
    facet_scan.run(args.work)
    register = gap_register.run(args.work)
    _append_log(args.work,
                f"gaps: 登记空白 {register['n_gaps']} 条 "
                f"（{json.dumps(register['by_type'], ensure_ascii=False)}，"
                f"themes_source={register['themes_source']}）")
    print(json.dumps({"n_gaps": register["n_gaps"], "by_type": register["by_type"]},
                     ensure_ascii=False))


def cmd_appraise(args):
    appraisal = appraise.run(args.work, args.out)
    recs = {}
    for r in appraisal["appraisals"]:
        recs[r["recommendation"]] = recs.get(r["recommendation"], 0) + 1
    _append_log(args.work,
                f"appraise: 评估 {len(appraisal['appraisals'])} 个候选选题"
                f"（来源 {appraisal['topics_source']}），档位分布 "
                f"{json.dumps(recs, ensure_ascii=False)}")
    print(json.dumps({"topics": len(appraisal["appraisals"]),
                      "recommendations": recs}, ensure_ascii=False))


def cmd_finalize(args):
    _append_log(args.work, "finalize: 组装终版 result.json")
    result = build_result.build(args.work, args.out)
    print(json.dumps({"status": result.get("status")}, ensure_ascii=False))


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--case", required=True)
    p.add_argument("--task", default=None)
    p.add_argument("--input-dir", default=None)
    p.add_argument("--work", required=True)
    p.add_argument("--out", required=True)
    for name in ("gaps", "appraise", "finalize"):
        p = sub.add_parser(name)
        p.add_argument("--work", required=True)
        if name in ("appraise", "finalize"):
            p.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    {"init": cmd_init, "gaps": cmd_gaps, "appraise": cmd_appraise,
     "finalize": cmd_finalize}[args.cmd](args)


if __name__ == "__main__":
    main(sys.argv[1:])
