#!/usr/bin/env python3
"""runcap.py — 运行取证与重放：命令级台账、失败现场保留、可重放脚本
（纯 Python 标准库）。

重心是运行调试与过程可复核：Agent 出错后的典型恶习是"不定位原因，换一
段代码继续试"。本工具把每一次执行变成一条带完整现场的结构化记录，使
失败可定位、过程可重放、结果可复核。

子命令：
  init     建档：对输入目录逐文件取 sha256 写 manifest，落盘
           result.json 诚实骨架（status=in_progress）
  exec     包装执行任意命令：记录命令行、工作目录、开始/结束时间、
           退出码、stdout/stderr（截断保留首尾）、涉及输入文件的哈希；
           非零退出时自动生成 failure_record（错误分类 + 建议处置）
  replay   从台账生成 replay.sh：复核者可逐步重放全部成功命令
  report   汇总台账：成功率、失败分类统计、重试链（同一命令的多次
           尝试）、总耗时，输出 run_summary.md
  seal     收尾：把台账摘要并入 /app/output/result.json 的 provenance，
           核对 case_id 与契约字段，未落实字段强制 partial

台账：/app/work/runs.jsonl，每行一个 JSON 事件，append-only。
"""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time

MAX_CAPTURE = 4000

FAIL_CLASSES = [
    ("ModuleNotFoundError", "依赖缺失", "改用标准库实现或在 provenance 记录实际依赖与版本"),
    ("FileNotFoundError", "路径错误", "用绝对路径；先 ls 核对再运行，不猜文件名"),
    ("PermissionError", "权限不足", "改用可写工作区 /app/work；不就地修改只读输入"),
    ("UnicodeDecodeError", "编码问题", "按 utf-8-sig→utf-8→gb18030 顺序探测并记录实际编码"),
    ("KeyError", "字段名不符", "先 profile 数据核对其真实列名，用显式映射对齐"),
    ("no such table", "表名错误", "查询前先列出 sqlite_master 表清单"),
    ("no such column", "列名错误", "用 PRAGMA table_info 核对后再写查询"),
    ("MemoryError", "内存不足", "改流式处理/分块聚合；记录数据规模"),
    ("Timeout", "超时", "缩小数据切片先验证逻辑，再放全量"),
]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def cmd_init(args):
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.output, exist_ok=True)
    manifest = {}
    for root, _d, names in os.walk(args.input):
        for n in sorted(names):
            p = os.path.join(root, n)
            rel = os.path.relpath(p, args.input)
            manifest[rel] = {"sha256": sha256_file(p), "bytes": os.path.getsize(p)}
    _dump(os.path.join(args.work, "input_manifest.json"), manifest)
    case_id = "UNKNOWN_CASE_ID"
    fields = []
    cj = os.path.join(args.input, "case.json")
    if os.path.isfile(cj):
        try:
            case = json.load(open(cj, encoding="utf-8"))
            case_id = case.get("case_id") or case.get("id") or case_id
            oc = case.get("output_contract") or {}
            if isinstance(oc, dict):
                oc = oc.get("fields") or oc.get("required") or list(oc)
            fields = [f if isinstance(f, str) else str(f.get("name")) for f in oc]
        except Exception as e:  # noqa: BLE001
            manifest["_case_json_error"] = str(e)
    skeleton = {"case_id": case_id, "status": "in_progress",
                **{k: None for k in fields},
                "anomalies": [], "missing_fields": [],
                "provenance": {"input_manifest": "input_manifest.json",
                               "runs_log": "runs.jsonl",
                               "python": platform.python_version()}}
    _dump(os.path.join(args.output, "result.json"), skeleton)
    print("INIT OK case_id=%s inputs=%d 骨架已落盘" % (case_id, len(manifest)))
    return 0


