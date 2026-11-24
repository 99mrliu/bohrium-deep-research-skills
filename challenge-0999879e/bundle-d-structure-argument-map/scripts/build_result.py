#!/usr/bin/env python3
"""build_result.py — 汇总 doc_map + chain_register + lint 候选处置，产出最终成果。

用法:
    python3 build_result.py --input /input --work /app/work --output /app/output

读取:
    work/doc_map.json           结构图（必需）
    work/chain_register.json    论证链登记（缺失则降级为 partial）
    work/lint_candidates.json   机械候选（缺失则降级为 partial）
    work/lint_dispositions.json Agent 对候选的处置（可选；缺失则候选保持 pending_review）

产物（原子写）:
    /app/output/result.json     含 case_id 与 output_contract 全部字段
    /app/output/review_report.md 可编辑审查报告（结构问题/论证链问题分节 + 两张图）

退出码: 0 成功；非 0 失败并打印原因到 stderr。
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile

DEFAULT_FIELDS = ["case_id", "status", "review_report", "findings", "sources",
                  "uncertainty", "change_log"]
ROLE_LABELS = {"abstract": "摘要", "introduction": "引言", "methods": "方法",
               "results": "结果", "discussion": "讨论", "conclusion": "结论",
               "references": "参考文献"}
TYPE_LABELS = {"causal_confusion": "因果/相关混淆",
               "unsupported_conclusion": "外推/无据结论",
               "unanswered_question": "答非所问（引言问题未回应）",
               "missing_section": "结构缺位",
               "ambiguous_section": "结构角色歧义",
               "broken_chain_link": "论证链缺环",
               "broken_chain_pair": "论证链上下游不一致"}


def eprint(msg):
    sys.stderr.write("build_result.py: %s\n" % msg)


def read_json(path, default=None):
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception as exc:  # noqa: BLE001
        eprint("警告：%s 解析失败(%s)，按缺失处理" % (path, exc))
        return default


def atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def resolve_contract(case):
    contract = case.get("output_contract")
    if isinstance(contract, list) and all(isinstance(x, str) for x in contract):
        return list(contract), None
    if isinstance(contract, dict):
        return list(contract.keys()), None
    return list(DEFAULT_FIELDS), ("case.json 未提供可识别的 output_contract，"
                                  "已回退默认字段集 %s" % DEFAULT_FIELDS)


def tree_lines(nodes, depth=0):
    out = []
    for n in nodes:
        role = ("  [%s]" % ROLE_LABELS.get(n["role"], n["role"])) if n.get("role") else ""
        out.append("%s- %s (L%s)%s" % ("  " * depth, n["title"], n.get("line", "?"), role))
        out.extend(tree_lines(n.get("children", []), depth + 1))
    return out


def main():
    ap = argparse.ArgumentParser(description="汇总结构图与论证链，生成 result.json 与 review_report.md")
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    case = read_json(os.path.join(args.input, "case.json"), {}) or {}
    case_id = case.get("case_id", "unknown-case")
    contract, contract_note = resolve_contract(case)
    uncertainty, change_log, findings, sources = [], [], [], []
    if contract_note:
        uncertainty.append(contract_note)

    doc_map = read_json(os.path.join(args.work, "doc_map.json"))
    if doc_map is None:
        eprint("失败：缺少 work/doc_map.json，请先运行 doc_map.py")
        return 2
    register = read_json(os.path.join(args.work, "chain_register.json"))
    lint = read_json(os.path.join(args.work, "lint_candidates.json"))
    dispositions = read_json(os.path.join(args.work, "lint_dispositions.json"),
                             {"dispositions": []})
    disp_map = {d.get("candidate_id"): d for d in
                (dispositions or {}).get("dispositions", [])}

    extract = doc_map.get("extract", {})
    if extract.get("error"):
        uncertainty.append("文本抽取失败（%s）：以下结论仅限已抽取内容，"
                           "整体判定为 unable_to_check" % extract["error"])
    sources.append({
        "file": doc_map.get("manuscript_file"),
        "sha256": doc_map.get("manuscript_sha256"),
        "extract_method": extract.get("method"),
        "extract_error": extract.get("error"),
    })

    # ---------- 结构问题（机械判定，客观可核，直接 confirmed）----------
    struct_findings = []
    for role, info in sorted(doc_map.get("role_matrix", {}).items()):
        label = ROLE_LABELS.get(role, role)
        if info["status"] == "absent":
            sev = "major" if role in ("methods", "results", "discussion",
                                      "conclusion", "references",
                                      "abstract", "introduction") else "minor"
            struct_findings.append({
                "type": "missing_section", "severity": sev,
                "facet": "结构完整性(深查面)",
                "title": "标准小节缺失：%s" % label,
                "description": "要素齐备性矩阵中 %s(%s) 状态为 absent；稿件属于"
                               "'结构看着像论文但关键部分缺位'（见 references/structure_rubric.md）。"
                               % (label, role),
                "evidence": {"quote_a": "(全文无该小节标题)",
                             "locator_a": role,
                             "quote_b": "已识别标题: %s" % " / ".join(
                                 h["title"] for h in doc_map.get("headings", []))[:300],
                             "locator_b": "doc_map.headings"},
                "status": "confirmed",
            })
        elif info["status"] == "ambiguous":
            struct_findings.append({
                "type": "ambiguous_section", "severity": "minor",
                "facet": "结构完整性(深查面)",
                "title": "标准小节疑似重复：%s" % label,
                "description": "%s 命中多个标题: %s" % (
                    label, " / ".join(h["title"] for h in info["headings"])),
                "evidence": {"quote_a": " / ".join(h["title"] for h in info["headings"]),
                             "locator_a": role,
                             "quote_b": "", "locator_b": ""},
                "status": "pending_review",
            })

    # ---------- 论证链候选处置 ----------
    chain_findings, rejected = [], []
    for cand in (lint or {}).get("candidates", []):
        disp = disp_map.get(cand["id"])
        verdict = (disp or {}).get("verdict", "pending_review")
        note = (disp or {}).get("note", "")
        if verdict == "rejected":
            rejected.append("%s(%s): %s" % (cand["id"], cand["type"], note))
            continue
        ev = cand["evidence"]
        chain_findings.append({
            "type": cand["type"],
            "severity": "major" if verdict == "confirmed" else "major",
            "facet": "论证链",
            "title": "%s（规则 %s）" % (TYPE_LABELS.get(cand["type"], cand["type"]),
                                        cand["rule"]),
            "description": "机械候选经 Agent 核对: %s。防误报说明: %s" % (
                note or ("尚未处置，保持待复核" if verdict == "pending_review" else verdict),
                cand.get("false_positive_guard", "")),
            "evidence": {"quote_a": ev.get("design_quote", ""),
                         "locator_a": ev.get("design_locator", ""),
                         "quote_b": ev.get("claim_quote", ""),
                         "locator_b": ev.get("claim_locator", ""),
                         **({"new_value": ev["new_value"]} if ev.get("new_value") else {})},
            "status": "confirmed" if verdict == "confirmed" else "pending_review",
            "candidate_origin": cand["id"],
        })

    # ---------- 论证链登记缺口 ----------
    if register is None:
        uncertainty.append("缺少 chain_register.json：论证链六环未登记，"
                           "论证链分面降级为 partially_checked")
    else:
        for link in register.get("links", []):
            if link.get("status") == "broken":
                chain_findings.append({
                    "type": "broken_chain_link", "severity": "major",
                    "facet": "论证链",
                    "title": "论证链缺环：%s" % link.get("label", link["link"]),
                    "description": "Agent 登记时确认该环在稿件中缺失（status=broken）。",
                    "evidence": {"quote_a": link.get("quote", ""),
                                 "locator_a": link.get("locator", ""),
                                 "quote_b": "", "locator_b": link["link"]},
                    "status": "confirmed",
                })
            elif link.get("status") == "pending_review":
                uncertainty.append("论证链环节 %s(%s) 仍 pending_review，未登记原文引用"
                                   % (link.get("label"), link["link"]))
        for pair in register.get("pairs", []):
            if pair.get("consistent") is False:
                chain_findings.append({
                    "type": "broken_chain_pair", "severity": "major",
                    "facet": "论证链",
                    "title": "论证链不一致：%s -> %s" % (pair["from"], pair["to"]),
                    "description": pair.get("note", ""),
                    "evidence": {"quote_a": "", "locator_a": pair["from"],
                                 "quote_b": "", "locator_b": pair["to"]},
                    "status": "confirmed",
                })
    if lint is None:
        uncertainty.append("缺少 lint_candidates.json：机械候选扫描未运行")

    # ---------- 稳定编号（幂等）----------
    struct_findings.sort(key=lambda f: (f["type"], f["title"]))
    chain_findings.sort(key=lambda f: (f.get("candidate_origin", ""),
                                       f["type"], f["title"]))
    for i, f in enumerate(struct_findings, 1):
        f["id"] = "SR-%03d" % i
    for i, f in enumerate(chain_findings, 1):
        f["id"] = "AC-%03d" % i
    findings = struct_findings + chain_findings

    # ---------- 六分面覆盖（最低检查点见 references/facet_coverage.md）----------
    confirmed_types = {f["type"] for f in findings if f["status"] == "confirmed"}
    stats_terms = any(t in " ".join(
        s["text"] for s in doc_map.get("section_sentences", {}).get("results", []))
        for t in ["p<", "p=", "p <", "P<", "±", "CI", "置信", "标准差", "SD", "t=", "r="])
    facet_coverage = {
        "事实核验": {"status": "partially_checked",
                     "note": "已做跨节数值一致性核对（结论数值 vs 结果节）；"
                             "外部事实与数据真伪未核"},
        "引用支持": {"status": "partially_checked" if doc_map["role_matrix"].get(
                        "references", {}).get("status") == "present" else "unable_to_check",
                     "note": "仅核对参考文献小节存在性与文中引文形式；未逐条验证文献真实性"},
        "方法设计": {"status": "partially_checked",
                     "note": "已抽取设计类型关键词供因果判定；样本量/偏倚控制未深查"},
        "统计报告": {"status": "checked_clean" if stats_terms else "issues_found",
                     "note": "结果节%s出现统计量报告（p/CI/±/r 等最低检查点）"
                             % ("已" if stats_terms else "未")},
        "论证链": {"status": "issues_found" if confirmed_types & {
                        "causal_confusion", "unsupported_conclusion",
                        "unanswered_question", "broken_chain_link",
                        "broken_chain_pair"} else (
                        "checked_clean" if lint is not None else "partially_checked"),
                   "note": "本 bundle 深查面：假设→方法→结果→结论逐环登记 + 机械候选扫描"},
        "学术规范": {"status": "partially_checked",
                     "note": "未做查重/署名/伦理声明核查；仅确认声明性文字存在与否"},
    }

    # ---------- 复核记录 ----------
    pending = [f for f in findings if f["status"] == "pending_review"]
    change_log.append("doc_map.py: 抽取 %d 字符, 标题 %d 个, 角色矩阵完成"
                      % (extract.get("char_count", 0), len(doc_map.get("headings", []))))
    change_log.append("chain_lint.py: 候选 %d 条, 处置 confirmed %d / rejected %d / 未处置 %d"
                      % (len((lint or {}).get("candidates", [])),
                         sum(1 for c in (lint or {}).get("candidates", [])
                             if disp_map.get(c["id"], {}).get("verdict") == "confirmed"),
                         len(rejected),
                         sum(1 for c in (lint or {}).get("candidates", [])
                             if c["id"] not in disp_map)))
    for r in rejected:
        change_log.append("驳回候选: %s" % r)
    if pending:
        uncertainty.append("%d 条 finding 仍为 pending_review，需人工复核，"
                           "本报告未对其下最终结论" % len(pending))
    if register is None or lint is None:
        status = "partial"
    elif extract.get("error"):
        status = "partial"
    else:
        status = "completed"

    # ---------- review_report.md ----------
    rm = doc_map.get("role_matrix", {})
    lines = []
    lines.append("# 论文质量审查报告（bundle-d：结构完整性与论证链制图）")
    lines.append("")
    lines.append("- case_id: `%s`" % case_id)
    lines.append("- 稿件: `%s`" % doc_map.get("manuscript_file"))
    lines.append("- SHA-256: `%s`" % doc_map.get("manuscript_sha256"))
    lines.append("- 抽取方式: %s；状态: **%s**" % (extract.get("method"), status))
    lines.append("")
    lines.append("## 一、结构图")
    lines.append("")
    lines.append("### 1.1 标题层级树")
    lines.append("")
    lines.append("```")
    tl = tree_lines(doc_map.get("structure_tree", []))
    lines.extend(tl if tl else ["(未解析出标题)"])
    lines.append("```")
    lines.append("")
    lines.append("### 1.2 要素齐备性矩阵")
    lines.append("")
    lines.append("| 标准角色 | 状态 | 命中标题 |")
    lines.append("|---|---|---|")
    for role in ["abstract", "introduction", "methods", "results",
                 "discussion", "conclusion", "references"]:
        info = rm.get(role, {"status": "absent", "headings": []})
        hits = " / ".join(h["title"] for h in info["headings"]) or "—"
        lines.append("| %s(%s) | %s | %s |" % (ROLE_LABELS[role], role,
                                                info["status"], hits))
    lines.append("")
    lines.append("### 1.3 摘要 ↔ 结论要素对应矩阵（按关键词重叠配对）")
    lines.append("")
    lines.append("| 结论句 | 定位 | 最匹配摘要句 | 重叠度 |")
    lines.append("|---|---|---|---|")
    for a in doc_map.get("abstract_conclusion_alignment", []):
        lines.append("| %s | %s | %s | %.2f |" % (
            a["conclusion_sentence"][:60], a["conclusion_locator"],
            (a.get("best_abstract_sentence") or "—")[:60], a["overlap_score"]))
    if not doc_map.get("abstract_conclusion_alignment"):
        lines.append("| — | — | — | — |")
    lines.append("")
    lines.append("### 1.4 引言问题 ↔ 结论回答配对")
    lines.append("")
    lines.append("| 引言问题 | 定位 | 最匹配结论句 | 重叠度 | 候选判定 |")
    lines.append("|---|---|---|---|---|")
    for q in doc_map.get("intro_questions", []):
        lines.append("| %s | %s | %s | %.2f | %s |" % (
            q["question"][:60], q["question_locator"],
            (q.get("best_conclusion_sentence") or "—")[:60],
            q["overlap_score"],
            "已回应" if q.get("answered_candidate") else "疑似未回应"))
    if not doc_map.get("intro_questions"):
        lines.append("| — | — | — | — | — |")
    lines.append("")
    lines.append("## 二、论证链图")
    lines.append("")
    lines.append("| 环节 | 主张(Agent 登记) | 原文引用 | 定位 | 状态 |")
    lines.append("|---|---|---|---|---|")
    if register:
        for lk in register.get("links", []):
            lines.append("| %s %s | %s | %s | %s | %s |" % (
                lk["id"], lk["label"], (lk.get("claim") or "—")[:40],
                (lk.get("quote") or "—")[:60], lk.get("locator") or "—",
                lk.get("status")))
    else:
        lines.append("| — | 未登记 | — | — | — |")
    lines.append("")
    lines.append("## 三、结构问题清单")
    lines.append("")
    if struct_findings:
        for f in struct_findings:
            lines.append("- **%s [%s/%s]** %s — %s（证据: %s @%s）" % (
                f["id"], f["severity"], f["status"], f["title"],
                f["description"], f["evidence"]["quote_b"][:80],
                f["evidence"]["locator_b"]))
    else:
        lines.append("- 未发现结构缺位/歧义问题。")
    lines.append("")
    lines.append("## 四、论证链问题清单")
    lines.append("")
    if chain_findings:
        for f in chain_findings:
            lines.append("- **%s [%s/%s]** %s" % (f["id"], f["severity"],
                                                  f["status"], f["title"]))
            lines.append("  - 依据 A（%s）: %s" % (f["evidence"]["locator_a"],
                                                  f["evidence"]["quote_a"][:120]))
            lines.append("  - 依据 B（%s）: %s" % (f["evidence"]["locator_b"],
                                                  f["evidence"]["quote_b"][:120]))
            lines.append("  - 说明: %s" % f["description"][:200])
    else:
        lines.append("- 未发现论证链问题（或候选均被驳回）。")
    lines.append("")
    lines.append("## 五、六分面覆盖")
    lines.append("")
    lines.append("| 分面 | 状态 | 说明 |")
    lines.append("|---|---|---|")
    for k, v in facet_coverage.items():
        lines.append("| %s | %s | %s |" % (k, v["status"], v["note"]))
    lines.append("")
    lines.append("## 六、不确定性与限度")
    lines.append("")
    for u in uncertainty or ["无"]:
        lines.append("- %s" % u)
    lines.append("")
    lines.append("## 七、复核记录（change_log）")
    lines.append("")
    for c in change_log:
        lines.append("- %s" % c)
    lines.append("")
    report_md = "\n".join(lines)

    # ---------- result.json（契约对齐 + 原子写）----------
    result = {k: None for k in contract}
    result.update({
        "case_id": case_id,
        "status": status,
        "review_report": report_md,
        "findings": findings,
        "sources": sources,
        "uncertainty": uncertainty,
        "change_log": change_log,
        "manuscript_sha256": doc_map.get("manuscript_sha256"),
        "facet_coverage": facet_coverage,
        "review_report_path": os.path.join(os.path.abspath(args.output),
                                           "review_report.md"),
        "counts": {"total": len(findings),
                   "confirmed": sum(1 for f in findings if f["status"] == "confirmed"),
                   "pending_review": len(pending)},
    })
    atomic_write(os.path.join(args.output, "result.json"),
                 json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    atomic_write(os.path.join(args.output, "review_report.md"), report_md)
    print("result.json 与 review_report.md 已生成: findings %d 条 "
          "(confirmed %d, pending %d), status=%s" % (
              len(findings), result["counts"]["confirmed"], len(pending), status))
    return 0


if __name__ == "__main__":
    sys.exit(main())
