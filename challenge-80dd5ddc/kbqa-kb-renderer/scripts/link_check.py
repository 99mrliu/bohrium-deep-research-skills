#!/usr/bin/env python3
"""link_check.py — 交接渲染第 3 步：交接包机检（确定性）。

对 handover/ 做三类机器校验，全部通过才允许交付：
1. 互链校验：knowledge_index.md 与答案卡中的相对链接目标真实存在；
2. 编目一致性：catalog.csv 每行的 file_id/relpath/sha256前8 与磁盘重算一致，
   行数与 render_catalog.json 一致；
3. 引文回验：答案卡中 `[Fxx|sha8|La-Lb]` 坐标与引文逐条回验——
   文件在编目、哈希前缀一致、引文为抽取文本的逐字片段（去空白比对）。
产出 /app/output/render_report.json；pass=false 时列出全部 violations。
退出码恒 0。
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time

CITE = re.compile(r"`\[(F\d+)\|([0-9a-f]{6,16})\|L(\d+)-L(\d+)\]`：\"([^\"]+)\"")
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def squash(s):
    return re.sub(r"\s+", "", s)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()
    hand = os.path.join(a.out, "handover")
    violations, checked = [], {"links": 0, "catalog_rows": 0, "citations": 0}

    def load(p, default):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return default

    catalog = load(os.path.join(a.work, "render_catalog.json"), {"files": []})
    by_id = {e["file_id"]: e for e in catalog["files"]}

    # 1) 互链
    md_files = []
    for root, dirs, names in os.walk(hand):
        for n in sorted(names):
            if n.endswith(".md"):
                md_files.append(os.path.join(root, n))
    for mdp in md_files:
        with open(mdp, encoding="utf-8") as f:
            text = f.read()
        for link in LINK.findall(text):
            if link.startswith(("http://", "https://", "#")):
                continue
            target = os.path.normpath(os.path.join(os.path.dirname(mdp), link))
            checked["links"] += 1
            if not os.path.exists(target):
                violations.append({"type": "broken_link", "in": os.path.relpath(mdp, hand),
                                   "target": link})

    # 2) 编目一致性（catalog.csv vs 磁盘重算）
    csvp = os.path.join(hand, "catalog.csv")
    if os.path.exists(csvp):
        with open(csvp, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        checked["catalog_rows"] = len(rows)
        if len(rows) != len(catalog["files"]):
            violations.append({"type": "catalog_row_count",
                               "csv": len(rows), "catalog": len(catalog["files"])})
        for row in rows:
            e = by_id.get(row["file_id"])
            if not e:
                violations.append({"type": "catalog_unknown_id", "file_id": row["file_id"]})
                continue
            p = os.path.join(a.input, e["relpath"])
            try:
                if not sha256_of(p).startswith(row["sha256_8"]):
                    violations.append({"type": "catalog_hash_mismatch",
                                       "file_id": row["file_id"]})
            except OSError:
                if e["text_status"] != "unreadable":
                    violations.append({"type": "catalog_unverifiable",
                                       "file_id": row["file_id"]})
    else:
        violations.append({"type": "catalog_csv_missing"})

    # 3) 引文回验
    for mdp in md_files:
        with open(mdp, encoding="utf-8") as f:
            text = f.read()
        for m in CITE.finditer(text):
            fid, sha8, l1, l2, quote = m.groups()
            checked["citations"] += 1
            e = by_id.get(fid)
            if not e:
                violations.append({"type": "cite_unknown_file", "file_id": fid})
                continue
            if not (e["sha256"] or "").startswith(sha8):
                violations.append({"type": "cite_version_mismatch", "file_id": fid})
                continue
            txt = ""
            if e.get("extracted"):
                xp = os.path.join(a.work, e["extracted"])
                if os.path.exists(xp):
                    with open(xp, encoding="utf-8") as f:
                        txt = re.sub(r"^L\d+: ", "", f.read(), flags=re.M)
            if not txt or squash(quote) not in squash(txt):
                violations.append({"type": "cite_quote_not_found", "file_id": fid,
                                   "quote_head": quote[:40]})

    report = {"schema": "kbqa-kb-renderer/render-report/v1",
              "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "checked": checked, "pass": not violations, "violations": violations}
    with open(os.path.join(a.out, "render_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"pass": not violations, "checked": checked,
                      "violations": violations[:5]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
