#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_quotes.py — 引用门控校验。

读取模型填写的 assessments/<doc_id>.jsonl（每行
{"item_id","judgment","quote","locator","rationale"}），
归一化后校验 quote 是否真实出现在所标页；找不到时尝试全文检索并报告实际页。
校验失败的判断降级为 not_assessable 并记入 verify_report.json；
降级后的结果写 assessments_verified/<doc_id>.jsonl。
仅标准库。
"""
import argparse
import json
import os
import re
import sys
import unicodedata

JUDGMENTS = ("met", "partial", "not_met", "not_assessable")
LOCATOR_RE = re.compile(r"p(\d+)(?:\s*[.．]\s*¶\s*(\d+))?")


def log(msg):
    print("[verify_quotes] %s" % msg, file=sys.stderr)


def normalize(s):
    """统一归一化：NFKC（全/半角折叠）→ 去连字符断行 → 去全部空白 → 小写折叠。"""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("-\n", "").replace("-\r\n", "")
    s = s.replace("­", "")  # soft hyphen
    s = re.sub(r"\s+", "", s)
    return s.casefold()


def parse_locator(locator):
    m = LOCATOR_RE.search(locator or "")
    if not m:
        return None, None
    return int(m.group(1)), (int(m.group(2)) if m.group(2) else None)


def load_pages(work_dir, doc_id):
    pages = {}
    path = os.path.join(work_dir, "pages", doc_id + ".jsonl")
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    obj = json.loads(line)
                    pages[int(obj["page"])] = obj.get("text", "")
    except Exception as e:
        log("页面读取失败 %s: %s" % (path, e))
    return pages


def verify_one(quote, locator, pages):
    """返回 (status, actual_pages)。status ∈ ok / wrong_page / not_found / missing_quote / no_locator"""
    if not quote or not quote.strip():
        return "missing_quote", []
    page, _para = parse_locator(locator)
    if page is None:
        return "no_locator", []
    nq = normalize(quote)
    if not nq:
        return "missing_quote", []
    norm_pages = {p: normalize(t) for p, t in pages.items()}
    if page in norm_pages and nq in norm_pages[page]:
        return "ok", [page]
    actual = [p for p, t in sorted(norm_pages.items()) if nq in t]
    if actual:
        return "wrong_page", actual
    return "not_found", []


def main():
    ap = argparse.ArgumentParser(description="摘录引用门控校验")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--assessments-dir", default=None)
    args = ap.parse_args()

    adir = args.assessments_dir or os.path.join(args.work, "assessments")
    outdir = os.path.join(args.work, "assessments_verified")
    os.makedirs(outdir, exist_ok=True)

    report = {"total": 0, "ok": 0, "wrong_page": 0, "not_found": 0,
              "missing_quote": 0, "no_locator": 0, "skipped_na": 0,
              "invalid_judgment": 0, "downgraded": [], "details": [],
              "files_missing": []}

    if not os.path.isdir(adir):
        log("评估目录不存在: %s（模型尚未填写任何判断）" % adir)
        report["files_missing"].append(adir)
        with open(os.path.join(args.work, "verify_report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return 0

    for fn in sorted(os.listdir(adir)):
        if not fn.endswith(".jsonl"):
            continue
        doc_id = os.path.splitext(fn)[0]
        pages = load_pages(args.work, doc_id)
        out_lines = []
        with open(os.path.join(adir, fn), "r", encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception as e:
                    report["details"].append({"doc_id": doc_id, "line": ln,
                                              "status": "parse_error", "error": str(e)})
                    continue
                report["total"] += 1
                item_id = rec.get("item_id", "UNKNOWN")
                judgment = (rec.get("judgment") or "").strip()
                if judgment not in JUDGMENTS:
                    report["invalid_judgment"] += 1
                    rec["verification"] = {"status": "invalid_judgment",
                                           "original_judgment": judgment}
                    rec["judgment"] = "not_assessable"
                    rec["rationale"] = (rec.get("rationale") or "") + " [门控：非法判断值，已降级]"
                    report["downgraded"].append({"doc_id": doc_id, "item_id": item_id,
                                                 "reason": "invalid_judgment"})
                    out_lines.append(rec)
                    continue
                if judgment == "not_assessable":
                    report["skipped_na"] += 1
                    rec["verification"] = {"status": "skipped_na"}
                    out_lines.append(rec)
                    continue
                status, actual = verify_one(rec.get("quote"), rec.get("locator"), pages)
                report["details"].append({"doc_id": doc_id, "item_id": item_id,
                                          "status": status, "actual_pages": actual})
                if status == "ok":
                    report["ok"] += 1
                    rec["verification"] = {"status": "ok"}
                else:
                    report[status] = report.get(status, 0) + 1
                    rec["verification"] = {"status": status, "actual_pages": actual}
                    rec["judgment"] = "not_assessable"
                    rec["rationale"] = (rec.get("rationale") or "") + \
                        " [门控：摘录校验失败(%s)，已降级]" % status
                    report["downgraded"].append({"doc_id": doc_id, "item_id": item_id,
                                                 "reason": status,
                                                 "actual_pages": actual})
                out_lines.append(rec)
        with open(os.path.join(outdir, fn), "w", encoding="utf-8") as f:
            for rec in out_lines:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log("%s: %d 条已校验" % (doc_id, len(out_lines)))

    with open(os.path.join(args.work, "verify_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in
                      ("total", "ok", "wrong_page", "not_found",
                       "missing_quote", "skipped_na")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
