#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_gates.py — 受控返修阶段机（本 Skill 的第一公民是「受控运行」）。

阶段：orient → materials → anchors → decisions（人判门）→ apply → letter → qc → finalize

子命令：
  run     从第一个未完成阶段执行；decisions 门未满足则打印 JUDGMENT LIST 并停下（exit 0）
  mark    确认 work/decisions.json 与 work/edits.json 已填好，继续走完后续阶段
  status  打印各阶段 done / PENDING / FAILED

选项：
  --input   输入目录（默认 /input，含 case.json、task.md、materials/）
  --work    工作目录（默认 /app/work；检查点 state/、判断文件、run.log 放这里）
  --output  交付目录（默认 /app/output；result.json 与产物放这里）
  --force STAGE  使 STAGE 及其全部下游阶段检查点失效后重跑

幂等：阶段产物存在且输入指纹（sha256）未变 → 打印 [SKIP] 跳过。
每步失败不阻断后续步骤：记入 run.log 与 JUDGMENT LIST，整体退出码为 1。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import workers  # noqa: E402

STAGES = ["orient", "materials", "anchors", "decisions", "apply", "letter", "qc", "finalize"]
GATE = "decisions"


class GateStop(Exception):
    def __init__(self, missing):
        super().__init__("判断门未满足")
        self.missing = missing


class StageFail(Exception):
    pass


