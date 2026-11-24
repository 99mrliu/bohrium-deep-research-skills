#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""corpus_search.py — 在本地语料上执行已校验的检索式（双轨：patent / npl）。

仅依赖 python3 标准库。退出码：0 成功；2 spec 违规；3 一致性失败（未使用）。

执行语义（可解释、可复算）：
  * 文档类型由前 matter 标记 `doctype:` 判定：patent → patent 轨；paper → npl 轨；
    无标记的文件记入 files_skipped（绝不臆测内容）。
  * 匹配为字面词组匹配：大小写不敏感、词组须连续出现；ASCII 词项额外要求
    字母数字边界（防止 "H01M" 误中 "H01M12"）；CJK 词项按连续子串判定。
  * 块间按 spec 的 operator 语义：本文档实现“每块至少命中 1 个词项”(AND 语义)；
    operator 为 OR 的块与相邻块合并取并集（罕见，默认全部 AND）。
  * exclusion_terms 命中即整篇排除（附理由），不计入命中也不计入零命中。
  * classification_codes 过滤仅作用于 patent 轨（R5）。
  * 去重键：patent 轨 = family（无则规范化公开号）；npl 轨 = DOI（无则规范化标题）。
  * 每条命中保留：doc_id, track, matched_terms（哪个块哪个词）, locator（file+line）,
    dedup_key。无任何匹配/被过滤的文档计入 no_match_docs，供筛选分母与遗漏说明。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from query_build import load_spec, validate_spec  # noqa: E402

DOC_EXTS = (".txt", ".md")


def parse_doc(path):
    """解析前 matter（--- 包裹的 key: value 行）与全文行列表。"""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    meta = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            kv = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
            if kv:
                meta[kv.group(1).strip().lower()] = kv.group(2).strip()
    return meta, text.splitlines()


def term_matches_line(term, line):
    """字面词组匹配：大小写不敏感；ASCII 词项要求字母数字边界。"""
    t = term.casefold()
    l = line.casefold()
    if re.fullmatch(r"[a-z0-9 ./+\-]+", t):
        pattern = r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])"
        return re.search(pattern, l) is not None
    return t in l


