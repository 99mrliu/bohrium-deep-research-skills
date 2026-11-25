#!/usr/bin/env python3
"""run_minimal_example.py — 端到端最小示例 + 自检。

流程（全部离线、确定性）：
  1. concept_parse   : case.json -> 概念块
  2. query_build     : 概念块 -> 三源布尔检索式（初始）
  3. query_lint      : 静态审计（初始 + 修订后）
  4. coverage_check  : 已知项召回验证（初始检索式）
  5. 依据诊断确定性生成"最小化查询修订"（取每颗未命中种子每个漏配块的 top-1 建议），
     重建检索式并重跑覆盖验证（修订后）
  6. assemble_result : 按 output_contract 汇总 result.json
  7. 自检：
     - 埋点断言：seed-3 在初始检索式下于 crossref/arxiv 为 miss、漏配块为 method、
       top-1 建议为 "message passing"，修订后转为 hit；
     - result.json 含 output_contract 全部字段；
     - bundle 约束：文件数 ≤50、单文件 ≤500KB、总计 ≤2MB、无符号链接、
       全部 UTF-8 文本、每个文件带扩展名。

用法: python3 run_minimal_example.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BUNDLE_ROOT = SCRIPT_DIR.parent
EXAMPLE = BUNDLE_ROOT / "examples" / "minimal"
OUT = EXAMPLE / "output"

sys.path.insert(0, str(SCRIPT_DIR))
import assemble_result  # noqa: E402
import concept_parse  # noqa: E402
import coverage_check  # noqa: E402
import query_build  # noqa: E402
import query_lint  # noqa: E402

MAX_FILES = 50
MAX_FILE_BYTES = 500 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024


def dump(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(BUNDLE_ROOT)}")


def derive_revisions(coverage: dict) -> list[dict]:
    """从初始覆盖诊断中确定性抽取最小化修订：每颗 miss 种子、每个漏配块的 top-1 建议。"""
    revisions: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for seed in coverage.get("missed_seeds", []):
        for src in seed["miss_in_sources"]:
            diag = seed["diagnosis"][src]
            for item in diag.get("minimal_revision", []):
                key = (item["concept"], item["add_term"])
                if key in seen:
                    continue
                seen.add(key)
                revisions.append({
                    "concept": item["concept"],
                    "add_term": item["add_term"],
                    "rationale": (
                        f"种子 {seed['seed_id']} 在源 {src} 被概念块 "
                        f"'{item['concept']}' 挡掉（该块无同义词命中其记录）；"
                        f"加入从该记录文本确定性抽取的 top-1 候选同义词 "
                        f"'{item['add_term']}' 为最小化修订"),
                    "evidence": {
                        "seed_id": seed["seed_id"],
                        "seed_locator": seed["seed_locator"],
                        "record_locator": seed["record_locators"][src],
                    },
                })
    return revisions


def apply_revisions(concepts: list[dict], revisions: list[dict]) -> list[dict]:
    revised = copy.deepcopy(concepts)
    for rev in revisions:
        for blk in revised:
            if blk["id"] == rev["concept"] and rev["add_term"] not in blk["terms"]:
                blk["terms"].append(rev["add_term"])
    return revised


def check_bundle_constraints(root: Path) -> dict:
    files = [p for p in sorted(root.rglob("*")) if p.is_file() or p.is_symlink()]
    problems: list[str] = []
    total = 0
    for p in files:
        if p.is_symlink():
            problems.append(f"符号链接: {p.relative_to(root)}")
            continue
        size = p.stat().st_size
        total += size
        if size > MAX_FILE_BYTES:
            problems.append(f"单文件超 500KB: {p.relative_to(root)} ({size}B)")
        if not p.suffix:
            problems.append(f"无扩展名: {p.relative_to(root)}")
        try:
            p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, ValueError):
            problems.append(f"非 UTF-8 文本: {p.relative_to(root)}")
    if len(files) > MAX_FILES:
        problems.append(f"文件数 {len(files)} > {MAX_FILES}")
    if total > MAX_TOTAL_BYTES:
        problems.append(f"总大小 {total}B > {MAX_TOTAL_BYTES}B")
    return {"file_count": len(files), "total_bytes": total, "problems": problems}


def main() -> int:
    print("== 07-query-coverage-engineering: minimal example ==")
    case_path = EXAMPLE / "case.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    materials = EXAMPLE / case["materials_dir"]

    print("[1/7] concept_parse")
    concepts_doc = concept_parse.parse_case(case_path, EXAMPLE / "task.md")
    dump(concepts_doc, OUT / "concepts.json")
    concepts = concepts_doc["concepts"]
    assert concepts, "概念块为空"

    print("[2/7] query_build (initial)")
    queries_initial = {"concepts": concepts, "window": case.get("window"),
                       "queries": query_build.build_all(concepts, case.get("window"))}
    dump(queries_initial, OUT / "queries.json")

    print("[3/7] query_lint (initial)")
    lint_initial = query_lint.lint(concepts, queries_initial["queries"])

    print("[4/7] coverage_check (initial)")
    coverage_initial = coverage_check.run(case, concepts, materials)
    dump(coverage_initial, OUT / "coverage_initial.json")

    print("[5/7] derive & apply minimal revisions, rebuild, re-run coverage")
    revisions = derive_revisions(coverage_initial)
    dump(revisions, OUT / "revisions.json")
    revised_concepts = apply_revisions(concepts, revisions)
    queries_revised = {"concepts": revised_concepts, "window": case.get("window"),
                       "queries": query_build.build_all(revised_concepts, case.get("window"))}
    dump(queries_revised, OUT / "queries_revised.json")
    lint_revised = query_lint.lint(revised_concepts, queries_revised["queries"])
    lint_report = dict(lint_revised)  # 顶层 = 最终（修订后）lint 结果
    lint_report["per_stage"] = {"initial": lint_initial, "revised": lint_revised}
    lint_report["note"] = "lint 只做静态审计与建议；召回修复由 coverage_check 诊断驱动"
    dump(lint_report, OUT / "lint_report.json")
    coverage_revised = coverage_check.run(case, revised_concepts, materials)
    dump(coverage_revised, OUT / "coverage_revised.json")

    print("[6/7] assemble_result")
    paths = {
        "case": str(case_path),
        "concepts": str(OUT / "concepts.json"),
        "queries": str(OUT / "queries_revised.json"),
        "queries_initial": str(OUT / "queries.json"),
        "lint": str(OUT / "lint_report.json"),
        "coverage": str(OUT / "coverage_revised.json"),
        "coverage_initial": str(OUT / "coverage_initial.json"),
        "revisions": str(OUT / "revisions.json"),
    }
    result = assemble_result.assemble(case, paths)
    dump(result, OUT / "result.json")

    print("[7/7] self-checks")
    # --- 埋点断言：seed-3 初始漏检、诊断为 method 块、建议 message passing、修订后命中
    s3 = next(s for s in coverage_initial["seeds"] if s["seed_id"] == "seed-3")
    for src in ("crossref", "arxiv"):
        cell = s3["sources"][src]
        assert cell["status"] == "miss", f"seed-3 {src} 初始应为 miss，实为 {cell['status']}"
        assert cell["missed_blocks"] == ["method"], f"seed-3 {src} 漏配块应为 ['method']"
        top1 = cell["diagnosis"]["suggestions"]["method"][0]["term"]
        assert top1 == "message passing", f"seed-3 {src} top-1 建议应为 'message passing'，实为 '{top1}'"
    assert s3["sources"]["europepmc"]["status"] == "absent_from_snapshot", \
        "seed-3 在 europepmc 应为 absent_from_snapshot"
    s3r = next(s for s in coverage_revised["seeds"] if s["seed_id"] == "seed-3")
    for src in ("crossref", "arxiv"):
        assert s3r["sources"][src]["status"] == "hit", \
            f"seed-3 {src} 修订后应为 hit，实为 {s3r['sources'][src]['status']}"
    print("  PASS 埋点断言: seed-3 初始漏检 -> 诊断 method 块缺 'message passing' -> 修订后命中")

    # --- lint 预期：QL003 命中过宽 term 'property'；QL001 命中 crossref 短语退化
    q3 = [f for f in lint_initial["findings"] if f["rule_id"] == "QL003" and f["term"] == "property"]
    assert q3 and q3[0]["severity"] == "warn", "QL003 应对 'property' 给出 warn"
    q1 = [f for f in lint_initial["findings"] if f["rule_id"] == "QL001"]
    assert q1, "QL001 应对 crossref 多词 term 给出 info"
    assert lint_initial["summary"]["error"] == 0, "初始 lint 不应有 error"
    print(f"  PASS lint 断言: summary={lint_initial['summary']}")

    # --- result.json 契约校验
    contract = case["output_contract"]
    missing = [f for f in contract if f not in result]
    assert not missing, f"result.json 缺契约字段: {missing}"
    assert result["case_id"] == case["case_id"]
    assert result["status"] == "complete", \
        f"修订后应 complete（无未命中种子、无 lint error），实为 {result['status']}: {result['partial_reasons']}"
    assert result["missed_seeds"], "result.missed_seeds 应记录初始漏检诊断"
    assert any(r["add_term"] == "message passing" for r in result["query_revisions"])
    print(f"  PASS 契约断言: {len(contract)} 个字段齐全, status=complete")

    # --- bundle 约束自查
    bc = check_bundle_constraints(BUNDLE_ROOT)
    print(f"  bundle: files={bc['file_count']} total={bc['total_bytes']}B problems={bc['problems']}")
    assert not bc["problems"], f"bundle 约束自查失败: {bc['problems']}"
    print("  PASS bundle 约束: <=50 文件 / 单文件 <=500KB / 总计 <=2MB / 无符号链接 / 全 UTF-8 / 均有扩展名")

    print("== ALL CHECKS PASSED ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
