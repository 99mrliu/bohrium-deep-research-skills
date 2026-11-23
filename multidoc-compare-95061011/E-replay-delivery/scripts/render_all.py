#!/usr/bin/env python3
"""render_all.py — 确定性渲染器（记录为体、渲染为影）。

唯一事实来源：work/cells.jsonl + work/decisions.jsonl（格式见 references/record-format.md）。
从记录确定性渲染全部人读产物：
  out/comparison-matrix.md   主比较矩阵 + 六维度可比性矩阵 + 定量合成判定
  out/integration-report.md  简短整合报告（句级 cell_id 引用）
  out/result.json            朝 work/result.schema.json 收口的契约产物

保证：
  * 字节级确定性：排序确定、无时间戳、无随机；同样的记录永远产出字节一致的产物。
  * 渲染后自校验：把生成的 markdown 表格数字回解析，与 JSONL 逐格对账；失败非零退出。
  * manifest 断点续跑：输入 sha256 未变且产物齐全时跳过（--force 强制重渲染）。

仅标准库，无网络。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifest as mf  # noqa: E402

DIMS = ["task", "metric", "units", "material", "pollutant", "budget"]
DIM_ZH = {
    "task": "任务",
    "metric": "指标",
    "units": "单位",
    "material": "材料",
    "pollutant": "污染物",
    "budget": "预算",
}
DIM_CODES = {
    "comparable": "C",
    "not_comparable": "N",
    "not_reported": "NR",
    "unknown": "U",
}
VERDICTS = {"allowed", "blocked", "partial"}
ARTIFACTS = ["comparison-matrix.md", "integration-report.md", "result.json"]
CID_RE = re.compile(r"⟦([A-Za-z0-9_-]+)⟧$")


def fmt_num(x):
    return "%g" % x


def dump_json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def load_jsonl(path):
    recs = []
    if not path.exists():
        return recs
    for ln, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise SystemExit(f"[render_all] {path}:{ln} JSON 解析失败: {e}")
    return recs


def validate_cells(cells):
    errors = []
    ids = set()
    for r in cells:
        for k in ("cell_id", "paper_document_id", "paragraph_id", "field"):
            if k not in r:
                errors.append(f"记录缺键 {k}: {r!r}")
        cid = r.get("cell_id")
        if cid in ids:
            errors.append(f"cell_id 重复: {cid}")
        ids.add(cid)
        comp = r.get("comparability")
        if not isinstance(comp, dict):
            errors.append(f"{cid}: 缺 comparability 对象（六维度必填）")
            continue
        for d in DIMS:
            if comp.get(d) not in DIM_CODES:
                errors.append(
                    f"{cid}: comparability.{d} 非法（须为 {sorted(DIM_CODES)} 之一）"
                )
        num = r.get("numeric_value")
        if num is not None and not isinstance(num, (int, float)):
            errors.append(f"{cid}: numeric_value 必须是数字或 null")
    if errors:
        raise SystemExit("[render_all] cells.jsonl 记录校验失败:\n" + "\n".join(errors))


def validate_decisions(decisions):
    errors = []
    ids = set()
    for d in decisions:
        for k in ("decision_id", "subject", "verdict", "reason"):
            if k not in d:
                errors.append(f"判定缺键 {k}: {d!r}")
        did = d.get("decision_id")
        if did in ids:
            errors.append(f"decision_id 重复: {did}")
        ids.add(did)
        if d.get("verdict") not in VERDICTS:
            errors.append(f"{did}: verdict 非法（须为 allowed/blocked/partial）")
    if errors:
        raise SystemExit("[render_all] decisions.jsonl 判定校验失败:\n" + "\n".join(errors))


def cell_text(rec):
    """矩阵一格的规范文本。数值格：'<num> <unit> ⟦C-xxx⟧'；文本格：'<value> ⟦C-xxx⟧'；未报告：'— ⟦NR⟧'。"""
    if rec is None:
        return "— ⟦NR⟧"
    cid = rec["cell_id"]
    num = rec.get("numeric_value")
    unit = rec.get("unit")
    val = rec.get("value")
    if num is not None:
        body = fmt_num(num) + ((" " + unit) if unit else "")
    elif val is not None:
        body = str(val)
    else:
        return "— ⟦NR⟧"
    if "|" in body or "⟦" in body or "⟧" in body:
        raise SystemExit(f"[render_all] {cid}: 值含表格保留字符: {body!r}")
    return f"{body} ⟦{cid}⟧"


def render_matrix_md(cells, decisions, papers, fields, by_pair):
    L = []
    L.append("# 比较矩阵（由 render_all.py 从 JSONL 记录确定性渲染）")
    L.append("")
    L.append(
        "> 唯一事实来源：work/cells.jsonl + work/decisions.jsonl。"
        "⟦C-xxx⟧ 为 cell_id，可回溯至记录的 (paper_document_id, paragraph_id)；⟦NR⟧ = not_reported。"
        "本文件由记录生成，请勿手工编辑。"
    )
    L.append("")
    L.append("## 1. 共同字段比较矩阵")
    L.append("")
    L.append("| field | " + " | ".join(papers) + " |")
    L.append("|" + "---|" * (len(papers) + 1))
    for f in fields:
        row = [f] + [cell_text(by_pair.get((p, f))) for p in papers]
        L.append("| " + " | ".join(row) + " |")
    L.append("")
    L.append("## 2. 六维度可比性矩阵（C=comparable, N=not_comparable, NR=not_reported, U=unknown）")
    L.append("")
    L.append("| document_id | field | " + " | ".join(DIMS) + " |")
    L.append("|" + "---|" * (len(DIMS) + 2))
    for p in papers:
        for f in fields:
            rec = by_pair.get((p, f))
            if rec is None:
                codes = ["NR"] * len(DIMS)
            else:
                codes = [DIM_CODES[rec["comparability"][d]] for d in DIMS]
            L.append("| " + " | ".join([p, f] + codes) + " |")
    L.append("")
    L.append("## 3. 定量合成判定（任何数值合并之前必须过六维度检验；blocked 禁止合并）")
    L.append("")
    if not decisions:
        L.append("- （无判定记录）")
    for d in decisions:
        basis = ", ".join(d.get("based_on_cells", [])) or "—"
        L.append(
            f"- **{d['decision_id']}** [{d['verdict']}] {d['subject']}：{d['reason']}（依据：{basis}）"
        )
    L.append("")
    return "\n".join(L)


def self_check_matrix(md, cells, papers, fields, by_pair, by_id):
    """回解析生成的 markdown 主矩阵，与 JSONL 逐格对账。返回错误列表（空=通过）。"""
    errors = []
    lines = md.splitlines()
    header = "| field | " + " | ".join(papers) + " |"
    if header not in lines:
        return ["未找到主矩阵表头"]
    h = lines.index(header)
    cols = [c.strip() for c in lines[h].strip().strip("|").split("|")][1:]
    if cols != papers:
        errors.append(f"表头列 {cols} 与论文集合 {papers} 不符")
    seen_pairs = set()
    i = h + 2  # 跳过分隔行
    while i < len(lines) and lines[i].startswith("|"):
        parts = [p.strip() for p in lines[i].strip().strip("|").split("|")]
        field = parts[0]
        for paper, celltxt in zip(cols, parts[1:]):
            m = CID_RE.search(celltxt)
            if not m:
                errors.append(f"{field}/{paper}: 缺 cell_id 标记: {celltxt!r}")
                continue
            cid = m.group(1)
            body = celltxt[: m.start()].strip()
            rec_expected = by_pair.get((paper, field))
            if cid == "NR":
                if rec_expected is not None and (
                    rec_expected.get("numeric_value") is not None
                    or rec_expected.get("value") is not None
                ):
                    errors.append(
                        f"{field}/{paper}: 表格为 NR 但记录 {rec_expected['cell_id']} 有值"
                    )
                continue
            rec = by_id.get(cid)
            if rec is None:
                errors.append(f"{field}/{paper}: 引用了不存在的 {cid}")
                continue
            if rec["paper_document_id"] != paper or rec["field"] != field:
                errors.append(
                    f"{cid}: 表格位置({paper},{field})与记录"
                    f"({rec['paper_document_id']},{rec['field']})不符"
                )
            num = rec.get("numeric_value")
            if num is not None:
                expected_body = fmt_num(num) + ((" " + rec["unit"]) if rec.get("unit") else "")
                if body != expected_body:
                    errors.append(f"{cid}: 表格值 {body!r} ≠ 记录 {expected_body!r}")
                else:
                    tok = body.split(" ")[0]
                    try:
                        back = float(tok)
                        if abs(back - float(num)) > 1e-9:
                            errors.append(f"{cid}: 数字回解析 {back} ≠ 记录 {num}")
                    except ValueError:
                        errors.append(f"{cid}: 数字回解析失败 {tok!r}")
            else:
                if body != str(rec.get("value")):
                    errors.append(f"{cid}: 表格文本 {body!r} ≠ 记录 {rec.get('value')!r}")
            seen_pairs.add((paper, field))
        i += 1
    for r in cells:
        has_val = r.get("numeric_value") is not None or r.get("value") is not None
        if has_val and (r["paper_document_id"], r["field"]) not in seen_pairs:
            errors.append(f"记录 {r['cell_id']} 未在矩阵中出现")
    return errors


# 维度 -> 字段名提示：为 (paper, dim) 选"代表 cell" 时优先取 field 含该提示的记录，
# 使 uncertainty 的"首见"落在语义最相关的格子上（如 pollutant 不可比首见 pollutant 格）。
DIM_FIELD_HINT = {
    "task": "task",
    "metric": "efficiency",
    "units": "unit",
    "material": "material",
    "pollutant": "pollutant",
    "budget": "dosage",
}


def build_uncertainty(cells, decisions):
    """由非 comparable 维度（按 paper×dim 去重）与 blocked/partial 判定生成缺失边界清单。"""
    # 先按 (paper, dim, value) 分组，再选代表 cell（确定性：组内按既定排序取优先匹配者）
    groups = {}
    order = []
    for r in cells:  # 调用前已排序
        comp = r.get("comparability", {})
        for d in DIMS:
            v = comp.get(d)
            if v == "comparable":
                continue
            key = (r["paper_document_id"], d, v)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(r)
    items = []
    for key in order:
        paper, d, v = key
        members = groups[key]
        hint = DIM_FIELD_HINT[d]
        rep = next((m for m in members if hint in m["field"]), members[0])
        cell_id = rep["cell_id"]
        note = rep.get("note") or "无备注"
        if v == "not_comparable":
            items.append(
                f"{paper} 的 {DIM_ZH[d]}({d}) 维度不可比"
                f"（首见 {cell_id}：{note}）"
            )
        elif v == "not_reported":
            items.append(
                f"{paper} 的 {DIM_ZH[d]}({d}) 维度存在未报告项"
                f"（首见 {cell_id}）"
            )
        else:
            items.append(
                f"{paper} 的 {DIM_ZH[d]}({d}) 维度可比性未知"
                f"（首见 {cell_id}）"
            )
    for d in decisions:
        if d.get("verdict") in ("blocked", "partial"):
            items.append(
                f"判定 {d['decision_id']}（{d['verdict']}）：{d['subject']} — {d['reason']}"
            )
    return items


def build_sources(cells):
    agg = {}
    for r in cells:
        agg.setdefault(r["paper_document_id"], set()).add(r["paragraph_id"])
    return [
        {"document_id": k, "paragraph_ids": sorted(v)} for k, v in sorted(agg.items())
    ]


def build_result(schema, cells, decisions, uncertainty, status, sources):
    matrix_entries = [
        {
            "cell_id": r["cell_id"],
            "document_id": r["paper_document_id"],
            "paragraph_id": r["paragraph_id"],
            "field": r["field"],
            "value": r.get("value"),
            "numeric_value": r.get("numeric_value"),
            "unit": r.get("unit"),
        }
        for r in cells
    ]
    comparability_entries = [
        {
            "cell_id": r["cell_id"],
            "document_id": r["paper_document_id"],
            "field": r["field"],
            "comparability": {d: r["comparability"][d] for d in DIMS},
        }
        for r in cells
    ]
    synthesis_entries = [
        {
            "decision_id": d["decision_id"],
            "subject": d["subject"],
            "verdict": d["verdict"],
            "reason": d["reason"],
            "based_on_cells": d.get("based_on_cells", []),
        }
        for d in decisions
    ]
    known = {
        "comparison_matrix": matrix_entries,
        "comparability_assessment": comparability_entries,
        "synthesis": synthesis_entries,
        "sources": sources,
        "uncertainty": uncertainty,
        "result": {
            "matrix": matrix_entries,
            "comparability": comparability_entries,
            "synthesis": synthesis_entries,
        },
    }
    result = {"case_id": schema["case_id"]}
    for f in schema.get("contract_fields", []):
        if f in ("status", "case_id"):
            continue
        result[f] = known.get(f)  # 未识别的契约字段填 null，lint 只强制"在场"
    if not schema.get("contract_fields"):
        result["result"] = known["result"]
    result["status"] = status
    result["sources"] = sources
    result["uncertainty"] = uncertainty
    return result


def render_report_md(cells, decisions, papers, uncertainty, status):
    L = ["# 多文档整合报告（由 render_all.py 从 JSONL 记录确定性渲染）", ""]
    L.append(
        f"本报告由 work/cells.jsonl（{len(cells)} 条单元格记录）与 "
        f"work/decisions.jsonl（{len(decisions)} 条可比性判定）渲染；"
        "每个事实句级引用 cell_id，可回溯至 (document_id, paragraph_id)。请勿手工编辑。"
    )
    L.append("")
    L.append("## 分论文要点")
    for p in papers:
        facts = []
        for r in [c for c in cells if c["paper_document_id"] == p]:
            if r.get("numeric_value") is not None:
                unit = (" " + r["unit"]) if r.get("unit") else ""
                facts.append(
                    f"{r['field']} = {fmt_num(r['numeric_value'])}{unit}"
                    f"（{r['cell_id']}，{p}/{r['paragraph_id']}）"
                )
            elif r.get("value") is not None:
                facts.append(
                    f"{r['field']} = {r['value']}（{r['cell_id']}，{p}/{r['paragraph_id']}）"
                )
            else:
                facts.append(f"{r['field']} 未报告（{r['cell_id']}）")
        L.append(f"- **{p}**：" + "；".join(facts) + "。")
    L.append("")
    L.append("## 可比性与合成结论")
    if not decisions:
        L.append("- （无判定记录）")
    for d in decisions:
        L.append(f"- {d['decision_id']} [{d['verdict']}] {d['subject']}：{d['reason']}")
    L.append("")
    L.append("## 不确定性与缺失边界")
    if not uncertainty:
        L.append("- （无）")
    for u in uncertainty:
        L.append(f"- {u}")
    L.append("")
    L.append(f"交付状态：{status}")
    L.append("")
    return "\n".join(L)


def run(workdir, outdir, force=False, register=True):
    workdir = Path(workdir)
    outdir = Path(outdir)
    cells_path = workdir / "cells.jsonl"
    dec_path = workdir / "decisions.jsonl"
    schema_path = workdir / "result.schema.json"
    for p in (cells_path, dec_path, schema_path):
        if not p.exists():
            raise SystemExit(
                f"[render_all] 缺少输入: {p}"
                "（先运行 init_contract.py，并按 references/record-format.md 写入记录）"
            )
    inputs = [cells_path, dec_path, schema_path]
    if register and not force and mf.should_skip(workdir, "render", inputs):
        print("[render_all] 阶段 render：输入未变且产物齐全，跳过（幂等续跑）。")
        return

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    cells = load_jsonl(cells_path)
    decisions = load_jsonl(dec_path)
    validate_cells(cells)
    validate_decisions(decisions)

    # 确定性排序
    cells = sorted(cells, key=lambda r: (r["paper_document_id"], r["field"], r["cell_id"]))
    decisions = sorted(decisions, key=lambda d: d["decision_id"])
    papers = sorted({r["paper_document_id"] for r in cells})
    fields = sorted({r["field"] for r in cells})
    by_pair = {(r["paper_document_id"], r["field"]): r for r in cells}
    by_id = {r["cell_id"]: r for r in cells}

    # 渲染主矩阵并自校验（回解析数字对账）
    md = render_matrix_md(cells, decisions, papers, fields, by_pair)
    errors = self_check_matrix(md, cells, papers, fields, by_pair, by_id)
    if errors:
        raise SystemExit(
            "[render_all] 自校验失败（markdown 回解析与 JSONL 对账不符），停止交付:\n"
            + "\n".join("  - " + e for e in errors)
        )

    uncertainty = build_uncertainty(cells, decisions)
    status = "success" if not uncertainty else "partial"
    sources = build_sources(cells)
    result = build_result(schema, cells, decisions, uncertainty, status, sources)
    report = render_report_md(cells, decisions, papers, uncertainty, status)

    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "comparison-matrix.md").write_text(md, encoding="utf-8")
    (outdir / "integration-report.md").write_text(report, encoding="utf-8")
    (outdir / "result.json").write_text(dump_json(result), encoding="utf-8")

    if register:
        mf.begin_stage(workdir, "render", inputs)
        mf.end_stage(workdir, "render", [outdir / a for a in ARTIFACTS])
    print(
        f"[render_all] 渲染完成并通过自校验：{len(cells)} 单元格 / {len(decisions)} 判定 "
        f"-> {', '.join(ARTIFACTS)}；status={status}"
    )


def main():
    ap = argparse.ArgumentParser(description="确定性渲染器：从 JSONL 记录生成全部人读产物")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--outdir", default="/app/output")
    ap.add_argument("--force", action="store_true", help="忽略 manifest 断点，强制重渲染")
    args = ap.parse_args()
    run(args.workdir, args.outdir, force=args.force, register=True)


if __name__ == "__main__":
    main()
