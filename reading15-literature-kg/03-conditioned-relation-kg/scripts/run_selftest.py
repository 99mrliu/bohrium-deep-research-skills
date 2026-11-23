#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自检测试：在合成示例上真实执行完整流水线，并运行负例测试。

正向断言：
  P1 校验 0 错误；P2 节点 >=8；P3 边 >=9；P4 真实执行查询 >=3；
  P5 冲突被检出（TransB 在 LowMT-100 上的 29.8 vs 30.5 BLEU）；
  P6 result.json 镜像了 output_contract 全部键。
负例测试：
  N1 不匹配引文 → quote_check 判 match=false；
  N2 无指标的“全局比较” → condition_lint C1 降级 uncertain；
  N3 cited-background 被当一手证据 → 校验器 R8 拒绝；
  N4 冲突证据必须被标记（conflicts.json 含 K1 记录）。
用法：
  python3 run_selftest.py --bundle <bundle_root>
输出：examples/synthetic-case/output/selftest_report.json；全过退出码 0。
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from relation_common import (BASE_VOCAB, load_json, dump_json,  # noqa: E402
                             load_corpus)
from quote_check import check_quote  # noqa: E402
from condition_lint import lint_edge  # noqa: E402
from relation_validate import validate_edge  # noqa: E402


def run(cmd, cwd):
    proc = subprocess.run([sys.executable] + cmd, cwd=cwd,
                          capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description="conditioned-relation-kg 自检")
    ap.add_argument("--bundle", default=os.path.dirname(HERE),
                    help="bundle 根目录")
    args = ap.parse_args(argv)
    bundle = os.path.abspath(args.bundle)
    case_dir = os.path.join(bundle, "examples", "synthetic-case")
    inp = os.path.join(case_dir, "input")
    work = os.path.join(case_dir, "work")
    out = os.path.join(case_dir, "output")
    os.makedirs(work, exist_ok=True)
    os.makedirs(out, exist_ok=True)

    checks, commands = [], []

    def step(name, cmd, expect_rc=0):
        rc, so, se = run(cmd, cwd=bundle)
        commands.append({"name": name, "cmd": "python3 " + " ".join(cmd),
                         "exit_code": rc, "stdout": so[-400:], "stderr": se[-400:]})
        checks.append({"id": name, "pass": rc == expect_rc,
                       "detail": "exit=%d" % rc})
        return rc

    # ---- 正向流水线（真实执行）----
    step("S0_bootstrap", ["scripts/case_bootstrap.py", "--input", inp, "--out", out])
    step("S1_validate", ["scripts/relation_validate.py", "--relations",
                         os.path.join(case_dir, "relations.json"),
                         "--input", inp, "--nodes",
                         os.path.join(case_dir, "nodes.json"),
                         "--out", os.path.join(out, "relation_audit.json")])
    step("S2_lint", ["scripts/condition_lint.py", "--relations",
                     os.path.join(case_dir, "relations.json"),
                     "--out", os.path.join(work, "relations_linted.json"),
                     "--findings", os.path.join(out, "lint_findings.json")])
    step("S3_conflicts", ["scripts/conflict_detect.py", "--relations",
                          os.path.join(work, "relations_linted.json"),
                          "--out", os.path.join(out, "conflicts.json")])
    step("S4_graph", ["scripts/graph_build.py", "--nodes",
                      os.path.join(case_dir, "nodes.json"), "--relations",
                      os.path.join(work, "relations_linted.json"), "--merges",
                      os.path.join(case_dir, "merge_decisions.json"),
                      "--outdir", out])
    step("S5_queries", ["scripts/query_run.py", "--graph",
                        os.path.join(out, "graph.jsonl"), "--queries",
                        os.path.join(case_dir, "queries_spec.json"),
                        "--out", os.path.join(out, "queries.json")])
    step("S6_preview", ["scripts/graph_preview.py", "--graph",
                        os.path.join(out, "graph.json"), "--outdir", out])
    step("S7_assemble", ["scripts/assemble.py", "--case",
                         os.path.join(inp, "case.json"), "--outdir", out])

    # ---- 正向断言 ----
    audit = load_json(os.path.join(out, "relation_audit.json"))
    checks.append({"id": "P1_validate_clean",
                   "pass": audit["n_errors"] == 0,
                   "detail": "errors=%d warnings=%d" % (audit["n_errors"],
                                                        audit["n_warnings"])})
    graph = load_json(os.path.join(out, "graph.json"))
    checks.append({"id": "P2_nodes_ge8", "pass": len(graph["nodes"]) >= 8,
                   "detail": "nodes=%d" % len(graph["nodes"])})
    checks.append({"id": "P3_edges_ge9", "pass": len(graph["edges"]) >= 9,
                   "detail": "edges=%d" % len(graph["edges"])})
    queries = load_json(os.path.join(out, "queries.json"))
    checks.append({"id": "P4_queries_ge3",
                   "pass": queries["n_executed"] >= 3,
                   "detail": "executed=%d" % queries["n_executed"]})
    conflicts = load_json(os.path.join(out, "conflicts.json"))
    k1 = [c for c in conflicts["conflicts"] if c["kind"] == "K1_numeric"]
    checks.append({"id": "P5_conflict_flagged", "pass": len(k1) >= 1,
                   "detail": "K1=%d total=%d" % (len(k1),
                                                 conflicts["n_conflicts"])})
    result = load_json(os.path.join(out, "result.json"))
    contract = load_json(os.path.join(inp, "case.json")).get("output_contract", {})
    mirrored = result.get("contract_mirror", {})
    checks.append({"id": "P6_contract_mirrored",
                   "pass": set(contract) <= set(mirrored)
                   and result.get("case_id") == "synthetic-conditioned-relation-demo",
                   "detail": "keys=%d/%d" % (len(set(contract) & set(mirrored)),
                                             len(contract))})

    # ---- 负例测试 ----
    corpus, _ = load_corpus(inp)
    n1 = check_quote(corpus, "SYN-P1", "SYN-P1.s3.p1",
                     "TransA achieves 99.9 BLEU on LowMT-100")
    checks.append({"id": "N1_mismatch_quote_rejected",
                   "pass": n1["match"] is False,
                   "detail": json.dumps(n1, ensure_ascii=False)})
    bad_global = {"edge_id": "neg2", "relation": "outperforms",
                  "subject": "n_transA", "object": "n_transB",
                  "voice": "primary-results", "conditions": {},
                  "evidence": [{"source_id": "SYN-P1",
                                "paragraph_id": "SYN-P1.s3.p2",
                                "quote": "TransA therefore outperforms TransB"}]}
    _, f2 = lint_edge(bad_global)
    checks.append({"id": "N2_global_comparison_downgraded",
                   "pass": any(f["rule"] == "C1" for f in f2),
                   "detail": "findings=%s" % [f["rule"] for f in f2]})
    cited_bad = {"edge_id": "neg3", "relation": "measured_on",
                 "subject": "n_transB", "object": "n_wmt",
                 "voice": "cited-background", "used_as_primary_evidence": True,
                 "conditions": {"dataset": "n_wmt", "metric": "n_bleu"},
                 "measurement": {"kind": "score", "value": 41.2, "unit": "BLEU"},
                 "evidence": [{"source_id": "SYN-P1",
                               "paragraph_id": "SYN-P1.s1.p1",
                               "quote": "TransB was previously reported to achieve"}]}
    probs3 = validate_edge(cited_bad, BASE_VOCAB, corpus)
    checks.append({"id": "N3_cited_voice_rejected",
                   "pass": any(p[1] == "R8" for p in probs3),
                   "detail": "rules=%s" % [p[1] for p in probs3]})
    checks.append({"id": "N4_conflict_evidence_flagged",
                   "pass": len(k1) >= 1 and all(
                       e.get("in_conflict") for e in graph["edges"]
                       if e["edge_id"] in {"e3", "e8"}),
                   "detail": "edges e3/e8 marked in_conflict"})

    n_pass = sum(1 for c in checks if c["pass"])
    report = {"bundle": "03-conditioned-relation-kg",
              "synthetic": True,
              "n_checks": len(checks), "n_pass": n_pass,
              "all_pass": n_pass == len(checks),
              "commands": commands, "checks": checks}
    dump_json(report, os.path.join(out, "selftest_report.json"))
    print("selftest: %d/%d pass -> %s"
          % (n_pass, len(checks), os.path.join(out, "selftest_report.json")))
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
