#!/usr/bin/env python3
"""build_result.py — 组装最终 result.json 并渲染 review_report.md。

输入（均在 --work-dir 下）：
  inventory.json       source_inventory.py 产物（case_id、契约字段、保真台账）
  findings_draft.json  调用 Agent 撰写的 finding 草稿
  anchor_report.json   anchor_verify.py 产物（verified / not_found）
  answers.json         调用 Agent 撰写的总体回答（可选；缺失则如实降级 partial）

规则：
- 契约字段对齐：inventory 中记录的 output_contract 字段一个不缺（list/dict 已在
  source_inventory 阶段归一化为字段名列表）。
- 诚实门：任一契约字段为 null 且 null_reasons 无说明 → status 自动降为 partial，
  并在 uncertainty/change_log 留痕。
- 锚定降级：anchor_report 中 not_found 的 finding 一律 status=pending_review，
  保留 downgrade_reason；verified 的保留草稿状态（默认 confirmed）。
- 原子写入：先写 .tmp 再 os.replace。
- review_report.md：逐条 finding（位置/严重度/原文引用/判定依据/待复核标记）
  + 保真台账附录 + 六分面覆盖登记。

退出码：0 成功；非 0 失败并打印原因到 stderr。
"""
import argparse
import datetime
import json
import os
import sys

FACETS = ["事实核验", "引用支持", "方法设计", "统计报告", "论证链", "学术规范"]
FACET_STATES = {"checked_clean", "issues_found", "partially_checked", "unable_to_check"}


def fail(msg, code=2):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def load_json(path, what, required=True, default=None):
    if not os.path.isfile(path):
        if required:
            fail(f"缺少 {what}: {path}", code=3)
        return default
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        fail(f"{what} 不是合法 JSON: {path}（{e}）", code=3)


def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def merge_findings(draft, anchor):
    verified_ids = {e["id"]: e for e in anchor.get("verified", [])}
    downgraded = {e["id"]: e for e in anchor.get("not_found", [])}
    out = []
    for f in draft:
        fid = f["id"]
        item = {
            "id": fid,
            "facet": f.get("facet"),
            "severity": f.get("severity"),
            "location": f.get("location"),
            "original_text": f.get("original_text"),
            "claim": f.get("claim"),
            "basis": f.get("basis"),
        }
        if fid in downgraded:
            item["status"] = "pending_review"
            item["anchor"] = "not_found"
            item["downgrade_reason"] = downgraded[fid]["reason"]
        elif fid in verified_ids:
            v = verified_ids[fid]
            item["status"] = f.get("status", "confirmed")
            item["anchor"] = "verified"
            item["matched_file"] = v["matched_file"]
        else:
            # 草稿中出现但 anchor_report 未覆盖：不应发生，按诚实原则降级
            item["status"] = "pending_review"
            item["anchor"] = "not_found"
            item["downgrade_reason"] = "anchor_report 未覆盖此条目（可能草稿在 verify 后被改动），按未锚定处理"
        out.append(item)
    return out