def norm_pub_number(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def norm_title(s):
    s = (s or "").casefold()
    s = re.sub(r"[^0-9a-z一-鿿]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def dedup_key(track, meta):
    if track == "patent":
        fam = (meta.get("family") or "").strip()
        if fam:
            return "FAM:" + re.sub(r"\s+", "", fam).upper()
        return "PUB:" + norm_pub_number(meta.get("pub_number"))
    doi = (meta.get("doi") or "").strip()
    if doi:
        return "DOI:" + doi.casefold()
    return "TITLE:" + norm_title(meta.get("title"))


def collect_files(roots):
    files = []
    for root in roots:
        if os.path.isfile(root):
            files.append(root)
            continue
        for dirpath, _dirs, names in os.walk(root):
            for n in sorted(names):
                if n.endswith(DOC_EXTS):
                    files.append(os.path.join(dirpath, n))
    return sorted(dict.fromkeys(files))


def run(spec, roots):
    blocks = spec.get("blocks", [])
    excl = spec.get("exclusion_terms") or []
    codes = {c.strip().casefold() for c in (spec.get("classification_codes") or [])
             if isinstance(c, str) and c.strip()}

    files = collect_files(roots)
    hits, no_match_docs, excluded_docs, files_skipped = [], [], [], []
    term_doc_counts = {}   # "块名::词项" -> 命中该词项的文档数
    block_doc_counts = {}  # 块名 -> 命中该块至少一词的文档数

    for path in files:
        meta, lines = parse_doc(path)
        doctype = (meta.get("doctype") or "").strip().lower()
        doc_id = meta.get("doc_id") or os.path.splitext(os.path.basename(path))[0]
        if doctype not in ("patent", "paper"):
            files_skipped.append({"file": path,
                                  "reason": "缺少 doctype 前 matter 标记，未纳入任何轨道"})
            continue
        track = "patent" if doctype == "patent" else "npl"

        # 逐块匹配（统计与命中判定共用）
        block_results = []
        for b in blocks:
            bname = b.get("name") or ""
            term_hits = []
            for t in b.get("terms", []):
                text = (t.get("text") or "").strip()
                if not text:
                    continue
                lns = [ln for ln, line in enumerate(lines, 1)
                       if term_matches_line(text, line)]
                key = "%s::%s" % (bname, text)
                if lns:
                    term_doc_counts[key] = term_doc_counts.get(key, 0) + 1
                    term_hits.append({"term": text,
                                      "intent": t.get("intent"),
                                      "lines": lns})
            if term_hits:
                block_doc_counts[bname] = block_doc_counts.get(bname, 0) + 1
            block_results.append((bname, term_hits))

        # 排除词：命中即整篇排除
        excl_hit = None
        for e in excl:
            for ln, line in enumerate(lines, 1):
                if term_matches_line(e["text"], line):
                    excl_hit = {"term": e["text"],
                                "reason": e.get("reason", ""), "line": ln}
                    break
            if excl_hit:
                break
        if excl_hit:
            excluded_docs.append({
                "doc_id": doc_id, "track": track, "file": path,
                "reason": "命中排除词 %r（第 %d 行）：%s"
                          % (excl_hit["term"], excl_hit["line"], excl_hit["reason"])})
            continue

        # 块覆盖：每块至少命中 1 词（AND 语义）
        uncovered = [bname for bname, th in block_results if not th]
        if uncovered:
            no_match_docs.append({"doc_id": doc_id, "track": track, "file": path,
                                  "reason": "未覆盖概念块: %s" % ", ".join(uncovered)})
            continue

        # 分类号过滤：仅 patent 轨（R5）
        if track == "patent" and codes:
            doc_codes = {c.strip().casefold()
                         for c in re.split(r"[;,]", meta.get("classification", ""))
                         if c.strip()}
            if not (codes & doc_codes):
                no_match_docs.append({"doc_id": doc_id, "track": track, "file": path,
                                      "reason": "分类号过滤未通过（patent 轨限定: %s）"
                                                % ", ".join(sorted(codes))})
                continue

        matched_terms = [{"block": bname, "terms": th}
                         for bname, th in block_results if th]
        first = matched_terms[0]["terms"][0]
        hits.append({
            "doc_id": doc_id,
            "track": track,
            "matched_terms": matched_terms,
            "locator": {"file": path, "line": first["lines"][0]},
            "dedup_key": dedup_key(track, meta),
        })

    # 去重合并：patent 轨按同族/公开号，npl 轨按 DOI/标题
    records = {}
    for h in hits:
        k = h["dedup_key"]
        if k in records:
            rec = records[k]
            rec["members"].append(h["doc_id"])
            rec["locators"].append(h["locator"])
            for mt in h["matched_terms"]:
                tgt = next((x for x in rec["matched_terms"]
                            if x["block"] == mt["block"]), None)
                if tgt is None:
                    rec["matched_terms"].append(mt)
                    continue
                have = {tt["term"] for tt in tgt["terms"]}
                for tt in mt["terms"]:
                    if tt["term"] not in have:
                        tgt["terms"].append(tt)
        else:
            records[k] = {"doc_id": k, "track": h["track"],
                          "members": [h["doc_id"]],
                          "matched_terms": h["matched_terms"],
                          "locators": [h["locator"]],
                          "dedup_key": k}

    zero_hit_terms = sorted(
        "%s::%s" % (b.get("name") or "", (t.get("text") or "").strip())
        for b in blocks for t in b.get("terms", [])
        if (t.get("text") or "").strip()
        and "%s::%s" % (b.get("name") or "", (t.get("text") or "").strip())
        not in term_doc_counts)
    uncovered_blocks = sorted(b.get("name") or "" for b in blocks
                              if (b.get("name") or "") not in block_doc_counts)

    return {
        "meta": {
            "research_question": spec.get("research_question"),
            "roots": roots,
            "files_scanned": len(files),
            "files_skipped": files_skipped,
            "term_doc_counts": term_doc_counts,
            "zero_hit_terms": zero_hit_terms,
            "uncovered_blocks": uncovered_blocks,
        },
        "hits": hits,
        "records": list(records.values()),
        "no_match_docs": no_match_docs,
        "excluded_docs": excluded_docs,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="本地语料双轨检索执行")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("run")
    pr.add_argument("--spec", required=True)
    pr.add_argument("--roots", nargs="+", required=True)
    pr.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    try:
        spec = load_spec(args.spec)
    except (OSError, json.JSONDecodeError) as exc:
        print("FAIL R6: 无法读取 spec：%s" % exc, file=sys.stderr)
        return 2
    errors = validate_spec(spec)
    if errors:
        for rid, msg in errors:
            print("FAIL %s: %s" % (rid, msg), file=sys.stderr)
        print("run 中止：spec 未通过校验", file=sys.stderr)
        return 2

    result = run(spec, args.roots)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    m = result["meta"]
    print("run: 扫描 %d 个文件（跳过 %d），原始命中 %d，去重后记录 %d，"
          "排除 %d，未命中 %d → %s"
          % (m["files_scanned"], len(m["files_skipped"]), len(result["hits"]),
             len(result["records"]), len(result["excluded_docs"]),
             len(result["no_match_docs"]), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
