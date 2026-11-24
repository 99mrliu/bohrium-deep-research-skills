#!/usr/bin/env python3
"""run_case.py — bundle A 编排器。

用法：
  python3 run_case.py init     --case /input/case.json --task /input/task.md \
                               --input-dir /input --work /app/work --out /app/output
  python3 run_case.py verify   --work /app/work --out /app/output
  python3 run_case.py finalize --work /app/work --out /app/output

init 在数秒内完成：防御式解析 → 文本抽取锚点化 → 来源取证 → 写出 partial result.json
（status=in_progress）。verify 执行引用门控并修订草稿。finalize 组装终版 result.json。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_result  # noqa: E402
import ingest  # noqa: E402
import quote_gate  # noqa: E402
import source_forensics  # noqa: E402


def cmd_init(args):
    profile, docs, groups = ingest.build_corpus(args.case, args.task, args.input_dir, args.work)
    manifest = source_forensics.run(args.work)
    os.makedirs(args.out, exist_ok=True)
    tiers = {}
    for e in manifest:
        tiers[e["trust_tier"]] = tiers.get(e["trust_tier"], 0) + 1
    partial = {
        "case_id": profile["case_id"],
        "status": "in_progress",
        "note": "init 完成：解析与来源取证已落盘；模型阶段（筛选/主题/证据表/草稿）进行中。",
        "docs": len(docs), "trust_tiers": tiers, "dup_groups": len(groups),
    }
    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(partial, f, ensure_ascii=False, indent=2)
    log = [f"init: 解析 {len(docs)} 篇（trust {tiers}），近重复组 {len(groups)} 个"]
    with open(os.path.join(args.work, "change_log.json"), "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(json.dumps(partial, ensure_ascii=False))


def cmd_verify(args):
    report = quote_gate.run(args.work, args.out)
    log_path = os.path.join(args.work, "change_log.json")
    log = json.load(open(log_path, encoding="utf-8")) if os.path.exists(log_path) else []
    log.append(f"verify: {report['verified']}/{report['total_evidence']} 证据行通过，"
               f"降级 {report['downgraded_sentences']} 句")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(json.dumps({"gate_passed": report["gate_passed"],
                      "verified": report["verified"]}, ensure_ascii=False))


def cmd_finalize(args):
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
    p = sub.add_parser("verify")
    p.add_argument("--work", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("finalize")
    p.add_argument("--work", required=True)
    p.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    {"init": cmd_init, "verify": cmd_verify, "finalize": cmd_finalize}[args.cmd](args)


if __name__ == "__main__":
    main(sys.argv[1:])
