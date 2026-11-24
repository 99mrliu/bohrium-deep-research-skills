#!/usr/bin/env python3
"""check_consistency.py — 基于 index.json 做跨章节一致性检查，输出 consistency_report.json。

规则（详见 references/consistency_rules.md）：
  dangling-float-reference(error)   orphan-float(warn)
  duplicate-float-number(error)     heading-number-gap(error)
  citation-without-entry(error)     orphan-reference-entry(warn)
  abbrev-redefined-differently(error)  duplicate-definition-across-chapters(warn)
  term-variant-residue(warn)        non-thesis-structure(warn，降级提示)

退出码：存在 error 级问题 → 1；否则 0；索引不可读 → 2。
用法：python3 check_consistency.py --index index.json --out consistency_report.json
"""
import argparse
import json
import sys

RULES = {
    "dangling-float-reference": ("error", "正文引用了不存在的图表编号",
                                 "核对目标题注编号：若题注存在则为笔误，改正文引用；若图表已删除，删除或改写该引用。"),
    "orphan-float": ("warn", "题注存在但正文从未引用",
                     "在正文合适位置补充“如图 x-y 所示”式引用，或删除该图表。"),
    "duplicate-float-number": ("error", "同一类型图表编号被多个题注使用",
                               "保留其一，其余按顺序重新编号，并用 impact.py --renumber 找出全部需同步修改的引用点。"),
    "heading-number-gap": ("error", "同级标题编号出现跳号",
                           "补齐缺失小节，或重排后续标题编号。"),
    "citation-without-entry": ("error", "正文引用的文献编号在参考文献小节中没有条目",
                               "补充对应文献条目，或删除/改写该引用点。"),
    "orphan-reference-entry": ("warn", "参考文献条目从未被正文引用",
                               "在正文补充引用 [n]，或删除该条目。"),
    "abbrev-redefined-differently": ("error", "同一缩略语被定义为不同的全称",
                                     "统一全称，仅保留首次定义点。"),
    "duplicate-definition-across-chapters": ("warn", "同一缩略语在多个章节重复定义",
                                             "仅在首次出现的章节定义，后续章节直接使用缩略语。"),
    "term-variant-residue": ("warn", "同一概念存在多种写法（术语漂移）",
                             "按工单统一为规范写法；参考文献条目标题保持原文不纳入统计。"),
    "non-thesis-structure": ("warn", "材料缺少编号标题/题注/引文，不像分章节论文结构",
                             "结构性规则已降级：仅 float/citation 计数可用，请人工确认材料形态。"),
}


def loc(file, line):
    return {"file": file, "line": line}


