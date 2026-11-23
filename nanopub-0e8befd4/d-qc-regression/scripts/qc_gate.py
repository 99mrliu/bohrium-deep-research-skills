#!/usr/bin/env python3
"""qc_gate.py — 断言台账对抗性质量门（纯标准库）。

输入台账 JSON：
  {"case_id": ..., "source_text": "<原文提取文本或 null>",
   "source": {...}, "claims": [...]}
输出 qc-report.json：每条断言 verdict（pass/review/reject）+ 可复现判定依据，
汇总给出 result.status 上限建议。退出码：有 reject → 1，否则 0。

核验的是可机械检查性质；语义蕴含仍需人对照原文（见 references/error-catalog.md）。
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

VERSION = "1.0.0"

RELATIONS = {
    "outperforms", "underperforms", "comparable_to", "equivalent_to",
    "has_parameter", "has_property", "has_value", "has_complexity",
    "part_of", "consists_of", "uses", "extends", "derived_from",
    "causes", "enables", "inhibits", "requires", "limits",
    "correlates_with", "associated_with", "reports", "evaluated_on",
    "supports", "generates", "takes_input", "produces_output", "applies_to",
    "trained_on",
}
MODALITIES = {"asserted", "hedged", "speculative", "proposed"}
POLARITIES = {"positive", "negative"}
CLAIM_STATUS = {"asserted", "not_reported", "conflict", "inferred"}
HEDGES = ["may", "might", "could", "suggest", "likely", "possibly",
          "potentially", "appears", "seems", "propose", "approximately"]
PRONOUNS = {"it", "they", "this", "these", "we", "its", "their"}
RELATION_CUES = {
    "outperform": "outperforms", "underperform": "underperforms",
    "cause": "causes", "enable": "enables", "inhibit": "inhibits",
    "require": "requires", "correlat": "correlates_with",
    "associat": "associated_with", "support": "supports",
    "generate": "generates", "consist": "consists_of", "extend": "extends",
}
MAX_QUOTE_WORDS = 55


def norm(s):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).lower()
    return re.sub(r"\s+", " ", s).strip()


def numbers(s):
    return [m.group(0) for m in
            re.finditer(r"(?<![\w.])\d+(?:\.\d+)?(?![\d])", s)]


def semantic_key(c):
    quals = c.get("qualifiers", []) or []
    qtxt = sorted(norm(q if isinstance(q, str) else q.get("text", "")) for q in quals)
    return "|".join([norm(c.get("subject", "")), str(c.get("relation", "")),
                     norm(str(c.get("object", ""))), ";".join(qtxt),
                     str(c.get("polarity", "positive"))])


def audit_pairs(claims):
    """成对检查：精确重复（E_DUPLICATE）与量纲签名冲突（W_CONFLICT_UNRESOLVED）。
    返回 {claim_id: [finding,...]} 与汇总计数 dict。"""
    import difflib

    def obj_sig(o):
        return re.sub(r"\d+(?:\.\d+)?", "#", norm(str(o)))

    out = defaultdict(list)
    counts = defaultdict(int)
    by_key = defaultdict(list)
    for c in claims:
        by_key[semantic_key(c)].append(str(c.get("id", "?")))
    for key, ids in by_key.items():
        if len(ids) > 1:
            counts["E_DUPLICATE"] += len(ids) - 1
            for dup in ids[1:]:
                out[dup].append({"code": "E_DUPLICATE",
                                 "message": f"与 {ids[0]} 语义键相同",
                                 "evidence": {"duplicate_of": ids[0]}})
    by_sr = defaultdict(list)
    for c in claims:
        by_sr[(norm(c.get("subject", "")), str(c.get("relation", "")))].append(c)
    flagged = set()
    for (s, r), items in by_sr.items():
        if not (s and r) or len(items) < 2:
            continue
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                oi = norm(str(items[i].get("object", "")))
                oj = norm(str(items[j].get("object", "")))
                if not oi or not oj or oi == oj:
                    continue
                ratio = difflib.SequenceMatcher(None, obj_sig(oi), obj_sig(oj)).ratio()
                if ratio < 0.6:
                    continue
                if all(c.get("status") == "conflict" or c.get("adjudication")
                       for c in (items[i], items[j])):
                    continue
                ids = sorted({str(items[i].get("id", "?")),
                              str(items[j].get("id", "?"))})
                gkey = tuple(ids)
                if gkey in flagged:
                    continue
                flagged.add(gkey)
                counts["W_CONFLICT_UNRESOLVED"] += 1
                for cid in ids:
                    out[cid].append({
                        "code": "W_CONFLICT_UNRESOLVED",
                        "message": f"{ids} 同主体同关系、客体签名相似但取值不同，"
                                   "须标 conflict 或写 adjudication",
                        "evidence": {"group": ids,
                                     "objects": [str(items[i].get("object")),
                                                 str(items[j].get("object"))]}})
    return out, counts


def audit_claim(c, src_norm, src_numbers):
    cid = str(c.get("id", "?"))
    findings = []

    def add(code, msg, evidence=None):
        f = {"code": code, "message": msg}
        if evidence is not None:
            f["evidence"] = evidence
        findings.append(f)

    text = str(c.get("text", ""))
    subject = norm(c.get("subject", ""))
    relation = str(c.get("relation", ""))
    obj = c.get("object", "")
    quals = c.get("qualifiers", []) or []
    ev = c.get("evidence", {}) or {}
    quote = str(ev.get("quote", "") or "")
    status = str(c.get("status", "asserted"))

    # 必填与枚举
    if not text.strip():
        add("E_EMPTY_TEXT", "断言文本为空")
    if not subject:
        add("E_SUBJECT_MISSING", "subject 为空")
    if subject in PRONOUNS:
        add("E_PRONOUN_SUBJECT", "subject 是代词，必须解析为实体",
            evidence=c.get("subject"))
    if norm(text).split(" ", 1)[0] in PRONOUNS:
        add("E_PRONOUN_SUBJECT", "断言文本以代词开头",
            evidence=norm(text).split(" ", 1)[0])
    if not relation:
        add("E_RELATION_MISSING", "relation 为空")
    elif relation not in RELATIONS:
        add("E_RELATION_UNKNOWN", "relation 越出受控词表", evidence=relation)
    if not norm(str(obj)):
        add("E_OBJECT_MISSING", "object 为空")
    pol = str(c.get("polarity", "positive"))
    if pol not in POLARITIES:
        add("E_POLARITY_UNKNOWN", "polarity 枚举越界", evidence=pol)
    mod = str(c.get("modality", "asserted"))
    if mod not in MODALITIES:
        add("E_MODALITY_UNKNOWN", "modality 枚举越界", evidence=mod)
    if status not in CLAIM_STATUS:
        add("E_STATUS_UNKNOWN", "status 枚举越界", evidence=status)

    # 来源元数据
    src = c.get("source", {}) or {}
    if status == "asserted" and not (src.get("title") or src.get("identifier")
                                     or c.get("source_id")):
        add("E_SOURCE_METADATA_MISSING", "断言缺来源身份（title/identifier/source_id）")

    # 状态纪律
    if status == "not_reported" and not c.get("searched_scope"):
        add("E_SCOPE_MISSING", "not_reported 必须写 searched_scope（检索范围）")
    if status == "asserted" and not quote.strip():
        add("E_EVIDENCE_MISSING", "asserted 断言必须带逐字引文")
    if status == "inferred" and not (ev.get("inference") or c.get("inference")):
        add("W_INFERENCE_UNDOCUMENTED", "inferred 断言缺推理步骤说明")

    # 逐字性（有 source_text 时核验）
    qn = norm(quote)
    if quote.strip() and src_norm is not None:
        if qn not in src_norm:
            add("E_QUOTE_NOT_VERBATIM",
                "引文在来源文本中找不到（归一化后）：改写/翻译/拼接均不允许",
                evidence=quote[:80])
    elif quote.strip() and src_norm is None:
        add("W_SOURCE_TEXT_UNAVAILABLE",
            "无 source_text（如无文本层），逐字性降级为人工目检并需记录")

    # 数值一致性
    if qn:
        qnums = set(numbers(qn))
        for num in numbers(norm(str(obj))) + numbers(norm(text)):
            if num not in qnums:
                add("W_NUMBER_NOT_IN_QUOTE", "断言数值不在引文中",
                    evidence={"number": num, "quote": quote[:80]})
                break

    # 模态一致性
    if qn and status == "asserted":
        found = [h for h in HEDGES if h in qn]
        t_has = any(h in norm(text) for h in HEDGES)
        if found and not t_has and mod == "asserted":
            add("W_HEDGE_MISMATCH", "引文含模态词但断言升级为事实",
                evidence={"hedges": found})

    # 证据宽度
    words = len(re.findall(r"\S+", quote)) if quote else 0
    if words > MAX_QUOTE_WORDS:
        add("W_EVIDENCE_TOO_BROAD", f"引文 {words} 词超出最小充分建议",
            evidence={"words": words})

    # 复合谓语（近义线索不算第二关系：如 applies_to 句中的 "extend to"）
    CUE_EQUIV = {"extend": {"extends", "applies_to"}}
    low = norm(text)
    extra = sorted({rel for cue, rel in RELATION_CUES.items()
                    if cue in low and rel != relation
                    and relation not in CUE_EQUIV.get(cue, set())})
    if extra:
        add("W_ATOMIC_BUNDLE", "文本含第二关系谓语线索，疑似打包",
            evidence={"extra_relations": extra})

    hard = any(f["code"].startswith("E_") for f in findings)
    return cid, ("reject" if hard else ("review" if findings else "pass")), findings


def main():
    ap = argparse.ArgumentParser(description="断言台账质量门")
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.ledger, encoding="utf-8") as fh:
        ledger = json.load(fh)
    claims = ledger.get("claims", [])
    src_text = ledger.get("source_text")
    if src_text is None and ledger.get("source_text_file"):
        # 支持从相对台账所在目录的文本文件加载原文
        base = os.path.dirname(os.path.abspath(args.ledger))
        cand = os.path.join(base, ledger["source_text_file"])
        if os.path.isfile(cand):
            with open(cand, encoding="utf-8") as fh:
                src_text = fh.read()
    src_norm = norm(src_text) if src_text else None
    src_numbers = set(numbers(src_norm)) if src_norm else set()

    report = {"tool": "qc_gate", "version": VERSION,
              "case_id": ledger.get("case_id"),
              "claims_total": len(claims), "results": [], "summary": {}}
    counts = defaultdict(int)
    verdict_count = defaultdict(int)

    results = []
    for c in claims:
        cid, verdict, findings = audit_claim(c, src_norm, src_numbers)
        for f in findings:
            counts[f["code"]] += 1
        verdict_count[verdict] += 1
        results.append({"id": cid, "verdict": verdict,
                        "status": c.get("status", "asserted"),
                        "adjudication": c.get("adjudication"),
                        "findings": findings})

    # 成对检查（重复 + 量纲签名冲突），逻辑见 audit_pairs
    pair_findings, pair_counts = audit_pairs(claims)
    for cid, fs in pair_findings.items():
        for f in fs:
            counts[f["code"]] += 1
        for r in results:
            if r["id"] == cid:
                r["findings"].extend(fs)
                if any(f["code"].startswith("E_") for f in fs):
                    r["verdict"] = "reject"
                elif r["verdict"] == "pass":
                    r["verdict"] = "review"

    rejects = sum(1 for r in results if r["verdict"] == "reject")
    reviews_open = sum(1 for r in results
                       if r["verdict"] == "review" and not r.get("adjudication"))
    special = sum(1 for c in claims
                  if c.get("status") in ("not_reported", "conflict"))
    if rejects:
        status_cap = "partial"
        note = "存在 reject：修复/删除/降级后复检，禁止 success"
    elif reviews_open or special:
        status_cap = "partial"
        note = "有未判读 review 或特殊条目：补 adjudication 或按 partial 交付"
    else:
        status_cap = "success"
        note = "门通过，可按 success 交付"

    report["results"] = results
    report["summary"] = {
        "verdicts": dict(verdict_count),
        "reject_open": rejects, "review_open": reviews_open,
        "special_entries": special,
        "by_code": dict(sorted(counts.items())),
        "status_cap": status_cap, "status_note": note,
        "gate": "pass" if not rejects else "fail",
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 1 if rejects else 0


if __name__ == "__main__":
    sys.exit(main())
