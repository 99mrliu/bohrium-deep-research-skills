#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_quotes.py — 审计级摘录校验：归一化子串匹配 + 字符偏移报告。

对 recheck/<doc_id>.jsonl 中每行 sides[].quote：
  1. 归一化（连字符断行还原 + 全部空白折叠为单空格）；
  2. 在所标 page 的归一化页文本中做子串匹配，报告字符偏移区间；
  3. 页内不命中则搜全文档：命中他页→page_mismatch；完全不命中→not_found；
  4. 任一 side 失败 → 整行降级（verified=false, downgraded=true），原 status 保留
     但下游聚合时按"未验证"降权处理。
产出：verify_report.json；并就地更新 recheck/*.jsonl（追加 verification 字段）。
仅标准库。
"""
import argparse
import json
import os
import re
import sys


def normalize(s):
    """统一归一化：去连字符断行、折叠一切空白为单空格。"""
    if not s:
        return ""
    s = re.sub(r"-\s*\n\s*", "", s)      # 连字符断行还原
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    return rows


def verify_doc(work_dir, recheck_path, report_failures):
    doc_id = os.path.basename(recheck_path)[:-len(".jsonl")]
    pages = load_jsonl(os.path.join(work_dir, "pages", doc_id + ".jsonl"))
    norm_pages = {p["page"]: normalize(p.get("text", "")) for p in pages}
    whole = " ".join(norm_pages[k] for k in sorted(norm_pages))
    rows = load_jsonl(recheck_path)
    n_rows_ok = 0
    for row in rows:
        sides = row.get("sides") or []
        ver = {"verified": True, "offsets": []}
        if not sides:
            # 无摘录行（如 absent 缺口）不参与锚定校验，标记 n/a
            ver = {"verified": True, "offsets": [], "note": "no_quote"}
            row["verification"] = ver
            n_rows_ok += 1
            continue
        for idx, sd in enumerate(sides):
            nq = normalize(sd.get("quote", ""))
            page = sd.get("page")
            entry = {"side": idx, "page": page, "found": False}
            if nq and page in norm_pages:
                pos = norm_pages[page].find(nq)
                if pos >= 0:
                    entry.update({"found": True,
                                  "offset": [pos, pos + len(nq)]})
                    ver["offsets"].append(entry)
                    continue
            # 页内未命中 → 全文搜
            pos = whole.find(nq) if nq else -1
            if pos >= 0:
                entry.update({"found": False, "reason": "page_mismatch",
                              "doc_offset": [pos, pos + len(nq)]})
            else:
                entry.update({"found": False, "reason": "not_found"})
            ver["verified"] = False
            ver["offsets"].append(entry)
            report_failures.append({
                "row_id": row.get("id"), "doc_id": doc_id, "side": idx,
                "page": page, "reason": entry["reason"],
                "quote_preview": nq[:120]})
        if not ver["verified"]:
            row["downgraded"] = True  # 整行降级
        else:
            n_rows_ok += 1
        row["verification"] = ver
    with open(recheck_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows), n_rows_ok


def main():
    ap = argparse.ArgumentParser(description="摘录归一化校验")
    ap.add_argument("--work-dir", default="/app/work")
    args = ap.parse_args()
    rdir = os.path.join(args.work_dir, "recheck")
    failures = []
    total_rows, total_ok, total_sides = 0, 0, 0
    if os.path.isdir(rdir):
        for fn in sorted(os.listdir(rdir)):
            if fn.endswith(".jsonl"):
                nr, nok = verify_doc(args.work_dir,
                                     os.path.join(rdir, fn), failures)
                total_rows += nr
                total_ok += nok
    report = {
        "total_rows": total_rows,
        "verified_rows": total_ok,
        "failed_rows": total_rows - total_ok,
        "failures": failures,
        "normalization": "连字符断行还原 + 空白折叠为单空格；归一化子串匹配",
    }
    with open(os.path.join(args.work_dir, "verify_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"rows": total_rows, "verified": total_ok,
                      "failed": total_rows - total_ok}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
