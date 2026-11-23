#!/usr/bin/env python3
"""atomize_lint.py — 原子断言粒度与限定保留核验（纯标准库）。

输入 JSONL，每行一条断言草稿，字段见 references/field-dictionary.md。
输出 lint-report.json；存在 E_* 硬错误时退出码 1，否则 0。

本工具做可机械执行的检查（关系词表、复合谓语提示、代词主语、数值/模态/范围
一致性、重复检测）。它不证明语义蕴含：引文是否真支持断言须由人对照原文。
"""
import argparse
import difflib
import json
import re
import sys
import unicodedata
from collections import defaultdict

VERSION = "1.0.0"

# 受控关系词表（与 references/relation-vocabulary.md 同步；任务自带词表时以任务为准）
RELATIONS = {
    # 比较与性能
    "outperforms", "underperforms", "comparable_to", "equivalent_to",
    # 参数与属性
    "has_parameter", "has_property", "has_value", "has_complexity",
    # 结构与组成
    "part_of", "consists_of", "uses", "extends", "derived_from",
    # 因果与机制
    "causes", "enables", "inhibits", "requires", "limits",
    # 关联与证据
    "correlates_with", "associated_with", "reports", "evaluated_on",
    "trained_on", "applies_to",
    # 功能与用途
    "supports", "generates", "takes_input", "produces_output",
}
MODALITIES = {"asserted", "hedged", "speculative", "proposed"}
POLARITIES = {"positive", "negative"}
CONFIDENCES = {"high", "medium", "low"}

PRONOUNS = {"it", "they", "this", "these", "we", "he", "she", "its", "their"}
HEDGES = ["may", "might", "could", "suggests", "suggest", "likely", "possibly",
          "potentially", "appears to", "seems to", "we propose", "proposed",
          "approximately", "about", "roughly"]
# 比较措辞（compared to/with 等）由 relation 本身表达，不算丢失的范围限定
SCOPE_MARKERS = [
    "only ", "exclusively", "to date", "so far", "currently",
    "in vitro", "in vivo", "at most", "at least",
    "up to", "no more than", "less than", "more than",
]
# 复合谓语提示：两个不同关系词根出现在同一断言文本
RELATION_CUES = {
    "outperform": "outperforms", "underperform": "underperforms",
    "equivalent": "equivalent_to", "comparable": "comparable_to",
    "cause": "causes", "enable": "enables", "inhibit": "inhibits",
    "require": "requires", "correlat": "correlates_with",
    "associat": "associated_with", "support": "supports",
    "generate": "generates", "consist": "consists_of", "extend": "extends",
    "derives": "derived_from", "derived": "derived_from",
}
COORDINATORS = [" and ", " as well as ", "; ", " in addition", " while ",
                " whereas ", " along with ", " together with ", " moreover"]


def norm(s):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).lower()
    return re.sub(r"\s+", " ", s).strip()


def token_numbers(s):
    """提取独立数值：排除标识符内嵌数字（S1、R1、k19）。"""
    return [m.group(0) for m in
            re.finditer(r"(?<![\w.])\d+(?:\.\d+)?(?![\d])", s)]


def load_claims(path):
    claims = []
    with open(path, "r", encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                c = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"E_JSON line {ln}: {exc}", file=sys.stderr)
                sys.exit(2)
            c["_line"] = ln
            claims.append(c)
    return claims


def lint_claim(c, vocab):
    cid = str(c.get("id", f"line-{c['_line']}"))
    findings = []

    def add(code, msg, **kw):
        item = {"code": code, "message": msg}
        item.update(kw)
        findings.append(item)

    text = c.get("text", "")
    subject = norm(c.get("subject", ""))
    relation = str(c.get("relation", ""))
    obj = c.get("object", "")
    quals = c.get("qualifiers", []) or []
    modality = str(c.get("modality", ""))
    polarity = str(c.get("polarity", "positive"))
    ev = c.get("evidence", {}) or {}
    quote = ev.get("quote", "") or ""

    # --- schema 级硬错误 ---
    if not text.strip():
        add("E_EMPTY_TEXT", "断言文本为空")
    if not subject:
        add("E_SUBJECT_MISSING", "subject 为空")
    if subject in PRONOUNS:
        add("E_PRONOUN_SUBJECT", f"subject 是代词 '{c.get('subject')}'，必须解析为实体")
    if not relation:
        add("E_RELATION_MISSING", "relation 为空")
    elif relation not in vocab:
        add("E_RELATION_UNKNOWN", f"relation '{relation}' 不在受控词表")
    if not norm(obj):
        add("E_OBJECT_MISSING", "object 为空")
    if not quote.strip():
        add("E_EVIDENCE_MISSING", "evidence.quote 为空，无法回到原文")
    if modality and modality not in MODALITIES:
        add("E_MODALITY_UNKNOWN", f"modality '{modality}' 不在 {sorted(MODALITIES)}")
    if polarity and polarity not in POLARITIES:
        add("E_POLARITY_UNKNOWN", f"polarity '{polarity}' 不在 {sorted(POLARITIES)}")
    conf = str(c.get("confidence", {}).get("level", c.get("confidence", "")))
    if conf and conf not in CONFIDENCES:
        add("W_CONFIDENCE_UNKNOWN", f"confidence '{conf}' 建议取 {sorted(CONFIDENCES)}")

    # --- 代词开头提示 ---
    first = norm(text).split(" ", 1)[0] if norm(text) else ""
    if first in PRONOUNS:
        add("E_PRONOUN_SUBJECT", f"断言文本以代词 '{first}' 开头，离开段落不可读")

    # --- 复合谓语（打包提示；近义线索不算第二关系，如 applies_to 句中的 "extend to"） ---
    CUE_EQUIV = {"extend": {"extends", "applies_to"}}
    cues = set()
    low = norm(text)
    for cue, rel in RELATION_CUES.items():
        if cue in low and rel != relation and relation not in CUE_EQUIV.get(cue, set()):
            cues.add(rel)
    if cues:
        add("W_ATOMIC_BUNDLE",
            f"文本含 relation '{relation}' 之外的谓语线索 {sorted(cues)}，疑似多条断言打包",
            extra_relations=sorted(cues))

    # --- 数值一致性（按数值集合比较，避免标识符与小数子串误报） ---
    if quote:
        qn = norm(quote)
        qnums = set(token_numbers(qn))
        for num in token_numbers(norm(str(obj))) + token_numbers(norm(text)):
            if num not in qnums:
                add("W_NUMBER_NOT_IN_QUOTE",
                    f"数值 '{num}' 未出现在引文中，确认是否抄录错误或多步计算未注明")
                break

        # --- 模态一致性 ---
        q_has_hedge = any(h in qn for h in HEDGES)
        t_has_hedge = any(h in low for h in HEDGES)
        if q_has_hedge and not t_has_hedge and modality == "asserted":
            add("W_HEDGE_MISMATCH",
                "引文含模态限定（may/suggest/…）但断言写为 asserted，不得升级为事实")

        # --- 范围限定保留 ---
        dropped = []
        for mk in SCOPE_MARKERS:
            if mk in qn and mk.strip() not in low and not any(
                    mk.strip() in norm(q if isinstance(q, str) else q.get("text", ""))
                    for q in quals):
                dropped.append(mk.strip())
        if dropped:
            add("W_SCOPE_DROPPED",
                f"引文含范围限定 {dropped} 但未写入断言文本或 qualifiers", dropped=dropped)
    return cid, findings


