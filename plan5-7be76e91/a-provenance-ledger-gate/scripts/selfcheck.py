#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — provenance-ledger-gate 端到端自查

在 examples/ 合成示例上跑通三个脚本全流程，并验证：
  1. 正例：claim_audit(claims_good.json) exit 0；domain_check(plan_a) exit 0。
  2. 负例：claim_audit(claims_bad.json) exit 3 且 stdout 缺陷清单精确命中预埋的
     2 条陷阱（1 unsupported + 1 conflict）；domain_check(plan_a+plan_b) exit 3
     且精确命中预埋的 1 条域外违例。
  3. 确定性：同一命令双跑，产物文件逐字节一致、stdout 一致。
全部通过则本脚本 exit 0；任一失败 exit 3；用法错误 exit 2。

用法：
  python3 selfcheck.py [--examples-dir ../examples]
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SYNTH_NOTE = "合成示例 / SYNTHETIC EXAMPLE，非正式案例结果"
ASOF = "2026-01-01"

# 预埋陷阱的精确期望（见 examples/README.md 与 claims_bad.json / plan_b.json）
EXPECTED_AUDIT_DEFECTS = sorted([
    ("conflict", "PLAN-A", "parameters.fbs_percent"),
    ("unsupported", "PLAN-B", "interpretation_criteria.doubling_time_hours"),
])
EXPECTED_DOMAIN_VIOLATIONS = sorted([
    ("out_of_domain", "PLAN-B", "temperature_c"),
])


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=False)
    return proc.returncode, proc.stdout, proc.stderr


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def parse_defects(stdout_bytes, tag):
    """解析 stdout 中 TAG\\t 开头的行，返回排序后的三元组列表。"""
    triples = []
    for line in stdout_bytes.decode("utf-8").splitlines():
        if line.startswith(tag + "\t"):
            parts = line.split("\t")
            triples.append((parts[1], parts[2], parts[3]))
    return sorted(triples)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="在 examples/ 合成输入上端到端自查 source_registry/claim_audit/domain_check。")
    parser.add_argument("--examples-dir",
                        default=os.path.normpath(os.path.join(HERE, "..", "examples")),
                        help="examples 目录（默认：本脚本同级 ../examples）")
    args = parser.parse_args(argv)

    ex = os.path.abspath(args.examples_dir)
    scripts = {
        "registry": os.path.join(HERE, "source_registry.py"),
        "audit": os.path.join(HERE, "claim_audit.py"),
        "domain": os.path.join(HERE, "domain_check.py"),
    }
    for name, path in scripts.items():
        if not os.path.isfile(path):
            print("ERROR: 缺少脚本 %s (%s)" % (name, path), file=sys.stderr)
            return 2
    for path in (os.path.join(ex, "claims_good.json"),
                 os.path.join(ex, "claims_bad.json"),
                 os.path.join(ex, "mini-case.json"),
                 os.path.join(ex, "sources"),
                 os.path.join(ex, "plans", "plan_a.json"),
                 os.path.join(ex, "plans", "plan_b.json")):
        if not os.path.exists(path):
            print("ERROR: 示例文件缺失: %s" % path, file=sys.stderr)
            return 2

    failures = []

    def check(name, ok, detail=""):
        print("%s %s%s" % ("PASS" if ok else "FAIL", name, (" — " + detail) if detail else ""))
        if not ok:
            failures.append(name)

    with tempfile.TemporaryDirectory(prefix="plg_selfcheck_") as tmp:
        # --- 1. registry 正例 + 双跑一致 ---
        reg1 = os.path.join(tmp, "registry_run1.json")
        reg2 = os.path.join(tmp, "registry_run2.json")
        base_reg = [sys.executable, scripts["registry"],
                    "--input-dir", os.path.join(ex, "sources"),
                    "--asof", ASOF, "--note", SYNTH_NOTE]
        rc1, _, err1 = run(base_reg + ["--out", reg1])
        rc2, _, _ = run(base_reg + ["--out", reg2])
        check("registry exit 0", rc1 == 0, "rc=%d stderr=%s" % (rc1, err1.decode('utf-8', 'replace')))
        check("registry 双跑字节一致", rc1 == 0 and rc2 == 0 and read_bytes(reg1) == read_bytes(reg2))

        # --- 2. claim_audit 正例（good） + 双跑一致 ---
        def audit_cmd(claims, tag):
            return [sys.executable, scripts["audit"],
                    "--claims", os.path.join(ex, claims),
                    "--registry", reg1,
                    "--out-json", os.path.join(tmp, "%s.json" % tag),
                    "--out-md", os.path.join(tmp, "%s.md" % tag),
                    "--note", SYNTH_NOTE]

        rc_g1, _, _ = run(audit_cmd("claims_good.json", "audit_good_1"))
        rc_g2, _, _ = run(audit_cmd("claims_good.json", "audit_good_2"))
        check("audit(good) exit 0", rc_g1 == 0, "rc=%d" % rc_g1)
        same_g = (read_bytes(os.path.join(tmp, "audit_good_1.json"))
                  == read_bytes(os.path.join(tmp, "audit_good_2.json"))
                  and read_bytes(os.path.join(tmp, "audit_good_1.md"))
                  == read_bytes(os.path.join(tmp, "audit_good_2.md")))
        check("audit(good) 双跑字节一致", rc_g1 == 0 and rc_g2 == 0 and same_g)

        # --- 3. claim_audit 负例（bad）：exit 3 + 缺陷精确命中 + 双跑一致 ---
        rc_b1, out_b1, _ = run(audit_cmd("claims_bad.json", "audit_bad_1"))
        rc_b2, out_b2, _ = run(audit_cmd("claims_bad.json", "audit_bad_2"))
        check("audit(bad) exit 3", rc_b1 == 3, "rc=%d" % rc_b1)
        got = parse_defects(out_b1, "DEFECT")
        check("audit(bad) 缺陷清单精确命中预埋 2 条",
              got == EXPECTED_AUDIT_DEFECTS,
              "got=%r expected=%r" % (got, EXPECTED_AUDIT_DEFECTS))
        same_b = (out_b1 == out_b2
                  and read_bytes(os.path.join(tmp, "audit_bad_1.json"))
                  == read_bytes(os.path.join(tmp, "audit_bad_2.json")))
        check("audit(bad) 双跑 stdout/产物一致", rc_b2 == 3 and same_b)

        # --- 4. domain_check 正例（仅 plan_a） ---
        def domain_cmd(tag, *plans):
            return [sys.executable, scripts["domain"],
                    "--case", os.path.join(ex, "mini-case.json"),
                    "--plans"] + [os.path.join(ex, "plans", p) for p in plans] + [
                    "--out", os.path.join(tmp, "%s.json" % tag),
                    "--note", SYNTH_NOTE]

        rc_d1, _, _ = run(domain_cmd("domain_good_1", "plan_a.json"))
        rc_d2, _, _ = run(domain_cmd("domain_good_2", "plan_a.json"))
        check("domain(plan_a) exit 0", rc_d1 == 0, "rc=%d" % rc_d1)
        same_d = (read_bytes(os.path.join(tmp, "domain_good_1.json"))
                  == read_bytes(os.path.join(tmp, "domain_good_2.json")))
        check("domain(plan_a) 双跑字节一致", rc_d2 == 0 and same_d)

        # --- 5. domain_check 负例（plan_a + plan_b）：exit 3 + 精确命中域外参数 ---
        rc_db1, out_db1, _ = run(domain_cmd("domain_bad_1", "plan_a.json", "plan_b.json"))
        rc_db2, out_db2, _ = run(domain_cmd("domain_bad_2", "plan_a.json", "plan_b.json"))
        check("domain(plan_a+plan_b) exit 3", rc_db1 == 3, "rc=%d" % rc_db1)
        gotd = parse_defects(out_db1, "VIOLATION")
        check("domain(bad) 违例清单精确命中预埋域外参数",
              gotd == EXPECTED_DOMAIN_VIOLATIONS,
              "got=%r expected=%r" % (gotd, EXPECTED_DOMAIN_VIOLATIONS))
        check("domain(bad) 双跑 stdout 一致", rc_db2 == 3 and out_db1 == out_db2)

    if failures:
        print("\n自查未通过，失败项：%s" % ", ".join(failures))
        return 3
    print("\n自查全部通过（正例 exit 0、负例 exit 3 精确命中陷阱、双跑逐字节一致）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
