#!/usr/bin/env python3
"""qa_verify.py — 引文机器核验闸门（确定性，stdlib-only）。

逐条核验 citations.jsonl 中的引文：
  1. file_id 是否存在于索引；
  2. 文件当前 SHA-256 是否与引文声明的 sha8 一致（版本坐标核验）；
  3. 引文是否为该版本内容的逐字片段（去除全部空白后子串比对，兼容跨行/CJK）；
  4. 声明行号区间与真实位置的偏离（warning，不判失败但留痕）。
核验不通过时给出 difflib 最佳近似（相似度 ≥0.85 才给出），供改写后重新核验。
报告写 /app/output/citation_verification.json；verdict=all_passed 是
result.json 允许 status=completed 的前提之一。
退出码恒 0。
"""
import argparse
import difflib
import hashlib
import json
import os
import re
import sys
import time


def squash(s):
    return re.sub(r"\s+", "", s)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--citations", required=True, help="citations.jsonl：每行一条引文")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.work, "kb_index.json"), encoding="utf-8") as f:
        index = json.load(f)
    by_id = {e["file_id"]: e for e in index["files"]}

    citations = []
    with open(a.citations, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                citations.append(json.loads(line))

    results = []
    for c in citations:
        cid = c.get("claim_id") or c.get("citation_id") or "?"
        fid = c.get("file_id")
        quote = c.get("quote") or ""
        r = {"claim_id": cid, "citation_id": c.get("citation_id"),
             "file_id": fid, "pass": False,
             "reason": None, "best_match": None}
        e = by_id.get(fid)
        if not e:
            r["reason"] = "file_id_not_in_index"
        elif e["text_status"] != "ok":
            r["reason"] = "file_unreadable"
        elif c.get("sha8") and not (e["sha256"] or "").startswith(c["sha8"]):
            r["reason"] = "version_mismatch"
            r["actual_sha8"] = (e["sha256"] or "")[:8]
        elif not quote.strip():
            r["reason"] = "empty_quote"
        else:
            with open(os.path.join(a.work, e["extracted"]), encoding="utf-8") as f:
                raw = f.read()
            plain = re.sub(r"^L\d+: ", "", raw, flags=re.M)
            if squash(quote) in squash(plain):
                r["pass"] = True
                # 定位真实行号，核对声明区间
                lines = plain.splitlines()
                hits = [i + 1 for i, l in enumerate(lines)
                        if squash(quote)[:40] and squash(quote)[:40] in squash(l)]
                if not hits:
                    # 跨行引文：滑窗定位起始行
                    acc = ""
                    for i, l in enumerate(lines):
                        acc += squash(l)
                        if squash(quote)[:40] in acc:
                            hits = [max(1, i - 3)]
                            break
                r["actual_lines"] = hits[:3]
                declared = c.get("line_start")
                if declared and hits and abs(hits[0] - int(declared)) > 3:
                    r["warning"] = "line_offset>3 (declared L%s, actual L%s)" % (declared, hits[0])
            else:
                r["reason"] = "quote_not_found"
                # difflib 最佳近似
                best, best_ratio, best_ln = None, 0.0, None
                lines = plain.splitlines()
                for i in range(len(lines)):
                    for w in (1, 2, 3):
                        cand = "".join(lines[i:i + w])
                        ratio = difflib.SequenceMatcher(
                            None, squash(quote), squash(cand)).ratio()
                        if ratio > best_ratio:
                            best, best_ratio, best_ln = cand, ratio, i + 1
                if best_ratio >= 0.85:
                    r["best_match"] = {"line_start": best_ln, "text": best.strip()[:300],
                                       "similarity": round(best_ratio, 3)}
        results.append(r)

    n_pass = sum(1 for r in results if r["pass"])
    report = {"schema": "kbqa-answer-forge/citation-verification/v1",
              "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "total": len(results), "passed": n_pass, "failed": len(results) - n_pass,
              "verdict": "all_passed" if results and n_pass == len(results) else
                         ("no_citations" if not results else "has_failures"),
              "results": results}
    with open(os.path.join(a.out, "citation_verification.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in ("total", "passed", "failed", "verdict")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
