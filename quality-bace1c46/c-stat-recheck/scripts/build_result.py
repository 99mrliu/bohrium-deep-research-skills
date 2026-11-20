#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装终版 result.json，并渲染 recheck_report.md 与 audit_trail.md。

在 extract_corpus.py 写入的部分 result.json 基础上更新：
  status → completed（或 partial_failure）；补 statistics / verification /
  uncertainties / change_log；contract_fields 按已知字段名尽力填充，未知字段
  保持 null 并记入 uncertainties；output_contract 始终原样镜像。
audit_trail.md 提供逐行复现协议：输入/产物 sha256、命令序列、每行结论的
输入定位（文件、页、归一化偏移）。
仅标准库。
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time


def sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def load_jsonl(path):
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    return rows


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def md_cell(s):
    s = re.sub(r"\s+", " ", str(s if s is not None else "")).strip()
    return s.replace("|", "\\|")


CONTRACT_FILLERS = [
    (("grade", "quality", "rating", "level"), lambda g, c, v: g.get("grade")),
    (("limited",), lambda g, c, v: g.get("limited")),
    (("finding", "check", "result", "discrepanc", "count", "statistic"),
     lambda g, c, v: g.get("counts")),
    (("audit", "trail", "reproduc"), lambda g, c, v: "audit_trail.md"),
    (("report", "summary", "markdown"), lambda g, c, v: "recheck_report.md"),
    (("verif", "quote", "anchor", "evidence"), lambda g, c, v: {
        "verified_rows": v.get("verified_rows"),
        "failed_rows": v.get("failed_rows")}),
]


def fill_contract_fields(fields, grades, verify, uncertainties):
    out = {}
    for k in fields:
        kl = k.lower()
        val = None
        for keys, fn in CONTRACT_FILLERS:
            if any(t in kl for t in keys):
                val = fn(grades, None, verify)
                break
        out[k] = val
        if val is None:
            uncertainties.append("output_contract 字段 %r 无法由脚本自动填充，"
                                 "保留 null，需模型/人工补充。" % k)
    return out


def render_report(case_id, docs, rows, queue, grades, verify):
    L = []
    L.append("# 统计复核报告（stat-recheck-evidence-auditor）")
    L.append("")
    L.append("- case_id：`%s`" % case_id)
    L.append("- 总等级：**%s**%s" % (
        grades.get("grade"),
        "（limited：仅摘要口径）" if grades.get("limited") else ""))
    c = grades.get("counts", {})
    L.append("- 机械复核：pass=%(pass)d，discrepancy（已验证/未验证）="
             "%(discrepancy_verified)d/%(discrepancy_unverified)d，"
             "not_recomputable=%(not_recomputable)d" % c)
    L.append("- 完整性：reported=%(completeness_reported)d，"
             "absent=%(completeness_absent)d" % c)
    L.append("- 摘录校验：%s/%s 行通过" % (verify.get("verified_rows"),
                                            verify.get("total_rows")))
    L.append("")
    L.append("> discrepancy 仅表示“报告内部不一致，需人工核对”，不构成对论文"
             "正确性或学术诚信的判断；p 值重算为近似方法，边界情形谨慎解读。")
    L.append("")
    L.append("## 文献清单")
    L.append("")
    L.append("| doc_id | 类型 | 仅摘要 | 页数 | 状态 | 标题/来源 |")
    L.append("|---|---|---|---|---|---|")
    for d in docs:
        L.append("| %s | %s | %s | %s | %s | %s |" % (
            d.get("doc_id"), d.get("kind"),
            "是" if d.get("abstract_only") else "否",
            d.get("num_pages"), d.get("status"),
            md_cell(d.get("title") or os.path.basename(
                d.get("source_path") or ""))))
    L.append("")
    L.append("## 复核行表（维度—判断—证据—锚点）")
    L.append("")
    L.append("| id | 检查项 | 结论 | 已验证 | 重算值 | 报告值 | 容差 | 页 | 摘录（截断） | 说明 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        sides = r.get("sides") or []
        pages = ",".join(str(s.get("page")) for s in sides)
        q = md_cell((sides[0].get("quote") if sides else ""))[:120]
        ver = (r.get("verification") or {}).get("verified", True)
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            md_cell(r.get("id")), md_cell(r.get("check_type")),
            r.get("status"), "是" if ver else "**否（降级）**",
            md_cell(r.get("computed")), md_cell(r.get("reported")),
            md_cell(r.get("tolerance")), md_cell(pages), q,
            md_cell(r.get("note"))[:160]))
    L.append("")
    comp_rows = [r for r in rows if r["check_type"].startswith("completeness:")]
    L.append("## 报告完整性缺口表")
    L.append("")
    L.append("| 文献 | 检查项 | 状态 | 页 | 摘录（截断） | 说明 |")
    L.append("|---|---|---|---|---|---|")
    for r in comp_rows:
        sides = r.get("sides") or []
        L.append("| %s | %s | %s | %s | %s | %s |" % (
            r.get("doc_id"), md_cell(r.get("check_type")), r.get("status"),
            md_cell(",".join(str(s.get("page")) for s in sides)),
            md_cell((sides[0].get("quote") if sides else ""))[:100],
            md_cell(r.get("note"))[:160]))
    L.append("")
    if queue:
        L.append("## 待语义裁决队列（needs_semantic，已由模型确认的结论见 change_log）")
        L.append("")
        for q in queue:
            L.append("- `%s`：%s" % (q.get("doc_id"), md_cell(q.get("question"))))
        L.append("")
    L.append("## 等级推导")
    L.append("")
    for step in grades.get("derivation", []):
        L.append("- %s" % step)
    L.append("")
    return "\n".join(L)


