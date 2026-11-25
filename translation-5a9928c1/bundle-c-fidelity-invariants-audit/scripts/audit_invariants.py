#!/usr/bin/env python3
"""audit_invariants.py — 源/译文不变量逐段句对齐比对。

用法: audit_invariants.py --translations TR.json --source source.md \
        --out audit.json --review human_review.md [--allow-explained]

类别: missing / changed / added（quantity,statistic,citation,ref）
      negation_lost / qualifier_lost（句级）
段级 signal_explanation（写进 translations.json 对应条目）说明合法差异；
配合 --allow-explained 时该类差异降级为人工确认项，不计 exit 1。
"""
import argparse, json, os, re, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_invariants import extract

SENT_SPLIT = re.compile(r'(?<=[.!?；;])\s+|(?<=[。！？])|(?<=[.!?；;])(?=[一-鿿])|\n+')

def sentences(text):
    return [s.strip() for s in SENT_SPLIT.split(text) if s.strip()]

def norm_multiset(items):
    c = Counter()
    for it in items:
        key = (it["kind"], it["normalized"], it.get("unit"))
        c[key] += 1
    return c

def diff_kind(src_items, tgt_items, kinds):
    """返回 (missing, added, changed[(from,to)], convention[])。"""
    s = norm_multiset([i for i in src_items if i["kind"] in kinds])
    t = norm_multiset([i for i in tgt_items if i["kind"] in kinds])
    missing, added = [], []
    for k in s:
        if t.get(k, 0) < s[k]:
            missing += [k] * (s[k] - t.get(k, 0))
    for k in t:
        if s.get(k, 0) < t[k]:
            added += [k] * (t[k] - s.get(k, 0))
    # 惯例抵消：值相同且（单位相同 | 任一侧无单位）→ 非硬性（裸数↔带单位、单位换写）
    convention = []
    used_conv = set()
    for mi, m in enumerate(missing):
        for ai, ad in enumerate(added):
            if ai in used_conv:
                continue
            if ad[0] == m[0] and ad[1] == m[1] and (ad[2] == m[2] or m[2] is None or ad[2] is None):
                convention.append((m, ad)); used_conv.add(ai)
                break
    if convention:
        missing = [m for m in missing if not any(m == c[0] for c in convention)]
        added = [ad for ai, ad in enumerate(added) if ai not in used_conv]
    changed = []
    used = set()
    for m in missing:
        kind, val, unit = m
        # 配对为 changed 仅限：带单位数值 或 统计量；引用/编号/裸数不配對（防误配）
        if kind not in ("statistic",) and unit is None:
            continue
        for i, ad in enumerate(added):
            if i in used:
                continue
            if ad[0] == kind and ad[2] == unit and ad[1] != val:
                changed.append((m, ad)); used.add(i); break
    missing = [m for m in missing if not any(m == c[0] for c in changed)]
    added = [ad for i, ad in enumerate(added) if i not in used]
    return missing, added, changed, convention

