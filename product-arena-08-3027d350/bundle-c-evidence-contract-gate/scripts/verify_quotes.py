#!/usr/bin/env python3
"""verify_quotes.py — 逐字引文门禁（证据与契约核验技能 C 的组件 1）。

规则：凡是要写进交付物的"原文引述"（quote），必须能在抽取源文本中逐字命中
（NFKC + 空白归一化后）。未命中者给 difflib 近似提示；确需保留的必须走
waiver 并写明 waiver_reason。门禁不过，引文不得进入 result.json。

输入：
    --claims   claims.jsonl，每行 {"id","quote","page"?,"waiver"?,"waiver_reason"?}
    --sources  抽取源文本目录（*.txt）或单个 .txt 文件
输出 gate_report.json（始终写盘）：
    verified[] / near_miss[{id,ratio,hint}] / missing[] / waived[] / violations[]
退出码 0=全部通过或合规豁免；1=存在未豁免的未命中引文；3=输入不可用。
"""
import argparse
import difflib
import glob
import json
import os
import sys
import unicodedata


def normalize(s):
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("　", " ")
    return " ".join(s.split()).lower()


def load_sources(path):
    texts = []
    if os.path.isdir(path):
        files = sorted(glob.glob(os.path.join(path, "*.txt")))
    else:
        files = [path]
    for fp in files:
        with open(fp, encoding="utf-8", errors="replace") as f:
            texts.append({"file": os.path.basename(fp), "text": f.read()})
    return texts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--claims", required=True)
    ap.add_argument("--sources", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    if not os.path.exists(args.claims):
        print(json.dumps({"status": "failed", "reason": "claims_missing"}))
        return 3
    sources = load_sources(args.sources)
    if not sources:
        print(json.dumps({"status": "failed", "reason": "sources_empty"}))
        return 3
    corpus = [{"file": s["file"], "norm": normalize(s["text"]),
               "raw": s["text"]} for s in sources]

    verified, near_miss, missing, waived, violations = [], [], [], [], []
    with open(args.claims, encoding="utf-8") as f:
        for ln, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            claim = json.loads(line)
            cid = claim.get("id", f"line{ln}")
            quote = claim.get("quote", "")
            nq = normalize(quote)
            hit = next((c["file"] for c in corpus if nq and nq in c["norm"]),
                       None)
            if hit:
                verified.append({"id": cid, "source": hit,
                                 "page": claim.get("page")})
                continue
            best, best_file, best_ratio = "", None, 0.0
            for c in corpus:
                # 近似提示：在等长滑窗上找最高相似度
                L = len(nq)
                if L == 0 or not c["norm"]:
                    continue
                for i in range(0, max(1, len(c["norm"]) - L + 1),
                               max(1, L // 4)):
                    r = difflib.SequenceMatcher(
                        None, nq, c["norm"][i:i + L]).ratio()
                    if r > best_ratio:
                        best_ratio, best, best_file = \
                            r, c["norm"][i:i + L], c["file"]
            if claim.get("waiver"):
                if claim.get("waiver_reason"):
                    waived.append({"id": cid, "reason": claim["waiver_reason"],
                                   "nearest_ratio": round(best_ratio, 3)})
                else:
                    violations.append({"id": cid,
                                       "violation": "waiver 缺 waiver_reason"})
            else:
                entry = {"id": cid, "nearest_ratio": round(best_ratio, 3),
                         "nearest": best[:160], "nearest_file": best_file}
                (near_miss if best_ratio >= 0.6 else missing).append(entry)

    ok = not near_miss and not missing and not violations
    report = {"status": "pass" if ok else "fail",
              "counts": {"verified": len(verified),
                         "near_miss": len(near_miss),
                         "missing": len(missing),
                         "waived": len(waived),
                         "violations": len(violations)},
              "verified": verified, "near_miss": near_miss,
              "missing": missing, "waived": waived, "violations": violations,
              "rule": "未通过门禁的引文不得进入 result.json；"
                      "豁免必须带 waiver_reason"}
    with open(os.path.join(args.out, "gate_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report["counts"] | {"status": report["status"]},
                     ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
