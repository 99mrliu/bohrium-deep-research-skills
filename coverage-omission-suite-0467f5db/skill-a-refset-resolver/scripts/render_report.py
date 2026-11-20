#!/usr/bin/env python3
"""render_report.py — 步骤⑩：复核与交付。

汇总各阶段产物（materials_index / reference_set / coverage / miss_attribution），
生成人读覆盖报告 coverage_report.md、matplotlib 可用时渲染覆盖率预览 PNG
（可用则渲染，绝不强制），并组装 result.json（含 case_id、output_contract
全部字段、status、sources、uncertainty、change_log）。

退出码：0 正常；2 部分产物缺失（诚实降级）；3 参考集缺失（校验失败）。
仅标准库。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_NAME = "render_report.py"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def try_render_png(coverage, out_path):
    """matplotlib 可用时渲染覆盖率预览；失败静默返回 False。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    try:
        den = coverage.get("denominator", 0)
        hit = coverage.get("hit", 0)
        miss = coverage.get("miss", 0)
        if den == 0:
            return False
        fig, ax = plt.subplots(figsize=(4, 4))
        ax.pie([hit, miss], labels=[f"hit {hit}", f"miss {miss}"],
               colors=["#4C9A6A", "#C4554C"], autopct="%1.1f%%",
               startangle=90)
        ax.set_title(f"Coverage {coverage.get('coverage_ratio')}")
        fig.tight_layout()
        fig.savefig(out_path, dpi=120)
        plt.close(fig)
        return True
    except Exception:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="汇总产物，生成覆盖报告与 result.json。")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--outdir", default="/app/output")
    args = ap.parse_args(argv)

    refset = load_json(os.path.join(args.outdir, "reference_set.json"))
    if not refset:
        print(f"[{SCRIPT_NAME}] 缺少 reference_set.json，无法交付。",
              file=sys.stderr)
        return 3
    coverage = load_json(os.path.join(args.outdir, "coverage.json")) or {}
    attribution = load_json(os.path.join(args.outdir, "miss_attribution.json")) or {}
    meta = load_json(os.path.join(args.workdir, "case_meta.json")) or {}
    mindex = load_json(os.path.join(args.workdir, "materials_index.json")) or {}
    dedup_log = load_json(os.path.join(args.outdir, "dedup_log.json")) or {}
    exclusion_log = load_json(os.path.join(args.outdir, "exclusion_log.json")) or {}

    case_id = refset.get("case_id", "unknown_case")
    limitations = []
    for src in (refset, coverage, meta, mindex):
        for lim in (src or {}).get("limitations", []):
            if lim not in limitations:
                limitations.append(lim)

    # ---- 状态汇总（最弱环节决定全局） ----
    stage_statuses = [
        refset.get("status", "failed"),
        coverage.get("status", "partial" if coverage else "partial"),
        attribution.get("status", "partial" if attribution else "partial"),
    ]
    if "failed" in stage_statuses:
        status = "failed"
    elif "partial" in stage_statuses:
        status = "partial"
    else:
        status = "complete"

    # ---- sources ----
    sources = []
    for m in mindex.get("materials", []):
        sources.append({"file": m.get("path"), "type": m.get("type"),
                        "sha1": m.get("sha1"), "usage": "参考集材料/本地核验语料"})
    for s in sources:
        if s.get("type") in ("crossref_response", "europepmc_response",
                             "publisher_response"):
            s["usage"] = "本地核验真值源"

    # ---- uncertainty ----
    uncertainty = []
    for c in coverage.get("records", []):
        if c.get("match_level") == "title_similarity":
            uncertainty.append({
                "ref_id": c["ref_id"],
                "issue": "仅按标题相似度回退匹配，存在误判风险，建议人工复核。",
                "evidence": c.get("evidence")})
    for e in refset.get("records", []):
        if e.get("disposition") == "needs_manual_review":
            uncertainty.append({
                "ref_id": e.get("ref_id"),
                "issue": f"处置为 needs_manual_review（{', '.join(e.get('flags', []))}）",
                "evidence": {"source": e.get("source")}})

    # ---- change_log ----
    change_log = [{
        "time": now_iso(), "actor": SCRIPT_NAME,
        "change": "汇总交付：覆盖报告与 result.json 组装完成。",
        "reason": "复核与交付环节"}]
    if refset.get("frozen_at"):
        change_log.insert(0, {
            "time": refset["frozen_at"], "actor": "refset_build.py",
            "change": f"参考集冻结 v{refset.get('schema_version')}，"
                      f"分母 {refset.get('stats', {}).get('total')} 条。",
            "reason": "冻结后分母不可再改动"})

    # ---- result.json ----
    contract = meta.get("output_contract", {})
    result = {
        "case_id": case_id,
        "status": status,
        "denominator": coverage.get("denominator", refset.get("stats", {}).get("total")),
        "hit": coverage.get("hit"),
        "miss": coverage.get("miss"),
        "coverage_ratio": coverage.get("coverage_ratio"),
        "sources": sources,
        "uncertainty": uncertainty,
        "change_log": change_log,
        "limitations": limitations,
        "artifacts": {
            "reference_set": "reference_set.json",
            "dedup_log": "dedup_log.json",
            "exclusion_log": "exclusion_log.json",
            "coverage": "coverage.json",
            "miss_list": "miss_list.csv",
            "miss_attribution_json": "miss_attribution.json",
            "miss_attribution_csv": "miss_attribution.csv",
            "coverage_report": "coverage_report.md",
        },
    }
    # output_contract 字段：逐一填充；缺失以 null 填充并记入 change_log
    filled_contract = {}
    for field in (contract if isinstance(contract, list) else list(contract.keys())):
        value = result.get(field)
        if value is None:
            value = None
            change_log.append({
                "time": now_iso(), "actor": SCRIPT_NAME,
                "change": f"output_contract 字段 {field} 无对应产物，以 null 填充。",
                "reason": "诚实降级，不虚构"})
        filled_contract[field] = value
    result["output_contract_fields"] = filled_contract

    with open(os.path.join(args.outdir, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    # ---- 覆盖报告（人读） ----
    png_ok = try_render_png(coverage,
                            os.path.join(args.outdir, "coverage_preview.png"))
    lines = []
    lines.append(f"# 检索覆盖报告 — {case_id}")
    lines.append("")
    lines.append(f"- 生成时间：{now_iso()}")
    lines.append(f"- 全局状态：{status}")
    lines.append(f"- 参考集版本：v{refset.get('schema_version')} "
                 f"（冻结于 {refset.get('frozen_at')}）")
    stats = refset.get("stats", {})
    lines.append(f"- 分母（冻结参考集）：{stats.get('total')} 条，"
                 f"其中 usable {stats.get('usable')}、"
                 f"需人工复核 {stats.get('needs_manual_review')}、"
                 f"排除 {stats.get('excluded')}、合并去重 {stats.get('merged_away')}")
    lines.append(f"- 覆盖：hit {coverage.get('hit')} / miss {coverage.get('miss')}，"
                 f"覆盖率 {coverage.get('coverage_ratio')}")
    lines.append("")
    lines.append("## 分母可信性说明")
    lines.append("")
    lines.append(refset.get("denominator_policy", ""))
    lines.append("")
    lines.append("## 漏检归因摘要")
    lines.append("")
    for r in attribution.get("reports", [])[:50]:
        lines.append(f"### {r.get('ref_id')} — {r.get('title')}")
        for f in r.get("probe_findings", []):
            lines.append(f"- 探针 `{f['probe']}`：{f['attribution']}")
            for ev in f.get("evidence", [])[:2]:
                ptr = (ev.get("evidence_file", "") or "") + (ev.get("evidence_ptr", "") or "")
                quote = ev.get("evidence_quote", "") or str(ev)[:160]
                lines.append(f"  - 证据 {ptr}：{quote[:160]}")
        lines.append("")
    lines.append("## 不确定项与局限")
    lines.append("")
    for u in uncertainty[:50]:
        lines.append(f"- {u.get('ref_id')}: {u.get('issue')}")
    for lim in limitations:
        lines.append(f"- 局限：{lim}")
    if png_ok:
        lines.append("")
        lines.append("![coverage preview](coverage_preview.png)")
    with open(os.path.join(args.outdir, "coverage_report.md"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"[{SCRIPT_NAME}] status={status} coverage={coverage.get('coverage_ratio')} "
          f"png={'yes' if png_ok else 'no'} artifacts→{args.outdir}")
    return 0 if status != "failed" else 2


if __name__ == "__main__":
    sys.exit(main())
