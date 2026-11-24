#!/usr/bin/env python3
"""texaudit.py — 稿件事实审计（事实来源闸门·第 2 步）。

扫描指定稿件 .tex，抽取正文数字/单位、百分比、样本量、\\cite 键、\\ref，
与 matscan.py 生成的 facts.jsonl 比对，逐条给出判定：

  matched    材料中有完全一致（数值与单位相容）的条目，给出材料 file:line
  unmatched  材料中找不到；附最接近的候选条目作复核线索，显式标注弱匹配
  conflict   材料（或材料之间）存在口径不同的同上下文数值

本脚本只报告，绝不修改稿件。

用法:
    python3 texaudit.py --draft /path/to/main.tex --work /app/work

产出:
    <work>/audit/coverage.json
    <work>/audit/coverage.md
"""
import argparse
import difflib
import json
import os
import re
import sys

NUM_UNIT_RE = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)(?:\s?)"
    r"(m/s|km/h|kg|mg|kDa|Da|mol|mM|uM|µM|nM|mL|uL|µL|nm|mm|cm|km|"
    r"ms|s|min|h|K|Pa|kPa|MPa|GPa|eV|keV|MeV|GeV|Hz|kHz|MHz|GHz|"
    r"degC|°C|°F|V|mV|A|mA|W|kW|J|kJ|N)\b"
)
PERCENT_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?\\?%")
SAMPLE_RE = re.compile(r"\b[nN]\s?=\s?(\d+)\b")
CITE_RE = re.compile(r"\\cite[t|p|alp|num|yearpar|s]*\{([^}]*)\}")
REF_RE = re.compile(r"\\(?:ref|eqref|autoref|pageref)\{([^}]*)\}")
LABEL_RE = re.compile(r"\\label\{([^}]*)\}")

NUMERIC_TYPES = {"num_unit", "percent", "sample_size", "data_value"}

LATIN_RE = re.compile(r"[a-z_]{3,}")
CJK_RUN_RE = re.compile(r"[一-鿿]+")


def tokens(s):
    """拉丁词（>=3 字母）+ 中文二元组，用于上下文重合度判断。"""
    s = s.lower()
    toks = set(LATIN_RE.findall(s))
    for run in CJK_RUN_RE.findall(s):
        if len(run) == 1:
            toks.add(run)
        else:
            for i in range(len(run) - 1):
                toks.add(run[i:i + 2])
    return toks


def strong_overlap(a_toks, b_toks):
    """上下文足够相似才允许判 conflict：共享 >=1 个拉丁词或 >=2 个中文二元组。"""
    inter = a_toks & b_toks
    latin = [t for t in inter if LATIN_RE.fullmatch(t)]
    cjk = [t for t in inter if not LATIN_RE.fullmatch(t)]
    return bool(latin) or len(cjk) >= 2, sorted(inter)


def as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def num_equal(a, b):
    if a == b:
        return True
    fa, fb = as_float(a), as_float(b)
    if fa is None or fb is None:
        return False
    return abs(fa - fb) <= 1e-9 * max(1.0, abs(fa), abs(fb))


def unit_compatible(u1, u2):
    return (not u1) or (not u2) or u1 == u2