def render_report(case_id, status, findings, inv, facet_status, summary, uncertainty):
    lines = []
    lines.append(f"# 审查报告：{case_id}")
    lines.append("")
    lines.append(f"- 总体状态：**{status}**")
    lines.append(f"- 输入文件数：{inv['file_count']}；"
                 f"抽取成功 {sum(1 for e in inv['files'] if e['extract_status'] == 'ok')} 个")
    lines.append(f"- finding 总数：{len(findings)}；"
                 f"待复核 {sum(1 for f in findings if f['status'] == 'pending_review')} 条")
    if summary:
        lines.append("")
        lines.append("## 总体结论")
        lines.append("")
        lines.append(summary)
    lines.append("")
    lines.append("## 六分面覆盖登记")
    lines.append("")
    lines.append("| 分面 | 状态 | 说明 |")
    lines.append("| --- | --- | --- |")
    for facet in FACETS:
        fs = facet_status.get(facet, {})
        lines.append(f"| {facet} | {fs.get('status', 'unable_to_check')} | {fs.get('notes', '')} |")
    lines.append("")
    lines.append("## 逐条 finding")
    lines.append("")
    for f in findings:
        flag = " ⚠️待复核" if f["status"] == "pending_review" else ""
        lines.append(f"### {f['id']}（{f.get('facet') or '未标注'} / {f.get('severity') or '未标注'}）{flag}")
        lines.append("")
        lines.append(f"- **位置**：{f.get('location') or '未标注'}")
        lines.append(f"- **状态**：{f['status']}（锚定：{f['anchor']}）")
        if f["status"] == "pending_review":
            lines.append(f"- **待复核原因**：{f.get('downgrade_reason', '未说明')}")
        lines.append(f"- **原文引用**：> {f.get('original_text') or '（空）'}")
        lines.append(f"- **问题陈述**：{f.get('claim') or '（空）'}")
        lines.append(f"- **判定依据**：{f.get('basis') or '（空）'}")
        lines.append("")
    lines.append("## 附录：保真台账")
    lines.append("")
    lines.append("| 文件 | SHA-256 | 字节数 | 抽取方式 | 抽取状态 | 字符数 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for e in inv["files"]:
        lines.append(
            f"| {e['file']} | `{e['sha256'][:16]}…` | {e['bytes']} | "
            f"{e['extract_method']} | {e['extract_status']} | {e['char_count']} |")
    if uncertainty:
        lines.append("")
        lines.append("## 不确定性记录")
        lines.append("")
        for u in uncertainty:
            lines.append(f"- {u}")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="组装最终 result.json（诚实门+原子写入）并渲染 review_report.md")
    ap.add_argument("--work-dir", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--out-dir", default="/app/output", help="输出目录（默认 /app/output）")
    args = ap.parse_args()

    wd = args.work_dir
    os.makedirs(args.out_dir, exist_ok=True)
    inv = load_json(os.path.join(wd, "inventory.json"),
                    "inventory.json（先运行 source_inventory.py）")
    anchor = load_json(os.path.join(wd, "anchor_report.json"),
                       "anchor_report.json（先运行 anchor_verify.py verify）")
    draft_data = load_json(os.path.join(wd, "findings_draft.json"), "findings_draft.json")
    if isinstance(draft_data, dict):
        draft_data = draft_data.get("findings", [])
    draft = []
    for i, item in enumerate(draft_data):
        f = dict(item)
        fid = f.get("id")
        f["id"] = fid if isinstance(fid, str) and fid else f"f-{i + 1:03d}"
        draft.append(f)
    answers = load_json(os.path.join(wd, "answers.json"), "answers.json",
                        required=False, default=None)

    case_id = inv.get("case_id", "unknown-case")
    contract = inv.get("output_contract_fields") or [
        "case_id", "status", "review_report", "findings", "sources",
        "uncertainty", "change_log",
    ]

    # ---- 合并 Agent 回答 ----
    uncertainty = list(inv.get("contract_note") and [inv["contract_note"]] or [])
    change_log = ["source_inventory: 保真台账建立",
                  "anchor_verify: 原文锚定复验完成"]
    summary, facet_status, null_reasons = None, {}, {}
    if answers is None:
        uncertainty.append("answers.json 缺失：总体结论与六分面登记未填写")
        null_reasons["review_report_summary"] = "answers.json 缺失"
        for facet in FACETS:
            facet_status[facet] = {"status": "unable_to_check", "notes": "answers.json 缺失"}
    else:
        summary = answers.get("summary")
        change_log.append("answers.json: Agent 总体回答已合并")
        for u in answers.get("uncertainty") or []:
            uncertainty.append(u)
        for c in answers.get("change_log") or []:
            change_log.append(c)
        raw_fs = answers.get("facet_status") or {}
        for facet in FACETS:
            fs = raw_fs.get(facet) or {}
            st = fs.get("status", "unable_to_check")
            if st not in FACET_STATES:
                st = "unable_to_check"
                uncertainty.append(f"answers.json 中分面「{facet}」状态非法，按 unable_to_check 处理")
            facet_status[facet] = {"status": st, "notes": fs.get("notes", "")}
        if summary is None:
            null_reasons["review_report_summary"] = "answers.json 未提供 summary"
    for e in inv["files"]:
        if e["extract_status"] != "ok":
            uncertainty.append(f"{e['file']}: 抽取状态 {e['extract_status']}（{e['note']}）")

    findings = merge_findings(draft, anchor)
    pending = sum(1 for f in findings if f["status"] == "pending_review")
    if pending:
        uncertainty.append(
            f"{pending} 条 finding 原文锚定复验未通过，已自动降级为 pending_review（见各条 downgrade_reason）")

    # ---- 组装契约字段 ----
    status = "complete" if (answers is not None and answers.get("status") == "complete") else "partial"
    values = {
        "case_id": case_id,
        "status": status,
        "review_report": None,  # 渲染后填充
        "findings": findings,
        "sources": [
            {"file": e["file"], "sha256": e["sha256"], "bytes": e["bytes"],
             "extract_method": e["extract_method"], "extract_status": e["extract_status"],
             "char_count": e["char_count"], "note": e["note"]}
            for e in inv["files"]
        ],
        "uncertainty": uncertainty,
        "change_log": change_log,
    }

    report_md = render_report(case_id, status, findings, inv, facet_status,
                              summary, uncertainty)
    values["review_report"] = report_md

    result = {}
    for field in contract:
        v = values.get(field)
        result[field] = v
        if v is None and field not in null_reasons:
            null_reasons[field] = "字段为 null 且无填充来源"
    result["null_reasons"] = null_reasons
    result["facet_coverage"] = facet_status
    result["anchor_summary"] = {
        "total_findings": anchor.get("total_findings"),
        "verified": anchor.get("verified_count"),
        "not_found": anchor.get("not_found_count"),
        "downgraded_ids": [e["id"] for e in anchor.get("not_found", [])],
    }
    result["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # ---- 诚实门：契约字段 null 且无说明 → 强制 partial ----
    forced = False
    for field in contract:
        if field in ("case_id", "status"):
            continue
        if result.get(field) is None and field not in null_reasons:
            forced = True
            uncertainty.append(f"诚实门触发：契约字段 {field} 为 null 且无 null_reasons 说明")
    if forced:
        result["status"] = "partial"
        result.setdefault("change_log", []).append(
            "build_result: 诚实门触发，status 强制降为 partial")
        values["review_report"] = render_report(
            case_id, "partial", findings, inv, facet_status, summary, uncertainty)
        result["review_report"] = values["review_report"]
        result["uncertainty"] = uncertainty

    # ---- 原子写出 ----
    result_path = os.path.join(args.out_dir, "result.json")
    atomic_write_json(result_path, result)
    report_path = os.path.join(args.out_dir, "review_report.md")
    tmp = report_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(result["review_report"])
    os.replace(tmp, report_path)

    print(json.dumps({
        "result": result_path,
        "report": report_path,
        "status": result["status"],
        "findings": len(findings),
        "pending_review": pending,
        "contract_fields": contract,
        "contract_fields_missing": [f for f in contract if f not in result],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
