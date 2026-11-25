#!/usr/bin/env python3
"""selfcheck.py — 合成夹具端到端自检。

在临时目录内生成合成夹具(非真实专利/论文),依次运行
name_norm.py -> entity_match.py -> cross_ledger.py,断言:
  1. "Acme, Inc." ≡ "ACME INCORPORATED"        -> auto 档
  2. "Globex Ltd." vs "Globex GmbH"            -> candidate 档,记 suffix_conflict
  3. "Zhang Wei" vs "Wei Zhang"                -> candidate 档,记 order_variant,
                                                  绝不进入 auto
  4. 明显不匹配的 "Initech LLC" / "Umbrella Corp" 保持 unmatched
  5. ledger 行锚点为源文件逐字子串;伪造锚点(篡改 quote)必须校验失败
  6. 阈值/权重完全来自 policy JSON(篡改 high 阈值后判定随之改变)
全部通过则打印摘要并 exit 0;任一断言失败即 exit 1;用法错误 exit 2。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[1]
SCRIPTS = BUNDLE / "scripts"
SUFFIX_TABLE = BUNDLE / "references" / "legal_suffix_table.json"

sys.path.insert(0, str(SCRIPTS))
from cross_ledger import verify_anchor  # noqa: E402

POLICY = {
    "thresholds": {"high": 0.9, "low": 0.2},
    "weights": {
        "exact_norm": 0.4,
        "core_eq": 0.15,
        "core_containment": 0.15,
        "token_jaccard": 0.1,
        "initial_surname": 0.2,
    },
}

PATENT_SRC = """SYNTHETIC SELF-CHECK FIXTURE -- not a real patent document.
Record SC-PAT-1
Title: Deterministic reconciliation of bibliographic entities
Applicant: Acme, Inc.
Applicant: Globex Ltd.
Assignee: Initech LLC
Inventors: Zhang Wei; Priya Nair
"""

PAPER_SRC = """SYNTHETIC SELF-CHECK FIXTURE -- not a real paper.
Paper SC-PAP-1
Authors: Wei Zhang; P. Nair
Affiliation: ACME INCORPORATED
Affiliation: ACME Incorporated Research Lab
Prior-art entity: Globex GmbH
Cited entity: Umbrella Corp
"""

LEFT_ENTITIES = [
    {"id": "SC-APP-1", "raw": "Acme, Inc.", "role": "applicant"},
    {"id": "SC-APP-2", "raw": "Globex Ltd.", "role": "applicant"},
    {"id": "SC-ASG-1", "raw": "Initech LLC", "role": "assignee"},
    {"id": "SC-INV-1", "raw": "Zhang Wei", "role": "inventor"},
    {"id": "SC-INV-2", "raw": "Priya Nair", "role": "inventor"},
]

RIGHT_ENTITIES = [
    {"id": "SC-AU-1", "raw": "Wei Zhang", "role": "author"},
    {"id": "SC-AU-2", "raw": "P. Nair", "role": "author"},
    {"id": "SC-AFF-1", "raw": "ACME INCORPORATED", "role": "affiliation"},
    {"id": "SC-AFF-2", "raw": "ACME Incorporated Research Lab", "role": "affiliation"},
    {"id": "SC-PA-1", "raw": "Globex GmbH", "role": "prior_art_entity"},
    {"id": "SC-CIT-1", "raw": "Umbrella Corp", "role": "cited_entity"},
]


def run(script, *args):
    proc = subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(
            f"{script} exited {proc.returncode}\nstdout:{proc.stdout}\n"
            f"stderr:{proc.stderr}")
    return proc


def auto_pair(report, lraw, rraw):
    for m in report["auto_matches"]:
        if m["left"].get("raw") == lraw and m["right"].get("raw") == rraw:
            return m
    return None


def cand_pair(report, lraw, rraw):
    for grp in report["candidate_pairs"]:
        if grp["left"].get("raw") != lraw:
            continue
        for alt in grp["alternatives"]:
            if alt["right"].get("raw") == rraw:
                return alt
    return None


def non_match_has(report, side, raw):
    return any(n["side"] == side and n["entity"].get("raw") == raw
               for n in report["non_matches"])


def main():
    checks = 0

    def ok(label):
        nonlocal checks
        checks += 1
        print(f"  PASS {label}")

    tmp = Path(tempfile.mkdtemp(prefix="entity_reconciler_selfcheck_"))
    patent_src = tmp / "sc_patent.txt"
    paper_src = tmp / "sc_paper.txt"
    patent_src.write_text(PATENT_SRC, encoding="utf-8")
    paper_src.write_text(PAPER_SRC, encoding="utf-8")

    left_raw = tmp / "left_raw.json"
    right_raw = tmp / "right_raw.json"
    left_norm = tmp / "left_norm.json"
    right_norm = tmp / "right_norm.json"
    policy_path = tmp / "policy.json"
    report_path = tmp / "match_report.json"
    ledger_path = tmp / "ledger.json"

    left_raw.write_text(json.dumps(LEFT_ENTITIES, ensure_ascii=False), encoding="utf-8")
    right_raw.write_text(json.dumps(RIGHT_ENTITIES, ensure_ascii=False), encoding="utf-8")
    policy_path.write_text(json.dumps(POLICY), encoding="utf-8")

    print("[1/3] name_norm.py")
    run("name_norm.py", "--suffix-table", str(SUFFIX_TABLE),
        "--input", str(left_raw), "--output", str(left_norm))
    run("name_norm.py", "--suffix-table", str(SUFFIX_TABLE),
        "--input", str(right_raw), "--output", str(right_norm))

    ln = {e["raw"]: e for e in json.loads(left_norm.read_text(encoding="utf-8"))["names"]}
    rn = {e["raw"]: e for e in json.loads(right_norm.read_text(encoding="utf-8"))["names"]}
    acme = ln["Acme, Inc."]
    rules = [r["rule"] for r in acme["applied_rules"]]
    if acme["normalized"] == "acme inc" and "R2" in rules and "R3" in rules \
            and acme["kind"] == "org" and acme["canonical_suffix"] == "inc":
        ok('audit trail: "Acme, Inc." -> "acme inc" with R2+R3 recorded, kind=org')
    else:
        raise AssertionError(f"FAILED: audit trail for 'Acme, Inc.': {acme}")
    acme_inc = rn["ACME INCORPORATED"]
    rules2 = [r["rule"] for r in acme_inc["applied_rules"]]
    r4 = [r for r in acme_inc["applied_rules"] if r["rule"] == "R4"]
    if acme_inc["normalized"] == "acme inc" and "R4" in rules2 and r4 \
            and r4[0]["raw"] == "acme incorporated" \
            and r4[0]["normalized"] == "acme inc":
        ok('audit trail: R4 records "acme incorporated" -> "acme inc" (raw->normalized)')
    else:
        raise AssertionError(f"FAILED: R4 audit for 'ACME INCORPORATED': {acme_inc}")
    if ln["Zhang Wei"]["kind"] == "person":
        ok('kind: "Zhang Wei" classified person')
    else:
        raise AssertionError("FAILED: 'Zhang Wei' not classified person")

    print("[2/3] entity_match.py")
    run("entity_match.py", "--left", str(left_norm), "--right", str(right_norm),
        "--policy", str(policy_path), "--output", str(report_path))
    report = json.loads(report_path.read_text(encoding="utf-8"))

    m = auto_pair(report, "Acme, Inc.", "ACME INCORPORATED")
    if m and m["score"] >= POLICY["thresholds"]["high"]:
        ok('"Acme, Inc." ≡ "ACME INCORPORATED" -> auto band')
    else:
        raise AssertionError("FAILED: Acme pair not auto")

    c = cand_pair(report, "Globex Ltd.", "Globex GmbH")
    if c and "suffix_conflict" in c["flags"]:
        ok('"Globex Ltd." vs "Globex GmbH" -> candidate with suffix_conflict')
    else:
        raise AssertionError("FAILED: Globex pair not candidate/suffix_conflict")

    c = cand_pair(report, "Zhang Wei", "Wei Zhang")
    if c and "order_variant" in c["flags"] \
            and auto_pair(report, "Zhang Wei", "Wei Zhang") is None:
        ok('"Zhang Wei" vs "Wei Zhang" -> candidate order_variant, NOT auto')
    else:
        raise AssertionError("FAILED: Zhang Wei pair handling")

    if non_match_has(report, "left", "Initech LLC") \
            and non_match_has(report, "right", "Umbrella Corp"):
        ok('"Initech LLC" / "Umbrella Corp" stay unmatched (non_match)')
    else:
        raise AssertionError("FAILED: clear non-match was matched")

    st = report["statistics"]
    if st["auto_count"] == len(report["auto_matches"]) and \
            st["non_match_count"] == len(report["non_matches"]):
        ok("statistics recomputed consistently with lists")
    else:
        raise AssertionError("FAILED: statistics inconsistent")

    # thresholds must come from the policy file, not hardcoded
    policy2 = dict(POLICY)
    policy2["thresholds"] = {"high": 1.01, "low": 0.2}
    policy2_path = tmp / "policy_high101.json"
    report2_path = tmp / "match_report2.json"
    policy2_path.write_text(json.dumps(policy2), encoding="utf-8")
    run("entity_match.py", "--left", str(left_norm), "--right", str(right_norm),
        "--policy", str(policy2_path), "--output", str(report2_path))
    report2 = json.loads(report2_path.read_text(encoding="utf-8"))
    if report2["policy"]["thresholds"]["high"] == 1.01 \
            and auto_pair(report2, "Acme, Inc.", "ACME INCORPORATED") is None \
            and cand_pair(report2, "Acme, Inc.", "ACME INCORPORATED") is not None:
        ok("thresholds loaded from policy JSON (high=1.01 demotes Acme to candidate)")
    else:
        raise AssertionError("FAILED: thresholds appear hardcoded")

    print("[3/3] cross_ledger.py")
    run("cross_ledger.py", "--left", str(left_norm), "--right", str(right_norm),
        "--left-sources", str(patent_src), "--right-sources", str(paper_src),
        "--policy", str(policy_path), "--output", str(ledger_path))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))

    if len(ledger["rows"]) == len(LEFT_ENTITIES):
        ok("ledger has one row per left entity")
    else:
        raise AssertionError("FAILED: ledger row count")

    anchored = [r for r in ledger["rows"] if r["anchors"]["left"]]
    if all(verify_anchor(r["anchors"]["left"]) for r in anchored) and anchored:
        ok(f"all {len(anchored)} left anchors are verbatim substrings (sha256+span)")
    else:
        raise AssertionError("FAILED: left anchor verification")

    right_anchored = [r for r in ledger["rows"] if r["anchors"]["right"]]
    if all(verify_anchor(r["anchors"]["right"]) for r in right_anchored) and right_anchored:
        ok(f"all {len(right_anchored)} right anchors are verbatim substrings")
    else:
        raise AssertionError("FAILED: right anchor verification")

    # negative assertion: a forged quote must fail verification
    forged = dict(anchored[0]["anchors"]["left"])
    forged["quote"] = ("X" + forged["quote"][1:]) if forged["quote"] else "X"
    if not verify_anchor(forged):
        ok("negative: forged quote fails anchor verification")
    else:
        raise AssertionError("FAILED: forged quote was accepted!")

    nm = [r for r in ledger["rows"] if r["entity_raw"] == "Initech LLC"][0]
    if nm["band"] == "non_match" and nm["matched_counterpart_raw"] is None \
            and nm["anchors"]["right"] is None:
        ok('unmatched side stays null ("Initech LLC": counterpart null, never inferred)')
    else:
        raise AssertionError("FAILED: unmatched row not null")

    cand_rows = [r for r in ledger["rows"] if r["band"] == "candidate"]
    if cand_rows and all(r["alternatives"] and r["requires_review"] for r in cand_rows):
        ok(f"{len(cand_rows)} candidate row(s) carry alternatives + requires_review")
    else:
        raise AssertionError("FAILED: candidate rows lack alternatives")

    print(f"\nSELFCHECK OK: {checks} assertions passed. Fixtures: {tmp}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