def flag_per_sentence(src_sents, tgt_sents, kind):
    """源句有标记而对应译句无标记 → 句索引列表。"""
    lost = []
    for i, ss in enumerate(src_sents):
        if i >= len(tgt_sents):
            break
        s_has = any(it["kind"] == kind for it in extract(ss))
        t_has = any(it["kind"] == kind for it in extract(tgt_sents[i]))
        if s_has and not t_has:
            lost.append({"sentence_index": i, "source_snippet": ss[:120]})
    return lost

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--translations", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--review", required=True)
    ap.add_argument("--allow-explained", action="store_true")
    a = ap.parse_args()

    tr = json.load(open(a.translations, encoding="utf-8"))
    items = tr["segments"] if isinstance(tr, dict) else tr
    src_text = open(a.source, encoding="utf-8", errors="replace").read()
    src_inv = extract(src_text)

    report = {"segments": [], "summary": Counter()}
    explained_counter = Counter()
    for seg in items:
        sid = seg["id"]
        sents_src = sentences(seg.get("source", ""))
        sents_tgt = sentences(seg.get("translation", ""))
        tgt_inv = extract(seg.get("translation", ""))
        issues = []
        if len(sents_src) != len(sents_tgt):
            issues.append({"class": "sentence_count_mismatch",
                           "detail": f"源 {len(sents_src)} 句 / 译 {len(sents_tgt)} 句，按序号对齐可能有偏差",
                           "confirm": True})
        mk, ad, ch, conv = diff_kind(extract(seg.get("source", "")), tgt_inv,
                                     ("quantity", "statistic", "citation", "ref"))
        for m, a2 in conv:
            issues.append({"class": "unit_convention", "kind": m[0], "value": m[1],
                           "from_unit": m[2], "to_unit": a2[2], "confirm": True})
        for k in mk:
            issues.append({"class": "missing", "kind": k[0], "value": k[1], "unit": k[2]})
        for k in ad:
            issues.append({"class": "added", "kind": k[0], "value": k[1], "unit": k[2]})
        for f, t2 in ch:
            issues.append({"class": "changed", "kind": f[0], "from": f[1], "to": t2[1], "unit": f[2]})
        for fl in flag_per_sentence(sents_src, sents_tgt, "negation"):
            issues.append({"class": "negation_lost", **fl})
        for fl in flag_per_sentence(sents_src, sents_tgt, "qualifier"):
            issues.append({"class": "qualifier_lost", **fl})

        explained = []
        if seg.get("signal_explanation") and a.allow_explained:
            keep = []
            for iss in issues:
                if iss.get("confirm") or iss["class"] in ("missing", "changed", "added",
                                                          "negation_lost", "qualifier_lost"):
                    explained.append(iss)
                    explained_counter[iss["class"]] += 1
                else:
                    keep.append(iss)
            issues = keep
        report["segments"].append({"id": sid, "issues": issues, "explained": explained,
                                   "n_source_sentences": len(sents_src),
                                   "n_target_sentences": len(sents_tgt)})
        for iss in issues:
            report["summary"][iss["class"]] += 1
    report["summary"]["explained"] = sum(explained_counter.values())

    summary = dict(report["summary"])
    hard = sum(summary.get(k, 0) for k in ("missing", "changed", "added",
                                           "negation_lost", "qualifier_lost"))
    report["summary"] = summary
    json.dump(report, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    L = ["# 人工确认清单（保真不变量审计）", ""]
    L.append(f"- 硬性差异: {hard}（missing/changed/added/negation_lost/qualifier_lost）")
    L.append(f"- 已说明差异(signal_explanation): {summary.get('explained', 0)}")
    L.append(f"- 句数不齐提示: {summary.get('sentence_count_mismatch', 0)}（按句序号对齐，需人工核对）")
    L.append("")
    for seg in report["segments"]:
        for iss in seg["issues"]:
            L.append(f"- `{seg['id']}` **{iss['class']}** " +
                     (f"{iss.get('kind')} `{iss.get('value') or (str(iss.get('from'))+'→'+str(iss.get('to')))}` {iss.get('unit') or ''}"
                      if iss["class"] in ("missing", "added", "changed")
                      else iss.get("detail", iss.get("source_snippet", ""))))
    for seg in report["segments"]:
        for iss in seg["explained"]:
            L.append(f"- `{seg['id']}` 已说明差异 **{iss['class']}** `{iss.get('value') or iss.get('from')}`（见该段 signal_explanation）")
    if hard == 0:
        L.append("")
        L.append("无未说明的硬性差异。")
    L.append("")
    L.append("纪律：审计差异是信号不是改译指令；合法语序/单位调整须写 signal_explanation；"
             "不得为清零而改坏正确译文。")
    open(a.review, "w", encoding="utf-8").write("\n".join(L) + "\n")

    print(f"audit: hard={hard} explained={summary.get('explained', 0)} "
          f"sent_mismatch={summary.get('sentence_count_mismatch', 0)} -> {a.out}")
    sys.exit(1 if hard else 0)

if __name__ == "__main__":
    main()
