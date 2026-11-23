#!/usr/bin/env python3
"""render_court.py — 渲染裁定产物与交付件，并对报告做叙述绑定 lint。

产物（写入 --outdir）：
  decision-matrix.md    论文对 × 六维度裁定网格（✓/○/△/?/✗）+ 阻断明细表
  comparison-matrix.md  许可内字段视图（每个 PERMIT 一张表；被阻断请求单列）
  verdict-report.md     裁定报告模板：每个比较句带 [DEC-…]/[PERMIT-…]，agent 只许扩写不许造结论
  result.json           交付件：case_id 原样复制 + output_contract 全部字段 + status/sources/uncertainty
  lint.json             叙述绑定 lint 结果

lint（--lint 指定报告路径，缺省检查刚渲染的 verdict-report.md）：
  1. 报告中引用的 [DEC-…]/[PERMIT-…] 必须真实存在；
  2. 启发式：一句中同时出现 ≥2 个 doc_id 与数字/比较词而无 [PERMIT-…] → 告警"疑似未许可定量比较句"。

用法：
  python3 render_court.py --decisions decisions.jsonl --profiles profiles.json \
      --workorder comparison-workorder.json [--case case.json] \
      --permits pool_a.json pool_b.json --outdir OUTDIR [--lint REPORT.md]
"""
import argparse
import json
import re
import sys
from itertools import combinations
from pathlib import Path

SYMBOL = {"comparable": "✓", "convertible": "○", "subset_only": "△",
          "undecidable": "?", "blocked": "✗"}
CORE_DIMENSIONS = ["task", "metric", "units", "material", "pollutant", "budget"]
ID_RE = re.compile(r"\[(DEC|PERMIT)-[A-Za-z0-9_.\-]+\]")
ANY_REF_RE = re.compile(r"\[[A-Z]{2,8}-[A-Za-z0-9_.\-]+\]")  # DEC/PERMIT/REQ 等任意登记引用
CMP_WORDS = re.compile(r"均值|平均|高于|低于|优于|差于|排名|更快|更强|更高|更低|显著")
NUM_RE = re.compile(r"\d")


def load_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def fmt_side(side):
    if not side or not side.get("reported"):
        return "（未报告）"
    return f"{side['value']}〔{side['paragraph_id']}: “{side['quote']}”〕"


def render_decision_matrix(decisions, dim_records, overall_records, doc_ids, case_id):
    lines = []
    lines.append(f"# 可比性裁定矩阵（case_id: {case_id}）")
    lines.append("")
    lines.append("图例：✓ comparable ｜ ○ convertible ｜ △ subset_only ｜ ? undecidable ｜ ✗ blocked")
    lines.append("")
    dims = [d for d in CORE_DIMENSIONS]
    extra = sorted({r["dimension"] for r in dim_records} - set(dims))
    dims += extra

    # 总览网格
    lines.append("## 总览：论文对 × 维度")
    lines.append("")
    header = "| 论文对 | " + " | ".join(dims) + " | 总裁定 |"
    lines.append(header)
    lines.append("|" + "---|" * (len(dims) + 2))
    for ov in overall_records:
        pair = " × ".join(ov["doc_pair"])
        cells = [f"{SYMBOL[ov['dimension_verdicts'][d]]} {ov['dimension_verdicts'][d]}" for d in dims]
        lines.append(f"| {pair} | " + " | ".join(cells) +
                     f" | {SYMBOL[ov['verdict']]} **{ov['verdict']}** |")
    lines.append("")

    # 逐对明细
    lines.append("## 逐对裁定明细")
    for ov in overall_records:
        a, b = ov["doc_pair"]
        lines.append("")
        lines.append(f"### {a} × {b} — 总裁定：{SYMBOL[ov['verdict']]} {ov['verdict']}"
                     f"（最严维度：{', '.join(ov['strictest_dimensions'])}）")
        lines.append("")
        lines.append("| 维度 | 裁定 | decision_id | A 取值（定位） | B 取值（定位） | 说明 |")
        lines.append("|---|---|---|---|---|---|")
        for d in dims:
            rec = next(r for r in dim_records if r["doc_pair"] == [a, b] and r["dimension"] == d)
            bd = rec["blocking_detail"]
            lines.append(f"| {d} | {SYMBOL[rec['verdict']]} {rec['verdict']} | {rec['decision_id']} "
                         f"| {fmt_side(bd['value_a'])} | {fmt_side(bd['value_b'])} | {rec['note']} |")
    lines.append("")

    # 阻断明细表
    lines.append("## 阻断明细表（所有非 comparable 裁定）")
    lines.append("")
    lines.append("| decision_id | 论文对 | 维度 | verdict | A 取值 | B 取值 | 双方 quote 定位 |")
    lines.append("|---|---|---|---|---|---|---|")
    for rec in dim_records:
        if rec["verdict"] == "comparable":
            continue
        bd = rec["blocking_detail"]
        loc_a = f"{bd['value_a']['paragraph_id']}" if bd["value_a"]["reported"] else "—"
        loc_b = f"{bd['value_b']['paragraph_id']}" if bd["value_b"]["reported"] else "—"
        va = bd["value_a"]["value"] if bd["value_a"]["reported"] else "（未报告）"
        vb = bd["value_b"]["value"] if bd["value_b"]["reported"] else "（未报告）"
        lines.append(f"| {rec['decision_id']} | {' × '.join(rec['doc_pair'])} | {rec['dimension']} "
                     f"| {SYMBOL[rec['verdict']]} {rec['verdict']} | {va} | {vb} | A:{loc_a} / B:{loc_b} |")
    lines.append("")
    return "\n".join(lines)


