#!/usr/bin/env python3
"""build_result.py — 汇总 numeric_report + citation_ledger (+ 可选 answers.json)
生成契约对齐的 /app/output/result.json 与可编辑 review_report.md。

契约要点：
  - output_contract 宽容解析（list 或 dict；缺失回退默认字段集并在
    uncertainty 说明）；result.json 必须含原 case_id 与全部契约字段。
  - 诚实门：任何契约字段为 null 且无 null_reasons 说明 → 状态降 partial。
  - 原子写入（mkstemp + os.replace）。
退出码：0 成功；非 0 失败并打印原因到 stderr。仅用标准库。
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile

VERSION = "1.0.0"
DEFAULT_CONTRACT = ["case_id", "status", "review_report", "findings",
                    "sources", "uncertainty", "change_log"]
SKIP_FILES = {"case.json", "task.md", "answers.json"}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return json.load(f)


def load_case(input_dir):
    case_id, contract, notes = "unknown_case", list(DEFAULT_CONTRACT), []
    path = os.path.join(input_dir, "case.json")
    try:
        data = load_json(path)
        case_id = data.get("case_id") or case_id
        oc = data.get("output_contract")
        if isinstance(oc, dict):
            contract = list(oc.keys())
        elif isinstance(oc, list) and all(isinstance(x, str) for x in oc):
            contract = list(oc)
        else:
            notes.append("output_contract 缺失或格式未知，回退默认字段集 "
                         + json.dumps(DEFAULT_CONTRACT, ensure_ascii=False))
    except FileNotFoundError:
        notes.append("case.json 缺失，使用默认 case_id 与默认字段集")
    except Exception as e:  # noqa: BLE001
        notes.append("case.json 解析失败(%s)，回退默认字段集" % e)
    if "case_id" not in contract:
        contract = ["case_id"] + contract
    return case_id, contract, notes


def atomic_write_json(path, obj):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def collect_findings(numeric, ledger, pending_review):
    findings = []
    for f in (numeric or {}).get("findings", []):
        findings.append({
            "id": f["id"], "facet": f["facet"], "severity": f["severity"],
            "type": f["type"],
            "title": "数值不一致：%s 出现 %s" % (
                f["quantity"], " / ".join(f["distinct_values"])),
            "locations": f["locations"], "evidence": f["evidence"],
            "basis": "确定性跨小节数值比对（references/numeric_consistency.md）",
            "status": "open",
        })
    seq = 1
    if ledger:
        c = ledger["checks"]
        for d in c["dangling"]:
            findings.append({
                "id": "CITE-%03d" % seq, "facet": "引用支持", "severity": "major",
                "type": "dangling_citation",
                "title": "悬空引用：正文引用了不存在的条目 [%s]" % d["n"],
                "locations": [{"line": d["line"], "quote": d["context"]}],
                "evidence": "正文第%d行引用 [%s]，但参考文献表无此条目" % (
                    d["line"], d["n"]),
                "basis": "引文标记与参考文献表机械对照（cite_match）",
                "status": "open",
            })
            seq += 1
        for d in c["duplicates"]:
            findings.append({
                "id": "CITE-%03d" % seq, "facet": "引用支持", "severity": "major",
                "type": "duplicate_entry",
                "title": "重复著录：条目 %s" % d["entries"],
                "locations": [{"quote": d["reason"]}],
                "evidence": d["reason"],
                "basis": "DOI/文本相似度机械判定（difflib ≥0.85 或 DOI 相同）",
                "status": "open",
            })
            seq += 1
        for n in c["uncited"]:
            findings.append({
                "id": "CITE-%03d" % seq, "facet": "引用支持",
                "severity": "minor", "type": "uncited_entry",
                "title": "参考文献 [%s] 未被正文引用" % n,
                "locations": [], "evidence": "正文引文标记集合不含 %s" % n,
                "basis": "引文标记与参考文献表机械对照（cite_match）",
                "status": "open",
            })
            seq += 1
        for d in c["doi_issues"]:
            findings.append({
                "id": "CITE-%03d" % seq, "facet": "学术规范",
                "severity": "minor", "type": "doi_malformed",
                "title": "条目[%s] DOI 格式异常" % d["entry"],
                "locations": [{"quote": d["token"]}], "evidence": d["issue"],
                "basis": "DOI 正则校验 ^10\\.\\d{4,9}/\\S+$",
                "status": "open",
            })
            seq += 1
        for s in ledger.get("support", []):
            if s["verdict"] == "cannot_verify":
                pending_review.append({
                    "id": "SUP-%03d" % (len(pending_review) + 1),
                    "facet": "引用支持",
                    "item": "论断↔被引主张支持判定：条目 [%s]" % s["entry"],
                    "reason": s["note"],
                    "action_needed": "获取被引文献全文/摘要后按 references/support_rubric.md 人工判定",
                })
            else:
                findings.append({
                    "id": "CITE-%03d" % seq, "facet": "引用支持",
                    "severity": "info", "type": "support_assessment",
                    "title": "条目 [%s] 支持初判：%s" % (s["entry"], s["verdict"]),
                    "locations": [], "evidence": s["note"],
                    "basis": "词元重叠启发式（需人工复核）", "status": "open",
                })
                seq += 1
    return findings


def facet_coverage(numeric, ledger, pending_review):
    cov = {}
    if numeric is None:
        cov["事实核验"] = {"status": "unable_to_check",
                          "note": "numeric_report 缺失"}
    elif numeric["findings"]:
        cov["事实核验"] = {"status": "issues_found",
                          "note": "%d 条候选数值不一致" % len(numeric["findings"])}
    else:
        cov["事实核验"] = {"status": "checked_clean",
                          "note": "全部数值提及跨小节比对通过"}
    if ledger is None:
        cov["引用支持"] = {"status": "unable_to_check", "note": "citation_ledger 缺失"}
    elif not ledger["references_section_found"]:
        cov["引用支持"] = {"status": "unable_to_check",
                          "note": "未找到参考文献小节（WARNING 已记录）"}
    elif (ledger["checks"]["dangling"] or ledger["checks"]["duplicates"]
          or ledger["checks"]["uncited"]):
        cov["引用支持"] = {"status": "issues_found",
                          "note": "悬空 %d / 未引 %d / 重复 %d" % (
                              len(ledger["checks"]["dangling"]),
                              len(ledger["checks"]["uncited"]),
                              len(ledger["checks"]["duplicates"]))}
    else:
        cov["引用支持"] = {"status": "checked_clean", "note": "引文标记对照通过"}
    n_note = "numeric_scan 顺带核对了样本量(n=)一致性" if numeric else "未运行"
    cov["统计报告"] = {"status": "partially_checked",
                      "note": n_note + "；检验方法/效应量/CI 超出本 bundle 深查面"}
    for facet in ("方法设计", "论证链", "学术规范"):
        note = "按 facet_coverage.md 最低检查点轮查"
        if facet == "学术规范" and ledger and ledger["checks"]["doi_issues"]:
            cov[facet] = {"status": "issues_found",
                          "note": "%d 处 DOI 格式异常" % len(ledger["checks"]["doi_issues"])}
        else:
            cov[facet] = {"status": "partially_checked",
                          "note": note + "；非本 bundle 深查面，未发现问题不等于无问题"}
    return cov


def render_report(case_id, status, findings, pending_review, cov,
                  sources, uncertainty):
    out = ["# 论文质量审查报告（bundle-b：引用支持 × 数值一致性）", "",
           "- case_id: `%s`" % case_id,
           "- 状态: **%s**" % status,
           "- 深查面: 引用支持、事实核验（数值一致性）；其余四分面按最低检查点轮查",
           "", "## 分面覆盖", ""]
    for k, v in cov.items():
        out.append("- %s: `%s` — %s" % (k, v["status"], v["note"]))
    out += ["", "## 发现清单（%d 条）" % len(findings), ""]
    for f in findings:
        out.append("### %s [%s/%s] %s" % (f["id"], f["facet"], f["severity"], f["title"]))
        out.append("- 判定依据: %s" % f["basis"])
        out.append("- 证据: %s" % f["evidence"])
        for loc in f["locations"]:
            bits = []
            if loc.get("section"):
                bits.append(str(loc["section"]))
            if loc.get("line"):
                bits.append("第%s行" % loc["line"])
            bits.append("「%s」" % (loc.get("quote") or loc.get("raw") or "")[:120])
            out.append("  - %s" % " ".join(bits))
        out.append("")
    out += ["## 待复核（%d 条，不凭空补结论）" % len(pending_review), ""]
    for p in pending_review:
        out.append("- **%s** [%s] %s — 原因: %s；建议: %s" % (
            p["id"], p["facet"], p["item"], p["reason"], p["action_needed"]))
    out += ["", "## 材料与版本", ""]
    for s in sources:
        out.append("- `%s` sha256=%s…（%d 字节）" % (s["file"], s["sha256"][:16],
                                                      s["bytes"]))
    if uncertainty:
        out += ["", "## 不确定性声明", ""]
        out.extend("- %s" % u for u in uncertainty)
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="汇总扫描产物 → 契约对齐 result.json + review_report.md（原子写入）")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.input):
        print("错误: 输入目录不存在: %s" % args.input, file=sys.stderr)
        return 2
    os.makedirs(args.output, exist_ok=True)
    os.makedirs(args.work, exist_ok=True)

    case_id, contract, uncertainty = load_case(args.input)

    numeric = ledger = None
    nr = os.path.join(args.work, "numeric_report.json")
    cl = os.path.join(args.work, "citation_ledger.json")
    if os.path.isfile(nr):
        numeric = load_json(nr)
    else:
        uncertainty.append("numeric_report.json 缺失：数值一致性未查（先运行 numeric_scan.py）")
    if os.path.isfile(cl):
        ledger = load_json(cl)
    else:
        uncertainty.append("citation_ledger.json 缺失：引文对照未做（先运行 cite_match.py）")
    if ledger:
        uncertainty.extend(ledger.get("warnings", []))
    if numeric:
        uncertainty.extend(numeric.get("warnings", []))
    ans = os.path.join(args.work, "answers.json")
    if os.path.isfile(ans):  # 可选：外部问答产物原样并入 uncertainty 备注
        uncertainty.append("已并入 answers.json（%d 字节）" % os.path.getsize(ans))

    sources = []
    for fn in sorted(os.listdir(args.input)):
        p = os.path.join(args.input, fn)
        if os.path.isfile(p) and fn not in SKIP_FILES:
            sources.append({"file": fn, "sha256": sha256_of(p),
                            "bytes": os.path.getsize(p)})

    pending_review = []
    findings = collect_findings(numeric, ledger, pending_review)
    cov = facet_coverage(numeric, ledger, pending_review)

    status = "complete" if (numeric is not None and ledger is not None
                            and not any("缺失" in u for u in uncertainty)) \
        else "partial"
    report_md = render_report(case_id, status, findings, pending_review, cov,
                              sources, uncertainty)
    with open(os.path.join(args.output, "review_report.md"), "w",
              encoding="utf-8") as f:
        f.write(report_md)

    result = {}
    for field in contract:
        result[field] = None
    result["case_id"] = case_id
    for field in contract:
        if field == "status":
            result[field] = status
        elif field == "review_report":
            result[field] = "review_report.md"
        elif field == "findings":
            result[field] = findings
        elif field == "sources":
            result[field] = sources
        elif field == "uncertainty":
            result[field] = uncertainty
        elif field == "change_log":
            result[field] = [
                {"seq": 1, "action": "scan", "detail": "numeric_scan + cite_match"},
                {"seq": 2, "action": "aggregate",
                 "detail": "build_result 汇总 %d findings / %d pending_review" % (
                     len(findings), len(pending_review))},
            ]
    # 诚实门：仍为 null 的契约字段必须有 null_reasons，否则降 partial
    null_fields = [k for k in contract if result.get(k) is None]
    if null_fields:
        result["null_reasons"] = {k: "本 bundle 深查面不产出该字段，留待其他分面补充"
                                  for k in null_fields}
        if status == "complete":
            status = "partial"
            result["status"] = "partial"
            uncertainty.append("诚实门：字段 %s 为 null，状态降 partial" % null_fields)
    result["facet_coverage"] = cov
    result["pending_review"] = pending_review
    result["status"] = status
    result["uncertainty"] = uncertainty

    atomic_write_json(os.path.join(args.output, "result.json"), result)
    print("build_result 完成: status=%s, findings=%d, pending_review=%d, 契约字段=%d" % (
        status, len(findings), len(pending_review), len(contract)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
