#!/usr/bin/env python3
"""audit_replay.py — 闭环复核：确定性端到端复跑 + 审计抽样。

确定性复跑（Deterministic replay）：
  以固定顺序、固定参数在 work/replay 下重跑 parse_case → freeze_refset →
  match_coverage → supplement_engine（全部离线，无网络），比较两次运行的：
  refset_hash、覆盖集合、补检停止规则与新增覆盖集合。不一致 → 写入
  change_log 并以退出码 3 拒绝交付结论。

审计抽样（Audit sampling，详见 references/audit_protocol.md）：
  - 边界命中（method=title_sim 且得分落在边界带内）100% 复核；
  - 干净命中按 ref_id 排序后每第 5 条抽取（比例约 20%，确定性规则，
    无需随机种子）；
  - 复核内容：重匹配结论一致性 + 命中证据是否能在本地源文件中复现。
  一致性比率写入 audit_report.json；分歧进入 change_log.json。

退出码：0 复核通过；2 材料不足；3 确定性/校验失败。仅标准库，支持 --help。
"""
import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from match_coverage import (  # noqa: E402
    EXIT_OK, EXIT_INSUFFICIENT, EXIT_VALIDATION,
    load_json, norm_title, match_record,
)


def run_replay(case, task, retrieved, materials, replay_work, scripts_dir):
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["TZ"] = "UTC"
    steps = [
        ["parse_case.py", "--case", case, "--task", task, "--work", replay_work],
        ["freeze_refset.py", "--parsed", os.path.join(replay_work, "parsed_case.json"),
         "--materials", materials, "--work", replay_work],
        ["match_coverage.py", "--refset", os.path.join(replay_work, "refset.json"),
         "--retrieved", *retrieved,
         "--out", os.path.join(replay_work, "coverage_initial.json")],
        ["supplement_engine.py", "--refset", os.path.join(replay_work, "refset.json"),
         "--coverage", os.path.join(replay_work, "coverage_initial.json"),
         "--materials", materials, "--work", replay_work],
    ]
    results = []
    for step in steps:
        cmd = [sys.executable, os.path.join(scripts_dir, step[0])] + step[1:]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        results.append({
            "script": step[0],
            "exit_code": proc.returncode,
            "stderr_tail": (proc.stderr or "")[-500:],
        })
        if proc.returncode not in (0, 2):
            break
    return results