def cmd_exec(args):
    os.makedirs(args.work, exist_ok=True)
    log = os.path.join(args.work, "runs.jsonl")
    cmd = list(args.command)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("EXEC: 空命令", file=sys.stderr)
        return 2
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          cwd=args.cwd or os.getcwd())
    dt = time.time() - t0
    stdout, stderr = proc.stdout or "", proc.stderr or ""
    out_path = os.path.join(args.work, "stdout_%s.txt" % args.tag)
    err_path = os.path.join(args.work, "stderr_%s.txt" % args.tag)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(stdout)
    with open(err_path, "w", encoding="utf-8") as f:
        f.write(stderr)
    rec = {"tag": args.tag, "cmd": cmd, "cwd": args.cwd or os.getcwd(),
           "exit_code": proc.returncode, "elapsed_s": round(dt, 3),
           "stdout_file": os.path.basename(out_path),
           "stderr_file": os.path.basename(err_path),
           "stdout_tail": stdout[-MAX_CAPTURE:] if len(stdout) > MAX_CAPTURE else stdout,
           "stderr_tail": stderr[-MAX_CAPTURE:] if len(stderr) > MAX_CAPTURE else stderr}
    if args.hash:
        rec["input_hashes"] = {p: sha256_file(p) for p in args.hash
                               if os.path.isfile(p)}
    if proc.returncode != 0:
        rec["failure_record"] = classify_failure(stderr + "\n" + stdout)
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    sys.stdout.write(stdout)
    sys.stderr.write(stderr)
    print("[runcap] tag=%s exit=%d %.2fs -> runs.jsonl" % (args.tag, proc.returncode, dt),
          file=sys.stderr)
    return proc.returncode


def classify_failure(text):
    for needle, cls, advice in FAIL_CLASSES:
        if needle in text:
            return {"class": cls, "matched": needle, "advice": advice,
                    "raw_tail": text[-800:]}
    return {"class": "未分类", "matched": None,
            "advice": "读 stderr_tail 定位根因；修复后以同 tag 重跑形成重试链",
            "raw_tail": text[-800:]}


def cmd_replay(args):
    log = os.path.join(args.work, "runs.jsonl")
    events = _read_log(log)
    lines = ["#!/usr/bin/env bash",
             "# replay.sh — 由 runcap 从 runs.jsonl 生成；逐步重放所有最终成功命令",
             "set -uo pipefail", ""]
    seen_latest = {}
    for e in events:
        seen_latest[e["tag"]] = e  # 同一 tag 只重放最后一次（收敛后的版本）
    for e in seen_latest.values():
        if e["exit_code"] != 0:
            lines.append("# 跳过（最终仍失败）: %s -> %s"
                         % (e["tag"], " ".join(e["cmd"])))
            continue
        lines.append("echo '== replay %s'" % e["tag"])
        lines.append("( cd %s && %s ) || echo 'REPLAY FAILED: %s'"
                     % (e["cwd"], " ".join(_shq(c) for c in e["cmd"]), e["tag"]))
        lines.append("")
    out = os.path.join(args.work, "replay.sh")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.chmod(out, 0o755)
    print("REPLAY OK: %s（%d 条命令）" % (out, len(seen_latest)))
    return 0


def _shq(s):
    if not s or any(c in s for c in " \t'\"$`\\|&;<>()*"):
        return "'" + s.replace("'", "'\\''") + "'"
    return s


def _read_log(log):
    if not os.path.isfile(log):
        raise SystemExit("NO_LOG: %s 不存在" % log)
    return [json.loads(l) for l in open(log, encoding="utf-8") if l.strip()]


