#!/usr/bin/env python3
"""fault_inject.py — 受控故障注入: 证明 partial 路径真实可用, 不是纸面承诺。

在 workdir/fault_lab/ 的 scratch 副本上注入受控故障, 验证
checkpoint / qc_gates / assemble 的 partial 路径全部"受控失败"
(非零退出 + 问题落盘), 而不是静默产出错误结果。

场景:
  s1_deleted_section   删掉图题所在行 -> qc_gates figure_ref_integrity 必须 FAIL
  s2_broken_json       把 result.json 写成坏 JSON -> checkpoint validate 必须非零退出
  s3_missing_contract_key  删掉一个契约键 -> checkpoint validate 必须报"契约键缺失"

产出 workdir/fault_report.json, 标注 controlled=true (受控测试, 非真实运行事故)。
输出确定性: 不含绝对路径与时间戳。仅依赖 python3 标准库。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

SCHEMA = "fault-report/v1"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
QC_GATES = os.path.join(SCRIPT_DIR, "qc_gates.py")
CHECKPOINT = os.path.join(SCRIPT_DIR, "checkpoint.py")

NOTE = ("受控故障注入测试 (controlled fault-injection drill): "
        "全部故障注入在 workdir/fault_lab/ 的 scratch 副本上进行, "
        "未触碰真实产物; 本报告证明 partial 降级路径真实可用。")


def atomic_write_json(path, obj):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".fault-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def run_cmd(argv):
    return subprocess.run([sys.executable] + argv,
                          capture_output=True, text=True)


def copy_chapters(src, dst):
    os.makedirs(dst, exist_ok=True)
    for f in sorted(os.listdir(src)):
        if f.endswith(".md"):
            shutil.copyfile(os.path.join(src, f), os.path.join(dst, f))


def scenario_deleted_section(lab, args):
    """删掉第一章含图题/表题行的那一行, figure_ref_integrity 必须 FAIL。"""
    work = os.path.join(lab, "s1_work")
    chaps = os.path.join(lab, "s1_chapters")
    os.makedirs(work, exist_ok=True)
    copy_chapters(args.chapters, chaps)
    removed = None
    for f in sorted(os.listdir(chaps)):
        p = os.path.join(chaps, f)
        with open(p, encoding="utf-8") as fh:
            lines = fh.readlines()
        out, done = [], False
        for ln in lines:
            s = ln.lstrip()
            if not done and (s.startswith("图") or s.startswith("表")) \
                    and len(s) > 1 and s[1].isdigit():
                removed = "%s: %s" % (f, s.strip())
                done = True
                continue
            out.append(ln)
        if done:
            with open(p, "w", encoding="utf-8") as fh:
                fh.writelines(out)
            break
    if removed is None:
        return {"name": "s1_deleted_section", "injected_fault": "无图题行可删",
                "expected": "qc_gates FAIL", "exit_code": -1,
                "observed": "场景无法构造", "verdict": "UNCONTAINED"}
    proc = run_cmd([QC_GATES, "run", "--workorder", args.workorder,
                    "--chapters", chaps, "--workdir", work])
    rep_overall, failed = "?", []
    rep_path = os.path.join(work, "gates_report.json")
    if os.path.exists(rep_path):
        with open(rep_path, encoding="utf-8") as fh:
            rep = json.load(fh)
        rep_overall = rep.get("overall")
        failed = rep.get("failed_items")
    contained = proc.returncode != 0 and rep_overall != "PASS"
    return {
        "name": "s1_deleted_section",
        "injected_fault": "删除图题/表题行: %s" % removed,
        "expected": "qc_gates 非零退出且 gates_report overall!=PASS",
        "exit_code": proc.returncode,
        "observed": "overall=%s failed_items=%s" % (rep_overall, failed),
        "verdict": "contained" if contained else "UNCONTAINED",
    }


def scenario_broken_json(lab, args):
    """把 result.json 写成坏 JSON, checkpoint validate 必须非零退出。"""
    out = os.path.join(lab, "s2_out")
    work = os.path.join(lab, "s2_work")
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as fh:
        fh.write("{ this is not valid json ")
    proc = run_cmd([CHECKPOINT, "validate", "--workdir", work,
                    "--outdir", out, "--case", args.case])
    first = (proc.stdout.strip().splitlines() or [""])[0]
    contained = proc.returncode != 0 and "JSON" in proc.stdout
    return {
        "name": "s2_broken_json",
        "injected_fault": "result.json 写入截断的非法 JSON",
        "expected": "checkpoint validate 非零退出并报非法 JSON",
        "exit_code": proc.returncode,
        "observed": first,
        "verdict": "contained" if contained else "UNCONTAINED",
    }


def scenario_missing_contract_key(lab, args):
    """从 result.json 副本删掉一个契约键, validate 必须报缺失。"""
    out = os.path.join(lab, "s3_out")
    work = os.path.join(lab, "s3_work")
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(args.outdir, "result.json"), encoding="utf-8") as fh:
        result = json.load(fh)
    with open(args.case, encoding="utf-8") as fh:
        fields = json.load(fh).get("output_contract", {}).get("fields", [])
    victim = next((f for f in fields if f in result), None)
    if victim is None:
        return {"name": "s3_missing_contract_key", "injected_fault": "无契约键可删",
                "expected": "validate 报契约键缺失", "exit_code": -1,
                "observed": "场景无法构造", "verdict": "UNCONTAINED"}
    del result[victim]
    with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    proc = run_cmd([CHECKPOINT, "validate", "--workdir", work,
                    "--outdir", out, "--case", args.case])
    contained = proc.returncode != 0 and victim in proc.stdout
    observed = next((ln for ln in proc.stdout.splitlines() if victim in ln),
                    proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else "")
    return {
        "name": "s3_missing_contract_key",
        "injected_fault": "删除契约键: %s" % victim,
        "expected": "checkpoint validate 非零退出并报该键缺失",
        "exit_code": proc.returncode,
        "observed": observed.strip(),
        "verdict": "contained" if contained else "UNCONTAINED",
    }


def cmd_run(args):
    lab = os.path.join(args.workdir, "fault_lab")
    if os.path.exists(lab):
        shutil.rmtree(lab)
    os.makedirs(lab)
    scenarios = [
        scenario_deleted_section(lab, args),
        scenario_broken_json(lab, args),
        scenario_missing_contract_key(lab, args),
    ]
    for s in scenarios:
        print("[fault] %s verdict=%s (exit=%s)" % (s["name"], s["verdict"], s["exit_code"]))
    all_ok = all(s["verdict"] == "contained" for s in scenarios)
    report = {
        "schema": SCHEMA,
        "controlled": True,
        "note": NOTE,
        "scenarios": scenarios,
        "overall": "all-contained" if all_ok else "UNCONTAINED-FAILURE",
    }
    if args.note:
        report["example_note"] = args.note
    atomic_write_json(os.path.join(args.workdir, "fault_report.json"), report)
    print("[fault] overall=%s" % report["overall"])
    if not all_ok:
        raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser(description="controlled fault injection drill (stdlib only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="运行全部受控故障场景")
    p.add_argument("--workdir", required=True)
    p.add_argument("--outdir", required=True, help="真实 result.json 所在目录 (只读)")
    p.add_argument("--case", required=True)
    p.add_argument("--workorder", required=True)
    p.add_argument("--chapters", required=True, help="编辑后章节目录 (只读)")
    p.add_argument("--note", default=None, help="附加示例标注 (如合成示例)")
    p.set_defaults(fn=cmd_run)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
