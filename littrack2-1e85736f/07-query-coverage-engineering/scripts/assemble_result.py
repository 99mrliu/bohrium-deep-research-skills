#!/usr/bin/env python3
"""assemble_result.py — 汇总各阶段产物，按 output_contract 强制校验并写出 result.json。

规则：
  - result.json 必须包含 case.json output_contract 列出的全部字段；
  - 缺失字段补 null，且 status 置为 "partial"，并在 contract_notes 中逐条说明；
  - 任何降级信号（概念块降级解析、无种子图谱、源无快照、lint 存在 error）也置 partial；
  - 绝不编造文献、DOI、元数据或检索结果；事实性字段值带 locator（文件路径 + JSON 指针）。

仅用 Python3 标准库，完全离线，确定性输出。

用法:
  python3 assemble_result.py --case case.json --concepts concepts.json \
      --queries queries.json --lint lint_report.json \
      --coverage coverage_revised.json --coverage-initial coverage_initial.json \
      [--revisions revisions.json] --out result.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_omissions(coverage: dict, lint: dict, concepts_doc: dict) -> list[str]:
    """确定性生成遗漏说明。"""
    omissions: list[str] = []
    for seed in coverage.get("seeds", []):
        absent_in = [s for s, c in seed["sources"].items() if c["status"] == "absent_from_snapshot"]
        if absent_in:
            omissions.append(
                f"种子 {seed['seed_id']} 在源 {absent_in} 的快照中不存在，"
                f"无法验证该源召回（可能该源未收录或快照未覆盖；非检索式问题，见 locator "
                f"{seed['seed_locator']['path']}#{seed['seed_locator']['pointer']}）")
        outside = [s for s, c in seed["sources"].items() if c["status"] == "outside_window"]
        if outside:
            omissions.append(
                f"种子 {seed['seed_id']} 在源 {outside} 中记录日期超出窗口，被窗口条件排除")
    for src, summ in coverage.get("summary", {}).items():
        if summ.get("no_snapshot"):
            omissions.append(f"源 {src} 无快照数据，该源覆盖验证缺失")
    if concepts_doc.get("degraded"):
        omissions.append("概念块来自降级路径（规则抽取或人工补全），覆盖结论依赖模型复核后的概念块")
    if coverage.get("seeds_total", 0) == 0:
        omissions.append("材料中无种子参考图谱，已知项召回验证整体缺失（诚实降级）")
    omissions.append(
        "覆盖验证仅针对保留的种子清单；真实全量相关文献的召回率离线不可知，"
        "本结果是召回能力的可验证下界，不是完整召回证明")
    return omissions


def assemble(case: dict, paths: dict) -> dict:
    concepts_doc = _load(paths["concepts"]) if paths.get("concepts") else {}
    queries_doc = _load(paths["queries"]) if paths.get("queries") else {}
    queries_initial_doc = _load(paths["queries_initial"]) if paths.get("queries_initial") else None
    lint_doc = _load(paths["lint"]) if paths.get("lint") else {}
    coverage = _load(paths["coverage"]) if paths.get("coverage") else {}
    coverage_initial = _load(paths["coverage_initial"]) if paths.get("coverage_initial") else None
    revisions = _load(paths["revisions"]) if paths.get("revisions") else []

    partial_reasons: list[str] = []
    if concepts_doc.get("degraded"):
        partial_reasons.append("概念块为降级解析结果（needs_model_review）")
    if lint_doc.get("summary", {}).get("error"):
        partial_reasons.append(f"lint 存在 {lint_doc['summary']['error']} 条 error 级 finding")
    if not coverage or coverage.get("seeds_total", 0) == 0:
        partial_reasons.append("无有效已知项覆盖验证（无种子图谱或无材料）")
    if coverage.get("missed_seeds"):
        # 若最终（修订后）覆盖仍有 miss，则为 partial
        partial_reasons.append(f"最终覆盖仍有 {len(coverage['missed_seeds'])} 颗种子未命中")

    omissions = build_omissions(coverage, lint_doc, concepts_doc) if coverage else [
        "无覆盖验证产物，无法生成遗漏说明"]

    result: dict = {
        "case_id": case.get("case_id"),
        "status": "complete",
        "synthetic": bool(case.get("synthetic", False)),
        "synthetic_note": case.get("synthetic_note"),
        "concepts": {
            "final": coverage.get("concepts_used"),
            "initial": concepts_doc.get("concepts"),
            "degraded": concepts_doc.get("degraded"),
            "needs_model_review": concepts_doc.get("needs_model_review"),
            "warnings": concepts_doc.get("warnings", []),
            "locator": concepts_doc.get("locator"),
        },
        "queries": {
            "initial": (queries_initial_doc or queries_doc).get("queries"),
            "final": queries_doc.get("queries"),
            "window": queries_doc.get("window"),
            "locator": {"path": paths.get("queries"), "pointer": "/queries"},
        },
        "lint_report": {
            "findings": lint_doc.get("findings"),
            "summary": lint_doc.get("summary"),
            "rule_table": lint_doc.get("rule_table"),
            "locator": {"path": paths.get("lint"), "pointer": "/"},
        },
        "coverage": {
            "final": coverage or None,
            "initial_summary": (coverage_initial or {}).get("summary"),
            "locator": {"path": paths.get("coverage"), "pointer": "/"},
        },
        "missed_seeds": (coverage_initial or coverage).get("missed_seeds"),
        "query_revisions": revisions,
        "omissions": omissions,
        "locators": {
            "case": {"path": paths.get("case"), "pointer": "/"},
            "concepts": concepts_doc.get("locator"),
            "queries": {"path": paths.get("queries"), "pointer": "/queries"},
            "lint_report": {"path": paths.get("lint"), "pointer": "/"},
            "coverage_final": {"path": paths.get("coverage"), "pointer": "/"},
            "coverage_initial": {"path": paths.get("coverage_initial"),
                                 "pointer": "/"} if paths.get("coverage_initial") else None,
        },
    }

    contract = case.get("output_contract") or []
    contract_notes: list[str] = []
    for field in contract:
        if field not in result:
            result[field] = None
            contract_notes.append(f"output_contract 字段 '{field}' 缺失，已补 null")
    if contract_notes:
        partial_reasons.extend(contract_notes)

    if partial_reasons:
        result["status"] = "partial"
    result["contract_notes"] = contract_notes
    result["partial_reasons"] = partial_reasons
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="按 output_contract 汇总并校验 result.json")
    ap.add_argument("--case", required=True)
    ap.add_argument("--concepts", required=True)
    ap.add_argument("--queries", required=True, help="最终（修订后）queries.json")
    ap.add_argument("--queries-initial", default=None)
    ap.add_argument("--lint", required=True)
    ap.add_argument("--coverage", required=True, help="最终（修订后）coverage json")
    ap.add_argument("--coverage-initial", default=None)
    ap.add_argument("--revisions", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    case = _load(args.case)
    paths = {
        "case": args.case, "concepts": args.concepts, "queries": args.queries,
        "queries_initial": args.queries_initial, "lint": args.lint,
        "coverage": args.coverage, "coverage_initial": args.coverage_initial,
        "revisions": args.revisions,
    }
    result = assemble(case, paths)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[assemble_result] status={result['status']} "
          f"partial_reasons={len(result['partial_reasons'])} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
