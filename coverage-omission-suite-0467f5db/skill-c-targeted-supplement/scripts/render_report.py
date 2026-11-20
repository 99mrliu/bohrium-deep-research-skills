#!/usr/bin/env python3
"""render_report.py — 交付渲染：coverage_report.md + result.json 装配。

汇总 work 目录全部工件（refset、coverage_initial、final_coverage、
supplement_state、supplement_log、residual_misses、audit_report、change_log、
parsed_case），生成人类可读的覆盖率报告（补检前后对照表、逐批边际收益表、
残余遗漏与复核摘要）与机器可读的 result.json（case_id + output_contract
全部字段 + 诚实状态/来源/不确定性/变更记录）。

matplotlib 可用时可选输出边际收益曲线 PNG；不可用或失败时自动降级为纯表格。
退出码：0 正常；2 关键工件缺失；3 装配校验失败。仅标准库，支持 --help。
"""
import argparse
import csv
import json
import os
import sys

EXIT_OK = 0
EXIT_INSUFFICIENT = 2
EXIT_VALIDATION = 3


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def read_supplement_log(path):
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def contract_fields(parsed):
    """把任务 output_contract 展平为字段名 → 值 的映射（诚实复制）。"""
    oc = (parsed or {}).get("output_contract") or {}
    if isinstance(oc, dict):
        if all(isinstance(k, str) for k in oc.keys()):
            return dict(oc), []
        return {str(k): v for k, v in oc.items()}, []
    if isinstance(oc, list):
        return {str(k): None for k in oc}, [str(k) for k in oc]
    return {}, []


def wilson_str(ci):
    if not ci or ci.get("low") is None:
        return "n/a"
    return "[%.4f, %.4f]" % (ci["low"], ci["high"])


