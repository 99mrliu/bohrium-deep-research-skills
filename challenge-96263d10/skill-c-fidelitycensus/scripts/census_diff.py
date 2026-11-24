#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""census_diff.py -- 两份普查的差异裁决：每个差异都定位到单元与 token。

文本序列：忽略空白差异（格式适配允许重排空白），其余逐单元比对，
定位首个不一致单元并给出前后文。数字/引用 token：多重集差集。
对象计数：逐项对比。退出码：0 全等; 1 有差异; 2 用法/输入错误。

用法:
  python3 census_diff.py 源普查.json 产物普查.json --out diff.json
"""
import argparse, json, re, sys

def norm(t):
    return re.sub(r"\s+", " ", t or "").strip()

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source")
    ap.add_argument("output")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    src = json.load(open(a.source, encoding="utf-8"))
    out = json.load(open(a.output, encoding="utf-8"))

    diffs = []
    # 1. 文本单元序列
    su = [norm(u["text"]) for u in src["units"]]
    ou = [norm(u["text"]) for u in out["units"]]
    if len(su) != len(ou):
        diffs.append({"kind": "unit_count", "detail": "源 %d 单元 vs 产物 %d 单元" % (len(su), len(ou)),
                      "locator": "global"})
    for i, (x, y) in enumerate(zip(su, ou)):
        if x != y:
            diffs.append({"kind": "text_mismatch",
                          "detail": "单元 %d 文本不同" % i,
                          "locator": "unit %d" % i,
                          "source_text": x[:200], "output_text": y[:200]})
            if sum(1 for d in diffs if d["kind"] == "text_mismatch") >= 20:
                diffs.append({"kind": "truncated", "detail": "文本差异超过 20 处，仅列前 20", "locator": "global"})
                break
    # 2. 数字 / 引用 token 多重集
    for cat in ("numeric", "citation"):
        s = dict(src["tokens"][cat]); o = dict(out["tokens"][cat])
        lost = {k: s[k] - o.get(k, 0) for k in s if s[k] > o.get(k, 0)}
        added = {k: o[k] - s.get(k, 0) for k in o if o[k] > s.get(k, 0)}
        if lost:
            diffs.append({"kind": "%s_lost" % cat, "detail": json.dumps(lost, ensure_ascii=False), "locator": "tokens"})
        if added:
            diffs.append({"kind": "%s_added" % cat, "detail": json.dumps(added, ensure_ascii=False), "locator": "tokens"})
    # 3. 对象计数
    so, oo = src["objects"], out["objects"]
    for k in sorted(set(so) | set(oo)):
        if so.get(k, 0) != oo.get(k, 0):
            diffs.append({"kind": "object_count", "detail": "%s: 源 %d vs 产物 %d" % (k, so.get(k, 0), oo.get(k, 0)),
                          "locator": "objects.%s" % k})

    report = {"source": a.source, "output": a.output,
              "identical": not diffs, "diff_count": len(diffs), "diffs": diffs}
    json.dump(report, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("identical=%s diffs=%d -> %s" % (not diffs, len(diffs), a.out))
    for d in diffs[:10]:
        print("  - [%s] %s @%s" % (d["kind"], d["detail"][:100], d["locator"]))
    sys.exit(1 if diffs else 0)

if __name__ == "__main__":
    main()
