#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qc_loop.py — 质量回路（budget-warden-qc）

读取 out/result.json 与 workdir/checkpoints，执行缺陷检查清单：
  Q1 case_id 缺失或为空            -> 可从 case.json/checkpoint 补回则自动修复
  Q2 必备顶层字段缺失              -> 补空值字段（自动修复）
  Q3 output_contract 字段未镜像     -> 按契约补 null 镜像（自动修复）
  Q4 记录/边缺少 source locator    -> 不可修复，逐条写入 uncertainty
  Q5 stub 比例过高（>50%）          -> 不可修复，写入 uncertainty 警示
  Q6 status 与实际完成阶段不符      -> 自动校正（ok -> partial）并记录
  Q7 checkpoint 链断裂             -> 不可修复，写入 uncertainty

能安全修复的自动修复并写 change_log；不能修复的逐条写入 uncertainty。
产物：workdir/qc_report.json 与 workdir/qc_report.md；stdout 打印 ok=true/false。
仅标准库、离线、位置无关。
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_FIELDS = ["case_id", "status", "seed", "candidates", "edges",
                   "sources", "evidence_records", "uncertainty"]
STUB_RATIO_WARN = 0.5


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def canon(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canon(obj), encoding="utf-8")


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(description="result.json 质量回路自检与安全修复")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--no-fix", action="store_true", help="只检查不修复（dry-run）")
    args = ap.parse_args(argv)

    outdir, workdir = Path(args.out), Path(args.workdir)
    result_path = outdir / "result.json"
    checks, change_log = [], []

    def add_check(cid, severity, fixable, detail, fixed=False):
        checks.append({"check": cid, "severity": severity, "fixable": fixable,
                       "detail": detail, "fixed": fixed})

    if not result_path.exists():
        add_check("Q0", "critical", False, "result.json 不存在：%s" % result_path)
        report = {"ok": False, "generated_at": utcnow(), "checks": checks,
                  "change_log": [], "result_path": str(result_path)}
        write_json(workdir / "qc_report.json", report)
        (workdir / "qc_report.md").write_text(
            "# QC 报告\n\n- ok=false：result.json 缺失，请先运行 warden.py。\n", encoding="utf-8")
        print("ok=false (result.json missing)")
        return 1

    result = read_json(result_path)
    uncertainty = result.setdefault("uncertainty", [])
    changed = False

    def fix(desc):
        nonlocal changed
        change_log.append({"time": utcnow(), "change": desc})
        changed = True

    def note_uncertainty(text):
        if text not in uncertainty:
            uncertainty.append(text)
            fix("追加 uncertainty：%s" % text)

    # ---------- Q1 case_id ----------
    cid = result.get("case_id")
    if not cid or cid == "unknown-case":
        recovered = None
        if Path(args.case).exists():
            try:
                recovered = read_json(args.case).get("case_id") or read_json(args.case).get("id")
            except Exception:
                recovered = None
        if not recovered:
            cp0 = workdir / "checkpoints" / "stage0.json"
            if cp0.exists():
                try:
                    recovered = read_json(cp0).get("data", {}).get("case_id")
                except Exception:
                    recovered = None
        if recovered and not args.no_fix:
            result["case_id"] = recovered
            fix("Q1: case_id 缺失/占位，已从输入恢复为 '%s'" % recovered)
            add_check("Q1", "critical", True, "case_id 缺失，已自动修复", fixed=True)
        elif recovered:
            add_check("Q1", "critical", True, "case_id 缺失（dry-run 未修复）")
        else:
            note_uncertainty("QC-Q1：case_id 缺失且无法从 case.json/checkpoint 恢复。")
            add_check("Q1", "critical", False, "case_id 缺失且无法恢复")
    else:
        add_check("Q1", "info", True, "case_id 正常：%s" % cid, fixed=True)

    # ---------- Q2 必备顶层字段 ----------
    missing = [f for f in REQUIRED_FIELDS if f not in result]
    if missing:
        if not args.no_fix:
            defaults = {"case_id": "unknown-case", "status": "partial", "seed": {},
                        "candidates": [], "edges": [], "sources": [],
                        "evidence_records": [], "uncertainty": []}
            for f in missing:
                result[f] = defaults[f]
            fix("Q2: 补齐缺失顶层字段 %s（空值）" % ", ".join(missing))
            note_uncertainty("QC-Q2：字段 %s 在原结果中缺失，已按空值补齐。"
                             % ", ".join(missing))
        add_check("Q2", "major", True, "缺失字段：%s" % ", ".join(missing),
                  fixed=not args.no_fix)
    else:
        add_check("Q2", "info", True, "必备顶层字段齐全", fixed=True)

    # ---------- Q3 output_contract 镜像 ----------
    contract_keys = []
    if Path(args.case).exists():
        try:
            oc = read_json(args.case).get("output_contract") or {}
            contract_keys = sorted(oc) if isinstance(oc, dict) else [str(k) for k in oc]
        except Exception:
            contract_keys = []
    mirror = result.get("contract") or {}
    absent = [k for k in contract_keys if k not in mirror]
    if absent:
        if not args.no_fix:
            mirror = result.setdefault("contract", {})
            for k in absent:
                mirror[k] = None
            fix("Q3: 补镜像 output_contract 缺失字段 %s（null）" % ", ".join(absent))
            note_uncertainty("QC-Q3：output_contract 字段 %s 未在原结果中镜像，已补 null。"
                             % ", ".join(absent))
        add_check("Q3", "major", True, "契约字段未镜像：%s" % ", ".join(absent),
                  fixed=not args.no_fix)
    else:
        add_check("Q3", "info", True, "output_contract 镜像完整（%d 字段）" % len(contract_keys),
                  fixed=True)
    null_keys = [k for k, v in (result.get("contract") or {}).items() if v is None]
    if null_keys:
        note_uncertainty("QC-Q3b：契约字段 %s 为 null，属契约允许的空值，但请人工确认。"
                         % ", ".join(sorted(null_keys)))
        add_check("Q3b", "minor", False, "契约空值字段：%s" % ", ".join(sorted(null_keys)))

    # ---------- Q4 locator 完整性 ----------
    no_loc, edge_no_loc = [], []
    for c in result.get("candidates") or []:
        src = c.get("source") or {}
        if not (isinstance(src, dict) and src.get("file") and src.get("pointer")):
            no_loc.append(c.get("record_id"))
    for e in result.get("edges") or []:
        src = e.get("source") or {}
        if not (isinstance(src, dict) and src.get("file") and src.get("pointer")):
            edge_no_loc.append("%s->%s/%s" % (e.get("source_id"), e.get("target_id"), e.get("type")))
    if no_loc or edge_no_loc:
        detail = "无 locator 记录 %d 条、边 %d 条" % (len(no_loc), len(edge_no_loc))
        note_uncertainty("QC-Q4：%s；locator 不可事后补造，请回源数据修复。明细：记录=%s；边=%s"
                         % (detail, sorted(x for x in no_loc if x),
                            sorted(edge_no_loc)[:20]))
        add_check("Q4", "major", False, detail)
    else:
        add_check("Q4", "info", False, "全部记录与边均带 source locator", fixed=True)

    # ---------- Q5 stub 比例 ----------
    cands = result.get("candidates") or []
    stubs = [c for c in cands if c.get("kind") == "stub"]
    ratio = (len(stubs) / len(cands)) if cands else 0.0
    if cands and ratio > STUB_RATIO_WARN:
        note_uncertainty(
            "QC-Q5：stub 比例 %.1f%%（%d/%d）超过阈值 50%%，语料覆盖度可能不足，"
            "结论可信度受限。" % (ratio * 100, len(stubs), len(cands)))
        add_check("Q5", "major", False, "stub 比例 %.1f%% 超阈值" % (ratio * 100))
    else:
        add_check("Q5", "info", False, "stub 比例 %.1f%%（%d/%d）"
                  % (ratio * 100, len(stubs), len(cands)), fixed=True)

    # ---------- Q6 status 与实际完成阶段一致 ----------
    ss = result.get("stage_summary") or {}
    completed = ss.get("completed_stage", 0)
    budget_limited = ss.get("budget_limited", False)
    status = result.get("status")
    cp3 = (workdir / "checkpoints" / "stage3.json").exists()
    inconsistent = None
    if status == "ok" and (completed < 3 or budget_limited or not cp3):
        inconsistent = "status=ok 但 completed_stage=%s、budget_limited=%s、stage3 checkpoint=%s" \
                       % (completed, budget_limited, cp3)
    if inconsistent:
        if not args.no_fix:
            result["status"] = "partial"
            fix("Q6: status 校正 ok -> partial（%s）" % inconsistent)
            note_uncertainty("QC-Q6：status 与实际完成度不符，已校正为 partial。")
        add_check("Q6", "major", True, inconsistent, fixed=not args.no_fix)
    elif status == "partial" and completed >= 3 and cp3 and not budget_limited:
        # partial 但管线已完整：多半存在未解析种子等诚实原因，仅提示不改写
        add_check("Q6", "minor", False,
                  "status=partial 且 stage3 已完成；请确认 partial 原因已在 uncertainty 说明")
    else:
        add_check("Q6", "info", True, "status 与完成阶段一致（%s/stage%d）"
                  % (status, completed), fixed=True)

    # ---------- Q7 checkpoint 链完整性 ----------
    cpdir = workdir / "checkpoints"
    have = sorted(int(p.stem.replace("stage", "")) for p in cpdir.glob("stage*.json")
                  if p.stem.replace("stage", "").isdigit())
    if completed > 0:
        expected = list(range(0, completed + 1))
        gaps = [i for i in expected if i not in have]
        if gaps:
            note_uncertainty("QC-Q7：checkpoint 链断裂，缺少 stage %s；"
                             "--resume 将回退到最近完整阶段。" % gaps)
            add_check("Q7", "minor", False, "checkpoint 缺口：%s" % gaps)
        else:
            add_check("Q7", "info", False, "checkpoint 链完整：stage %s" % have, fixed=True)
    else:
        add_check("Q7", "info", False, "仅 stage0，无需链式校验", fixed=True)

    # ---------- 汇总与落盘 ----------
    if changed and not args.no_fix:
        write_json(result_path, result)
    blocking = [c for c in checks if c["severity"] == "critical" and not c["fixed"]]
    majors_open = [c for c in checks if c["severity"] == "major" and not c["fixed"]]
    ok = not blocking and not majors_open
    report = {"ok": ok, "generated_at": utcnow(), "result_path": str(result_path),
              "checks": checks, "change_log": change_log,
              "summary": {"critical_open": len(blocking), "major_open": len(majors_open),
                          "auto_fixed": sum(1 for c in change_log),
                          "candidates": len(cands), "stubs": len(stubs)}}
    write_json(workdir / "qc_report.json", report)
    lines = ["# QC 报告（budget-warden-qc）", "",
             "- 结论：**ok=%s**" % str(ok).lower(),
             "- 结果文件：`%s`" % result_path,
             "- 自动修复 %d 处；未决 critical %d 项、major %d 项" % (
                 len(change_log), len(blocking), len(majors_open)), "",
             "## 检查明细", ""]
    for c in checks:
        mark = {"info": "✅", "minor": "🟡", "major": "🟠", "critical": "🔴"}.get(c["severity"], "•")
        lines.append("- %s **%s** [%s] %s%s" % (
            mark, c["check"], c["severity"], c["detail"],
            "（已修复）" if c["fixed"] and c["severity"] in ("major", "critical") else ""))
    if change_log:
        lines += ["", "## change_log", ""]
        for ch in change_log:
            lines.append("- %s：%s" % (ch["time"], ch["change"]))
    (workdir / "qc_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("ok=%s (auto_fixed=%d critical_open=%d major_open=%d)"
          % (str(ok).lower(), len(change_log), len(blocking), len(majors_open)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
