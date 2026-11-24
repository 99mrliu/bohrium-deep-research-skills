#!/usr/bin/env python3
"""redteam_scan.py — 对 deck.json 跑 R1–R8 确定性检测器，产出 findings_roundN.json。

每条 finding: {id, rule, slide, severity(error|warn), evidence, suggested_fix}。
finding id 确定性生成（rule-slide-序号），同一输入必得同一输出。

规则（详见 references/defect-taxonomy.md）：
  R1 数值漂移/幻觉（error）  R2 悬空引用（error）  R3 引文不逐字（error）
  R4 栏目名标题（warn）      R5 段落搬运（warn）    R6 备读者复读（warn）
  R7 局限缺失（error）       R8 示意图当数据（warn）

用法：redteam_scan.py deck.json facts.json --round N --report findings_roundN.json
退出码：0 扫描完成（无论是否有 finding）；2 输入文件问题。
"""
import argparse
import json
import re
import sys

UNITS = [
    "samples", "datasets", "points", "epochs",
    "kHz", "MHz", "kW", "keV", "MeV", "mV", "mA",
    "mm", "cm", "km", "kg", "mg", "ms", "min",
    "%", "dB", "Hz", "eV", "Pa",
    "s", "m", "g", "K", "V", "A", "W", "J",
]
NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?\s*(?:" + "|".join(UNITS) + r")(?![A-Za-z])")
REF_RE = re.compile(r"\b(?:Figure|Table)\s+\d+\b")
SCHEMATIC_RE = re.compile(r"schematic|diagram|illustration|architecture|overview", re.IGNORECASE)
GENERIC_SUFFIX = {
    "results", "result", "methods", "method", "methodology",
    "experiments", "experiment", "background", "introduction",
    "conclusion", "conclusions", "overview", "approach",
    "evaluation", "discussion", "related work",
}
JACCARD_THRESHOLD = 0.6


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def word_set(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def slide_texts(slide):
    """产出 (字段名, 文本) 列表，供 R1/R2 扫描。"""
    out = [("title", slide.get("title", ""))]
    for b in slide.get("bullets", []):
        out.append(("bullet", b))
    for c in slide.get("claims", []):
        out.append(("claim", c.get("text", "")))
    return out


def is_section_label(title: str) -> bool:
    """R4 启发式：短名词短语、无数字、词尾为通用栏目词 -> 疑似栏目名标题。"""
    t = norm(title)
    if not t:
        return False
    if any(ch.isdigit() for ch in t):
        return False
    words = t.split()
    if len(words) > 5:
        return False
    low = t.lower()
    if " ".join(words[-2:]).lower() in GENERIC_SUFFIX:
        return True
    return low.split()[-1] in GENERIC_SUFFIX


def locator_page(locator: str):
    m = re.search(r"(\d+)", locator or "")
    return int(m.group(1)) if m else None


def scan(deck, facts, round_no):
    anchors = set(facts.get("numeric_anchors", []))
    cap_labels = {c["label"] for c in facts.get("captions", [])}
    cap_by_label = {c["label"]: c for c in facts.get("captions", [])}
    pages_text = norm(" ".join(p["text"] for p in facts.get("pages", [])))
    sections = facts.get("sections", [])
    limitation_hints = facts.get("limitation_hints", [])
    findings = []
    counters = {}

    def add(rule, slide, severity, evidence, suggested_fix):
        key = (rule, slide or 0)
        counters[key] = counters.get(key, 0) + 1
        findings.append({
            "id": f"{rule}-s{slide or 0}-{counters[key]}",
            "rule": rule,
            "slide": slide,
            "severity": severity,
            "evidence": evidence,
            "suggested_fix": suggested_fix,
        })

    for slide in deck.get("slides", []):
        n = slide.get("slide")
        # ---- R1 数值漂移/幻觉 ----
        seen_tokens = set()
        for field, text in slide_texts(slide):
            for m in NUM_RE.finditer(text or ""):
                token = norm(m.group(0))
                if token in seen_tokens:
                    continue
                seen_tokens.add(token)
                if token not in anchors:
                    add("R1", n, "error",
                        {"token": token, "field": field, "context": norm(text)},
                        "删除该无出处数值 bullet，或将数值替换为事实池锚点并补逐字 quote")
        # ---- R2 悬空引用 ----
        refs = set(slide.get("figures", []) or [])
        for _, text in slide_texts(slide):
            refs.update(REF_RE.findall(text or ""))
        if slide.get("table"):
            refs.add(slide["table"].get("ref", ""))
        for ref in sorted(r for r in refs if r):
            if norm(ref) not in cap_labels:
                add("R2", n, "error",
                    {"ref": norm(ref), "known_captions": sorted(cap_labels)},
                    "删除该引用或降级为不含编号的文字描述（如 the cited figure）")
        # ---- R3 引文不逐字 ----
        for ci, claim in enumerate(slide.get("claims", []), 1):
            for si, src in enumerate(claim.get("sources", []), 1):
                q = src.get("quote")
                if src.get("kind") == "pdf" and q:
                    if norm(q) not in pages_text:
                        add("R3", n, "error",
                            {"claim_index": ci, "source_index": si,
                             "quote": q, "locator": src.get("locator")},
                            "把 quote 替换为论文分页文本中可逐字命中的句子（含空白归一化）")
        # ---- R4 栏目名标题 ----
        if slide.get("role") not in ("title",) and is_section_label(slide.get("title", "")):
            add("R4", n, "warn",
                {"title": slide.get("title", "")},
                "改写为含主张的句子式标题（带数值锚点或结论性动词）")
        # ---- R6 备读者复读 ----
        body = " ".join([slide.get("title", "")] + slide.get("bullets", []))
        notes = slide.get("notes", "") or ""
        sim = jaccard(word_set(body), word_set(notes))
        if notes.strip() and sim > JACCARD_THRESHOLD:
            add("R6", n, "warn",
                {"jaccard": round(sim, 3), "threshold": JACCARD_THRESHOLD},
                "备注改写为讲者提示（时间分配、强调点、应答预案），不得复读页面文字")
        # ---- R8 示意图当数据 ----
        if slide.get("role") == "results":
            for ref in slide.get("figures", []) or []:
                cap = cap_by_label.get(norm(ref))
                if cap and SCHEMATIC_RE.search(cap["text"]):
                    add("R8", n, "warn",
                        {"ref": norm(ref), "caption": cap["text"]},
                        "确认该图是否承载数据结论；纯示意图不得作为 results 页证据")

    # ---- R5 段落搬运（deck 级）----
    content = [s for s in deck.get("slides", []) if s.get("role") not in ("title",)]
    pages_seq = []
    for s in content:
        ps = [locator_page(src.get("locator"))
              for c in s.get("claims", []) for src in c.get("sources", [])]
        ps = [p for p in ps if p is not None]
        pages_seq.append(min(ps) if ps else None)
    roles = [s.get("role") for s in content]
    if (len(content) >= 3 and len(content) == len(sections)
            and len(set(roles)) == len(roles)
            and all(p is not None for p in pages_seq)
            and all(a < b for a, b in zip(pages_seq, pages_seq[1:]))):
        add("R5", None, "warn",
            {"roles": roles, "locator_pages": pages_seq,
             "sections": [s["title"] for s in sections]},
            "打破页序-章节一一同构：按受众叙事线重排（如结论先行、合并过渡页）")

    # ---- R7 局限缺失（deck 级）----
    if limitation_hints:
        has_lim = any(s.get("role") in ("limitation", "limitations")
                      for s in deck.get("slides", []))
        if not has_lim:
            add("R7", None, "error",
                {"hints": limitation_hints[:3]},
                "增加 role=limitations 页面，逐字引用论文 limitation 句")

    findings.sort(key=lambda f: (f["rule"], f["slide"] or 0, f["id"]))
    by_rule, by_sev = {}, {}
    for f in findings:
        by_rule[f["rule"]] = by_rule.get(f["rule"], 0) + 1
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
    return {
        "round": round_no,
        "deck": deck.get("_source", "deck.json"),
        "total": len(findings),
        "counts": {"by_rule": by_rule, "by_severity": by_sev},
        "findings": findings,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="对 deck.json 跑 R1-R8 红队检测器")
    ap.add_argument("deck", help="deck.json 路径")
    ap.add_argument("facts", help="facts.json 路径")
    ap.add_argument("--round", type=int, required=True, help="扫描轮次 N")
    ap.add_argument("--report", required=True, help="输出 findings_roundN.json")
    args = ap.parse_args(argv)

    try:
        with open(args.deck, encoding="utf-8") as f:
            deck = json.load(f)
        with open(args.facts, encoding="utf-8") as f:
            facts = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: 无法读取输入: {e}", file=sys.stderr)
        return 2

    deck["_source"] = args.deck
    report = scan(deck, facts, args.round)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(
        f"round={args.round} findings={report['total']} "
        f"by_rule={report['counts']['by_rule']} by_severity={report['counts']['by_severity']} "
        f"-> {args.report}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
