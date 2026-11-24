#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_forensics.py — 独立校验器（只读 /input 与 /app/output，仅标准库）。

不信任任何中间产物：重算输入与库内文件哈希、重跑签名与截断检查，
逐条核对 LIBRARY_MANIFEST.jsonl、FORENSICS_REPORT.json、隔离判定、
重复组、版本链、日志闭合，输出 audit_report.json（逐项 PASS/FAIL）。

用法：python3 verify_forensics.py --input /input --out /app/output
"""
import argparse
import json
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import forensics  # noqa: E402

SKIP_NAMES = {"case.json", "task.md"}
TERMINAL_JOURNAL_STATUS = {"done", "already_committed_identical", "alias_recorded",
                           "conflict_renamed"}


def nfc(s):
    return unicodedata.normalize("NFC", s)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))
    return rows


class Audit:
    def __init__(self):
        self.checks = []

    def check(self, name, ok, detail=""):
        self.checks.append({"name": name,
                            "status": "PASS" if ok else "FAIL",
                            "detail": detail})
        return ok

    def report(self):
        fails = [c for c in self.checks if c["status"] == "FAIL"]
        return {
            "auditor": "verify_forensics.py（独立校验器，只读重算）",
            "overall": "PASS" if not fails else "FAIL",
            "summary": {"total": len(self.checks), "pass": len(self.checks) - len(fails),
                        "fail": len(fails)},
            "checks": self.checks,
        }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    input_dir, out_dir = os.path.abspath(args.input), os.path.abspath(args.out)
    au = Audit()

    # ---- 输入文件清单（重走文件系统）
    input_files = []
    for dirpath, _dirs, files in os.walk(input_dir):
        for fn in files:
            rel = os.path.relpath(os.path.join(dirpath, fn), input_dir)
            if nfc(rel) in SKIP_NAMES and dirpath == input_dir:
                continue
            input_files.append(rel)
    input_files.sort(key=nfc)

    # ---- 交付物存在性
    manifest_p = os.path.join(out_dir, "LIBRARY_MANIFEST.jsonl")
    report_p = os.path.join(out_dir, "FORENSICS_REPORT.json")
    journal_p = os.path.join(out_dir, "operations_journal.jsonl")
    dup_p = os.path.join(out_dir, "duplicates.json")
    vc_p = os.path.join(out_dir, "version_chains.json")
    result_p = os.path.join(out_dir, "result.json")
    for p in (manifest_p, report_p, journal_p, dup_p, vc_p, result_p):
        au.check("deliverable_exists:%s" % os.path.basename(p),
                 os.path.isfile(p), p)
    if not all(os.path.isfile(p) for p in (manifest_p, report_p)):
        _emit(out_dir, au)
        return 1

    manifest = load_jsonl(manifest_p)
    report = load_json(report_p)
    frep = {r["path"]: r for r in report.get("records", [])}

    # ---- 1. manifest 行数 = 输入文件数，且一一对应
    mrows = {r["src"]: r for r in manifest}
    au.check("manifest_row_count_equals_input_count",
             len(manifest) == len(input_files),
             "manifest=%d input=%d" % (len(manifest), len(input_files)))
    au.check("manifest_covers_every_input",
             sorted(mrows, key=nfc) == input_files,
             "缺失=%s 多余=%s" % (sorted(set(input_files) - set(mrows))[:5],
                                  sorted(set(mrows) - set(input_files))[:5]))

    # ---- 2. 源端 fixity：重算输入哈希 == manifest.src_sha256
    bad = []
    for rel in input_files:
        try:
            h = forensics.stream_sha256(os.path.join(input_dir, rel))
        except OSError as exc:
            row = mrows.get(rel, {})
            if row.get("forensic_verdict") == "unreadable":
                continue  # 不可读文件源端无法重算，另行核对
            bad.append("%s: %s" % (rel, exc))
            continue
        if mrows.get(rel, {}).get("src_sha256") != h:
            bad.append(rel)
    au.check("src_fixity_recomputed_hash_matches_manifest", not bad, "; ".join(bad[:5]))

    # ---- 3. 目标端 fixity：重算库内文件哈希 == dst_sha256，fixity_match 为真
    bad = []
    for row in manifest:
        if not row.get("copied"):
            continue
        tgt = os.path.join(out_dir, row["target"])
        if not os.path.isfile(tgt):
            bad.append("missing target %s" % row["target"])
            continue
        h = forensics.stream_sha256(tgt)
        if h != row.get("dst_sha256") or row.get("fixity_match") is not True:
            bad.append(row["target"])
    au.check("dst_fixity_recomputed_hash_matches_manifest", not bad, "; ".join(bad[:5]))

    # ---- 4. 重跑取证：verdict 与 FORENSICS_REPORT 一致
    bad = []
    for rel in input_files:
        try:
            rec = forensics.forensic_file(os.path.join(input_dir, rel), rel)
        except Exception as exc:  # noqa: BLE001 - 校验器自身也要留证
            bad.append("%s: %s" % (rel, exc))
            continue
        want = frep.get(rel, {}).get("verdict")
        if rec["verdict"] != want:
            bad.append("%s: recomputed=%s report=%s" % (rel, rec["verdict"], want))
        if mrows.get(rel, {}).get("forensic_verdict") != rec["verdict"]:
            bad.append("%s: manifest verdict 不一致" % rel)
    au.check("forensic_verdicts_recomputed_match_report", not bad, "; ".join(bad[:5]))

    # ---- 5. 隔离判定：verdict≠authentic → library/_quarantine/<原相对路径>；
    #         authentic 不得进 _quarantine
    bad = []
    for row in manifest:
        v = row.get("forensic_verdict")
        tgt = row.get("target") or ""
        qp = os.path.join("library", "_quarantine", row["src"])
        if row.get("alias_of"):
            continue  # 别名行进 canonical 的目标，单独核对
        if v != "authentic":
            if tgt != qp:
                bad.append("%s 应隔离至 %s，实际 %s" % (row["src"], qp, tgt))
        else:
            if nfc(tgt).startswith(nfc(os.path.join("library", "_quarantine"))):
                bad.append("%s 为 authentic 却被隔离" % row["src"])
    # 别名行：目标必须等于其 canonical 的目标
    for row in manifest:
        if row.get("alias_of"):
            canon = mrows.get(row["alias_of"], {})
            if row.get("target") != canon.get("target"):
                bad.append("别名 %s 目标与 canonical %s 不一致" % (row["src"], row["alias_of"]))
    au.check("quarantine_placement_correct", not bad, "; ".join(bad[:5]))

    # ---- 6. 重复组：成员哈希一致、canonical 为 mtime 最早
    bad = []
    try:
        groups = load_json(dup_p).get("groups", [])
        for g in groups:
            paths = [g["canonical"]] + g.get("aliases", [])
            shas = set()
            mtimes = {}
            for p in paths:
                st = os.stat(os.path.join(input_dir, p))
                mtimes[p] = st.st_mtime
                shas.add(forensics.stream_sha256(os.path.join(input_dir, p)))
            if len(shas) != 1 or shas.pop() != g["sha256"]:
                bad.append("组 %s 哈希不一致" % g["canonical"])
            if mtimes[g["canonical"]] != min(mtimes.values()):
                bad.append("组 %s 的 canonical 非 mtime 最早" % g["canonical"])
        # 所有重复都被发现：输入中同哈希文件必须同组
        by_hash = {}
        for rel in input_files:
            by_hash.setdefault(forensics.stream_sha256(os.path.join(input_dir, rel)),
                               []).append(rel)
        known = {p for g in groups for p in [g["canonical"]] + g.get("aliases", [])}
        for sha, ps in by_hash.items():
            if len(ps) > 1 and not set(ps) <= known:
                bad.append("遗漏重复组：%s" % ps)
    except (OSError, ValueError) as exc:
        bad.append(str(exc))
    au.check("duplicate_groups_consistent", not bad, "; ".join(bad[:5]))

    # ---- 7. 版本链：成员词干一致、内容互异、supersedes 按 mtime 升序
    bad = []
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import run_case  # 复用 normalize_stem（只读函数）
        for ch in load_json(vc_p).get("chains", []):
            stems = {run_case.normalize_stem(os.path.basename(p)) for p in ch["members"]}
            if stems != {ch["stem"]}:
                bad.append("链 %s 词干不一致" % ch.get("stem"))
            shas = {forensics.stream_sha256(os.path.join(input_dir, p))
                    for p in ch["members"]}
            if len(shas) < 2:
                bad.append("链 %s 内容未互异" % ch.get("stem"))
            for e in ch.get("edges", []):
                m1 = os.stat(os.path.join(input_dir, e["from"])).st_mtime
                m2 = os.stat(os.path.join(input_dir, e["to"])).st_mtime
                if e.get("relation") != "supersedes" or m1 > m2:
                    bad.append("链 %s 边 %s→%s 时序错误" % (ch.get("stem"), e["from"], e["to"]))
    except (OSError, ValueError, KeyError) as exc:
        bad.append(str(exc))
    au.check("version_chains_valid", not bad, "; ".join(bad[:5]))

    # ---- 8. 日志闭合：全部条目处于终态，且含 apply stage_complete 事件
    bad = []
    try:
        journal = load_jsonl(journal_p)
        for e in journal:
            if e.get("event") == "stage_complete":
                continue
            if e.get("status") not in TERMINAL_JOURNAL_STATUS:
                bad.append("seq=%s status=%s" % (e.get("seq"), e.get("status")))
        if not any(e.get("event") == "stage_complete" and e.get("stage") == "apply"
                   for e in journal):
            bad.append("缺少 apply stage_complete 闭合事件")
    except (OSError, ValueError) as exc:
        bad.append(str(exc))
    au.check("operations_journal_closed", not bad, "; ".join(bad[:5]))

    # ---- 9. result.json 诚实性：有 case_id 与 contract_fields；
    #         存在隔离项时 status 不得为 complete
    bad = []
    try:
        res = load_json(result_p)
        if not res.get("case_id"):
            bad.append("缺 case_id")
        if not isinstance(res.get("contract_fields"), dict):
            bad.append("缺 contract_fields")
        quarantined = [r for r in report.get("records", [])
                       if r.get("verdict") != "authentic"]
        if quarantined and res.get("status") == "complete":
            bad.append("存在 %d 个隔离文件但 status=complete" % len(quarantined))
    except (OSError, ValueError) as exc:
        bad.append(str(exc))
    au.check("result_json_honest_status", not bad, "; ".join(bad[:5]))

    _emit(out_dir, au)
    return 0 if au.report()["overall"] == "PASS" else 1


def _emit(out_dir, au):
    rep = au.report()
    path = os.path.join(out_dir, "audit_report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("audit overall=%s (%d/%d PASS) -> %s"
          % (rep["overall"], rep["summary"]["pass"], rep["summary"]["total"], path))


if __name__ == "__main__":
    sys.exit(main())