def render_comparison_matrix(permits, profiles, case_id):
    lines = [f"# 许可内比较矩阵（case_id: {case_id}）", ""]
    lines.append("只有获得 PERMIT 的合成请求才在本矩阵中展开数值/定性视图；"
                 "被 BLOCK 的请求只登记阻断理由，绝不给出被阻断的数值结论。")
    lines.append("")
    granted = [p for p in permits if p.get("status") == "permit"]
    blocked = [p for p in permits if p.get("status") == "block"]
    if not granted:
        lines.append("（当前没有任何 PERMIT：不做任何跨论文数值视图。）")
        lines.append("")
    for p in granted:
        lines.append(f"## [{p['permit_id']}] {p['field']}（{p['claim_type']}）")
        lines.append("")
        lines.append(f"断言：{p.get('allowed_assertion', '')}")
        lines.append("")
        dims = p.get("required_dimensions") or CORE_DIMENSIONS
        lines.append("| 论文 | " + " | ".join(dims) + " |")
        lines.append("|---" + "|---" * len(dims) + "|")
        for doc in p["docs"]:
            cells = []
            for d in dims:
                slot = profiles["docs"].get(doc, {}).get(d)
                if slot and slot.get("reported"):
                    cells.append(f"{slot['value']}〔{slot['paragraph_id']}〕")
                else:
                    cells.append("（未报告）")
            lines.append(f"| {doc} | " + " | ".join(cells) + " |")
        lines.append("")
        for n in p.get("normalization_notes", []):
            lines.append(f"- 归一化说明：{n}")
        for c in p.get("caveats", []):
            lines.append(f"- 口径警告：{c}")
        lines.append("")
    if blocked:
        lines.append("## 被阻断的合成请求（仅登记，不给结论）")
        lines.append("")
        for p in blocked:
            lines.append(f"### [{p['request_id']}] {p.get('field', '')}（{p.get('claim_type', '')}）— BLOCK")
            lines.append("")
            lines.append(f"被阻断断言：{p.get('blocked_assertion', '')}")
            lines.append("")
            for b in p.get("blocking", []):
                if "decision_id" in b:
                    va = (b.get("value_a") or {}).get("value")
                    vb = (b.get("value_b") or {}).get("value")
                    lines.append(f"- 阻断维度 {b['dimension']}（{b['verdict']}）：{va!r} vs {vb!r} "
                                 f"[{b['decision_id']}]")
                else:
                    lines.append(f"- {b.get('reason')}")
            lines.append("")
    return "\n".join(lines)