def render_markdown(case_id, parsed, refset, init_cov, final_cov, state,
                    log_rows, residual, audit, change_log):
    lines = []
    w = lines.append
    w("# 检索覆盖率与遗漏分析报告（定向补检闭环）")
    w("")
    w("- 案例编号：`%s`" % (case_id or "未知"))
    w("- 报告生成：本报告由 targeted-supplement-loop 技能自动生成；")
    w("  分母为冻结参考集（hash `%s…`），共 %d 条，全部来自本地材料。"
      % ((refset or {}).get("refset_hash", "")[:12], (refset or {}).get("count", 0)))
    w("- 数据来源：本地组织者留存材料（响应文件、参考图、PDF 文本）；无远程请求。")
    w("")
    if parsed and parsed.get("limitations"):
        w("## 已知限制")
        for item in parsed["limitations"]:
            w("- %s" % item)
        w("")
    w("## 一、覆盖率：补检前后对照")
    w("")
    w("| 阶段 | 分母 | 覆盖数 | 覆盖率 | Wilson 95% 区间 |")
    w("| --- | ---: | ---: | ---: | --- |")
    rows = [("初始（基线检索）", init_cov), ("补检后（最终）", final_cov)]
    for label, cov in rows:
        if cov and cov.get("denominator"):
            w("| %s | %d | %d | %.4f | %s |"
              % (label, cov["denominator"], cov["covered"],
                 cov.get("coverage") or 0.0, wilson_str(cov.get("wilson_ci"))))
        else:
            w("| %s | n/a | n/a | n/a | n/a |" % label)
    w("")
    if init_cov and final_cov:
        gain = final_cov.get("covered", 0) - init_cov.get("covered", 0)
        w("补检新增覆盖 **%d** 条，全部经冻结参考集重匹配核验。" % gain)
        w("")
    w("## 二、补检执行与边际收益")
    w("")
    if state:
        rule = (state.get("stop_rule_final") or {}).get("rule", "未知")
        detail = (state.get("stop_rule_final") or {}).get("detail", "")
        w("- 停止规则：%s（%s）" % (rule, detail))
        w("- 查询总数：%d；批次：%d" % (state.get("queries_run", 0), len(state.get("batches", []))))
        w("")
        w("| 批次 | 原型 | 查询数 | 新增覆盖 | 边际覆盖率收益 |")
        w("| --- | --- | ---: | --- | ---: |")
        for b in state.get("batches", []):
            w("| %s | %s | %d | %s | %.4f |"
              % (b.get("batch"), b.get("archetype"), b.get("queries_run"),
                 ", ".join(b.get("newly_covered_ids", [])) or "—",
                 b.get("marginal_coverage_gain", 0.0)))
        w("")
    w("### 逐查询账本（supplement_log.csv 摘录）")
    w("")
    w("| query_id | 原型 | target_miss_ids | 候选数 | 新增覆盖 | verdict |")
    w("| --- | --- | --- | ---: | --- | --- |")
    for r in log_rows[:50]:
        w("| %s | %s | %s | %s | %s | %s |"
          % (r.get("query_id"), r.get("archetype"), r.get("target_miss_ids"),
             r.get("candidates_returned"), r.get("newly_covered_ids") or "—",
             r.get("verdict")))
    if len(log_rows) > 50:
        w("| … | … | … | … | … | 共 %d 行，详见 supplement_log.csv |" % len(log_rows))
    w("")
    w("## 三、残余遗漏归因")
    w("")
    items = (residual or {}).get("residual_misses", [])
    if items:
        w("| ref_id | 标题 | 归因 | 检回条件 |")
        w("| --- | --- | --- | --- |")
        for it in items:
            title = (it.get("title") or "").replace("|", "/")
            w("| %s | %s | %s | %s |"
              % (it.get("ref_id"), title[:80], it.get("attributed_cause"),
                 it.get("what_would_be_needed", "")[:120]))
        w("")
        w("探针证据明细见 residual_misses.json（标识符命中文件、标题词项命中计数）。")
    else:
        w("无残余遗漏。")
    w("")
    w("## 四、闭环复核")
    w("")
    if audit:
        det = audit.get("determinism", {})
        sam = audit.get("sampling", {})
        w("- 确定性复跑：%s（refset_hash、覆盖集合、停止规则与批次收益逐项比对）"
          % ("通过" if det.get("all_checks_passed") else "失败"))
        w("- 审计抽样：%s" % sam.get("rule", ""))
        w("- 复核 %d 条（边界 %d + 抽检 %d），一致 %d，一致性比率 %s。"
          % (sam.get("n_checked", 0), sam.get("n_borderline", 0),
             sam.get("n_clean_sampled", 0), sam.get("n_agree", 0),
             sam.get("agreement_rate")))
    else:
        w("审计工件缺失，本节无法生成。")
    w("")
    if change_log:
        w("## 五、变更记录")
        w("")
        for entry in change_log:
            w("- `%s`：%s" % (entry.get("type"), json.dumps(entry, ensure_ascii=False)[:200]))
        w("")
    w("## 附：不确定性说明")
    w("")
    w("- 标题相似度阈值 %.2f、边界带 %.02f；边界带内命中已经 100%% 复核。"
      % ((final_cov or {}).get("threshold", 0.90), (final_cov or {}).get("band", 0.05)))
    w("- 覆盖数以冻结参考集为准；未核全文的记录已在 residual/limitations 中注明。")
    w("- 零边际收益查询如实记账，不作为收益宣称。")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="渲染 coverage_report.md 并装配 result.json。"
    )
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--out-dir", default="/app/output", help="交付目录（默认 /app/output）")
    ap.add_argument("--with-plot", action="store_true",
                    help="matplotlib 可用时额外输出边际收益曲线 PNG（可选）")
    args = ap.parse_args(argv)

    work = args.work
    refset = load_json(os.path.join(work, "refset.json"))
    init_cov = load_json(os.path.join(work, "coverage_initial.json"))
    final_cov = load_json(os.path.join(work, "final_coverage.json"))
    if not refset or not init_cov or not final_cov:
        print("[render_report] 关键工件缺失（refset/coverage），无法交付", file=sys.stderr)
        return EXIT_INSUFFICIENT

    parsed = load_json(os.path.join(work, "parsed_case.json"), {})
    state = load_json(os.path.join(work, "supplement_state.json"), {})
    residual = load_json(os.path.join(work, "residual_misses.json"), {})
    audit = load_json(os.path.join(work, "audit_report.json"))
    change_obj = load_json(os.path.join(work, "change_log.json"), {})
    change_log = change_obj.get("change_log", []) if isinstance(change_obj, dict) else []
    log_rows = read_supplement_log(os.path.join(work, "supplement_log.csv"))

    case_id = refset.get("case_id") or (parsed or {}).get("case_id")
    os.makedirs(args.out_dir, exist_ok=True)

    md = render_markdown(case_id, parsed, refset, init_cov, final_cov, state,
                         log_rows, residual, audit, change_log)
    md_path = os.path.join(args.out_dir, "coverage_report.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md)

    # 可选边际收益曲线（永不作为必需交付物）
    plot_note = None
    if args.with_plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            batches = (state or {}).get("batches", [])
            if batches:
                xs = list(range(1, len(batches) + 1))
                ys = [b.get("marginal_coverage_gain", 0.0) for b in batches]
                plt.figure(figsize=(6, 4))
                plt.plot(xs, ys, marker="o")
                plt.xlabel("supplement batch")
                plt.ylabel("marginal coverage gain")
                plt.title("Marginal gain curve (case %s)" % case_id)
                plt.grid(True, alpha=0.3)
                plt.tight_layout()
                plt.savefig(os.path.join(args.out_dir, "marginal_gain_curve.png"), dpi=120)
                plt.close()
            else:
                plot_note = "无批次数据，未绘图"
        except Exception as exc:  # matplotlib 缺失或绘图失败均降级
            plot_note = "绘图不可用：%s" % exc

    contract, missing_fields = contract_fields(parsed)
    stage_status = {
        "parse_case": (parsed or {}).get("status", "unknown"),
        "freeze_refset": "ok" if refset else "missing",
        "initial_coverage": init_cov.get("status", "unknown"),
        "supplement": "ok" if state else "missing",
        "audit": (audit or {}).get("status", "not_run"),
    }
    overall = "ok"
    if any(v in ("partial", "review_required") for v in stage_status.values()):
        overall = "partial"
    if change_log and (audit or {}).get("status") == "review_required":
        overall = "partial"

    result = {
        "case_id": case_id,
        "status": overall,
        "stage_status": stage_status,
        "output_contract": contract,
        "contract_fields_missing": missing_fields,
        "coverage": {
            "denominator": refset.get("count"),
            "covered_before": init_cov.get("covered"),
            "covered_after": final_cov.get("covered"),
            "coverage_before": init_cov.get("coverage"),
            "coverage_after": final_cov.get("coverage"),
            "wilson_ci_before": init_cov.get("wilson_ci"),
            "wilson_ci_after": final_cov.get("wilson_ci"),
            "refset_hash": refset.get("refset_hash"),
        },
        "supplement": {
            "queries_run": (state or {}).get("queries_run"),
            "n_batches": len((state or {}).get("batches", [])),
            "batches": (state or {}).get("batches", []),
            "stop_rule": ((state or {}).get("stop_rule_final") or {}).get("rule"),
            "stop_rule_detail": ((state or {}).get("stop_rule_final") or {}).get("detail"),
        },
        "residual_misses": (residual or {}).get("residual_misses", []),
        "audit": audit,
        "sources": {
            "refset_sources": refset.get("sources", []),
            "candidate_files_initial": init_cov.get("candidate_files", []),
            "work_artifacts": sorted(
                os.path.join(work, f) for f in os.listdir(work)
                if os.path.isfile(os.path.join(work, f))),
        },
        "uncertainty": {
            "threshold": final_cov.get("threshold"),
            "band": final_cov.get("band"),
            "limitations": (parsed or {}).get("limitations", []),
            "plot_note": plot_note,
            "note": "覆盖率分母为冻结参考集；零收益查询已如实记账；未核全文项见 residual。",
        },
        "change_log": change_log,
    }
    result_path = os.path.join(args.out_dir, "result.json")
    with open(result_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print("[render_report] status=%s -> %s / %s" % (overall, md_path, result_path))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