class Ctx:
    def __init__(self, input_dir, work, output):
        self.input = os.path.abspath(input_dir)
        self.work = os.path.abspath(work)
        self.output = os.path.abspath(output)
        os.makedirs(os.path.join(self.work, "state"), exist_ok=True)
        os.makedirs(self.output, exist_ok=True)

    def log(self, msg):
        line = "%s %s" % (datetime.datetime.now().isoformat(timespec="seconds"), msg)
        print(line, flush=True)
        with open(os.path.join(self.work, "run.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def state_path(ctx, stage):
    return os.path.join(ctx.work, "state", stage + ".json")


def stage_inputs(ctx, stage):
    i, w, o = ctx.input, ctx.work, ctx.output
    m = {
        "orient":    [os.path.join(i, "case.json"), os.path.join(i, "task.md")],
        "materials": [os.path.join(i, "materials", "manuscript-baseline.md"),
                      os.path.join(i, "materials", "reviewer-comments.md")],
        "anchors":   [os.path.join(i, "materials", "reviewer-comments.md")],
        "decisions": [os.path.join(w, "decisions.json"), os.path.join(w, "edits.json")],
        "apply":     [os.path.join(w, "edits.json"),
                      os.path.join(i, "materials", "manuscript-baseline.md")],
        "letter":    [os.path.join(w, "decisions.json"), os.path.join(w, "changes.json")],
        "qc":        [os.path.join(o, "revised-manuscript.md"),
                      os.path.join(o, "response-letter.md"),
                      os.path.join(w, "changes.json"), os.path.join(w, "decisions.json"),
                      os.path.join(w, "edits.json"),
                      os.path.join(o, "evidence-checklist.json")],
        "finalize":  [os.path.join(o, "result.json"), os.path.join(w, "qc_report.json")],
    }
    return m[stage]


def fingerprint(ctx, stage):
    h = hashlib.sha256()
    for p in stage_inputs(ctx, stage):
        h.update(p.encode("utf-8"))
        if os.path.exists(p):
            with open(p, "rb") as f:
                h.update(f.read())
        else:
            h.update(b"__MISSING__")
    return h.hexdigest()


def write_state(ctx, stage, done, artifacts=None, error=None, extra=None):
    st = {"stage": stage, "done": bool(done), "fingerprint": fingerprint(ctx, stage),
          "artifacts": artifacts or [], "error": error, "ts": now()}
    if extra:
        st.update(extra)
    workers.write_json(state_path(ctx, stage), st)


def should_skip(ctx, stage):
    st = workers.read_json_opt(state_path(ctx, stage))
    if not st or not st.get("done"):
        return False
    if st.get("fingerprint") != fingerprint(ctx, stage):
        return False
    for a in st.get("artifacts", []):
        if not os.path.exists(a):
            return False
    return True


def invalidate(ctx, stage):
    for s in STAGES[STAGES.index(stage):]:
        p = state_path(ctx, s)
        if os.path.exists(p):
            os.remove(p)
    ctx.log("[FORCE] %s 及下游阶段检查点已失效" % stage)


def load_result(ctx):
    return workers.read_json_opt(os.path.join(ctx.output, "result.json")) or {}


def save_result(ctx, res):
    workers.write_json(os.path.join(ctx.output, "result.json"), res)


# ---------------------------------------------------------------- 阶段实现
def stage_orient(ctx):
    """读 case.json，立刻落一个合法的部分 result.json（早落盘原则）。"""
    case = workers.read_json_opt(os.path.join(ctx.input, "case.json"))
    res = load_result(ctx)
    if case is None:
        res.update({"case_id": "unknown", "status": "unable_to_determine",
                    "status_note": "case.json 缺失，无法判断任务契约",
                    "sources": [], "uncertainty": ["case.json 缺失"],
                    "change_records": []})
        save_result(ctx, res)
        raise StageFail("case.json 缺失：已落 unable_to_determine 的 result.json")
    contract = list((case.get("output_contract") or {}).keys())
    res["case_id"] = case.get("case_id")
    res["status"] = "partial"
    res["status_note"] = "运行中：orient 完成，后续阶段未完成（早落盘的诚实部分结果）"
    res.setdefault("sources", ["materials/manuscript-baseline.md",
                               "materials/reviewer-comments.md"])
    res.setdefault("uncertainty", ["运行中，各阶段尚未完成"])
    res.setdefault("change_records", [])
    for f in contract:
        res.setdefault(f, None)
    save_result(ctx, res)
    return [os.path.join(ctx.output, "result.json")], {"contract_fields": contract}


def stage_materials(ctx):
    """清点材料、复制进 work、生成锚点图；基线缺失立即落 unable_to_determine。"""
    failures = []
    mdir = os.path.join(ctx.work, "materials")
    os.makedirs(mdir, exist_ok=True)
    artifacts = []
    for name in ["manuscript-baseline.md", "reviewer-comments.md"]:
        src = os.path.join(ctx.input, "materials", name)
        dst = os.path.join(mdir, name)
        if os.path.exists(src):
            shutil.copyfile(src, dst)
            artifacts.append(dst)
        else:
            failures.append(("BASELINE_MISSING:" if "baseline" in name
                             else "COMMENTS_MISSING:") + name)
    base = os.path.join(mdir, "manuscript-baseline.md")
    if os.path.exists(base):
        amap_p = os.path.join(ctx.work, "anchor_map.json")
        workers.write_json(amap_p,
                           {"anchors": workers.build_anchor_map(workers.read_text(base))})
        artifacts.append(amap_p)
    if any(f.startswith("BASELINE_MISSING") for f in failures):
        res = load_result(ctx)
        res["status"] = "unable_to_determine"
        res["status_note"] = "基线稿缺失，无法执行修订"
        res.setdefault("uncertainty", []).append("manuscript-baseline.md 缺失")
        save_result(ctx, res)
    return artifacts, {"failures": failures}


def stage_anchors(ctx):
    """把审稿意见拆成子要求，生成 decisions.json / edits.json 判断骨架。"""
    src = os.path.join(ctx.work, "materials", "reviewer-comments.md")
    if not os.path.exists(src):
        src = os.path.join(ctx.input, "materials", "reviewer-comments.md")
    if not os.path.exists(src):
        raise StageFail("reviewer-comments.md 缺失，无法拆解意见")
    reqs = workers.parse_requirements(workers.read_text(src))
    if not reqs:
        raise StageFail("未解析到任何子要求（意见格式不符？）→ 需人工补充 decisions.json")
    req_p = os.path.join(ctx.work, "requirements.json")
    workers.write_json(req_p, {"requirements": reqs})
    d, e = workers.write_gate_skeletons(ctx.work, reqs)
    return [req_p, d, e], {"n_requirements": len(reqs)}


def stage_decisions(ctx):
    """人判门：仅在 mark（或判断文件已填）时通过。"""
    ok, missing = workers.check_decisions_filled(ctx.work)
    if not ok:
        raise GateStop(missing)
    return [os.path.join(ctx.work, "decisions.json"),
            os.path.join(ctx.work, "edits.json")], None


def stage_apply(ctx):
    """锚点落稿：逐字唯一匹配 + CHG 标记 + changes.json。"""
    base = os.path.join(ctx.work, "materials", "manuscript-baseline.md")
    if not os.path.exists(base):
        raise StageFail("基线缺失，无法落稿")
    edits = (workers.read_json_opt(os.path.join(ctx.work, "edits.json")) or {}).get("edits", [])
    revised, changes = workers.apply_edits(workers.read_text(base), edits)
    out_p = os.path.join(ctx.output, "revised-manuscript.md")
    workers.write_text(out_p, revised)
    ch_p = os.path.join(ctx.work, "changes.json")
    workers.write_json(ch_p, changes)
    res = load_result(ctx)
    res["revised_manuscript"] = "revised-manuscript.md"
    save_result(ctx, res)
    return [out_p, ch_p], {"n_applied": len(changes["applied"]),
                           "n_failed": len(changes["failures"])}


def stage_letter(ctx):
    """回复信骨架 + 派生产物（change-locations / evidence-checklist / change_record）。"""
    case = workers.read_json_opt(os.path.join(ctx.input, "case.json")) or {}
    decisions = workers.read_json_opt(os.path.join(ctx.work, "decisions.json")) or {}
    changes = workers.read_json_opt(os.path.join(ctx.work, "changes.json")) \
        or {"applied": [], "failures": []}
    reqs = (workers.read_json_opt(os.path.join(ctx.work, "requirements.json"))
            or {}).get("requirements", [])
    baseline = ""
    bp = os.path.join(ctx.work, "materials", "manuscript-baseline.md")
    if os.path.exists(bp):
        baseline = workers.read_text(bp)
    l_p = os.path.join(ctx.output, "response-letter.md")
    workers.write_text(l_p, workers.build_letter(case.get("case_id", "unknown"),
                                                 decisions.get("judgments", []),
                                                 changes, reqs))
    loc_p = os.path.join(ctx.output, "change-locations.json")
    workers.write_json(loc_p, workers.derive_change_locations(changes, baseline))
    ev_p = os.path.join(ctx.output, "evidence-checklist.json")
    workers.write_json(ev_p,
                       workers.derive_evidence_checklist(decisions.get("judgments", []),
                                                         changes))
    cr_p = os.path.join(ctx.work, "change_record.md")
    workers.write_text(cr_p, workers.change_record_md(changes))
    res = load_result(ctx)
    res["response_letter"] = "response-letter.md"
    res["change_locations"] = "change-locations.json"
    res["evidence_checklist"] = "evidence-checklist.json"
    res["change_records"] = [
        {"chg_id": c["chg_id"], "req_id": c.get("req_id"),
         "anchor_quote": c["anchor_quote"], "status": "applied"}
        for c in changes.get("applied", [])
    ] + [
        {"chg_id": f.get("chg_id"), "req_id": f.get("req_id"),
         "anchor_quote": f.get("anchor_quote"), "status": "failed:" + str(f.get("error"))}
        for f in changes.get("failures", [])
    ]
    save_result(ctx, res)
    return [l_p, loc_p, ev_p, cr_p], None


def stage_qc(ctx):
    """五维机器回检（qc_check.py）；失败不抛断后续，由 finalize 给出最终口径。"""
    w, o = ctx.work, ctx.output
    cmd = [sys.executable, os.path.join(HERE, "qc_check.py"),
           "--baseline", os.path.join(w, "materials", "manuscript-baseline.md"),
           "--revised", os.path.join(o, "revised-manuscript.md"),
           "--letter", os.path.join(o, "response-letter.md"),
           "--changes", os.path.join(w, "changes.json"),
           "--decisions", os.path.join(w, "decisions.json"),
           "--evidence", os.path.join(o, "evidence-checklist.json"),
           "--out", os.path.join(w, "qc_report.json")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    for ln in (r.stdout + r.stderr).splitlines():
        ctx.log("  qc| " + ln)
    if r.returncode != 0:
        raise StageFail("QC 未通过：见 work/qc_report.json；"
                        "修复后对相应阶段 --force 重跑（如 run --force apply）")
    return [os.path.join(w, "qc_report.json")], None


def stage_finalize(ctx):
    cmd = [sys.executable, os.path.join(HERE, "finalize.py"),
           "--case", os.path.join(ctx.input, "case.json"),
           "--work", ctx.work, "--output", ctx.output]
    r = subprocess.run(cmd, capture_output=True, text=True)
    for ln in (r.stdout + r.stderr).splitlines():
        ctx.log("  fz| " + ln)
    if r.returncode != 0:
        raise StageFail("finalize 未通过：诚实 result.json 已落盘，但交付不完整")
    return [os.path.join(ctx.output, "result.json")], None


IMPL = {"orient": stage_orient, "materials": stage_materials, "anchors": stage_anchors,
        "decisions": stage_decisions, "apply": stage_apply, "letter": stage_letter,
        "qc": stage_qc, "finalize": stage_finalize}


# ---------------------------------------------------------------- 门与清单
def print_gate_stop(ctx, missing):
    ctx.log("GATE-STOP decisions（判断门未满足，脚本停下等待 Agent 判断）")
    lines = ["",
             "== JUDGMENT LIST（需 Agent 逐条判断后填入 work/decisions.json 与 work/edits.json）=="]
    reqs = (workers.read_json_opt(os.path.join(ctx.work, "requirements.json"))
            or {}).get("requirements", [])
    for r in reqs:
        lines.append("- [%s] %s" % (r["req_id"], r["text"]))
    for m in missing:
        lines.append("* 缺失：" + m)
    lines.append('填好后执行：python3 "$SKILL/scripts/run_gates.py" mark')
    msg = "\n".join(lines)
    print(msg, flush=True)
    workers.write_text(os.path.join(ctx.work, "JUDGMENT_LIST.md"), msg + "\n")


def refresh_judgment_list(ctx):
    items = []
    for s in STAGES:
        st = workers.read_json_opt(state_path(ctx, s))
        if st and not st.get("done") and st.get("error"):
            items.append("- 阶段 %s 失败：%s" % (s, st["error"]))
    changes = workers.read_json_opt(os.path.join(ctx.work, "changes.json")) or {}
    for f in changes.get("failures", []):
        items.append("- 落稿失败 %s（%s）：锚点「%s」"
                     % (f.get("chg_id"), f.get("error"),
                        str(f.get("anchor_quote"))[:40]))
    msg = "== JUDGMENT LIST（遗留问题）==\n" + ("\n".join(items) if items else "（无遗留问题）")
    print(msg, flush=True)
    workers.write_text(os.path.join(ctx.work, "JUDGMENT_LIST.md"), msg + "\n")


# ---------------------------------------------------------------- 主流程
def run_stages(ctx, force=None):
    if force:
        if force not in STAGES:
            ctx.log("[ERROR] 未知阶段 %r，允许 %s" % (force, STAGES))
            return 2
        invalidate(ctx, force)
    any_fail = False
    for stage in STAGES:
        if stage == GATE:
            ok, missing = workers.check_decisions_filled(ctx.work)
            if not ok:
                print_gate_stop(ctx, missing)
                return 1 if any_fail else 0
        if should_skip(ctx, stage):
            ctx.log("[SKIP] %s（指纹一致，幂等跳过）" % stage)
            continue
        try:
            artifacts, extra = IMPL[stage](ctx)
            write_state(ctx, stage, True, artifacts=artifacts, extra=extra)
            ctx.log("[DONE] %s" % stage)
        except GateStop as g:
            write_state(ctx, stage, False, error="门未满足")
            print_gate_stop(ctx, g.missing)
            return 1 if any_fail else 0
        except Exception as e:  # 单步失败不阻断后续；记入 run.log 与 JUDGMENT LIST
            write_state(ctx, stage, False, error=str(e))
            ctx.log("[FAIL] %s: %s" % (stage, e))
            any_fail = True
            continue
    refresh_judgment_list(ctx)
    if any_fail:
        ctx.log("[END] 存在失败阶段，见上方 JUDGMENT LIST 与 run.log；"
                "预算记账：请在 run.log 追加 BUDGET spent=N remain=M")
        return 1
    ctx.log("[END] 全部阶段完成；预算记账：请在 run.log 追加 BUDGET spent=N remain=M")
    return 0


def cmd_status(ctx):
    print("阶段状态（work=%s）" % ctx.work)
    for s in STAGES:
        st = workers.read_json_opt(state_path(ctx, s))
        if st is None:
            mark = "PENDING"
        elif st.get("done"):
            mark = "done"
        else:
            mark = "FAILED(%s)" % (st.get("error") or "?")
        gate = "  <== 人判门" if s == GATE else ""
        print("  %-10s %s%s" % (s, mark, gate))
    ok, missing = workers.check_decisions_filled(ctx.work)
    print("判断门：%s" % ("已满足" if ok else "未满足（%d 项缺失）" % len(missing)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="run_gates.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "mark", "status"])
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--force", default=None, metavar="STAGE",
                    help="使 STAGE 及下游阶段检查点失效后重跑")
    args = ap.parse_args(argv)
    ctx = Ctx(args.input, args.work, args.output)
    if args.cmd == "status":
        return cmd_status(ctx)
    if args.cmd == "mark":
        ok, missing = workers.check_decisions_filled(ctx.work)
        if not ok:
            ctx.log("门未满足，mark 拒绝继续；缺失：")
            for m in missing:
                print("  - " + m, flush=True)
            return 1
        ctx.log("判断门已确认（mark），继续后续阶段")
    return run_stages(ctx, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
