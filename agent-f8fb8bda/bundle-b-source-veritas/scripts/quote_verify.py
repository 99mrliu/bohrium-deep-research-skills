#!/usr/bin/env python3
"""quote_verify.py — 逐字引用核验（evidence linkage gate）。

读取 --ledger 指定的 evidence_ledger.jsonl（每行一条：
{"evidence_id","doc","page","quote","field","note"}），对照 --corpus
语料目录（corpus_build.py 产物），对每条证据执行归一化子串匹配：
归一化 = NFKC + casefold + 空白压缩 + 连字符换行修复。

状态：
  verified       引用在所声明页内逐字命中
  page_mismatch  引用在文档其它页命中（页码标错；计入未回链，单独计数）
  not_verbatim   全文档归一化后仍找不到（疑似改写/臆造引用）
  doc_missing    ledger 声明的 doc 不在语料中
  quote_empty    quote 字段为空或缺失

产物（写入 --outdir，默认与 ledger 同目录）：
  verified_ledger.jsonl  每条证据追加 status / found_page / detail
  linkage_report.json    总回链率、按 field 分组回链率、未回链清单

退出码：0 全部 verified；1 存在任何非 verified（stdout 逐项失败清单）；
2 用法/IO 错误。仅标准库。
"""
import argparse
import json
import os
import re
import sys
import unicodedata

NON_VERIFIED = ("page_mismatch", "not_verbatim", "doc_missing",
                "quote_empty", "malformed_entry")


def normalize(text):
    """NFKC + casefold + 连字符换行修复 + 空白压缩。"""
    if text is None:
        return ""
    text = unicodedata.normalize("NFKC", text)
    # 修复 PDF 换行断词："experi-\nmental" -> "experimental"
    text = re.sub(r"-\s*\n\s*", "", text)
    text = text.casefold()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_corpus(corpus_dir):
    index_path = os.path.join(corpus_dir, "corpus_index.json")
    if not os.path.isfile(index_path):
        return None
    with open(index_path, encoding="utf-8") as f:
        index = json.load(f)
    docs = {}
    for d in index.get("docs", []):
        if d.get("parse_status") != "ok" or not d.get("text_file"):
            continue
        tpath = os.path.join(corpus_dir, d["text_file"])
        try:
            with open(tpath, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        docs[d["doc_id"]] = {"text": text, "spans": d.get("page_spans", [])}
    return docs


def verify_entry(entry, docs):
    eid = entry.get("evidence_id", "?")
    quote = entry.get("quote")
    if not quote or not str(quote).strip():
        return "quote_empty", None, "quote 为空"
    doc = entry.get("doc")
    if not doc or doc not in docs:
        return "doc_missing", None, f"doc '{doc}' 不在语料中"
    rec = docs[doc]
    nq = normalize(str(quote))
    if not nq:
        return "quote_empty", None, "quote 归一化后为空"
    # 页内匹配
    try:
        page = int(entry.get("page"))
    except (TypeError, ValueError):
        page = None
    spans = rec["spans"]
    if page is not None:
        for sp in spans:
            if sp.get("page") == page:
                seg = rec["text"][sp["start"]:sp["end"]]
                if nq in normalize(seg):
                    return "verified", page, "页内逐字命中"
    # 全文档匹配（定位真实页）
    for sp in spans:
        seg = rec["text"][sp["start"]:sp["end"]]
        if nq in normalize(seg):
            return "page_mismatch", sp["page"], \
                f"引用实际位于第 {sp['page']} 页，声明页为 {page}"
    return "not_verbatim", None, "归一化后全文档未命中（疑似改写或臆造）"


def main():
    ap = argparse.ArgumentParser(description="逐字引用核验（evidence linkage gate）")
    ap.add_argument("--ledger", default="/app/work/evidence_ledger.jsonl",
                    help="证据台账 JSONL（默认 /app/work/evidence_ledger.jsonl）")
    ap.add_argument("--corpus", default="/app/work/corpus",
                    help="语料目录（默认 /app/work/corpus）")
    ap.add_argument("--outdir", default=None,
                    help="产物目录（默认与 ledger 同目录）")
    args = ap.parse_args()

    if not os.path.isfile(args.ledger):
        print(f"[IO ERROR] ledger 不存在: {args.ledger}")
        return 2
    docs = load_corpus(args.corpus)
    if docs is None:
        print(f"[IO ERROR] 语料索引不存在: "
              f"{os.path.join(args.corpus, 'corpus_index.json')}"
              f"（先运行 corpus_build.py）")
        return 2

    outdir = args.outdir or os.path.dirname(os.path.abspath(args.ledger))
    os.makedirs(outdir, exist_ok=True)

    verified_entries = []
    failures = []
    total = 0
    by_field = {}
    status_count = {s: 0 for s in
                    ("verified",) + NON_VERIFIED}

    with open(args.ledger, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                entry = {"evidence_id": f"line_{lineno}"}
                status, found_page, detail = "malformed_entry", None, \
                    f"JSON 解析失败: {e}"
                status_count[status] += 1
                field = "?"
                by_field.setdefault(field, {"total": 0, "verified": 0})
                by_field[field]["total"] += 1
                failures.append(f"{entry['evidence_id']}: {status} — {detail}")
                verified_entries.append(
                    {**entry, "status": status, "found_page": found_page,
                     "detail": detail})
                continue
            status, found_page, detail = verify_entry(entry, docs)
            status_count[status] += 1
            field = str(entry.get("field", "?"))
            by_field.setdefault(field, {"total": 0, "verified": 0})
            by_field[field]["total"] += 1
            if status == "verified":
                by_field[field]["verified"] += 1
            else:
                failures.append(
                    f"{entry.get('evidence_id', '?')}: {status} — {detail}")
            verified_entries.append(
                {**entry, "status": status, "found_page": found_page,
                 "detail": detail})

    vpath = os.path.join(outdir, "verified_ledger.jsonl")
    with open(vpath, "w", encoding="utf-8") as f:
        for e in verified_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    by_field_rate = {
        k: {"total": v["total"], "verified": v["verified"],
            "linkage_rate": round(v["verified"] / v["total"], 4)
            if v["total"] else None}
        for k, v in sorted(by_field.items())}
    report = {
        "ledger": os.path.abspath(args.ledger),
        "corpus": os.path.abspath(args.corpus),
        "total": total,
        "verified": status_count["verified"],
        "page_mismatch": status_count["page_mismatch"],
        "not_verbatim": status_count["not_verbatim"],
        "doc_missing": status_count["doc_missing"],
        "quote_empty": status_count["quote_empty"],
        "malformed_entry": status_count["malformed_entry"],
        "linkage_rate": round(status_count["verified"] / total, 4)
        if total else None,
        "by_field": by_field_rate,
        "unverified": [
            {"evidence_id": e.get("evidence_id"), "status": e["status"],
             "detail": e["detail"]}
            for e in verified_entries if e["status"] != "verified"],
    }
    rpath = os.path.join(outdir, "linkage_report.json")
    with open(rpath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[quote_verify] 证据 {total} 条，verified {status_count['verified']} 条，"
          f"回链率 {report['linkage_rate']}")
    print(f"[quote_verify] 产物: {vpath} ; {rpath}")
    if failures:
        print("[quote_verify] 未回链清单:")
        for item in failures:
            print("  - " + item)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
