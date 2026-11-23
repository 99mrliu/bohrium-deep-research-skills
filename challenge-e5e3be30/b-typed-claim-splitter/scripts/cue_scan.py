#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cue_scan.py — 中英双语线索词扫描与类型化原子拆解建议引擎（纯标准库）

功能：
  1. 按 cue-lexicon.json 对每条论断做六类语义槽位扫描
     （comparator / negation / significance / condition / causal / scope），
     记录原词与字符位置；
  2. 给出建议拆分点（强分隔符恒拆；弱分隔符需两侧各有谓词线索；
     因果/范围从句标记前移拆分）；
  3. 生成建议的原子子判断列表（类型：fact / comparison / causal / scope，
     附所需证据类型、谓词主干、修饰槽位）；
  4. 生成槽位→子判断映射（每个槽位必须被恰好一个子判断认领，
     认领规则 = 槽位字符位置落在子判断区间内）。

退出码：0 成功；1 输入/运行错误；2 用法错误（argparse）。

用法：
  python3 cue_scan.py --claims claims.json [--lexicon cue-lexicon.json] [--out atoms.json]
  python3 cue_scan.py --help
"""
import argparse
import json
import os
import re
import sys

EVIDENCE_NEEDED = {
    "fact": "原文中对该事实的直接陈述（数值、定义、观测结果）",
    "comparison": "两个比较对象各自的数值/方向与样本信息，以及比较方向是否一致",
    "causal": "机制性证据（显微组织、对照实验、统计中介分析或作者明确的因果表述）",
    "scope": "原文关于适用范围/对象/条件限定的明确表述",
}

TRIM_CHARS = " \t，,。；;、：:（）()\"\u201c\u201d"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def iter_term_matches(text, term, lang):
    """对单个词条产出所有匹配。re: 前缀按正则；en 按词边界；zh 按子串。"""
    if term.startswith("re:"):
        pattern = term[3:]
        for m in re.finditer(pattern, text, re.IGNORECASE):
            yield m
    elif lang == "en":
        for m in re.finditer(r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE):
            yield m
    else:
        for m in re.finditer(re.escape(term), text):
            yield m


def find_slots(text, lexicon):
    """扫描六类槽位；同类别重叠匹配保留最长者。"""
    raw = []
    for cat, groups in lexicon["categories"].items():
        for lang in ("zh", "en"):
            terms = groups.get(lang, [])
            for term in terms:
                for m in iter_term_matches(text, term, lang):
                    raw.append({
                        "category": cat,
                        "term": term,
                        "text": m.group(0),
                        "start": m.start(),
                        "end": m.end(),
                    })
    # 同类别重叠去重：保留区间最长（等长保留先出现）
    raw.sort(key=lambda s: (s["start"], -(s["end"] - s["start"])))
    kept = []
    for s in raw:
        dup = False
        for k in kept:
            if k["category"] == s["category"] and s["start"] < k["end"] and k["start"] < s["end"]:
                dup = True
                break
        if not dup:
            kept.append(s)
    kept.sort(key=lambda s: s["start"])
    return kept


def make_pred_checker(lexicon):
    zh_hints = lexicon.get("predicate_hints", {}).get("zh", [])
    en_hints = lexicon.get("predicate_hints", {}).get("en", [])
    en_patterns = [re.compile(r"\b" + re.escape(h) + r"\b", re.IGNORECASE) for h in en_hints]

    def has_pred(s):
        if any(h in s for h in zh_hints):
            return True
        return any(p.search(s) for p in en_patterns)

    return has_pred


def find_split_points(text, lexicon, has_pred):
    """收集拆分点。strong 恒拆；weak 需两侧各有谓词；causal/scope 从句标记前移拆分（标记归右子句）。"""
    points = []
    sd = lexicon.get("split_delimiters", {})
    for d in sd.get("zh_strong", []):
        for m in re.finditer(re.escape(d), text):
            points.append({"pos": m.start(), "cut_end": m.end(), "kind": "strong", "delimiter": m.group(0)})
    for d in sd.get("zh_weak", []) + sd.get("en_weak", []):
        for m in re.finditer(re.escape(d), text):
            left, right = text[: m.start()], text[m.end():]
            if has_pred(left) and has_pred(right):
                points.append({"pos": m.start(), "cut_end": m.end(), "kind": "weak", "delimiter": m.group(0)})
    for cat, markers in lexicon.get("clause_markers", {}).items():
        for marker in markers:
            lang = "en" if re.fullmatch(r"[A-Za-z ]+", marker) else "zh"
            for m in iter_term_matches(text, marker, lang):
                if m.start() > 0:
                    points.append({"pos": m.start(), "cut_end": m.start(),
                                   "kind": cat + "_marker", "delimiter": m.group(0)})
    # 按位置去重（marker 优先于 weak，避免同位重复）
    points.sort(key=lambda p: (p["pos"], 0 if p["kind"].endswith("_marker") else 1))
    deduped = []
    for p in points:
        if deduped and p["pos"] == deduped[-1]["pos"]:
            continue
        deduped.append(p)
    return deduped


def build_clauses(text, points):
    """按拆分点切分子句，剥离首尾分隔/标点字符，返回非空子句区间。"""
    bounds = [0] + [p["pos"] for p in points] + [len(text)]
    cut_ends = {p["pos"]: p["cut_end"] for p in points}
    clauses = []
    for i in range(len(bounds) - 1):
        start, end = bounds[i], bounds[i + 1]
        # 左边界若来自分隔符拆分，跳过分隔符本身
        if start in cut_ends and cut_ends[start] > start:
            start = cut_ends[start]
        seg = text[start:end]
        lstrip = len(seg) - len(seg.lstrip(TRIM_CHARS))
        rstrip = len(seg.rstrip(TRIM_CHARS))
        seg2 = seg.strip(TRIM_CHARS)
        if seg2:
            clauses.append({"start": start + lstrip, "end": start + rstrip, "text": seg2})
    return clauses


def predicate_stem(text, lexicon):
    """谓词主干启发式：谓词线索词（长词优先）> 最长中文连续串 > 最长英文单词 > 截断文本。"""
    zh_hints = sorted(lexicon.get("predicate_hints", {}).get("zh", []), key=len, reverse=True)
    for h in zh_hints:
        if h in text:
            return h
    low = text.lower()
    for h in lexicon.get("predicate_hints", {}).get("en", []):
        if re.search(r"\b" + re.escape(h) + r"\b", low):
            return h
    runs = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    if runs:
        return max(runs, key=len)
    words = re.findall(r"[A-Za-z]{3,}", text)
    if words:
        return max(words, key=len)
    return text.strip()[:16]


def classify_clause(clause_slots, marker_kind):
    """类型优先级：causal > scope > comparison(含 comparator) > scope(仅 condition) > fact。"""
    cats = {s["category"] for s in clause_slots}
    if "causal" in cats or marker_kind == "causal_marker":
        return "causal"
    if "scope" in cats or marker_kind == "scope_marker":
        return "scope"
    if "comparator" in cats:
        return "comparison"
    if "condition" in cats:
        return "scope"
    return "fact"


def scan_claim(claim_id, text, lexicon, has_pred):
    slots = find_slots(text, lexicon)
    for i, s in enumerate(slots, 1):
        s["slot_id"] = "%s#s%d" % (claim_id, i)

    points = find_split_points(text, lexicon, has_pred)
    clauses = build_clauses(text, points)
    if not clauses:
        clauses = [{"start": 0, "end": len(text), "text": text.strip() or text}]

    # 每个子句起始处是否为 marker 拆分（决定归类提示）
    marker_at = {p["pos"]: p["kind"] for p in points if p["kind"].endswith("_marker")}

    atoms = []
    slot_mapping = {}
    for i, cl in enumerate(clauses, 1):
        cl_slots = [s for s in slots if cl["start"] <= s["start"] and s["end"] <= cl["end"]]
        mkind = None
        for pos, kind in marker_at.items():
            if cl["start"] <= pos < cl["end"] and pos - cl["start"] <= 4:
                mkind = kind
                break
        atype = classify_clause(cl_slots, mkind)
        modifiers = {}
        for cat in ("negation", "significance", "condition"):
            hits = [s["text"] for s in cl_slots if s["category"] == cat]
            if hits:
                modifiers[cat] = hits
        atom_id = "%s#a%d" % (claim_id, i)
        for s in cl_slots:
            slot_mapping[s["slot_id"]] = atom_id
        atoms.append({
            "atom_id": atom_id,
            "type": atype,
            "text": cl["text"],
            "span": [cl["start"], cl["end"]],
            "predicate_stem": predicate_stem(cl["text"], lexicon),
            "covers_slots": [s["slot_id"] for s in cl_slots],
            "modifiers": modifiers,
            "evidence_needed": EVIDENCE_NEEDED[atype],
        })

    warnings = []
    if not slots:
        warnings.append("未检测到任何线索词：按单一事实论断处理，请人工确认是否确为单谓词论断。")
    cmp_slots = [s for s in slots if s["category"] == "comparator"]
    if cmp_slots and len(clauses) == 1:
        warnings.append("检测到比较词但论断未被拆分：注意核实比较对象是否完整（可能为隐含比较）。")
    neg_slots = [s for s in slots if s["category"] == "negation"]
    for s in neg_slots:
        warnings.append("否定槽位 %s（'%s'）会反转所在子判断极性，核验时不得吞掉。" % (s["slot_id"], s["text"]))

    return {
        "id": claim_id,
        "text": text,
        "slots": slots,
        "split_points": points,
        "atoms": atoms,
        "slot_mapping": slot_mapping,
        "warnings": warnings,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="中英双语线索词扫描与类型化原子拆解建议引擎。输入 claims.json（数组，元素含 id/text），输出 atoms.json。")
    ap.add_argument("--claims", required=True, help="输入 claims.json 路径（JSON 数组，元素含 id 与 text 字段）")
    ap.add_argument("--lexicon", default=None,
                    help="线索词表路径（默认：<脚本目录>/../references/cue-lexicon.json）")
    ap.add_argument("--out", default=None, help="输出 atoms.json 路径（默认写到标准输出）")
    args = ap.parse_args(argv)

    lexicon_path = args.lexicon or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "references", "cue-lexicon.json")
    try:
        lexicon = load_json(lexicon_path)
        claims = load_json(args.claims)
    except (OSError, json.JSONDecodeError) as e:
        print("错误：无法读取输入文件：%s" % e, file=sys.stderr)
        return 1
    if not isinstance(claims, list) or not all(isinstance(c, dict) and "id" in c and "text" in c for c in claims):
        print("错误：claims.json 必须是数组，且每个元素含 id 与 text 字段。", file=sys.stderr)
        return 1

    has_pred = make_pred_checker(lexicon)
    results = [scan_claim(str(c["id"]), str(c["text"]), lexicon, has_pred) for c in claims]
    out = {
        "meta": {
            "tool": "cue_scan.py",
            "version": "1.0.0",
            "lexicon_version": lexicon.get("version", "unknown"),
            "note": "启发式拆解建议：拆分点与类型须经人工/模型复核后方可作为核验单元。",
        },
        "claims": results,
    }
    payload = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
        total_slots = sum(len(c["slots"]) for c in results)
        total_atoms = sum(len(c["atoms"]) for c in results)
        print("cue_scan 完成：%d 条论断 → %d 个槽位，%d 个原子子判断 → %s"
              % (len(results), total_slots, total_atoms, args.out))
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
