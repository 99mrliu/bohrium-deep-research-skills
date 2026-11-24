#!/usr/bin/env python3
"""run_case.py — bundle C 编排器。

用法：
  python3 run_case.py init     --case /input/case.json --task /input/task.md \
                               --input-dir /input --work /app/work --out /app/output
  python3 run_case.py verify   --work /app/work --out /app/output
  python3 run_case.py finalize --work /app/work --out /app/output

init 在数秒内完成：防御式解析 → 数值候选抽取 → 单位归一化 → 冲突检测 →
写出 partial result.json（status=in_progress，契约字段以 null 占位），防中断。
verify 执行数字回链门控并就地标 [数值未定位]。finalize 组装终版 result.json。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_result  # noqa: E402
import extract_quant  # noqa: E402
import ingest  # noqa: E402
import normalize_units  # noqa: E402
import numeric_conflict  # noqa: E402
import verify_quant  # noqa: E402


def append_log(work, entry):
    path = os.path.join(work, "change_log.json")
    log = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    log.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def cmd_init(args):
    profile, docs, groups = ingest.build_corpus(args.case, args.task, args.input_dir, args.work)
    cands = extract_quant.run(args.work)
    norm_rows = normalize_units.run(args.work)
    conf = numeric_conflict.run(args.work)
    unnorm = sum(1 for r in norm_rows if r.get("norm_status") != "ok")
    append_log(args.work,
               f"init: 解析 {len(docs)} 篇（近重复组 {len(groups)}），数值候选 {len(cands)} 个"
               f"（归一化 {len(norm_rows) - unnorm}、unnormalized {unnorm}），"
               f"跨文献比较 {conf['compared_pairs']} 对、冲突候选 {conf['conflict_count']} 对")
    partial = build_result.build(args.work, args.out, forced_status="in_progress")
    print(json.dumps({"case_id": partial.get("case_id"), "status": partial.get("status"),
                      "candidates": len(cands), "unnormalized": unnorm,
                      "conflicts": conf["conflict_count"]}, ensure_ascii=False))


def cmd_verify(args):
    report = verify_quant.run(args.work, args.out)
    append_log(args.work,
               f"verify: 数字回链门控 {report['linked']}/{report['total_numbers']} 通过，"
               f"未定位 {report['unlinked_count']} 个")
    print(json.dumps({"gate_passed": report["gate_passed"], "linked": report["linked"],
                      "unlinked": report["unlinked_count"]}, ensure_ascii=False))


def cmd_finalize(args):
    append_log(args.work, "finalize: 组装 result.json（镜像 output_contract）")
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
