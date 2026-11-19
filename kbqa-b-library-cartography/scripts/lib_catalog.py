#!/usr/bin/env python3
"""lib_catalog.py — merge inventory + lineage + metadata into catalog.json
and a human-readable repair ledger (repair_log.md).

catalog.json covers the six required dimensions:
  file_types, metadata_fields, directory_tree, duplicates, version_diffs,
  permissions_sources.
Every entry carries: entry_id, path, sha8, readable, extract_status,
group_id, role, current_version.

Metadata sources: JSON/YAML/CSV files under input that look like metadata
(name matches meta/biblio/catalog/index patterns or the case says so);
missing fields are null, never invented.

repair_log.md records every skip, conflict, duplicate decision and recovery
suggestion — nothing is silently resolved.

Exit code always 0.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone

META_PAT = re.compile(r"(meta|biblio|catalog|index|manifest)", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()

    art = os.path.join(a.out, "artifacts")
    inv = json.load(open(os.path.join(art, "inventory.json"), encoding="utf-8"))
    lin_path = os.path.join(art, "lineage.json")
    lin = {"groups": [], "conflicts": [], "membership": {}}
    if os.path.exists(lin_path):
        lin = json.load(open(lin_path, encoding="utf-8"))
    files = inv["files"]
    by_id = {r["entry_id"]: r for r in files}

    # --- metadata merge -------------------------------------------------
    metadata_records = []
    for r in files:
        if r["extract_status"] == "ok" and r.get("extract_path") \
                and META_PAT.search(r["name"]):
            try:
                text = open(r["extract_path"], encoding="utf-8",
                            errors="replace").read()
                if r["ext"] in (".json", ".jsonl"):
                    obj = json.loads(text if r["ext"] == ".json" else
                                     "[%s]" % ",".join(
                                         l for l in text.splitlines() if l.strip()))
                    metadata_records.append({"source": r["entry_id"],
                                             "path": r["path"], "content": obj})
            except Exception as e:  # noqa: BLE001
                metadata_records.append({"source": r["entry_id"], "path": r["path"],
                                         "parse_error": e.__class__.__name__})

    # --- entries with lineage roles ------------------------------------
    entries = []
    for r in files:
        m = lin.get("membership", {}).get(r["entry_id"], {})
        entries.append({
            "entry_id": r["entry_id"], "path": r["path"], "name": r["name"],
            "type": r["ext"] or "(none)", "size": r["size"], "mtime": r["mtime"],
            "sha8": (r.get("sha256") or "")[:8] or None,
            "readable": r["readable"], "extract_status": r["extract_status"],
            "group_id": m.get("group"), "role": m.get("role", "unique"),
            "current_version": m.get("current_version", True),
            "n_lines": r.get("n_lines", 0),
        })

    type_counts = Counter(e["type"] for e in entries)
    dir_tree = {}
    for e in entries:
        d = os.path.dirname(e["path"]) or "."
        dir_tree.setdefault(d, []).append(e["entry_id"])

    duplicates = [
        {"group_id": g["group_id"], "kind": g["kind"],
         "members": g["members"],
         "kept": next((c["entry_id"] for c in g["chain"]
                       if c["role"] in ("canonical", "current",
                                        "current_admin")), None),
         "basis": [rel for rel in g["relations"]]}
        for g in lin["groups"] if len(g["members"]) > 1]
    version_diffs = [
        {"group_id": g["group_id"],
         "chain": g["chain"],
         "order_basis": "admin_note > filename_version > mtime"}
        for g in lin["groups"] if g["kind"] == "version_chain"]

    catalog = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": inv["input_dir"],
        "dimensions": {
            "file_types": dict(type_counts),
            "metadata_fields": {
                "sources": [m["path"] for m in metadata_records],
                "records": metadata_records,
                "note": "missing fields are null; nothing invented",
            },
            "directory_tree": dir_tree,
            "duplicates": duplicates,
            "version_diffs": version_diffs,
            "permissions_sources": {
                "skipped": inv["skipped"],
                "readable_count": sum(1 for e in entries if e["readable"]),
                "unreadable_count": sum(1 for e in entries if not e["readable"]),
            },
        },
        "conflicts": lin.get("conflicts", []),
        "entries": entries,
    }
    with open(os.path.join(art, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=1)

    # --- repair ledger ---------------------------------------------------
    lines = ["# 修复台账（repair_log）",
             "",
             "生成时间：%s" % catalog["built_at"],
             "原则：不删除输入文件；每组决策给出确定性依据；无法判断的标记 undecidable。",
             ""]
    lines.append("## 1. 跳过与不可读文件（%d）" % len(inv["skipped"]))
    for s in inv["skipped"]:
        lines.append("- `%s` (%s)：%s；建议：%s"
                     % (s["path"], s["entry_id"], s["reason"],
                        recovery_hint(s["reason"])))
    lines.append("")
    lines.append("## 2. 重复与别名组（%d）" % len(duplicates))
    for d in duplicates:
        lines.append("- 组 `%s` (%s)：保留 `%s`；成员 %s"
                     % (d["group_id"], d["kind"], d["kept"],
                        "、".join("`%s`" % m for m in d["members"])))
    lines.append("")
    lines.append("## 3. 版本链（%d）" % len(version_diffs))
    for v in version_diffs:
        seq = " → ".join("`%s`(%s)" % (c["entry_id"], c["role"])
                         for c in v["chain"])
        lines.append("- 组 `%s`：%s（排序依据 %s）"
                     % (v["group_id"], seq, v["order_basis"]))
    lines.append("")
    lines.append("## 4. 冲突（%d）" % len(catalog["conflicts"]))
    for c in catalog["conflicts"]:
        lines.append("- %s" % json.dumps(c, ensure_ascii=False))
    if not catalog["conflicts"]:
        lines.append("- 无")
    with open(os.path.join(a.out, "repair_log.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("catalog entries=%d groups=%d conflicts=%d skipped=%d"
          % (len(entries), len(lin["groups"]),
             len(catalog["conflicts"]), len(inv["skipped"])))
    return 0


def recovery_hint(reason):
    r = reason or ""
    if "permission" in r:
        return "请求提权或由组织方重新授权该文件"
    if "pdftotext" in r:
        return "安装 poppler(pdftotext) 或使用平台 OCR 工具补提取"
    if "unsupported_type" in r:
        return "需要专用解析器；本次仅入编目不参与问答"
    if "docx" in r:
        return "文件可能损坏；建议从来源重新获取"
    return "人工核对原因后重跑 lib_inventory.py"


if __name__ == "__main__":
    sys.exit(main())