def extract_draft_facts(draft_path):
    """从稿件抽取事实条目，结构与 facts.jsonl 相同，另收 labels。"""
    facts, labels = [], set()
    with open(draft_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    n = 0

    def add(ftype, value, unit, lineno, line):
        nonlocal n
        n += 1
        facts.append({
            "id": "D%04d" % n,
            "type": ftype,
            "value": value.strip(),
            "unit": unit or "",
            "anchor": "%s:%d" % (os.path.basename(draft_path), lineno),
            "line_text": line.strip()[:300],
        })

    comment_re = re.compile(r"(?<!\\)%.*$")
    for i, raw in enumerate(lines, 1):
        # LaTeX 注释（未转义 % 起）不是稿件内容，抽取前剥离；\% 不受影响
        line = comment_re.sub("", raw)
        for m in LABEL_RE.finditer(line):
            labels.add(m.group(1).strip())
        for m in NUM_UNIT_RE.finditer(line):
            add("num_unit", m.group(1), m.group(2), i, raw)
        for m in PERCENT_RE.finditer(line):
            add("percent", m.group(1), "%", i, raw)
        for m in SAMPLE_RE.finditer(line):
            add("sample_size", m.group(1), "n", i, raw)
        for m in CITE_RE.finditer(line):
            for key in m.group(1).split(","):
                if key.strip():
                    add("cite_key", key.strip(), "", i, raw)
        for m in REF_RE.finditer(line):
            add("ref", m.group(1).strip(), "", i, raw)
    return facts, labels


def load_facts_db(path):
    facts = []
    if not os.path.isfile(path):
        return facts
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    facts.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return facts


def numeric_closeness(v, c):
    fv, fc = as_float(v), as_float(c)
    if fv is None or fc is None:
        return 0.0
    return 1.0 / (1.0 + abs(fv - fc) / max(abs(fc), 1e-9))


def audit(dfact, db_facts, bib_keys, labels):
    """对单条稿件事实分类，返回 entry dict。"""
    dfact["_tokens"] = tokens(dfact["line_text"])
    entry = {
        "draft_anchor": dfact["anchor"],
        "type": dfact["type"],
        "value": dfact["value"],
        "unit": dfact["unit"],
        "line_text": dfact["line_text"],
        "verdict": None,
        "material_anchors": [],
        "candidates": [],
        "note": "",
    }

    if dfact["type"] == "cite_key":
        hits = [f for f in db_facts
                if f["type"] == "bib_key" and f["value"] == dfact["value"]]
        if hits:
            entry["verdict"] = "matched"
            entry["material_anchors"] = [h["anchor"] for h in hits[:3]]
        else:
            entry["verdict"] = "unmatched"
            close = difflib.get_close_matches(dfact["value"],
                                              sorted(bib_keys), n=3, cutoff=0.3)
            entry["candidates"] = [
                {"value": c, "anchor": bib_keys.get(c, ""), "weak": True}
                for c in close]
            entry["note"] = "引用键未出现在任何材料 .bib 中；候选为弱匹配，仅供人工复核"
        return entry

    if dfact["type"] == "ref":
        if dfact["value"] in labels:
            entry["verdict"] = "matched"
            entry["material_anchors"] = ["(稿件内 \\label 已定义)"]
        else:
            entry["verdict"] = "unmatched"
            close = difflib.get_close_matches(dfact["value"],
                                              sorted(labels), n=3, cutoff=0.3)
            entry["candidates"] = [{"value": c, "anchor": "(稿件内 label)",
                                    "weak": True} for c in close]
            entry["note"] = "\\ref 指向的 label 未定义；候选为弱匹配"
        return entry

    # 数值类
    pool = [f for f in db_facts if f["type"] in NUMERIC_TYPES]
    exact, conflict_cands = [], []
    for f in pool:
        if not unit_compatible(dfact["unit"], f.get("unit", "")):
            continue
        if num_equal(dfact["value"], f["value"]):
            exact.append(f)
        else:
            ok, shared = strong_overlap(dfact["_tokens"], tokens(f["line_text"]))
            if ok:
                conflict_cands.append((f, shared))
    if exact:
        entry["verdict"] = "matched"
        entry["material_anchors"] = sorted({f["anchor"] for f in exact})[:5]
        if conflict_cands:
            entry["note"] = ("另有不同口径的材料条目存在（见 material_conflicts），"
                             "请人工确认采用口径")
    elif conflict_cands:
        entry["verdict"] = "conflict"
        entry["material_anchors"] = sorted({f["anchor"]
                                            for f, _ in conflict_cands})[:5]
        alts = sorted({"%s（%s）" % (vunit(f["value"], f.get("unit", "")),
                                     f["anchor"]) for f, _ in conflict_cands})
        entry["note"] = "材料同上下文中记载的数值不同: " + "; ".join(alts[:5])
    else:
        entry["verdict"] = "unmatched"
        ranked = sorted(pool, key=lambda f: numeric_closeness(dfact["value"],
                                                              f["value"]),
                        reverse=True)
        entry["candidates"] = [
            {"value": f["value"], "unit": f.get("unit", ""),
             "anchor": f["anchor"], "line_text": f["line_text"][:120],
             "weak": True}
            for f in ranked[:3] if numeric_closeness(dfact["value"],
                                                     f["value"]) > 0]
        entry["note"] = "材料中未找到该数值；候选为弱匹配，仅供人工复核"
    return entry


def material_conflicts(db_facts):
    """材料之间同上下文不同口径的数值对（与稿件无关的预警）。"""
    nums = [f for f in db_facts if f["type"] in NUMERIC_TYPES]
    out, seen = [], set()
    toks = {f["id"]: tokens(f["line_text"]) for f in nums}
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            a, b = nums[i], nums[j]
            fa, fb = a["anchor"].split(":")[0], b["anchor"].split(":")[0]
            if fa == fb:
                continue
            if not unit_compatible(a.get("unit", ""), b.get("unit", "")):
                continue
            if num_equal(a["value"], b["value"]):
                continue
            ok, shared = strong_overlap(toks[a["id"]], toks[b["id"]])
            if not ok:
                continue
            key = (a["anchor"], b["anchor"])
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "a": {"anchor": a["anchor"], "value": a["value"],
                      "unit": a.get("unit", "")},
                "b": {"anchor": b["anchor"], "value": b["value"],
                      "unit": b.get("unit", "")},
                "shared_context": shared[:6],
            })
    return out[:50]