def main():
    ap = argparse.ArgumentParser(description="跨章节一致性检查")
    ap.add_argument("--index", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    try:
        with open(args.index, encoding="utf-8") as fh:
            idx = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        print("ERROR: cannot read index: %s" % e, file=sys.stderr)
        return 2

    issues = []

    def add(rule, message, locations):
        sev, trig, sug = RULES[rule]
        issues.append({"rule": rule, "severity": sev, "message": message,
                       "locations": locations, "suggestion": sug})

    floats = idx.get("floats", [])
    refs = idx.get("float_refs", [])
    cap_set = {(f["kind"], f["number"]) for f in floats}
    ref_set = {(r["kind"], r["number"]) for r in refs}

    # 1 dangling-float-reference：按 (kind, number) 聚合
    dang = {}
    for r in refs:
        if (r["kind"], r["number"]) not in cap_set:
            dang.setdefault((r["kind"], r["number"]), []).append(loc(r["file"], r["line"]))
    for (kind, num) in sorted(dang):
        add("dangling-float-reference",
            "引用了不存在的%s %s" % ("图" if kind == "figure" else "表", num), dang[(kind, num)])

    # 2 orphan-float
    for f in floats:
        if (f["kind"], f["number"]) not in ref_set:
            add("orphan-float", "%s %s 有题注但正文无人引用"
                % ("图" if f["kind"] == "figure" else "表", f["number"]),
                [loc(f["file"], f["line"])])

    # 3 duplicate-float-number
    cap_count = {}
    for f in floats:
        cap_count.setdefault((f["kind"], f["number"]), []).append(loc(f["file"], f["line"]))
    for (kind, num) in sorted(cap_count):
        if len(cap_count[(kind, num)]) > 1:
            add("duplicate-float-number",
                "%s %s 的题注出现 %d 次" % ("图" if kind == "figure" else "表", num,
                                            len(cap_count[(kind, num)])),
                cap_count[(kind, num)])

    # 4 heading-number-gap：同文件、同父前缀的同级编号应连续
    by_file = {}
    for h in idx.get("headings", []):
        if h.get("number"):
            by_file.setdefault(h["file"], []).append(h)
    for f in sorted(by_file):
        groups = {}
        for h in by_file[f]:
            parts = h["number"].split(".")
            if parts[-1].isdigit():
                groups.setdefault(tuple(parts[:-1]), []).append((int(parts[-1]), h))
        for prefix in sorted(groups):
            seq = groups[prefix]
            for (pn, _), (cn, h) in zip(seq, seq[1:]):
                if cn > pn + 1:
                    missing = [".".join(list(prefix) + [str(m)]) for m in range(pn + 1, cn)]
                    add("heading-number-gap",
                        "标题编号跳号：%s 之后直接是 %s，缺少 %s"
                        % (".".join(list(prefix) + [str(pn)]), h["number"], "、".join(missing)),
                        [loc(h["file"], h["line"])])

    # 5/6 引文规则；参考文献小节缺失时整体降级为 warn
    cit = idx.get("citations", {})
    entries = {e["number"] for e in cit.get("entries", [])}
    cited_locs = {}
    for c in cit.get("references", []):
        for n in c["numbers"]:
            cited_locs.setdefault(n, []).append(loc(c["file"], c["line"]))
    degraded = not cit.get("bibliography_found") and bool(cited_locs)
    for n in sorted(cited_locs):
        if n not in entries:
            sev_override = "warn" if degraded else None
            msg = "引文 [%d] 没有对应的参考文献条目" % n
            if degraded:
                msg += "（未找到参考文献小节，citation 规则整体降级为 warn）"
            add("citation-without-entry", msg, cited_locs[n])
            if sev_override:
                issues[-1]["severity"] = sev_override
    if cit.get("bibliography_found"):
        for e in sorted(cit.get("entries", []), key=lambda x: (x["number"], x["file"], x["line"])):
            if e["number"] not in cited_locs:
                add("orphan-reference-entry", "参考文献条目 [%d] 从未被正文引用" % e["number"],
                    [loc(e["file"], e["line"])])

    # 7/8 缩略语
    by_abbr = {}
    for d in idx.get("abbreviations", {}).get("definitions", []):
        by_abbr.setdefault(d["abbr"], []).append(d)
    for ab in sorted(by_abbr):
        ds = by_abbr[ab]
        # 全称聚类：互相包含（一个为另一个的子串）视为同一定义，
        # 以吸收“本工作选用乙烯-醋酸乙烯酯共聚物（EVA）”这类句首前缀噪声；
        # 展示用全称取最短者。
        clusters = []
        for f in sorted({d["full"] for d in ds}, key=len):
            if not any(f in c or c in f for c in clusters):
                clusters.append(f)
        if len(clusters) > 1:
            add("abbrev-redefined-differently",
                "缩略语 %s 被定义为 %d 种不同全称：%s"
                % (ab, len(clusters), " / ".join(sorted(clusters))),
                [loc(d["file"], d["line"]) for d in ds])
        else:
            files = {d["file"] for d in ds}
            if len(files) > 1:
                add("duplicate-definition-across-chapters",
                    "缩略语 %s（%s）在 %d 个章节重复定义" % (ab, clusters[0], len(files)),
                    [loc(d["file"], d["line"]) for d in ds])

    # 9 术语变体残留
    forms = idx.get("term_forms", {})
    for g in idx.get("term_groups", []):
        present = [v for v in g["variants"] if forms.get(v)]
        if len(present) > 1:
            locs = []
            for v in present:
                for o in forms[v][:20]:
                    locs.append({"file": o["file"], "line": o["line"], "variant": v})
            add("term-variant-residue",
                "术语“%s”存在多种写法：%s"
                % (g["canonical"], "、".join("“%s”×%d" % (v, len(forms[v])) for v in present)),
                locs)

    # 10 非论文结构降级提示
    numbered = [h for h in idx.get("headings", []) if h.get("number")]
    if not floats and not numbered and not cited_locs:
        add("non-thesis-structure",
            "未发现编号标题、图表题注或 [n] 引文，材料可能不是分章节论文结构", [])

    issues.sort(key=lambda i: (i["rule"],
                               i["locations"][0]["file"] if i["locations"] else "",
                               i["locations"][0]["line"] if i["locations"] else 0))
    for k, i in enumerate(issues, 1):
        i2 = {"id": "ISSUE-%03d" % k}
        i2.update(i)
        issues[k - 1] = i2

    errors = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warn")
    report = {"schema": "consistency-report/v1",
              "summary": {"errors": errors, "warnings": warnings, "total": len(issues)},
              "bibliography_found": bool(cit.get("bibliography_found")),
              "issues": issues}
    if idx.get("note"):
        report["note"] = idx["note"]
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("consistency report: %s -> errors=%d warnings=%d" % (args.out, errors, warnings))
    for i in issues:
        first = i["locations"][0] if i["locations"] else {}
        print("  [%s] %s %s %s:%s" % (i["severity"].upper(), i["id"], i["rule"],
                                      first.get("file", "-"), first.get("line", "-")))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
