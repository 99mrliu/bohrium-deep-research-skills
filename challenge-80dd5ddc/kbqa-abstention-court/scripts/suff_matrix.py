#!/usr/bin/env python3
"""suff_matrix.py — 充分性法庭第 2 步：问题-证据面覆盖矩阵（确定性，stdlib-only）。

把每个问题机械分解为证据面（facet）：
  entity   命名实体/专有名词（连续大写/数字字母组合、中文专名段）
  numeric  问题中的数值与单位
  keyword  其余实义词（去停用词）
再逐面在索引中检索命中情况，形成 coverage_matrix.json：
每题 = facet × {found, files, best_lines}。矩阵是充分性裁决的机器依据，
模型不得跳过矩阵直接下结论。退出码恒 0。
"""
import argparse
import json
import os
import re
import sys
import time

STOP = set("the a an of in on at is are was were be been to for with by from as".split())
STOPCHAR = set("的了是在和有与及或对哪些什么多少为何是否怎么怎样请列出说明介绍呢吗吧啊各其该此"
               "每就都也还但又而且或者因为所以如果这那你我他她它们个种样上下中内里外前后")
CJK_SEG = re.compile(r"[一-鿿]{2,}")
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,}|[一-鿿]+|\d+(?:\.\d+)?\s*(?:%|℃|°C|摄氏度|eV|V|nm|h|小时)?")
UNIT_PAT = re.compile(r"\d+(?:\.\d+)?\s*(?:%|℃|°C|摄氏度|K|eV|Ω|mV|V|mA|W|nm|mm|cm|m|g|kg|h|小时|ppm|MPa)")


def facets_of(question):
    facets = []
    for m in UNIT_PAT.finditer(question):
        facets.append({"type": "numeric", "term": m.group(0)})
    seen_cjk = set()
    for m in TOKEN.finditer(question):
        t = m.group(0)
        if UNIT_PAT.fullmatch(t):
            continue
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_\-]{1,}", t):
            facets.append({"type": "entity", "term": t})
        else:
            for seg in CJK_SEG.findall(t):
                # 中文长段切成 2-4 字窗口取实义片段；含虚词字的窗口丢弃
                if len(seg) < 2:
                    continue
                if len(seg) <= 4:
                    windows = [seg]
                else:
                    windows = [seg[i:i + 3] for i in range(0, len(seg) - 2, 3)]
                for w in windows:
                    if w in seen_cjk or any(c in STOPCHAR for c in w):
                        continue
                    seen_cjk.add(w)
                    facets.append({"type": "keyword", "term": w})
    # 去重保序
    out, seen = [], set()
    for f in facets:
        if f["term"] not in seen:
            seen.add(f["term"])
            out.append(f)
    return out[:12]


def load_lines(work, entry):
    p = os.path.join(work, entry["extracted"]) if entry.get("extracted") else None
    if not p or not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^L(\d+): (.*)$", line.rstrip("\n"))
            if m:
                out.append((int(m.group(1)), m.group(2)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.work, "suff_index.json"), encoding="utf-8") as f:
        index = json.load(f)
    with open(os.path.join(a.work, "questions.json"), encoding="utf-8") as f:
        questions = json.load(f)["questions"]

    docs = {}  # fid -> [(line, text)]
    for e in index["files"]:
        if e["text_status"] == "ok":
            docs[e["file_id"]] = load_lines(a.work, e)

    matrix = []
    for q in questions:
        fq = {"question_id": q["question_id"], "question": q["question"],
              "facets": [], "coverage": None}
        for fac in facets_of(q["question"]):
            term = fac["term"]
            hits = []
            for fid, lines in docs.items():
                for ln, txt in lines:
                    if term.lower() in txt.lower():
                        hits.append({"file_id": fid, "line": ln,
                                     "text": txt.strip()[:120]})
                        if len(hits) >= 3:
                            break
                if len(hits) >= 3:
                    break
            fq["facets"].append({"type": fac["type"], "term": term,
                                 "found": bool(hits), "hits": hits})
        n = len(fq["facets"])
        found = sum(1 for x in fq["facets"] if x["found"])
        fq["coverage"] = {"facets_total": n, "facets_found": found,
                          "ratio": round(found / n, 3) if n else 0.0}
        matrix.append(fq)
    out = {"schema": "kbqa-abstention-court/coverage-matrix/v1",
           "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "matrix": matrix}
    with open(os.path.join(a.out, "coverage_matrix.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps([{"question_id": m["question_id"],
                       "coverage": m["coverage"]} for m in matrix], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
