#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""finalize.py — 终稿渲染 + 诚实门 + 原子落盘（最后一步，可重复运行，幂等）。

输入：work/answer_sheet.json + work/adjudication_report.json + work/extracted_text.txt
动作：
1. 取 adjudication 中 accepted 的 findings，按 (facet 序, severity 序, 锚点位置,
   original_text) 排序，编号 F001… 按排序后位置稳定分配（同输入必得同编号）。
2. 幂等重渲染 review_report.md：按 facet 分组、组内按 severity 排序；
   pending_review 与 rejected 单列留痕。
3. 终检（诚实门）：
   - output_contract 全部字段必须存在；
   - 任何字段为 null 且无 null_reasons 说明 → status 降 partial 并列出降级原因；
   - 存在 pending_review / 抽取错误 / 未知契约字段 → status=partial 并如实说明。
4. 原子写入（临时文件 + rename）result.json 与 review_report.md。
5. 打印一行验收摘要：findings 数 / 待复核数 / 降级原因。

仅使用 Python 3 标准库。
"""
import argparse
import datetime
import json
import os
import sys
import tempfile

FACETS = ["事实核验", "引用支持", "方法设计", "统计报告", "论证链", "学术规范"]
SEVERITIES = ["critical", "major", "minor", "info"]
FACET_STATUS_VALUES = {"checked_clean", "issues_found", "partially_checked", "unable_to_check"}
KNOWN_FIELDS = {"case_id", "status", "review_report", "findings",
                "sources", "uncertainty", "change_log"}


def eprint(*a):
    print(*a, file=sys.stderr)


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def load_json(path, what):
    if not os.path.isfile(path):
        eprint("ERROR: 未找到 %s（%s）" % (path, what))
        sys.exit(2)
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as ex:
        eprint("ERROR: %s 不是合法 JSON: %s" % (path, ex))
        sys.exit(2)


def atomic_write(path, text):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def norm_ws(s):
    return "".join(str(s).split())


def sort_key(entry):
    f = entry["finding"]
    facet_idx = FACETS.index(f["facet"]) if f.get("facet") in FACETS else len(FACETS)
    sev_idx = SEVERITIES.index(f["severity"]) if f.get("severity") in SEVERITIES else len(SEVERITIES)
    return (facet_idx, sev_idx, entry.get("anchor_pos", 1 << 30), f.get("original_text", ""))


def render_report(case_id, findings, pending, rejected, facet_cov, sources, uncertainty,
                  downgrade_reasons, status):
    L = []
    L.append("# 论文质量审查报告")
    L.append("")
    L.append("- case_id: `%s`" % case_id)
    L.append("- status: **%s**" % status)
    L.append("- accepted findings: %d；pending_review: %d；rejected: %d"
             % (len(findings), len(pending), len(rejected)))
    if downgrade_reasons:
        L.append("- 降级原因: %s" % "；".join(downgrade_reasons))
    L.append("")
    L.append("## 稿件版本（SHA-256）")
    L.append("")
    for it in sources.get("input_files", []):
        L.append("- `%s` sha256=`%s`%s" % (
            it.get("file"), it.get("sha256"),
            "（%s）" % it["extract_error"] if it.get("extract_error") else ""))
    if not sources.get("input_files"):
        L.append("- （无）")
    L.append("")
    L.append("## 分面覆盖")
    L.append("")
    L.append("| 分面 | 状态 | 说明 |")
    L.append("| --- | --- | --- |")
    for fac in FACETS:
        c = facet_cov.get(fac, {})
        L.append("| %s | %s | %s |" % (fac, c.get("status", "unable_to_check"),
                                        str(c.get("notes", "")).replace("|", "\\|")))
    L.append("")
    L.append("## Findings（按分面分组、组内按严重度排序；编号稳定）")
    for fac in FACETS:
        group = [f for f in findings if f["finding"].get("facet") == fac]
        if not group:
            continue
        L.append("")
        L.append("### %s" % fac)
        for f in group:
            g = f["finding"]
            loc = g.get("location", {})
            L.append("")
            L.append("#### %s [%s/%s] %s" % (f["id"], g["severity"], g["type"],
                                              g.get("title", g["original_text"][:30])))
            L.append("- 定位: `%s` § %s（anchor: %s）"
                     % (loc.get("file", "?"), loc.get("section", "?"), loc.get("anchor", "?")))
            L.append("- 原文: > %s" % g["original_text"])
            L.append("- 判定依据: %s" % g["evidence"])
            L.append("- 修改建议: %s" % g["suggestion"])
            if f.get("recheck_hints"):
                L.append("- ⚠ recheck: %s" % "；".join(f["recheck_hints"]))
    L.append("")
    L.append("## Pending Review（待人工复核，不凭空补结论）")
    L.append("")
    if pending:
        for e in pending:
            g = e.get("finding", {})
            L.append("- [#%d] %s：%s" % (e["index"], str(g.get("original_text", ""))[:60],
                                          "；".join(e.get("reasons", []))))
    else:
        L.append("- （无）")
    L.append("")
    L.append("## Rejected（机器复核驳回，留痕）")
    L.append("")
    if rejected:
        for e in rejected:
            g = e.get("finding", {})
            L.append("- [#%d] %s：%s" % (e["index"], str(g.get("original_text", g))[:60],
                                          "；".join(e.get("reasons", []))))
    else:
        L.append("- （无）")
    L.append("")
    L.append("## 不确定性记录")
    L.append("")
    if uncertainty:
        for u in uncertainty:
            L.append("- %s" % u)
    else:
        L.append("- （无）")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="终稿渲染 + 诚实门 + 原子落盘（幂等）")
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args(argv)

    sheet = load_json(os.path.join(args.work_dir, "answer_sheet.json"), "先运行 contract_init.py")
    adj = load_json(os.path.join(args.work_dir, "adjudication_report.json"),
                    "先运行 adjudicate.py check")
    case_id = sheet.get("case_id")
    if not case_id:
        eprint("ERROR: answer_sheet.json 缺 case_id")
        return 2

    corpus_norm = norm_ws(read_text(os.path.join(args.work_dir, "extracted_text.txt"))) \
        if os.path.isfile(os.path.join(args.work_dir, "extracted_text.txt")) else ""

    accepted, pending, rejected = [], [], []
    for e in adj.get("entries", []):
        d = e.get("disposition")
        if d == "accepted":
            # 终检时再次复验锚点位置（编号稳定性的位置键以此为准）
            pos = corpus_norm.find(norm_ws(e["finding"].get("original_text", "")))
            if pos >= 0:
                e["anchor_pos"] = pos
            accepted.append(e)
        elif d == "downgraded":
            pending.append(e)
        else:
            rejected.append(e)
    accepted.sort(key=sort_key)
    for i, e in enumerate(accepted, 1):
        e["id"] = "F%03d" % i

    # 分面状态：Agent 在答题纸中手填者优先；否则保守推导（不谎称 checked_clean）
    facet_cov = {}
    for fac in FACETS:
        c = dict(sheet.get("facet_coverage", {}).get(fac, {}))
        if c.get("status") not in FACET_STATUS_VALUES or not c.get("agent_filled"):
            if any(e["finding"].get("facet") == fac for e in accepted):
                c = {"status": "issues_found", "notes": "由 accepted findings 推导"}
            elif c.get("status") not in FACET_STATUS_VALUES or c.get("status") == "unable_to_check":
                c = {"status": "unable_to_check",
                     "notes": "Agent 未在答题纸中填写该分面核查结论（agent_filled 未置真）"}
        facet_cov[fac] = c

    sources = {"input_files": sheet.get("extraction", {}).get("files", [])}
    uncertainty = list(sheet.get("uncertainty", []))
    for e in pending:
        uncertainty.append("pending_review [#%d]: %s" % (
            e["index"], "；".join(r for r in e.get("reasons", []))))

    downgrade_reasons = []
    extract_errors = sheet.get("extraction", {}).get("errors", [])
    if extract_errors:
        downgrade_reasons.append("存在抽取错误 %d 项" % len(extract_errors))
    if pending:
        downgrade_reasons.append("存在 %d 条 pending_review 待人工复核" % len(pending))
    if any(e.get("recheck_hints") for e in accepted):
        downgrade_reasons.append("存在命中豁免词表/类型-分面不一致的 recheck 提示")

    fields = list(sheet.get("contract_fields", {}).keys())
    if not fields:
        eprint("ERROR: answer_sheet.json 中 contract_fields 为空")
        return 2

    report_md = render_report(case_id, accepted, pending, rejected, facet_cov,
                              sources, uncertainty, downgrade_reasons, "PENDING")

    change_log = list(sheet.get("change_log", []))
    change_log.append({"ts": utcnow(), "event": "finalize",
                       "detail": "accepted=%d pending=%d rejected=%d"
                                 % (len(accepted), len(pending), len(rejected))})

    # 契约字段装配
    null_reasons = {}
    result = {}
    for f in fields:
        if f == "case_id":
            result[f] = case_id
        elif f == "status":
            result[f] = "complete" if not downgrade_reasons else "partial"
        elif f == "review_report":
            result[f] = report_md
        elif f == "findings":
            result[f] = [dict(e["finding"], id=e["id"],
                              recheck_hints=e.get("recheck_hints", [])) for e in accepted]
        elif f == "sources":
            result[f] = sources
        elif f == "uncertainty":
            result[f] = uncertainty
        elif f == "change_log":
            result[f] = change_log
        else:
            cell = sheet["contract_fields"].get(f, {})
            if cell.get("status") == "filled" and cell.get("value") is not None:
                result[f] = cell["value"]
            else:
                result[f] = None
                null_reasons[f] = cell.get("null_reason") or \
                    "未知契约字段，Agent 未在答题纸中填写；为避免编造，置 null"
    if null_reasons:
        result["null_reasons"] = null_reasons

    # 诚实门：任何契约字段为 null 且无 null_reasons 说明 → 降 partial
    for f in fields:
        if result.get(f) is None and f not in null_reasons:
            downgrade_reasons.append("诚实门：契约字段 %s 为 null 且无 null_reasons 说明" % f)
            null_reasons[f] = "诚实门降级：该字段无法如实填充"
            result["null_reasons"] = null_reasons
    # 未知字段置 null 也构成 partial（诚实声明限度）
    if null_reasons and "存在未知契约字段置 null" not in "；".join(downgrade_reasons):
        downgrade_reasons.append("存在未知契约字段置 null（已给 null_reasons）")

    final_status = "complete" if not downgrade_reasons else "partial"
    result["status"] = final_status
    # 重渲染报告头中的 status
    report_md = report_md.replace("- status: **PENDING**", "- status: **%s**" % final_status)
    result["review_report"] = report_md if "review_report" in fields else result.get("review_report")
    if "review_report" in fields:
        result["review_report"] = report_md
    if "uncertainty" in fields:
        result["uncertainty"] = uncertainty
    if "change_log" in fields:
        result["change_log"] = change_log

    os.makedirs(args.output_dir, exist_ok=True)
    atomic_write(os.path.join(args.output_dir, "result.json"),
                 json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    atomic_write(os.path.join(args.output_dir, "review_report.md"), report_md)

    print("FINALIZE_OK findings=%d pending_review=%d rejected=%d status=%s reasons=[%s]"
          % (len(accepted), len(pending), len(rejected), final_status,
             "；".join(downgrade_reasons) if downgrade_reasons else "无"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