def render_verdict_report(overall_records, permits, case_id, doc_ids):
    granted = [p for p in permits if p.get("status") == "permit"]
    blocked = [p for p in permits if p.get("status") == "block"]
    lines = [f"# 可比性裁定报告（模板，case_id: {case_id}）", ""]
    lines.append("> **叙述绑定规范**：本节之后每个跨论文比较句必须引用 [DEC-…] 或 [PERMIT-…]；"
                 "无 PERMIT 不得写任何定量比较/排名/“优于”结论；定性对照若带口径警告必须复述该警告。")
    lines.append("")
    lines.append("## 1. 语料与任务")
    lines.append("")
    lines.append(f"语料论文：{', '.join(doc_ids)}。裁定维度："
                 f"{', '.join(CORE_DIMENSIONS)}（扩展键见裁定矩阵）。")
    lines.append("")
    lines.append("## 2. 任务级总裁定")
    lines.append("")
    for ov in overall_records:
        pair = " × ".join(ov["doc_pair"])
        lines.append(f"- {pair}：**{ov['verdict']}**（最严维度：{', '.join(ov['strictest_dimensions'])}）"
                     f"[{ov['decision_id']}]")
    lines.append("")
    lines.append("## 3. 许可内合成")
    lines.append("")
    if not granted:
        lines.append("（无 PERMIT：本节不得出现任何跨论文数值比较句。）")
    for p in granted:
        cave = "；".join(p.get("caveats", [])) or "无口径警告"
        lines.append(f"- [{p['permit_id']}] {p.get('allowed_assertion', '')}（{cave}）")
    lines.append("")
    lines.append("## 4. 被阻断的合成")
    lines.append("")
    if not blocked:
        lines.append("（无）")
    for p in blocked:
        for b in p.get("blocking", []):
            if "decision_id" in b:
                va = (b.get("value_a") or {}).get("value")
                vb = (b.get("value_b") or {}).get("value")
                lines.append(f"- [{p['request_id']}] 请求“{p.get('blocked_assertion', '')}”被阻断："
                             f"维度 {b['dimension']} 裁定 {b['verdict']}（{va!r} vs {vb!r}）"
                             f"[{b['decision_id']}]")
            else:
                lines.append(f"- [{p['request_id']}] 被阻断：{b.get('reason')}")
    lines.append("")
    lines.append("## 5. 不可比与未报告项（必须保留，不得删除）")
    lines.append("")
    for ov in overall_records:
        if ov["verdict"] in ("comparable", "convertible"):
            continue
        pair = " × ".join(ov["doc_pair"])
        lines.append(f"- {pair}：阻断/受限维度 = {', '.join(ov['blocking_dimensions'])}"
                     f"[{ov['decision_id']}]")
    lines.append("")
    return "\n".join(lines)


def lint_report(report_path, valid_ids, doc_ids):
    text = Path(report_path).read_text(encoding="utf-8")
    refs = ID_RE.findall(text)
    ref_ids = re.findall(r"\[((?:DEC|PERMIT)-[A-Za-z0-9_.\-]+)\]", text)
    unknown = sorted({r for r in ref_ids if r not in valid_ids})
    warnings = []
    # 启发式：检查"跨论文 + 数字/比较词 + 无任何登记引用"的句子。
    # 以行为单位判定"有出处"：同一行内存在任意登记引用（DEC/PERMIT/REQ）即视为已绑定，
    # 只有整行无引用的跨论文数值句才告警（避免句子切分把引文与断言拆开造成误报）。
    for line in text.splitlines():
        if ANY_REF_RE.search(line):
            continue
        for s in re.split(r"[。！？]", line):
            mentioned = [d for d in doc_ids if d in s]
            if len(mentioned) < 2:
                continue
            s_stripped = s
            for d in mentioned:
                s_stripped = s_stripped.replace(d, "")
            if not (NUM_RE.search(s_stripped) or CMP_WORDS.search(s_stripped)):
                continue
            if s.strip().startswith(("#", ">", "|")):
                continue
            warnings.append(f"疑似未许可的定量比较句: {s.strip()[:120]}")
    return {
        "report": str(report_path),
        "refs_found": len(ref_ids),
        "unknown_ids": unknown,
        "unlicensed_comparison_warnings": warnings,
        "ok": not unknown,
    }