def render_audit(case_id, input_dir, work_dir, rows):
    L = []
    L.append("# 审计复现协议（audit trail）")
    L.append("")
    L.append("复核人可按本文件逐条重跑脚本，复现每一行结论。全部脚本仅依赖 "
             "Python3 标准库（≥3.8）+ pdftotext。")
    L.append("")
    L.append("## 1. 命令序列")
    L.append("")
    L.append("```bash")
    L.append("python3 scripts/extract_corpus.py --input-dir %s --work-dir %s "
             "--output-dir /app/output" % (input_dir, work_dir))
    L.append("python3 scripts/harvest_numbers.py --work-dir %s" % work_dir)
    L.append("python3 scripts/recheck.py --work-dir %s" % work_dir)
    L.append("python3 scripts/verify_quotes.py --work-dir %s" % work_dir)
    L.append("python3 scripts/aggregate_grade.py --work-dir %s" % work_dir)
    L.append("python3 scripts/build_result.py --work-dir %s "
             "--input-dir %s --output-dir /app/output" % (work_dir, input_dir))
    L.append("```")
    L.append("")
    L.append("## 2. 输入文件哈希（sha256）")
    L.append("")
    for root in (input_dir,):
        if os.path.isdir(root):
            for dirpath, _d, files in os.walk(root):
                for fn in sorted(files):
                    fp = os.path.join(dirpath, fn)
                    L.append("- `%s`：%s" % (fp, sha256_file(fp)))
    L.append("")
    L.append("## 3. 中间产物哈希（sha256）")
    L.append("")
    for sub in ("docs.jsonl", "verify_report.json", "grades.json"):
        fp = os.path.join(work_dir, sub)
        if os.path.isfile(fp):
            L.append("- `%s`：%s" % (sub, sha256_file(fp)))
    for sub in ("pages", "numbers", "recheck", "anchors"):
        d = os.path.join(work_dir, sub)
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                L.append("- `%s/%s`：%s" % (sub, fn,
                                            sha256_file(os.path.join(d, fn))))
    L.append("")
    L.append("## 4. 每行结论的输入定位")
    L.append("")
    L.append("| 行 id | 检查项 | 结论 | 定位（页 + 归一化偏移） |")
    L.append("|---|---|---|---|")
    for r in rows:
        locs = []
        for off in (r.get("verification") or {}).get("offsets", []):
            if off.get("found"):
                locs.append("p%s @%d-%d" % (off.get("page"),
                                            off["offset"][0], off["offset"][1]))
            else:
                locs.append("p%s [%s]" % (off.get("page"),
                                          off.get("reason", "unverified")))
        L.append("| %s | %s | %s | %s |" % (
            md_cell(r.get("id")), md_cell(r.get("check_type")),
            r.get("status"), md_cell("; ".join(locs) or "无摘录（缺口类）")))
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="组装终版交付")
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--input-dir", default="/input")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    partial = load_json(os.path.join(args.output_dir, "result.json"),
                        default={}) or {}
    uncertainties = list(partial.get("uncertainties") or [])
    change_log = list(partial.get("change_log") or [])

    docs = load_jsonl(os.path.join(args.work_dir, "docs.jsonl"))
    rows = []
    rdir = os.path.join(args.work_dir, "recheck")
    if os.path.isdir(rdir):
        for fn in sorted(os.listdir(rdir)):
            if fn.endswith(".jsonl"):
                rows.extend(load_jsonl(os.path.join(rdir, fn)))
    queue = []
    qdir = os.path.join(args.work_dir, "semantic_queue")
    if os.path.isdir(qdir):
        for fn in sorted(os.listdir(qdir)):
            if fn.endswith(".jsonl"):
                queue.extend(load_jsonl(os.path.join(qdir, fn)))
    grades = load_json(os.path.join(args.work_dir, "grades.json"), default={}) \
        or {"grade": "ungradable", "counts": {}, "derivation": []}
    verify = load_json(os.path.join(args.work_dir, "verify_report.json"),
                       default={}) or {}

    failed_docs = [d for d in docs if d.get("status") != "ok"]
    status = "completed" if not failed_docs else "partial_failure"
    if failed_docs:
        uncertainties.append("%d 篇文献未能解析，相应维度仅能做缺失说明。"
                             % len(failed_docs))
    if verify.get("failed_rows"):
        uncertainties.append("%d 行摘录校验失败，已整行降级（downgraded=true），"
                             "其 discrepancy 结论按未验证降权计入分级。"
                             % verify["failed_rows"])
    uncertainties.append("p 值重算为近似实现（不完全 β/γ、erf），边界值 "
                         "（|重算-报告| 接近容差）结论需谨慎，详见 "
                         "rules/recheck_rules.md。")
    if any(d.get("abstract_only") for d in docs):
        uncertainties.append("含仅摘要文献：仅做摘要口径复核，标记 limited，"
                             "不外推全文结论。")

    contract = partial.get("output_contract") or {}
    fields = list((partial.get("contract_fields") or {}).keys())
    filled = fill_contract_fields(fields, grades, verify, uncertainties)

    change_log.append({
        "event": "final_result_built", "status": status,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "recheck_rows": len(rows),
        "grade": grades.get("grade")})

    result = dict(partial)
    result.update({
        "case_id": partial.get("case_id", "unknown_case"),
        "status": status,
        "skill": "stat-recheck-evidence-auditor",
        "output_contract": contract,      # 原样镜像，不增删字段
        "contract_fields": filled,
        "statistics_grade": grades,
        "verification_summary": {
            "total_rows": verify.get("total_rows"),
            "verified_rows": verify.get("verified_rows"),
            "failed_rows": verify.get("failed_rows"),
        },
        "sources": [{"doc_id": d.get("doc_id"),
                     "source_path": d.get("source_path"),
                     "source_sha256": d.get("source_sha256"),
                     "abstract_only": d.get("abstract_only"),
                     "status": d.get("status")} for d in docs],
        "recheck_rows_path": "work/recheck/",
        "semantic_queue_pending": len(queue),
        "uncertainties": uncertainties,
        "change_log": change_log,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    tmp = os.path.join(args.output_dir, "result.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(args.output_dir, "result.json"))

    with open(os.path.join(args.output_dir, "recheck_report.md"), "w",
              encoding="utf-8") as f:
        f.write(render_report(result["case_id"], docs, rows, queue,
                              grades, verify))
    with open(os.path.join(args.output_dir, "audit_trail.md"), "w",
              encoding="utf-8") as f:
        f.write(render_audit(result["case_id"], args.input_dir,
                             args.work_dir, rows))
    print(json.dumps({"status": status, "grade": grades.get("grade"),
                      "rows": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
