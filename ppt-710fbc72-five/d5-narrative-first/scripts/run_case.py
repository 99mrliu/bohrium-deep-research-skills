#!/usr/bin/env python3
"""run_case.py — narrative-first-deck 两阶段单入口。

用法:
  python3 run_case.py prepare --input /input --work /app/work --output /app/output
  python3 run_case.py finish  --input /input --work /app/work --output /app/output

prepare: 引导依赖 → 读 case.json/task.md/材料 → PyMuPDF 抽取论文章节/图/数字 →
         立即写 partial result.json（含 output_contract 全部字段）→
         预填 storyline.json 与 slide_plan.json 骨架 → 打印 NEXT ACTION。
finish : plan_lint 门禁（fail 则不构建、result.json 记 failed）→ build_deck →
         export_render → 汇总 evidence_map/artifacts(sha256)/uncertainty/change_log，
         写最终 result.json 并打印逐页核对清单。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent

CONTRACT_DEFAULTS = {
    "case_id": "", "status": "partial", "summary": "",
    "artifacts": [], "evidence_map": [], "sources": [],
    "uncertainty": [], "change_log": [],
}

STORYLINE_SKELETON = {
    "_doc": ("叙事主线是本 Skill 的创作核心，先写主线再写页。"
             "mainline 用四句话概括 problem/method/results/limitations；"
             "claims 按 problem→method→results→limitations 排序；"
             "每条 claim 必须有 evidence_refs（type: page|figure|table|section，ref 如 'p.4'/'Figure 2'，"
             "quote 为原文逐字段），depends_on 编码叙事先后（被依赖者必须先讲）。"
             "audience/duration_min 从 task.md 解析值预填，可改。数字必须与源文本逐字一致。"),
    "mainline": {"problem": "", "method": "", "results": "", "limitations": ""},
    "audience": "",
    "duration_min": None,
    "claims": [
        {"id": "c1", "text": "<一句话主张：问题是什么>", "evidence_refs": [], "depends_on": []},
        {"id": "c2", "text": "<一句话主张：方法是什么>", "evidence_refs": [], "depends_on": ["c1"]},
        {"id": "c3", "text": "<一句话主张：结果是什么>", "evidence_refs": [], "depends_on": ["c2"]},
        {"id": "c4", "text": "<一句话主张：限制与结论>", "evidence_refs": [], "depends_on": ["c3"]},
    ],
}

SLIDE_PLAN_SKELETON = {
    "_doc": ("每页恰好一个 claim_id（命中 storyline.claims）；kind 必须覆盖 "
             "title/background/method/results/discussion/conclusion；"
             "bullets 中数字须与源文本逐字一致；figures[].ref 必须与该页 claim 的 figure 证据一致；"
             "notes 是逐字讲稿，长度决定计时（中文≈4字/秒，英文≈2.2词/秒，总长须在 duration±15% 内）。"
             "候选数字句子见 work/paper/source_index.json 的 number_candidates。"),
    "slides": [
        {"kind": k, "title": "", "claim_id": None, "claim": "", "bullets": [],
         "figures": [], "evidence": [], "notes": "", "layout_hint": "Title and Content"}
        for k in ["title", "background", "method", "results", "discussion", "conclusion"]
    ],
}


def _contract_fields(case: dict) -> list:
    oc = case.get("output_contract") or {}
    fields = oc.get("fields") if isinstance(oc, dict) else None
    if not fields:
        fields = list(CONTRACT_DEFAULTS)
    return [f for f in fields if isinstance(f, str)]


def _empty_result(case: dict, status: str) -> dict:
    res = {}
    for f in _contract_fields(case):
        res[f] = CONTRACT_DEFAULTS.get(f, "")
    res["case_id"] = case.get("case_id", res.get("case_id") or "unknown")
    res["status"] = status
    return res


def cmd_prepare(args) -> int:
    input_dir, work, output = Path(args.input), Path(args.work), Path(args.output)
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    change_log = [{"ts": common.now_iso(), "event": "prepare 开始"}]

    degraded = common.bootstrap_deps(change_log)

    case = common.read_json(input_dir / "case.json", {}) or {}
    task_text = common.read_text(input_dir / "task.md")
    constraints = common.parse_task_constraints(task_text)
    materials = common.find_materials(input_dir, case)
    mats_found = {k: v for k, v in materials.items() if v}
    change_log.append({"ts": common.now_iso(), "event":
                       f"读取输入: case_id={case.get('case_id')}, constraints={constraints}, "
                       f"materials={mats_found}"})

    # 抽取论文
    source_index = {}
    if materials.get("paper_pdf"):
        try:
            source_index = common.extract_paper(materials["paper_pdf"], work)
            change_log.append({"ts": common.now_iso(), "event":
                               f"论文抽取: {source_index['n_pages']} 页, "
                               f"图 {len(source_index['figures'])}, 表 {len(source_index['tables'])}, "
                               f"数字候选句 {len(source_index['number_candidates'])}"})
        except Exception as e:  # noqa: BLE001
            degraded.append(f"论文 PDF 抽取失败: {e}")
    else:
        degraded.append("未发现论文 PDF 材料")

    # 解剖模板
    template_report = {}
    if materials.get("template_pptx"):
        try:
            template_report = common.template_anatomy(materials["template_pptx"])
            common.write_json(work / "template_report.json", template_report)
            change_log.append({"ts": common.now_iso(), "event":
                               f"模板解剖: {template_report['n_layouts']} 个版式"})
        except Exception as e:  # noqa: BLE001
            degraded.append(f"模板 PPTX 解剖失败: {e}")
    else:
        degraded.append("未发现模板 PPTX（build 将退回 python-pptx 默认模板）")

    common.write_json(work / "config.json", {
        "case_id": case.get("case_id"), "constraints": constraints,
        "materials": materials, "task_md": str(input_dir / "task.md"),
        "degraded": degraded, "prepared_at": common.now_iso(),
    })

    # partial-first：立即写 result.json（含全部 contract 字段）
    res = _empty_result(case, "partial")
    res["summary"] = ("prepare 完成：论文与模板已抽取，storyline/slide_plan 骨架已预填，"
                      "等待 Agent 编辑叙事主线与页面计划。")
    res["sources"] = [v for v in [materials.get("paper_pdf"), materials.get("template_pptx"),
                                  str(input_dir / "task.md")] if v]
    res["uncertainty"] = degraded + ["当前为 partial：deck 尚未构建"]
    res["change_log"] = change_log
    common.write_json(output / "result.json", res)

    # 预填骨架（已存在则不覆盖 Agent 的劳动）
    storyline = dict(STORYLINE_SKELETON)
    storyline["audience"] = constraints.get("audience") or ""
    storyline["duration_min"] = constraints.get("duration_min")
    if not (work / "storyline.json").exists():
        common.write_json(work / "storyline.json", storyline)
    if not (work / "slide_plan.json").exists():
        common.write_json(work / "slide_plan.json", SLIDE_PLAN_SKELETON)

    print("[prepare] 完成")
    print(f"  抽取: {source_index.get('n_pages', 0)} 页论文, "
          f"{len(source_index.get('figures', []))} 图, {len(source_index.get('tables', []))} 表")
    print(f"  约束: audience={constraints.get('audience')}, "
          f"duration={constraints.get('duration_min')}min, "
          f"slides={constraints.get('slides_min')}-{constraints.get('slides_max')}")
    if degraded:
        print(f"  degraded: {degraded}")
    print("NEXT ACTION: 编辑 /app/work/storyline.json（先写 mainline 与 claims，"
          "每条主张挂证据锚点 p.N/Figure N/Table N）")
    print("NEXT ACTION: 编辑 /app/work/slide_plan.json（一页一个 claim_id，bullets 数字逐字，"
          "notes 写逐字讲稿以匹配时长预算）")
    print("NEXT ACTION: 候选数字句子见 /app/work/paper/source_index.json → number_candidates；"
          "完成后运行 run_case.py finish")
    return 0


def _run_script(name: str, *cli) -> int:
    r = subprocess.run([sys.executable, str(SCRIPTS / name), *cli])
    return r.returncode


def _finalize_result(case, work, output, status, summary, degraded, change_log) -> dict:
    plan = common.read_json(Path(work) / "slide_plan.json", {}) or {}
    storyline = common.read_json(Path(work) / "storyline.json", {}) or {}
    claims = {c.get("id"): c for c in storyline.get("claims", [])}

    evidence_map = []
    for i, s in enumerate(plan.get("slides", []), 1):
        cid = s.get("claim_id")
        c = claims.get(cid, {})
        evidence_map.append({
            "slide": i, "kind": s.get("kind"), "title": s.get("title", ""),
            "claim_id": cid, "claim": s.get("claim") or c.get("text", ""),
            "anchors": [{"type": ev.get("type"), "ref": ev.get("ref"),
                         "quote": ev.get("quote", "")}
                        for ev in (c.get("evidence_refs", []) or [])],
            "figures": [{"ref": f.get("ref"), "path": f.get("path")}
                        for f in s.get("figures", [])],
        })

    artifacts = []
    for p in sorted(Path(output).rglob("*")):
        if p.is_file() and p.name != "result.json":
            artifacts.append({"path": str(p.relative_to(output)),
                              "sha256": common.sha256_file(p),
                              "bytes": p.stat().st_size})

    res = _empty_result(case, status)
    res["summary"] = summary
    if "artifacts" in res:
        res["artifacts"] = artifacts
    if "evidence_map" in res:
        res["evidence_map"] = evidence_map
    if "sources" in res:
        mats = common.read_json(Path(work) / "config.json", {}).get("materials", {})
        res["sources"] = [v for v in [mats.get("paper_pdf"), mats.get("template_pptx"),
                                      str(Path(work).parent / "input" / "task.md")] if v] \
            or [str(Path(work) / "paper" / "source_index.json")]
    if "uncertainty" in res:
        res["uncertainty"] = degraded + [
            "讲稿计时为语速模型估计（中文≈4字/秒、英文≈2.2词/秒），实际口播受语速/停顿/翻页影响，"
            "故预算按 duration±15% 判定；个别页估计误差可能更大。",
            "数字逐字校验以抽取文本为准；PDF 抽取本身的断行/乱码可能造成误报或漏报。",
        ]
    if "change_log" in res:
        res["change_log"] = change_log
    common.write_json(Path(output) / "result.json", res)
    return res


def cmd_finish(args) -> int:
    input_dir, work, output = Path(args.input), Path(args.work), Path(args.output)
    case = common.read_json(input_dir / "case.json", {}) or {}
    cfg = common.read_json(work / "config.json", {}) or {}
    change_log = [{"ts": common.now_iso(), "event": "finish 开始"}]
    degraded = list(cfg.get("degraded", []))

    # 1) 叙事门禁：fail → 不构建
    rc = _run_script("plan_lint.py", "--work", str(work), "--output", str(output),
                     "--input", str(input_dir))
    lint = common.read_json(output / "plan_lint_report.json", {}) or {}
    change_log.append({"ts": common.now_iso(), "event":
                       f"plan_lint overall={lint.get('overall')} fails={lint.get('fails')}"})
    if rc != 0:
        summary = ("plan_lint 未通过，已按门禁拒绝构建。失败规则: "
                   f"{lint.get('fails')}；详见 plan_lint_report.json，"
                   "修正 /app/work/storyline.json 与 slide_plan.json 后重跑 finish。")
        _finalize_result(case, work, output, "failed", summary, degraded, change_log)
        print(f"[finish] {summary}")
        return 1

    # 2) 构建
    rc = _run_script("build_deck.py", "--work", str(work), "--output", str(output))
    if rc != 0:
        _finalize_result(case, work, output, "failed", "build_deck 失败", degraded, change_log)
        return 1
    change_log.append({"ts": common.now_iso(), "event": "build_deck 完成"})

    # 3) 导出渲染 + QA
    _run_script("export_render.py", "--work", str(work), "--output", str(output))
    qa = common.read_json(output / "qa_report.json", {}) or {}
    if qa.get("degraded"):
        degraded += [f"导出环节 degraded: {d}" for d in qa["degraded"]]
    change_log.append({"ts": common.now_iso(), "event":
                       f"export_render status={qa.get('status')} "
                       f"parity={qa.get('page_parity', {}).get('parity')}"})

    parity = qa.get("page_parity", {}).get("parity")
    status = "partial" if (degraded or lint.get("overall") == "warn") else "success"
    if qa.get("pdf_pages") and not parity:
        status = "partial"
        degraded.append("pptx/PDF 页数不一致，见 qa_report.json")
    summary = (f"deck.pptx {qa.get('pptx_slides', '?')} 页已按模板构建并经 plan_lint 校验"
               f"（overall={lint.get('overall')}）；导出 deck.pdf 页数一致={parity}。"
               + (f" 存在 degraded/partial 项 {len(degraded)} 条。" if status == "partial" else ""))
    res = _finalize_result(case, work, output, status, summary, degraded, change_log)

    # 逐页核对清单
    print("[finish] 逐页核对清单（slide / kind / claim / 计时 / 证据锚点）:")
    timing = {t["slide"]: t for r in lint.get("rules", []) if r["rule"] == "R6_time_budget"
              for t in r["details"].get("timeline", [])}
    for em in res.get("evidence_map", []):
        t = timing.get(em["slide"], {})
        anchors = "; ".join(f"{a['type']}:{a['ref']}" for a in em["anchors"])
        print(f"  {em['slide']:>2}. [{em['kind']:<10}] {em['claim_id']}: {em['claim'][:40]}…"
              f"  ⏱~{t.get('seconds', '?')}s  证据: {anchors}")
    print(f"[finish] status={status} summary: {summary}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="narrative-first-deck 两阶段入口")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prepare", "finish"):
        p = sub.add_parser(name)
        p.add_argument("--input", required=True)
        p.add_argument("--work", required=True)
        p.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    return cmd_prepare(args) if args.cmd == "prepare" else cmd_finish(args)


if __name__ == "__main__":
    sys.exit(main())