def build_result_json(case, workorder, overall_records, dim_records, permits, outdir):
    case_id = (case or {}).get("case_id") or (workorder or {}).get("case_id") or "UNKNOWN"
    contract = (case or {}).get("output_contract")
    by_verdict = {}
    for r in dim_records:
        by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1
    overall_map = {" × ".join(ov["doc_pair"]): ov["verdict"] for ov in overall_records}
    fillers = {
        "comparison_matrix": {
            "pairs": { " × ".join(ov["doc_pair"]): ov["dimension_verdicts"] for ov in overall_records },
            "detail_file": "decision-matrix.md",
        },
        "comparability_decisions": {
            "total_dimension_decisions": len(dim_records),
            "by_verdict": by_verdict,
            "file": "decisions.jsonl",
        },
        "permitted_syntheses": [
            {"permit_id": p["permit_id"], "field": p["field"], "claim_type": p["claim_type"],
             "docs": p["docs"], "assertion": p.get("allowed_assertion", "")}
            for p in permits if p.get("status") == "permit"
        ],
        "blocked_syntheses": [
            {"request_id": p["request_id"], "field": p.get("field", ""),
             "claim_type": p.get("claim_type", ""), "docs": p.get("docs", []),
             "blocking_dimensions": sorted({b.get("dimension") for b in p.get("blocking", [])
                                            if b.get("dimension")}),
             "assertion_blocked": p.get("blocked_assertion", "")}
            for p in permits if p.get("status") == "block"
        ],
        "overall_verdicts": overall_map,
    }
    uncertainty = []
    result = {"case_id": case_id}
    if contract:
        for key in contract:
            if key in fillers:
                result[key] = fillers[key]
            else:
                result[key] = None
                uncertainty.append(f"output_contract 字段 '{key}' 无自动填充来源，置为 null")
    else:
        result["comparison_matrix"] = fillers["comparison_matrix"]
        result["comparability_decisions"] = fillers["comparability_decisions"]
        result["permitted_syntheses"] = fillers["permitted_syntheses"]
        result["blocked_syntheses"] = fillers["blocked_syntheses"]
        result["overall_verdicts"] = overall_map

    # status：无可比性产物→failed；存在 blocked/undecidable/subset_only 总裁定或字段缺失→partial
    if not overall_records:
        status = "failed"
    else:
        bad = [(p, v) for p, v in overall_map.items() if v not in ("comparable", "convertible")]
        missing_fields = [k for k, v in result.items() if v is None]
        if not bad and not missing_fields:
            status = "success"
        else:
            status = "partial"
            if bad:
                uncertainty.append("存在不可比/受限论文对：" +
                                   "；".join(f"{p}={v}" for p, v in bad))
            if missing_fields:
                uncertainty.append("未填充的契约字段：" + ", ".join(missing_fields))
    result["status"] = status
    result["sources"] = sorted({f"{ov['doc_pair'][0]}" for ov in overall_records} |
                               {f"{ov['doc_pair'][1]}" for ov in overall_records})
    result["uncertainty"] = uncertainty
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="渲染裁定矩阵 / 比较矩阵 / 报告模板 / result.json 并 lint")
    ap.add_argument("--decisions", required=True)
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--workorder", default=None)
    ap.add_argument("--case", default=None)
    ap.add_argument("--permits", nargs="*", default=[])
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--lint", default=None, help="要 lint 的报告路径（缺省=刚渲染的 verdict-report.md）")
    args = ap.parse_args()

    decisions = load_jsonl(args.decisions)
    profiles = json.loads(Path(args.profiles).read_text(encoding="utf-8"))
    workorder = json.loads(Path(args.workorder).read_text(encoding="utf-8")) if args.workorder else None
    case = json.loads(Path(args.case).read_text(encoding="utf-8")) if args.case else None
    permits = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.permits]

    overall_records = [d for d in decisions if d["dimension"] == "__overall__"]
    dim_records = [d for d in decisions if d["dimension"] != "__overall__"]
    doc_ids = (workorder or {}).get("documents") or sorted(profiles["docs"])
    case_id = (case or {}).get("case_id") or (workorder or {}).get("case_id") or "UNKNOWN"

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "decision-matrix.md").write_text(
        render_decision_matrix(decisions, dim_records, overall_records, doc_ids, case_id),
        encoding="utf-8")
    (outdir / "comparison-matrix.md").write_text(
        render_comparison_matrix(permits, profiles, case_id), encoding="utf-8")
    report_path = outdir / "verdict-report.md"
    report_path.write_text(
        render_verdict_report(overall_records, permits, case_id, doc_ids), encoding="utf-8")
    result = build_result_json(case, workorder, overall_records, dim_records, permits, outdir)
    (outdir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    valid_ids = {r["decision_id"] for r in decisions} | \
                {p["permit_id"] for p in permits if p.get("permit_id")}
    lint_target = args.lint or str(report_path)
    lint = lint_report(lint_target, valid_ids, doc_ids)
    (outdir / "lint.json").write_text(json.dumps(lint, ensure_ascii=False, indent=2),
                                      encoding="utf-8")

    print(f"OK: 产物写入 {outdir}")
    print(f"  decision-matrix.md / comparison-matrix.md / verdict-report.md / result.json / lint.json")
    print(f"  result.json status = {result['status']}")
    print(f"  lint: refs={lint['refs_found']} unknown={len(lint['unknown_ids'])} "
          f"warnings={len(lint['unlicensed_comparison_warnings'])}")
    for u in lint["unknown_ids"]:
        print(f"    [LINT-ERROR] 报告引用了不存在的 id: {u}")
    for w in lint["unlicensed_comparison_warnings"]:
        print(f"    [LINT-WARN] {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