def vunit(value, unit):
    """值+单位的展示形式：百分号直连，其余单位前加空格。"""
    if not unit:
        return str(value)
    return str(value) + (unit if unit == "%" else " " + unit)


def main():
    ap = argparse.ArgumentParser(description="稿件事实审计（只报告，不改稿）")
    ap.add_argument("--draft", required=True, help="稿件 .tex 路径")
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()

    audit_dir = os.path.join(args.work, "audit")
    os.makedirs(audit_dir, exist_ok=True)
    notes = []

    db_path = os.path.join(args.work, "facts", "facts.jsonl")
    db_facts = load_facts_db(db_path)
    if not db_facts:
        notes.append("事实库为空或不存在（%s）；请先运行 matscan.py。"
                     "所有条目将判为 unmatched。" % db_path)

    # 被审计稿件自身若在材料中被扫描过，其条目须排除，避免"自我匹配"
    # （稿件是审计对象，不是来源）。
    draft_base = os.path.basename(args.draft)
    before = len(db_facts)
    db_facts = [f for f in db_facts
                if os.path.basename(f["anchor"].split(":")[0]) != draft_base]
    if len(db_facts) != before:
        notes.append("已排除来自被审计稿件自身的 %d 条事实（%s），避免自我匹配"
                     % (before - len(db_facts), draft_base))

    bib_keys = {f["value"]: f["anchor"] for f in db_facts
                if f["type"] == "bib_key"}

    entries, mat_conf = [], []
    if not os.path.isfile(args.draft):
        notes.append("稿件不可读: %s（审计中止，已落盘空报告）" % args.draft)
    else:
        dfacts, labels = extract_draft_facts(args.draft)
        for d in dfacts:
            entries.append(audit(d, db_facts, bib_keys, labels))
        mat_conf = material_conflicts(db_facts)

    counts = {"matched": 0, "unmatched": 0, "conflict": 0}
    for e in entries:
        counts[e["verdict"]] = counts.get(e["verdict"], 0) + 1

    coverage = {
        "draft": os.path.abspath(args.draft),
        "facts_db": os.path.abspath(db_path),
        "counts": counts,
        "entries": entries,
        "material_conflicts": mat_conf,
        "notes": notes,
    }
    with open(os.path.join(audit_dir, "coverage.json"), "w",
              encoding="utf-8") as f:
        json.dump(coverage, f, ensure_ascii=False, indent=2)

    # coverage.md
    L = ["# 事实覆盖审计报告（coverage）", "",
         "稿件：`%s`" % coverage["draft"],
         "事实库：`%s`（%d 条）" % (coverage["facts_db"], len(db_facts)), "",
         "> 本报告由 texaudit.py 生成，只报告不改稿；"
         "弱匹配候选仅供人工复核，不得当作已证实。", "",
         "## 汇总", "",
         "- matched: %d" % counts["matched"],
         "- unmatched: %d" % counts["unmatched"],
         "- conflict: %d" % counts["conflict"],
         "- 材料间口径冲突（预警）: %d" % len(mat_conf), ""]

    def section(title, rows, headers, row_fn, empty):
        L.append("## %s" % title)
        L.append("")
        if not rows:
            L.append("（%s）" % empty)
        else:
            L.append("| " + " | ".join(headers) + " |")
            L.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for r in rows:
                L.append("| " + " | ".join(row_fn(r)) + " |")
        L.append("")

    def cell(s):
        return str(s).replace("|", "\\|").replace("\n", " ")

    section("conflict（口径冲突，需 Agent 裁定）",
            [e for e in entries if e["verdict"] == "conflict"],
            ["稿件位置", "类型", "稿件值", "材料锚点", "说明"],
            lambda e: [cell(e["draft_anchor"]), cell(e["type"]),
                       cell(vunit(e["value"], e["unit"])),
                       cell("; ".join(e["material_anchors"])), cell(e["note"])],
            "无")
    section("unmatched（材料外内容，需 Agent 显式处置）",
            [e for e in entries if e["verdict"] == "unmatched"],
            ["稿件位置", "类型", "稿件值", "最接近候选（弱匹配）", "说明"],
            lambda e: [cell(e["draft_anchor"]), cell(e["type"]),
                       cell(vunit(e["value"], e["unit"])),
                       cell("; ".join("%s @ %s [弱匹配]" %
                                     (vunit(c.get("value", ""), c.get("unit", "")),
                                      c.get("anchor", ""))
                                      for c in e["candidates"]) or "（无候选）"),
                       cell(e["note"])],
            "无")
    section("matched（已回溯到材料）",
            [e for e in entries if e["verdict"] == "matched"],
            ["稿件位置", "类型", "值", "材料锚点"],
            lambda e: [cell(e["draft_anchor"]), cell(e["type"]),
                       cell(vunit(e["value"], e["unit"])),
                       cell("; ".join(e["material_anchors"]))],
            "无")
    section("材料间口径冲突（预警，与稿件是否引用无关）", mat_conf,
            ["材料 A", "材料 B", "共享上下文"],
            lambda c: [cell("%s = %s" % (c["a"]["anchor"],
                                          vunit(c["a"]["value"], c["a"]["unit"]))),
                       cell("%s = %s" % (c["b"]["anchor"],
                                          vunit(c["b"]["value"], c["b"]["unit"]))),
                       cell(", ".join(c["shared_context"]))],
            "无")
    if notes:
        L.append("## 运行备注")
        L.append("")
        for n in notes:
            L.append("- %s" % n)
        L.append("")
    with open(os.path.join(audit_dir, "coverage.md"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(L))

    print("texaudit: matched=%d unmatched=%d conflict=%d 材料间冲突=%d -> %s"
          % (counts["matched"], counts["unmatched"], counts["conflict"],
             len(mat_conf), audit_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