def canon_key(c):
    quals = c.get("qualifiers", []) or []
    qtxt = sorted(norm(q if isinstance(q, str) else q.get("text", "")) for q in quals)
    return "|".join([norm(c.get("subject", "")), str(c.get("relation", "")),
                     norm(c.get("object", "")), ";".join(qtxt),
                     str(c.get("polarity", "positive"))])


def main():
    ap = argparse.ArgumentParser(description="原子断言粒度核验")
    ap.add_argument("--claims", required=True, help="断言草稿 JSONL 路径")
    ap.add_argument("--out", required=True, help="lint 报告 JSON 输出路径")
    args = ap.parse_args()

    claims = load_claims(args.claims)
    vocab = set(RELATIONS)
    report = {"tool": "atomize_lint", "version": VERSION,
              "claims_total": len(claims), "results": [], "summary": {}}
    counts = defaultdict(int)

    for c in claims:
        cid, findings = lint_claim(c, vocab)
        for f in findings:
            counts[f["code"]] += 1
        hard = any(f["code"].startswith("E_") for f in findings)
        report["results"].append({
            "id": cid, "verdict": "fail" if hard else ("review" if findings else "pass"),
            "findings": findings,
        })

    # 重复 / 近重复
    by_key = defaultdict(list)
    for c in claims:
        by_key[canon_key(c)].append(str(c.get("id", c["_line"])))
    for key, ids in by_key.items():
        if len(ids) > 1:
            counts["E_DUPLICATE"] += len(ids) - 1
            for r in report["results"]:
                if r["id"] in ids[1:]:
                    r["verdict"] = "fail"
                    r["findings"].append({"code": "E_DUPLICATE",
                                          "message": f"与 {ids[0]} 规范化键完全相同"})
    # 近重复：主体+关系相同、客体相似且限定范围相似（不同数据集/指标不算重复）
    def qual_str(c):
        quals = c.get("qualifiers", []) or []
        return ";".join(sorted(norm(q if isinstance(q, str) else q.get("text", ""))
                               for q in quals))

    by_sr = defaultdict(list)
    for c in claims:
        by_sr[(norm(c.get("subject", "")), str(c.get("relation", "")))].append(
            (str(c.get("id", c["_line"])), norm(c.get("object", "")), qual_str(c)))
    near_pairs = []
    for (s, r), items in by_sr.items():
        if not (s and r) or len(items) < 2:
            continue
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                oi, oj = items[i][1], items[j][1]
                if not oi or not oj:
                    continue
                oratio = difflib.SequenceMatcher(None, oi, oj).ratio()
                qratio = difflib.SequenceMatcher(None, items[i][2], items[j][2]).ratio()
                if (oratio >= 0.85 or oi in oj or oj in oi) and qratio >= 0.75:
                    near_pairs.append((items[i][0], items[j][0]))
    if near_pairs:
        counts["W_NEAR_DUPLICATE"] += len(near_pairs)
        for a, b in near_pairs:
            for res in report["results"]:
                if res["id"] in (a, b):
                    if res["verdict"] == "pass":
                        res["verdict"] = "review"
                    res["findings"].append({
                        "code": "W_NEAR_DUPLICATE",
                        "message": f"与 {b if res['id'] == a else a} 主体+关系相同且客体相近，"
                                   "考虑合并或区分限定"})

    hard_total = sum(v for k, v in counts.items() if k.startswith("E_"))
    report["summary"] = {
        "hard_errors": hard_total,
        "advisories": sum(v for k, v in counts.items() if k.startswith("W_")),
        "by_code": dict(sorted(counts.items())),
        "gate": "fail" if hard_total else "pass",
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 1 if hard_total else 0


if __name__ == "__main__":
    sys.exit(main())
