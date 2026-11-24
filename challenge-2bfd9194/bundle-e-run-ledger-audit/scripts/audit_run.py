#!/usr/bin/env python3
"""audit_run.py — 独立审计器（stdlib only，不 import 本 skill 其他脚本）。

只读 /input 与 /app/output，重新核算，逐项 PASS/FAIL 写 AUDIT_REPORT.json：
  A. input 每个材料文件在 LIBRARY_MANIFEST.jsonl 中有且仅有一条去向记录
  B. library/ 每个文件回指一条 journal done 记录，且 sha256 双端一致（文件实测=清单=日志）
  C. journal 每条 begin 有闭合 done/failed/reconciled；无坏行
  D. duplicates.json 与 version_chains.json 中列出的文件真实存在于 /input
  E. result.json status 与证据一致（有 failed 未恢复却报 complete → FAIL；
     其他项有 FAIL 却报 complete → FAIL）

用法：python3 audit_run.py --input /input --out /app/output
退出码：全 PASS = 0，有 FAIL = 1，自身无法运行 = 2。
"""
import argparse
import hashlib
import json
import os
import sys
import unicodedata
from datetime import datetime, timezone

CHUNK = 65536
EXCLUDE = {"case.json", "task.md"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def nfc(s):
    return unicodedata.normalize("NFC", s)


def walk_input(input_dir):
    """返回 {nfc_relpath: abspath}；不可读/错误也返回 relpath（值为 None 表不可读）。"""
    out = {}
    for root, dirs, files in os.walk(input_dir):
        dirs.sort()
        for name in sorted(files):
            if root == input_dir and name in EXCLUDE:
                continue
            ap = os.path.join(root, name)
            rel = nfc(os.path.relpath(ap, input_dir))
            out[rel] = ap if os.access(ap, os.R_OK) else None
    return out


def walk_tree(base):
    """返回 {nfc_relpath: sha256}（base 不存在返回空 dict）。"""
    out = {}
    if not os.path.isdir(base):
        return out
    for root, dirs, files in os.walk(base):
        dirs.sort()
        for name in sorted(files):
            ap = os.path.join(root, name)
            rel = nfc(os.path.relpath(ap, base))
            try:
                out[rel] = sha256_file(ap)
            except OSError:
                out[rel] = None
    return out


def read_jsonl(path):
    recs, bad = [], []
    if not os.path.exists(path):
        return recs, ["missing_file:" + path]
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                bad.append("line_%d_unparseable" % i)
    return recs, bad


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def main(argv=None):
    ap = argparse.ArgumentParser(description="run-ledger-audit 独立审计器")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    input_dir, out_dir = os.path.abspath(a.input), os.path.abspath(a.out)
    checks = []

    # ---- 装载证据 ----
    manifest, man_bad = read_jsonl(os.path.join(out_dir, "LIBRARY_MANIFEST.jsonl"))
    journal, jou_bad = read_jsonl(os.path.join(out_dir, "operations_journal.jsonl"))
    result = read_json(os.path.join(out_dir, "result.json"), {}) or {}
    input_files = walk_input(input_dir)
    library_files = walk_tree(os.path.join(out_dir, "library"))

    # ---- A. input 全覆盖且唯一 ----
    srcs = [m.get("src") for m in manifest if m.get("src")]
    missing_in_manifest = sorted(r for r in input_files if r not in srcs)
    dup_in_manifest = sorted({s for s in srcs if srcs.count(s) > 1})
    no_dst = sorted(m.get("src") for m in manifest
                    if m.get("src") and not m.get("dst") and m.get("action") not in
                    ("skipped_simulated_corrupt", "skipped_unreadable", "skipped_outside_input"))
    a_ok = not missing_in_manifest and not dup_in_manifest and not no_dst and not man_bad
    checks.append({"id": "A", "name": "input_manifest_coverage",
                   "status": "PASS" if a_ok else "FAIL",
                   "detail": {"input_files": len(input_files), "manifest_records": len(srcs),
                              "missing_in_manifest": missing_in_manifest,
                              "duplicate_src_records": dup_in_manifest,
                              "records_without_destination": no_dst, "manifest_bad_lines": man_bad}})

    # ---- B. library 文件回指 done 且哈希双端一致 ----
    done_by_dst = {}
    for r in journal:
        if r.get("op") == "done" and r.get("dst"):
            done_by_dst[r["dst"]] = r.get("sha256_dst")
    man_by_dst = {m.get("dst"): m.get("sha256") for m in manifest if m.get("dst")}
    b_problems = []
    for rel, sha in sorted(library_files.items()):
        dst = "library/" + rel
        jsha = done_by_dst.get(dst)
        msha = man_by_dst.get(dst)
        if jsha is None:
            b_problems.append({"file": dst, "problem": "no_done_record_in_journal"})
        elif sha is None:
            b_problems.append({"file": dst, "problem": "file_unreadable"})
        elif sha != jsha or (msha is not None and sha != msha):
            b_problems.append({"file": dst, "problem": "sha256_mismatch",
                               "file_sha": sha, "journal_sha": jsha, "manifest_sha": msha})
    checks.append({"id": "B", "name": "library_done_hash_consistency",
                   "status": "PASS" if not b_problems else "FAIL",
                   "detail": {"library_files": len(library_files), "problems": b_problems}})

    # ---- C. journal 闭合 ----
    closed = {}
    corrupt = []
    for r in journal:
        op = r.get("op")
        if op == "corrupt_line":
            corrupt.append(r.get("line_no"))
        elif op in ("done", "failed", "reconciled") and r.get("id"):
            closed.setdefault(r["id"], []).append(op)
    open_begins = sorted(r.get("id") for r in journal
                         if r.get("op") == "begin" and r.get("id") and r["id"] not in closed)
    c_ok = not open_begins and not corrupt and not jou_bad
    checks.append({"id": "C", "name": "journal_closure",
                   "status": "PASS" if c_ok else "FAIL",
                   "detail": {"journal_records": len(journal),
                              "begins_without_close": open_begins,
                              "corrupt_lines": corrupt, "journal_bad_lines": jou_bad}})

    # ---- D. 重复组与版本链文件真实存在 ----
    d_problems = []
    for fname, key in (("duplicates.json", "groups"), ("version_chains.json", "chains")):
        doc = read_json(os.path.join(out_dir, fname), {}) or {}
        for grp in doc.get(key, []) or []:
            members = grp.get("members") or ([grp.get("canonical")] + list(grp.get("aliases") or []))
            for m in members:
                if isinstance(m, dict):
                    m = m.get("path") or m.get("src")
                if m and nfc(m) not in input_files:
                    d_problems.append({"file": fname, "member": m, "problem": "not_in_input"})
    checks.append({"id": "D", "name": "dup_and_chain_members_exist",
                   "status": "PASS" if not d_problems else "FAIL",
                   "detail": {"problems": d_problems}})

    # ---- E. result.json status 与证据一致 ----
    status = result.get("status")
    unrecovered = []
    done_ids = {r.get("id") for r in journal if r.get("op") == "done"}
    for r in journal:
        if r.get("op") == "failed" and r.get("id") and r["id"] not in done_ids:
            unrecovered.append(r["id"])
    e_problems = []
    if status == "complete":
        if unrecovered:
            e_problems.append({"problem": "failed_ops_unrecovered_but_status_complete",
                               "ids": sorted(set(unrecovered))})
        for c in checks:
            if c["status"] == "FAIL":
                e_problems.append({"problem": "check_%s_failed_but_status_complete" % c["id"]})
    if status not in ("in_progress", "complete", "partial", "blocked"):
        e_problems.append({"problem": "unknown_status", "status": status})
    checks.append({"id": "E", "name": "status_consistent_with_evidence",
                   "status": "PASS" if not e_problems else "FAIL",
                   "detail": {"result_status": status,
                              "unrecovered_failed_ids": sorted(set(unrecovered)),
                              "problems": e_problems}})

    overall = "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL"
    report = {"audit": "run-ledger-audit independent audit",
              "generated_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
              "input_dir": input_dir, "output_dir": out_dir,
              "overall": overall, "checks": checks}
    path = os.path.join(out_dir, "AUDIT_REPORT.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    print(json.dumps({"overall": overall,
                      "checks": {c["id"]: c["status"] for c in checks}},
                     ensure_ascii=False))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
