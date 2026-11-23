#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""checkpoint.py — process-qc-guard 阶段检查点与最终导出。

子命令：
  save    记录 {stage, 输入依赖 sha256, 产物 sha256, 说明, 可选复跑命令}；原子写。
  list    列出全部检查点。
  resume  校验依赖哈希未变；变化 → STALE 警告并列出受影响产物。
  status  打印完成矩阵与"下次中断可从哪续"。
  export  汇总 case 契约、answers/items、probes 报告与检查点，原子刷新 result.json。

仅标准库；确定性产物（change_records 用逻辑序号，无 wall-clock）；绝不因畸形输入崩溃。
"""
import argparse
import hashlib
import json
import os
import re
import sys

SCHEMA = "process-qc-guard/checkpoint@1"


def sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def read_json_tolerant(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def ckpt_dir(work_dir):
    return os.path.join(work_dir, "checkpoints")


def ckpt_path(work_dir, stage):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", stage)
    return os.path.join(ckpt_dir(work_dir), safe + ".json")


def file_entry(path):
    rec = {"path": os.path.abspath(path)}
    try:
        st = os.stat(path)
        rec["bytes"] = st.st_size
        rec["sha256"] = sha256_file(path)
    except OSError as exc:
        rec["bytes"] = None
        rec["sha256"] = None
        rec["error"] = str(exc)
    return rec


def load_all(work_dir):
    """返回按 stage 排序的 [(stage, doc)]。"""
    out = []
    d = ckpt_dir(work_dir)
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        doc = read_json_tolerant(os.path.join(d, fn))
        if isinstance(doc, dict) and doc.get("stage"):
            out.append((doc["stage"], doc))
    return sorted(out, key=lambda x: (x[1].get("seq", 0), x[0]))


def verify_doc(doc):
    """校验单个检查点的依赖与产物，返回 (dep_problems, out_problems)。"""
    dep_problems, out_problems = [], []
    for dep in doc.get("deps", []):
        p = dep.get("path")
        now = sha256_file(p) if p else None
        if now is None:
            dep_problems.append({"path": p, "problem": "MISSING"})
        elif dep.get("sha256") and now != dep["sha256"]:
            dep_problems.append({"path": p, "problem": "CHANGED",
                                 "recorded": dep["sha256"], "current": now})
    for out in doc.get("outputs", []):
        p = out.get("path")
        now = sha256_file(p) if p else None
        if now is None:
            out_problems.append({"path": p, "problem": "MISSING"})
    return dep_problems, out_problems


def cmd_save(args):
    os.makedirs(ckpt_dir(args.work_dir), exist_ok=True)
    existing = load_all(args.work_dir)
    doc = {
        "schema": SCHEMA,
        "stage": args.stage,
        "seq": len(existing) + 1,
        "note": args.note or "",
        "deps": [file_entry(p) for p in (args.dep or [])],
        "outputs": [file_entry(p) for p in (args.out or [])],
        "cmd": args.cmd,
        "registered_for_rerun": bool(args.cmd),
    }
    atomic_write_json(ckpt_path(args.work_dir, args.stage), doc)
    print(json.dumps({"ok": True, "stage": args.stage, "seq": doc["seq"],
                      "deps": len(doc["deps"]), "outputs": len(doc["outputs"])},
                     ensure_ascii=False))
    return 0


def cmd_list(args):
    rows = [{"stage": s, "seq": d.get("seq"), "note": d.get("note", ""),
             "deps": len(d.get("deps", [])), "outputs": len(d.get("outputs", [])),
             "cmd_registered": bool(d.get("cmd"))}
            for s, d in load_all(args.work_dir)]
    print(json.dumps({"checkpoints": rows}, ensure_ascii=False, indent=2))
    return 0


def cmd_resume(args):
    stale, ok = [], []
    for stage, doc in load_all(args.work_dir):
        dep_problems, out_problems = verify_doc(doc)
        if dep_problems:
            stale.append({"stage": stage, "dep_problems": dep_problems,
                          "affected_outputs": [o.get("path") for o in doc.get("outputs", [])]})
        else:
            ok.append({"stage": stage, "outputs_missing": out_problems})
    report = {"verdict": "STALE" if stale else "CLEAN", "stale": stale, "ok": ok}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if stale:
        print("警告：检测到 STALE 检查点，受影响产物须重做后再交付。", file=sys.stderr)
        return 2
    return 0


def cmd_status(args):
    all_ck = load_all(args.work_dir)
    matrix, last_complete = [], None
    for stage, doc in all_ck:
        dep_problems, out_problems = verify_doc(doc)
        state = "STALE" if dep_problems else ("BROKEN" if out_problems else "COMPLETE")
        if state == "COMPLETE":
            last_complete = stage
        matrix.append({"stage": stage, "seq": doc.get("seq"), "state": state,
                       "dep_problems": dep_problems, "out_problems": out_problems})
    hint = ("下次中断可从阶段 '%s' 之后继续；其产物齐全、依赖未变。" % last_complete
            if last_complete else "无完整检查点：请从 init_run 重新开始。")
    print(json.dumps({"matrix": matrix, "resume_hint": hint},
                     ensure_ascii=False, indent=2))
    return 0


def extract_contract(case_obj):
    if not isinstance(case_obj, dict):
        return "unknown-case", []
    case_id = str(case_obj.get("case_id") or "unknown-case")
    contract = case_obj.get("output_contract")
    fields = []
    if isinstance(contract, dict):
        for key in ("required_fields", "fields", "properties"):
            val = contract.get(key)
            if isinstance(val, list):
                fields = [str(x) for x in val]
                break
            if isinstance(val, dict):
                fields = sorted(str(k) for k in val)
                break
    elif isinstance(contract, list):
        fields = [str(x) for x in contract]
    return case_id, fields


def cmd_export(args):
    """汇总检查点状态与探针结果，原子刷新 result.json。"""
    work = args.work_dir
    case_obj = read_json_tolerant(os.path.join(args.input_dir, "case.json"))
    case_id, fields = extract_contract(case_obj)

    answers, answers_name = None, None
    for name in ("answers.json", "items.json"):
        doc = read_json_tolerant(os.path.join(work, name))
        if isinstance(doc, dict):
            answers, answers_name = doc, name
            break
    if answers is None:
        print(json.dumps({"ok": False,
                          "reason": "工作目录无 answers.json/items.json，保留既有 result.json 骨架。"},
                         ensure_ascii=False))
        return 1

    items = answers.get("items") if isinstance(answers.get("items"), list) else []
    contract_values = answers.get("contract_fields")
    contract_values = contract_values if isinstance(contract_values, dict) else {}

    result, missing = {}, []
    for f in fields:
        v = contract_values.get(f)
        if v in (None, ""):
            hit = next((it for it in items
                        if isinstance(it, dict) and it.get("id") == f), None)
            v = hit.get("answer") if hit else None
        if v in (None, ""):
            missing.append(f)
            result[f] = None
        else:
            result[f] = v

    sources = answers.get("sources")
    if not isinstance(sources, list) or not sources:
        sources = sorted({str(it.get("evidence")) for it in items
                          if isinstance(it, dict) and it.get("evidence")})

    uncertainty = [str(it["uncertainty"]) for it in items
                   if isinstance(it, dict) and it.get("uncertainty")]
    uncertainty += ["契约字段 %s 无法作答，按契约置 null" % f for f in missing]

    probes = read_json_tolerant(os.path.join(work, "probes_report.json"))
    high = 0
    if isinstance(probes, dict):
        high = int(probes.get("summary", {}).get("high", 0))

    if high > 0:
        status, reason = "部分完成", "存在 %d 条未处理高危探针命中，详见 probes_report.json。" % high
    elif missing:
        status, reason = "部分完成", "契约字段未能全部作答：%s（已置 null 并记录 uncertainty）。" % "、".join(missing)
    else:
        status, reason = "成功", "全部契约字段已作答，失败探针无未处理高危。"

    records = [{"seq": i + 1, "stage": doc.get("stage"),
                "note": doc.get("note", "")}
               for i, (_s, doc) in enumerate(load_all(work))]
    records.append({"seq": len(records) + 1, "stage": "export",
                    "note": "checkpoint export 汇总 %s、probes 报告并刷新 result.json" % answers_name})

    result.update({
        "case_id": case_id,
        "status": status,
        "status_reason": reason,
        "sources": sources,
        "uncertainty": uncertainty,
        "change_records": records,
        "qc": {"probes_report": "probes_report.json（work 目录）",
               "probes_high_unresolved": high,
               "checkpoints": len(records) - 1},
    })
    out_path = os.path.join(args.output_dir, "result.json")
    os.makedirs(args.output_dir, exist_ok=True)
    atomic_write_json(out_path, result)
    print(json.dumps({"ok": True, "status": status, "status_reason": reason,
                      "missing_fields": missing, "written": out_path},
                     ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="process-qc-guard 阶段检查点与导出。")
    ap.add_argument("--work-dir", default="/app/work", help="工作目录（默认 /app/work）")
    sub = ap.add_subparsers(dest="subcommand", required=True)

    p = sub.add_parser("save", help="保存阶段检查点（原子写）")
    p.add_argument("--stage", required=True, help="阶段名，如 draft/verify/export")
    p.add_argument("--note", default="", help="说明")
    p.add_argument("--dep", action="append", help="输入依赖文件（可多次）")
    p.add_argument("--out", action="append", help="产物文件（可多次）")
    p.add_argument("--cmd", default=None, help="登记复跑命令（供 rerun_consistency 使用）")
    p.set_defaults(func=cmd_save)

    p = sub.add_parser("list", help="列出检查点")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("resume", help="校验依赖哈希，检出 STALE")
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("status", help="完成矩阵与续跑提示")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("export", help="汇总并刷新 result.json")
    p.add_argument("--input-dir", default="/input", help="输入目录（默认 /input）")
    p.add_argument("--output-dir", default="/app/output", help="交付目录（默认 /app/output）")
    p.set_defaults(func=cmd_export)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # 绝不崩溃：畸形输入降级为非零退出 + 说明
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)},
                         ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