def evidence_reproducible(match_entry, corpus_texts):
    """命中证据（标题/标识符）是否至少在一个本地源文件中复现。"""
    ev = match_entry.get("candidate_evidence") or {}
    title_norm = norm_title(ev.get("title")) or ""
    doi = (ev.get("doi") or "").lower()
    for path, text in sorted(corpus_texts.items()):
        if title_norm and title_norm in text:
            return True
        if doi and doi in text:
            return True
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="确定性复跑与审计抽样复核（边界命中全量 + 干净命中每第 5 条）。"
    )
    ap.add_argument("--case", required=True, help="case.json 路径")
    ap.add_argument("--task", default="/task.md", help="task.md 路径")
    ap.add_argument("--retrieved", nargs="+", required=True,
                    help="初始候选记录文件（与 match_coverage 一致）")
    ap.add_argument("--materials", default="/input", help="本地材料目录")
    ap.add_argument("--work", default="/app/work", help="工作目录（含主运行产物）")
    ap.add_argument("--scripts-dir", default=SCRIPT_DIR, help="脚本目录")
    ap.add_argument("--every", type=int, default=5, help="干净命中抽检间隔（默认每第 5 条）")
    args = ap.parse_args(argv)

    work = args.work
    refset_path = os.path.join(work, "refset.json")
    init_cov_path = os.path.join(work, "coverage_initial.json")
    final_cov_path = os.path.join(work, "final_coverage.json")
    state_path = os.path.join(work, "supplement_state.json")
    for required in (refset_path, init_cov_path, final_cov_path):
        if not os.path.isfile(required):
            print("[audit_replay] 缺少主运行产物：%s" % required, file=sys.stderr)
            return EXIT_INSUFFICIENT

    refset = load_json(refset_path)
    init_cov = load_json(init_cov_path)
    final_cov = load_json(final_cov_path)
    state = load_json(state_path) if os.path.isfile(state_path) else {}
    change_log = []

    # ---- 1. 确定性复跑 ----
    replay_work = os.path.join(work, "replay")
    os.makedirs(replay_work, exist_ok=True)
    run_results = run_replay(args.case, args.task, args.retrieved, args.materials,
                             replay_work, args.scripts_dir)
    determinism = {"runs": run_results, "checks": {}}
    exit_code = EXIT_OK

    replay_refset_path = os.path.join(replay_work, "refset.json")
    replay_init_path = os.path.join(replay_work, "coverage_initial.json")
    replay_final_path = os.path.join(replay_work, "final_coverage.json")
    replay_state_path = os.path.join(replay_work, "supplement_state.json")

    def compare(name, left, right):
        ok = left == right
        determinism["checks"][name] = {"match": ok}
        if not ok:
            change_log.append({
                "type": "determinism_mismatch", "check": name,
                "main": left, "replay": right,
            })
            return False
        return True

    all_ok = True
    if os.path.isfile(replay_refset_path):
        all_ok &= compare("refset_hash", refset.get("refset_hash"),
                          load_json(replay_refset_path).get("refset_hash"))
    else:
        all_ok = False
        change_log.append({"type": "replay_missing", "check": "refset"})
    if os.path.isfile(replay_init_path):
        r = load_json(replay_init_path)
        all_ok &= compare("initial_covered_ids", init_cov.get("covered_ids"),
                          r.get("covered_ids"))
    if os.path.isfile(replay_final_path):
        r = load_json(replay_final_path)
        all_ok &= compare("final_covered_ids", final_cov.get("covered_ids"),
                          r.get("covered_ids"))
    if os.path.isfile(replay_state_path):
        r = load_json(replay_state_path)
        all_ok &= compare("stop_rule",
                          (state.get("stop_rule_final") or {}).get("rule"),
                          (r.get("stop_rule_final") or {}).get("rule"))
        all_ok &= compare("batches_gains",
                          [b.get("marginal_coverage_gain") for b in state.get("batches", [])],
                          [b.get("marginal_coverage_gain") for b in r.get("batches", [])])

    if not all_ok:
        exit_code = EXIT_VALIDATION

    # ---- 2. 审计抽样 ----
    from supplement_engine import load_corpus
    _records, corpus_texts = load_corpus(args.materials)
    threshold = final_cov.get("threshold", 0.90)
    band = final_cov.get("band", 0.05)
    matches = [m for m in final_cov.get("matches", [])
               if m.get("status") in ("matched", "borderline")]
    borderline = [m for m in matches if m.get("status") == "borderline"
                  or (m.get("method") == "title_sim"
                      and m.get("score", 1.0) < threshold + band)]
    borderline_ids = {id(m) for m in borderline}
    clean = sorted([m for m in matches if id(m) not in borderline_ids],
                   key=lambda m: m.get("ref_id") or "")
    sampled = clean[args.every - 1::args.every] if args.every > 0 else clean

    checks = []
    n_agree = 0
    refs_by_id = {r["ref_id"]: r for r in refset.get("references", [])}
    for m in borderline + sampled:
        ref = refs_by_id.get(m.get("ref_id"))
        recheck = {"ref_id": m.get("ref_id"), "sample_kind":
                   "borderline" if id(m) in borderline_ids else "clean_every_%d" % args.every}
        ok = True
        if ref is None:
            ok = False
            recheck["reason"] = "ref_id 不在冻结参考集中"
        else:
            ev = m.get("candidate_evidence") or {}
            status2, method2, score2 = match_record(
                ref, ev, threshold, band)
            recheck["rematch"] = {"status": status2, "method": method2, "score": score2}
            if status2 not in ("matched", "borderline"):
                ok = False
                recheck["reason"] = "重匹配结论与主运行不一致"
            elif not evidence_reproducible(m, corpus_texts):
                ok = False
                recheck["reason"] = "命中证据未在任何本地源文件中复现"
        checks.append(recheck)
        if ok:
            n_agree += 1
        else:
            change_log.append({"type": "audit_disagreement", "detail": recheck})
    n_checked = len(checks)
    sampling = {
        "rule": "borderline 100%% 复核；干净命中按 ref_id 排序后每第 %d 条抽检" % args.every,
        "n_borderline": len(borderline),
        "n_clean_total": len(clean),
        "n_clean_sampled": len(sampled),
        "n_checked": n_checked,
        "n_agree": n_agree,
        "agreement_rate": round(n_agree / n_checked, 6) if n_checked else None,
        "checks": checks,
    }

    report = {
        "case_id": refset.get("case_id"),
        "determinism": {**determinism, "all_checks_passed": bool(all_ok)},
        "sampling": sampling,
        "change_log_entries": len(change_log),
        "status": "ok" if (all_ok and n_agree == n_checked) else "review_required",
    }
    with open(os.path.join(work, "audit_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(work, "change_log.json"), "w", encoding="utf-8") as fh:
        json.dump({"change_log": change_log}, fh, ensure_ascii=False, indent=2)

    print("[audit_replay] 确定性=%s 抽检=%d/%d 一致性=%s 退出码=%d"
          % ("通过" if all_ok else "失败", n_agree, n_checked,
             sampling["agreement_rate"], exit_code))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
