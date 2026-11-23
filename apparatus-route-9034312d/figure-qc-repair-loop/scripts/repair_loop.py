#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""repair_loop.py — render → QC → (export → 导出检查) 单轮执行器 + loop_log 维护。

角色分工：本脚本只负责"跑一轮并记账"；**修复 IR 的是 agent**——脚本永不修改
IR、永不手改 SVG、永不删除任何检查。agent 在轮次之间按 QC 报告里的
suggested_fix 编辑 IR，然后用同一命令再跑一次（轮次由 loop_log.json 自动递增）。

规则（详见 references/loop-protocol.md）：
  - 最多 max_rounds 轮（默认 2）。
  - 本轮 QC 无 error 级缺陷：导出 PDF/PNG，再做 EXPORT_FAIL 检查；全过 → clean。
  - 有 error 且 round < max：状态 needs_repair，打印缺陷清单给 agent 修 IR。
  - 有 error 且 round == max：照样导出（尽力交付），状态 partial，
    残余缺陷原样写入 loop_log.json.residual_defects——必须抄进 result.json
    的 uncertainties，诚实交付，禁止删检查蒙混。

用法:
  python3 repair_loop.py --ir figure_ir.json --workdir /app/work \
      --source-dir /app/work/sources --out-dir /app/output \
      [--max-rounds 2] [--no-export]

退出码: 0=clean, 2=needs_repair（agent 应修 IR 后重跑）, 3=partial（预算耗尽）,
1=本轮执行失败（渲染/质检脚本本身出错）。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RENDER = os.path.join(HERE, "ir_render.py")
QC = os.path.join(HERE, "qc_figure.py")
EXPORT = os.path.join(HERE, "export_svg.py")


def run(cmd):
    return subprocess.run([sys.executable] + cmd,
                          capture_output=True, text=True, timeout=600)


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ir", required=True)
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--source-dir", default=None)
    ap.add_argument("--out-dir", default="/app/output")
    ap.add_argument("--max-rounds", type=int, default=2)
    ap.add_argument("--no-export", action="store_true")
    args = ap.parse_args(argv[1:])

    workdir = os.path.abspath(args.workdir)
    out_dir = os.path.abspath(args.out_dir)
    source_dir = os.path.abspath(args.source_dir) if args.source_dir \
        else os.path.join(workdir, "sources")
    os.makedirs(workdir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    log_path = os.path.join(workdir, "loop_log.json")
    log = load_json(log_path) or {"max_rounds": args.max_rounds,
                                  "rounds": [], "status": "in_progress",
                                  "residual_defects": []}
    round_n = len(log["rounds"]) + 1
    rec = {"round": round_n, "ir": os.path.abspath(args.ir), "svg": None,
           "qc_report": None, "errors": None, "warns": None, "codes": [],
           "export_report": None, "action": None}

    # 1. 渲染
    svg_round = os.path.join(workdir, f"figure.round{round_n}.svg")
    r = run([RENDER, args.ir, "-o", svg_round])
    if r.returncode != 0 or not os.path.exists(svg_round):
        rec["action"] = "failed"
        rec["detail"] = (r.stderr or r.stdout or "ir_render 失败")[:500]
        log["rounds"].append(rec)
        log["status"] = "failed"
        write_json(log_path, log)
        print(f"[repair_loop] round {round_n}: 渲染失败，见 loop_log.json",
              file=sys.stderr)
        return 1
    rec["svg"] = svg_round

    # 2. QC（IR+SVG 级）
    qc_path = os.path.join(workdir, f"qc_report.round{round_n}.json")
    run([QC, args.ir, svg_round, source_dir,
         "--report", qc_path, "--round", str(round_n)])
    rep = load_json(qc_path) or {}
    summ = rep.get("summary", {})
    rec["qc_report"] = qc_path
    rec["errors"] = summ.get("errors", -1)
    rec["warns"] = summ.get("warns", 0)
    rec["codes"] = summ.get("codes", [])

    # 3. 干净 或 预算到顶 → 导出 + 导出检查
    final_svg = os.path.join(out_dir, "figure.svg")
    if rec["errors"] == 0 or round_n >= args.max_rounds:
        shutil.copyfile(svg_round, final_svg)
        if not args.no_export:
            pdf = os.path.join(out_dir, "figure.pdf")
            png = os.path.join(out_dir, "figure.png")
            exp_path = os.path.join(out_dir, "export_report.json")
            run([EXPORT, final_svg, "--pdf", pdf, "--png", png,
                 "--report", exp_path])
            rec["export_report"] = exp_path
            # 导出后复检（EXPORT_FAIL）
            run([QC, args.ir, final_svg, source_dir, "--report", qc_path,
                 "--round", str(round_n),
                 "--export-pdf", pdf, "--export-png", png])
            rep = load_json(qc_path) or rep
            summ = rep.get("summary", summ)
            rec["errors"] = summ.get("errors", rec["errors"])
            rec["warns"] = summ.get("warns", rec["warns"])
            rec["codes"] = summ.get("codes", rec["codes"])

    # 4. 判定
    if rec["errors"] == 0:
        rec["action"] = "clean"
        log["status"] = "clean"
        log["residual_defects"] = rep.get("defects", [])  # 可能剩 warn，照实记录
        exit_code = 0
    elif round_n < args.max_rounds:
        rec["action"] = "needs_repair"
        log["status"] = "in_progress"
        exit_code = 2
    else:
        rec["action"] = "partial"
        log["status"] = "partial"
        log["residual_defects"] = rep.get("defects", [])
        exit_code = 3

    log["rounds"].append(rec)
    write_json(log_path, log)

    print(f"[repair_loop] round {round_n}/{args.max_rounds}: "
          f"errors={rec['errors']} warns={rec['warns']} codes={rec['codes']} "
          f"-> {rec['action']}")
    if rec["action"] == "needs_repair":
        errs = [d for d in rep.get("defects", []) if d.get("severity") == "error"]
        print("[repair_loop] 待修复 error 级缺陷（请编辑 IR 后用同一命令重跑）:")
        for d in errs:
            print(f"  - [{d['code']}] {d['element']}: {d['evidence']}")
            print(f"    修复建议: {d['suggested_fix']}")
    elif rec["action"] == "partial":
        print("[repair_loop] 预算耗尽：尽力交付。残余缺陷已写入 loop_log.json"
              ".residual_defects，必须抄入 result.json 的 uncertainties。")
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
