#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_index.py — 独立校验器。只读 /input 与 /app/output，重新核算，出 audit_report.json。

核对项：
1. deliverables_present     交付物齐备
2. files_rows_eq_manifest   files 表行数 == manifest 行数
3. input_coverage           /input 可扫文件数 == manifest 行数（不静默跳过）
4. hash_spot_check          抽查 20%（至少 5 条）已落库文件，哈希与磁盘一致
5. qa_evidence_real         QA_LOG 每条 evidence.path 存在且 snippet 为文件真实子串（逐条全查）
6. rebuild_diff_empty       REBUILD_DIFF 为空 diff

用法：python3 verify_index.py --input /input --out /app/output [--report audit_report.json]
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys

REQUIRED = [
    "result.json", "library", "LIBRARY_MANIFEST.jsonl", "index/catalog.db",
    "index/index_stats.json", "QA_LOG.json", "SEARCH_GUIDE.md",
    "REBUILD_DIFF.json", "duplicates.json", "version_chains.json",
    "operations_journal.jsonl", "skipped_and_conflicts.json",
]
CORRUPT_MARK = b"[[SIMULATED-CORRUPT"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def decode_any(raw):
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
        except UnicodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def check(name, ok, detail):
    return {"check": name, "status": "PASS" if ok else "FAIL", "detail": detail}


def main(argv=None):
    ap = argparse.ArgumentParser(description="独立核对索引与 QA 证据")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", help="audit_report.json 路径（默认 <out>/audit_report.json）")
    args = ap.parse_args(argv)
    out, inp = args.out, args.input
    checks = []

    # 1. 交付物齐备
    missing = [r for r in REQUIRED if not os.path.exists(os.path.join(out, r))]
    checks.append(check("deliverables_present", not missing,
                        "missing: %s" % missing if missing else "all %d present"
                        % len(REQUIRED)))

    manifest_path = os.path.join(out, "LIBRARY_MANIFEST.jsonl")
    db_path = os.path.join(out, "index", "catalog.db")
    manifest_rows = []
    if os.path.isfile(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_rows = [json.loads(l) for l in f if l.strip()]

    # 2. files 表行数 == manifest 行数
    if os.path.isfile(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM files")
        files_rows = cur.fetchone()[0]
        checks.append(check(
            "files_rows_eq_manifest", files_rows == len(manifest_rows),
            "files=%d manifest=%d" % (files_rows, len(manifest_rows))))
    else:
        conn = None
        checks.append(check("files_rows_eq_manifest", False, "catalog.db missing"))

    # 3. 输入覆盖：/input 下（除 case.json/task.md）的文件数 == manifest 行数
    input_files = []
    if os.path.isdir(inp):
        for root, dirs, names in os.walk(inp):
            dirs.sort()
            for n in sorted(names):
                rel = os.path.relpath(os.path.join(root, n), inp)
                if rel in ("case.json", "task.md"):
                    continue
                input_files.append(rel)
    checks.append(check(
        "input_coverage", bool(manifest_rows) and
        len(input_files) == len(manifest_rows),
        "input_files=%d manifest_rows=%d" % (len(input_files), len(manifest_rows))))

    # 4. 哈希抽查 20%（至少 5 条，确定性取样）
    seen_rel = set()
    checkable = []
    for m in manifest_rows:
        rel = m.get("rel_path")
        if (rel and m.get("sha256") and not m.get("duplicate_of")
                and rel not in seen_rel
                and os.path.isfile(os.path.join(out, "library", rel))):
            seen_rel.add(rel)
            checkable.append(m)
    if checkable and conn:
        n = max(5, (len(checkable) + 4) // 5)
        n = min(n, len(checkable))
        step = max(1, len(checkable) // n)
        sample = [checkable[i] for i in range(0, len(checkable), step)][:n]
        bad = []
        for m in sample:
            disk = sha256_file(os.path.join(out, "library", m["rel_path"]))
            if disk != m["sha256"]:
                bad.append(m["rel_path"])
        checks.append(check(
            "hash_spot_check", not bad,
            "sampled=%d/%d mismatches=%s" % (len(sample), len(checkable), bad)))
    else:
        checks.append(check("hash_spot_check", bool(checkable),
                            "no checkable committed files"))

    # 5. QA 证据逐条全查：path 存在、snippet 是真实子串
    qa_path = os.path.join(out, "QA_LOG.json")
    qa_bad, qa_total, ev_total = [], 0, 0
    if os.path.isfile(qa_path):
        with open(qa_path, "r", encoding="utf-8") as f:
            qa_entries = [json.loads(l) for l in f if l.strip()]
        qa_total = len(qa_entries)
        for i, e in enumerate(qa_entries):
            status = e.get("status")
            if status not in ("answered", "partially_answered", "unanswered"):
                qa_bad.append({"line": i, "reason": "bad status %r" % status})
            if status in ("answered", "partially_answered") and not e.get("evidence"):
                qa_bad.append({"line": i, "reason": "answered without evidence"})
            for ev in e.get("evidence") or []:
                ev_total += 1
                rel = ev.get("path", "")
                p = os.path.join(out, "library", rel)
                if not (os.path.isfile(p) or os.path.isfile(os.path.join(out, rel))):
                    qa_bad.append({"line": i, "reason": "evidence path missing: %s" % rel})
                    continue
                if not os.path.isfile(p):
                    p = os.path.join(out, rel)
                with open(p, "rb") as fh:
                    content = decode_any(fh.read()).replace("\n", " ")
                snippet = (ev.get("snippet") or "").strip("…").strip()
                if not snippet or snippet not in content:
                    qa_bad.append({"line": i, "reason":
                                   "snippet not substring of %s" % rel})
    else:
        qa_bad.append({"line": -1, "reason": "QA_LOG.json missing"})
    checks.append(check(
        "qa_evidence_real", not qa_bad,
        "qa_entries=%d evidence_checked=%d problems=%s" % (qa_total, ev_total, qa_bad)))

    # 6. REBUILD_DIFF 为空
    diff_path = os.path.join(out, "REBUILD_DIFF.json")
    if os.path.isfile(diff_path):
        with open(diff_path, "r", encoding="utf-8") as f:
            diff = json.load(f)
        ok = (diff.get("status") == "empty_diff"
              and not diff.get("missing_in_rebuild") and not diff.get("extra_in_rebuild"))
        checks.append(check("rebuild_diff_empty", ok,
                            "status=%s missing=%d extra=%d" % (
                                diff.get("status"),
                                len(diff.get("missing_in_rebuild", [])),
                                len(diff.get("extra_in_rebuild", [])))))
    else:
        checks.append(check("rebuild_diff_empty", False, "REBUILD_DIFF.json missing"))

    if conn:
        conn.close()
    overall = "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL"
    report = {"overall": overall, "checks": checks,
              "scope": "read-only audit of %s against %s" % (out, inp)}
    report_path = args.report or os.path.join(out, "audit_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"overall": overall,
                      "failed": [c["check"] for c in checks
                                 if c["status"] != "PASS"],
                      "report": report_path}, ensure_ascii=False))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
