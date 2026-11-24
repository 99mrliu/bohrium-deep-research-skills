#!/usr/bin/env python3
"""catalog_check.py — 编目完整性校验 + 修复台账（bundle 1，确定性，stdlib-only）。

独立复核 forensic_scan 的编目：重新遍历输入目录，逐文件重算 SHA-256，
验证"每个真实文件都有一条编目记录、每条记录都与磁盘一致"——编目可核验性
由此而来，而不是自述。随后产出 repair_ledger.json（修复台账）与
catalog_report.md（人读报告）：重复副本处置建议、不可读文件清单、
当前版本指认、编目遗漏。

台账条目全部带状态 proposed/applied/skipped/failed，不把未完成写成完成。
"""
import argparse
import hashlib
import json
import os
import sys
import time

SKIP_NAMES = {"case.json", "task.md"}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.work, "catalog.json"), encoding="utf-8") as f:
        catalog = json.load(f)
    lineage_path = os.path.join(a.work, "lineage.json")
    lineage = json.load(open(lineage_path, encoding="utf-8")) if os.path.exists(lineage_path) \
        else {"version_groups": []}

    by_rel = {e["relpath"]: e for e in catalog["files"]}
    check = {"verified": [], "hash_mismatch": [], "missing_from_catalog": [],
             "catalog_entries_gone": [], "unverifiable": []}
    input_root = os.path.abspath(a.input)
    seen = set()
    for root, dirs, names in os.walk(input_root):
        dirs.sort()
        for n in sorted(names):
            if n in SKIP_NAMES and os.path.abspath(root) == input_root:
                continue
            if n.startswith("."):
                continue
            p = os.path.join(root, n)
            if os.path.islink(p) or not os.path.isfile(p):
                continue
            rel = os.path.relpath(p, input_root)
            seen.add(rel)
            e = by_rel.get(rel)
            if not e:
                check["missing_from_catalog"].append(rel)
                continue
            try:
                h = sha256_of(p)
                if h == e["sha256"]:
                    check["verified"].append(e["file_id"])
                else:
                    check["hash_mismatch"].append(
                        {"file_id": e["file_id"], "relpath": rel,
                         "catalog": e["sha256"][:12], "disk": h[:12]})
            except (OSError, PermissionError):
                check["unverifiable"].append({"file_id": e["file_id"], "relpath": rel})
    for rel, e in by_rel.items():
        if rel not in seen:
            check["catalog_entries_gone"].append({"file_id": e["file_id"], "relpath": rel})

    # 修复台账
    ledger = []
    # 重复组去重时的保留件：优先 lineage 裁定的 current 版本，其次非 copy 命名，再次小编号
    current_ids = {g["members"][0]["file_id"] for g in lineage.get("version_groups", [])}
    by_id = {e["file_id"]: e for e in catalog["files"]}

    def keep_priority(fid):
        name = by_id[fid]["relpath"].lower()
        is_copy = any(k in name for k in ("copy", "副本", "复件", "backup", "bak"))
        return (fid in current_ids, not is_copy, tuple(-int(c) for c in fid[1:]))

    for g in catalog.get("byte_duplicate_groups", []):
        members = sorted(g["members"], key=keep_priority, reverse=True)
        keep = members[0]
        for m in members[1:]:
            e = next(x for x in catalog["files"] if x["file_id"] == m)
            ledger.append({"action": "quarantine_duplicate", "status": "proposed",
                           "target": e["relpath"], "keep_file_id": keep,
                           "basis": "identical sha256 " + g["sha256"][:12]})
    for e in catalog["files"]:
        if e["text_status"] in ("unreadable", "extraction_failed", "no_text_layer",
                                "extraction_tool_missing"):
            ledger.append({"action": "needs_attention", "status": "proposed",
                           "target": e["relpath"], "text_status": e["text_status"],
                           "basis": "文本不可用；需恢复权限/OCR/转换工具后重扫"})
    for g in lineage.get("version_groups", []):
        cur = g["members"][0]
        ledger.append({"action": "designate_current_version", "status": "proposed",
                       "target": cur["relpath"], "file_id": cur["file_id"],
                       "basis": ("行政备注 " + cur["admin_note"]["source"]
                                 if cur.get("admin_note") else
                                 "文件名版本/mtime 排序"),
                       "historical": [m["relpath"] for m in g["members"][1:]]})
    for item in check["missing_from_catalog"]:
        ledger.append({"action": "catalog_gap", "status": "failed",
                       "target": item, "basis": "磁盘存在但编目缺失，需重跑 forensic_scan"})

    passed = (not check["hash_mismatch"] and not check["missing_from_catalog"]
              and not check["catalog_entries_gone"])
    report = {
        "schema": "kbqa-ingest-forensics/catalog-check/v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "independent_reverification": check,
        "catalog_pass": passed,
        "repair_ledger": ledger,
    }
    with open(os.path.join(a.out, "repair_ledger.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    lines = ["# 编目校验与修复报告", "",
             "- 生成时间：%s" % report["generated_at"],
             "- 独立复核通过：%s" % ("是" if passed else "否"),
             "- 已核验文件：%d；哈希不一致：%d；编目遗漏：%d；编目多余：%d；不可核验：%d"
             % (len(check["verified"]), len(check["hash_mismatch"]),
                len(check["missing_from_catalog"]), len(check["catalog_entries_gone"]),
                len(check["unverifiable"])),
             "", "## 修复台账（proposed，未执行的动作不写成已完成）", ""]
    for it in ledger:
        lines.append("- [%s] %s → `%s`（依据：%s）" % (
            it["status"], it["action"], it["target"], it["basis"]))
    if check["hash_mismatch"] or check["missing_from_catalog"]:
        lines += ["", "## 编目不一致（必须先解决再信任编目）", ""]
        for m in check["hash_mismatch"]:
            lines.append("- 哈希不一致：%(relpath)s（catalog=%(catalog)s disk=%(disk)s）" % m)
        for m in check["missing_from_catalog"]:
            lines.append("- 编目遗漏：%s" % m)
    with open(os.path.join(a.out, "catalog_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps({"catalog_pass": passed, "verified": len(check["verified"]),
                      "ledger_items": len(ledger)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
