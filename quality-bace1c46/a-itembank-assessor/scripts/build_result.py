#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装终版 result.json 并渲染人读版 assessment_table.md。

读取：case.json（case_id 与 output_contract）、docs.jsonl、design.json、
可选 design_overrides.json（模型对分型的修正，留痕进 change_records）、
assessments_verified/*.jsonl、verify_report.json、grades.json、itembank。
仅标准库。
"""
import argparse
import datetime
import json
import os
import re
import sys

ITEM_HEADER = re.compile(r"^## \[(?P<iid>[A-Z]+-\d+)\]\s*(?P<title>.*)$", re.M)
FIELD_LINE = re.compile(r"^-\s*(?P<key>维度|问题|核心)\s*[:：]\s*(?P<val>.*)$", re.M)
DOC_LIST_KEYS = ["documents", "papers", "references", "files",
                 "literature", "corpus", "materials"]
CONTRACT_KEYS = ["output_contract", "contract", "output_fields", "required_fields"]
CASE_ID_KEYS = ["case_id", "id", "caseId"]


def log(msg):
    print("[build_result] %s" % msg, file=sys.stderr)


def safe_read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_jsonl(path):
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return rows


def find_first_key(obj, keys):
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and obj[k] is not None:
                return obj[k]
        for v in obj.values():
            r = find_first_key(v, keys)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_first_key(v, keys)
            if r is not None:
                return r
    return None


def default_itembank():
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.normpath(os.path.join(here, "..", "itembank"))
    return cand if os.path.isdir(cand) else "itembank"


def parse_item_meta(itembank_dir):
    """item_id → {dimension, question, core, title}"""
    meta = {}
    if not os.path.isdir(itembank_dir):
        return meta
    for fn in sorted(os.listdir(itembank_dir)):
        if not fn.endswith(".md") or fn == "README.md":
            continue
        try:
            with open(os.path.join(itembank_dir, fn), "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            continue
        matches = list(ITEM_HEADER.finditer(text))
        for i, m in enumerate(matches):
            block = text[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)]
            fields = {}
            for fl in FIELD_LINE.finditer(block):
                fields[fl.group("key")] = fl.group("val").strip()
            meta[m.group("iid")] = {
                "title": m.group("title").strip(),
                "dimension": fields.get("维度", ""),
                "question": fields.get("问题", ""),
                "core": fields.get("核心", "").startswith("是"),
            }
    return meta


def md_escape(s):
    return (s or "").replace("|", "\\|").replace("\n", " ")


def main():
    ap = argparse.ArgumentParser(description="组装终版 result.json 与人读评价表")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--itembank", default=None)
    args = ap.parse_args()

    os.makedirs(args.output, exist_ok=True)
    case_obj = safe_read_json(args.case) or {}
    case_id = find_first_key(case_obj, CASE_ID_KEYS) or "unknown_case"
    contract = find_first_key(case_obj, CONTRACT_KEYS)
    meta = parse_item_meta(args.itembank or default_itembank())

    docs = load_jsonl(os.path.join(args.work, "docs.jsonl"))
    design = safe_read_json(os.path.join(args.work, "design.json")) or {"docs": {}}
    overrides = safe_read_json(os.path.join(args.work, "design_overrides.json")) or {}
    grades = safe_read_json(os.path.join(args.work, "grades.json")) or {}
    verify = safe_read_json(os.path.join(args.work, "verify_report.json")) or {}

    uncertainties = []
    change_records = []
    documents_out = []
    sources = []

    for rec in docs:
        doc_id = rec.get("doc_id")
        tier = rec.get("tier", "failed")
        dinfo = dict(design.get("docs", {}).get(doc_id, {}))
        overridden = False
        if doc_id in overrides:
            ov = overrides[doc_id]
            old = dinfo.get("design_type")
            dinfo["design_type"] = ov.get("design_type", old)
            overridden = True
            change_records.append({
                "doc_id": doc_id, "type": "design_type_override",
                "from": old, "to": dinfo["design_type"],
                "reason": ov.get("reason", "模型修正（未注明理由）")})
        if (dinfo.get("uncertain") and not overridden
                and dinfo.get("design_type") != "unassessable"):
            uncertainties.append("%s: 设计分型置信度低（%s, conf=%s），模型未修正"
                                 % (doc_id, dinfo.get("design_type"),
                                    dinfo.get("confidence")))
        if rec.get("note"):
            uncertainties.append("%s: %s" % (doc_id, rec["note"]))

        assessments = load_jsonl(os.path.join(
            args.work, "assessments_verified", doc_id + ".jsonl"))
        assess_out = []
        for a in assessments:
            iid = a.get("item_id", "UNKNOWN")
            m = meta.get(iid, {})
            assess_out.append({
                "item_id": iid,
                "dimension": m.get("dimension", ""),
                "question": m.get("question", ""),
                "core": m.get("core", False),
                "judgment": a.get("judgment", "not_assessable"),
                "quote": a.get("quote"),
                "locator": a.get("locator"),
                "rationale": a.get("rationale"),
                "verification": a.get("verification", {}),
            })
        g = grades.get(doc_id, {})
        if not g:
            uncertainties.append("%s: 缺少聚合分级结果" % doc_id)
        documents_out.append({
            "doc_id": doc_id,
            "title": rec.get("title"),
            "source_path": rec.get("source_path"),
            "tier": tier,
            "word_count": rec.get("word_count"),
            "design_type": dinfo.get("design_type", "other"),
            "design_confidence": dinfo.get("confidence"),
            "design_uncertain": dinfo.get("uncertain", False),
            "design_overridden": overridden,
            "matched_signals": dinfo.get("matched_signals", []),
            "grade": g.get("grade", "ungradable"),
            "derivation": g.get("derivation", []),
            "stats": g.get("stats", {}),
            "assessments": assess_out,
        })
        sources.append({"doc_id": doc_id, "source_path": rec.get("source_path"),
                        "tier": tier, "method": rec.get("method"),
                        "sha256": rec.get("sha256")})

    n_ungradable = sum(1 for d in documents_out if d["grade"] == "ungradable")
    if not documents_out:
        status = "failed"
        uncertainties.append("未发现任何可处理文献")
    elif n_ungradable:
        status = "partial"
    else:
        status = "completed"

    result = {
        "case_id": case_id,
        "status": status,
        "skill": "design-typed-itembank-assessor",
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "output_contract": contract,
        "documents": documents_out,
        "sources": sources,
        "uncertainties": uncertainties,
        "change_records": change_records,
        "verification_summary": {k: verify.get(k) for k in
                                 ("total", "ok", "wrong_page", "not_found",
                                  "missing_quote", "skipped_na", "invalid_judgment")},
        "artifacts": {"assessment_table_md": "assessment_table.md",
                      "verify_report": "verify_report.json",
                      "grades": "grades.json"},
    }
    # 镜像 output_contract 顶层字段：有真实产出则填值，否则置 null 并记 uncertainties
    grade_counts = {}
    for d in documents_out:
        grade_counts[d["grade"]] = grade_counts.get(d["grade"], 0) + 1
    overall_summary = (
        "共评价 %d 篇文献：%s；门控校验通过 %s/%s 条摘录。"
        % (len(documents_out),
           "，".join("%s %d 篇" % (g, c) for g, c in sorted(grade_counts.items())) or "无",
           result["verification_summary"].get("ok"),
           result["verification_summary"].get("total")))

    def contract_value_for(key):
        k = key.lower()
        if "assessment" in k and "table" in k:
            return "assessment_table.md"
        if "grade" in k:
            return {d["doc_id"]: d["grade"] for d in documents_out}
        if "summary" in k:
            return overall_summary
        if "uncertaint" in k:
            return uncertainties
        if "status" in k:
            return status
        return None

    if isinstance(contract, dict):
        for k in contract:
            if k not in result:
                v = contract_value_for(k)
                result[k] = v
                if v is None:
                    uncertainties.append(
                        "output_contract 字段 '%s' 无对应产出，置 null" % k)
    elif isinstance(contract, list):
        for k in contract:
            if isinstance(k, str) and k not in result:
                result[k] = contract_value_for(k)
    result["overall_summary"] = result.get("overall_summary") or overall_summary
    # uncertainties 可能在镜像后新增，需同步回写
    result["uncertainties"] = uncertainties

    tmp = os.path.join(args.output, "result.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(args.output, "result.json"))

    # ---- 渲染人读版评价表 ----
    lines = ["# 文献研究质量评价表", ""]
    lines.append("- case_id: `%s`" % case_id)
    lines.append("- 状态: **%s**；生成时间: %s" % (status, result["generated_at"]))
    lines.append("- 判断四态: met / partial / not_met / not_assessable；"
                 "摘录经门控归一化校验，失败者已降级并留痕。")
    vs = result["verification_summary"]
    lines.append("- 门控校验: 共 %s 条，通过 %s，页码不符 %s，未找到 %s，缺摘录 %s。"
                 % (vs.get("total"), vs.get("ok"), vs.get("wrong_page"),
                    vs.get("not_found"), vs.get("missing_quote")))
    lines.append("")
    for d in documents_out:
        title = d["title"] or os.path.basename(d["source_path"] or "") or d["doc_id"]
        lines.append("## %s — %s" % (d["doc_id"], md_escape(title)))
        lines.append("")
        lines.append("- 来源: `%s`；层级: %s；词数: %s"
                     % (d["source_path"], d["tier"], d["word_count"]))
        sig = ", ".join("%s×%s" % (s["signal"], s["count"])
                        for s in d["matched_signals"][:6]) or "无"
        lines.append("- 设计分型: **%s**（置信度 %s%s）；命中信号: %s"
                     % (d["design_type"], d["design_confidence"],
                        "，低置信" if d["design_uncertain"] else "", md_escape(sig)))
        if d["design_overridden"]:
            lines.append("- ⚠️ 分型经模型修正（见 change_records）")
        lines.append("- 总体等级: **%s**" % d["grade"])
        if d["derivation"]:
            lines.append("- 分级推导链:")
            for step in d["derivation"]:
                lines.append("  1. %s" % step)
        lines.append("")
        if d["assessments"]:
            lines.append("| 维度 | 条目 | 判断 | 证据（摘录 + 页锚） | 理由 |")
            lines.append("|---|---|---|---|---|")
            for a in d["assessments"]:
                ev = "（无可评价证据）"
                if a.get("quote"):
                    ev = "“%s” (%s)" % (md_escape(a["quote"]), a.get("locator") or "?")
                vstat = (a.get("verification") or {}).get("status", "")
                if vstat and vstat not in ("ok", "skipped_na"):
                    ev += " ⚠️%s" % vstat
                lines.append("| %s | %s %s%s | %s | %s | %s |" % (
                    md_escape(a["dimension"]), a["item_id"],
                    md_escape(a.get("question") or a.get("item_id")),
                    "（核心）" if a.get("core") else "",
                    a["judgment"], ev, md_escape(a.get("rationale"))))
        else:
            lines.append("_无条目判断记录。_")
        lines.append("")
    if uncertainties:
        lines.append("## 不确定性记录")
        lines.append("")
        for u in uncertainties:
            lines.append("- %s" % md_escape(u))
        lines.append("")
    with open(os.path.join(args.output, "assessment_table.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # 校验报告随交付复制到输出目录
    if verify:
        with open(os.path.join(args.output, "verify_report.json"), "w", encoding="utf-8") as f:
            json.dump(verify, f, ensure_ascii=False, indent=2)

    print(json.dumps({"case_id": case_id, "status": status,
                      "n_documents": len(documents_out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