def cmd_report(args):
    events = _read_log(os.path.join(args.work, "runs.jsonl"))
    total = len(events)
    fails = [e for e in events if e["exit_code"] != 0]
    classes = {}
    for e in fails:
        cls = (e.get("failure_record") or {}).get("class", "未分类")
        classes[cls] = classes.get(cls, 0) + 1
    retry = {}
    for e in events:
        retry.setdefault(e["tag"], []).append(e["exit_code"])
    chains = {t: v for t, v in retry.items() if len(v) > 1}
    elapsed = sum(e["elapsed_s"] for e in events)
    md = ["# 运行台账汇总（runcap report）", "",
          "- 执行事件总数: %d（成功 %d / 失败 %d）" % (total, total - len(fails), len(fails)),
          "- 总耗时: %.1fs" % elapsed, "",
          "## 失败分类"]
    for cls, n in sorted(classes.items(), key=lambda x: -x[1]):
        md.append("- %s: %d 次" % (cls, n))
    if not classes:
        md.append("- 无失败")
    md += ["", "## 重试链（同一 tag 多次执行）"]
    for t, codes in chains.items():
        md.append("- `%s`: 退出码序列 %s" % (t, codes))
    if not chains:
        md.append("- 无重试")
    md += ["", "## 全部事件"]
    for e in events:
        md.append("- `%s` exit=%d %.2fs: `%s`"
                  % (e["tag"], e["exit_code"], e["elapsed_s"], " ".join(e["cmd"])))
    out = os.path.join(args.work, "run_summary.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print("REPORT OK: %s（%d 事件 / %d 失败 / %d 条重试链）"
          % (out, total, len(fails), len(chains)))
    return 0


def cmd_seal(args):
    rpath = os.path.join(args.output, "result.json")
    if not os.path.isfile(rpath):
        raise SystemExit("SEAL: %s 不存在——先 init" % rpath)
    result = json.load(open(rpath, encoding="utf-8"))
    events = []
    log = os.path.join(args.work, "runs.jsonl")
    if os.path.isfile(log):
        events = _read_log(log)
    open_fails = {}
    for e in events:
        if e["exit_code"] != 0:
            open_fails[e["tag"]] = (e.get("failure_record") or {}).get("class", "未分类")
        else:
            open_fails.pop(e["tag"], None)  # 后续同 tag 成功则视为已解决
    result.setdefault("provenance", {}).update({
        "runs_log": "runs.jsonl", "run_summary": "run_summary.md",
        "n_executed": len(events),
        "unresolved_failures": open_fails})
    problems = []
    cj = os.path.join(args.input, "case.json")
    if os.path.isfile(cj):
        case = json.load(open(cj, encoding="utf-8"))
        cid = case.get("case_id") or case.get("id")
        if cid and result.get("case_id") != cid:
            problems.append("case_id 不一致")
        oc = case.get("output_contract") or {}
        if isinstance(oc, dict):
            oc = oc.get("fields") or oc.get("required") or list(oc)
        for f in oc:
            k = f if isinstance(f, str) else str(f.get("name"))
            if result.get(k) is None:
                problems.append("契约字段为 null: %s" % k)
    if open_fails and not result.get("missing_fields"):
        problems.append("存在未解决失败 %s，但 missing_fields 为空" % sorted(open_fails))
    if problems:
        if result.get("status") == "success":
            result["status"] = "partial"
        known = {m.get("field") for m in result.get("missing_fields", [])
                 if isinstance(m, dict)}
        for p in problems:
            f = p.split(": ")[-1]
            if f not in known:
                result.setdefault("missing_fields", []).append(
                    {"field": f, "reason": p})
        _dump(rpath, result)
        print("SEAL partial（%d 项）: %s" % (len(problems), "; ".join(problems)))
        return 1
    result["status"] = "success"
    _dump(rpath, result)
    print("SEAL OK: status=success，台账摘要已并入 provenance")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--input", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("exec")
    p.add_argument("--work", required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--cwd")
    p.add_argument("--hash", nargs="*", default=[])
    p.add_argument("command", nargs=argparse.REMAINDER)
    p.set_defaults(fn=cmd_exec)
    p = sub.add_parser("replay")
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_replay)
    p = sub.add_parser("report")
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("seal")
    p.add_argument("--input", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(fn=cmd_seal)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
