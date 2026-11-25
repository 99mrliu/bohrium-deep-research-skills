#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reproduce.py — 重复运行稳定性校验（budget-warden-qc）

在隔离临时目录把 warden 管线连跑 --runs 遍（默认 2），逐字节 diff 各份 result.json
（run_log.json 允许时间戳不同，不参与比较）。报告 identical=true/false 与差异点，
写入 workdir/reproduce_report.json 并打印摘要。退出码：一致 0，不一致或运行失败 1。

仅标准库、离线、位置无关（warden.py 按本文件所在目录定位）。
"""
import argparse
import difflib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def canon(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="warden 管线双跑一致性校验")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--roots", nargs="*", default=None)
    ap.add_argument("--max-depth", type=int, default=2)
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--workdir", default="/app/work", help="报告输出目录")
    ap.add_argument("--keep-dirs", action="store_true", help="保留临时运行目录便于排查")
    args = ap.parse_args(argv)

    warden = Path(__file__).resolve().parent / "warden.py"
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    runs = []
    for i in range(args.runs):
        tmp = Path(tempfile.mkdtemp(prefix="warden-repro-%d-" % i))
        cmd = [sys.executable, str(warden), "--case", str(args.case),
               "--out", str(tmp / "out"), "--workdir", str(tmp / "work"),
               "--max-depth", str(args.max_depth)]
        if args.roots:
            cmd += ["--roots"] + [str(r) for r in args.roots]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        result_path = tmp / "out" / "result.json"
        blob = result_path.read_bytes() if result_path.exists() else None
        runs.append({"run": i, "dir": str(tmp), "returncode": proc.returncode,
                     "stdout_tail": (proc.stdout or "")[-400:],
                     "stderr_tail": (proc.stderr or "")[-400:],
                     "result_bytes": (len(blob) if blob is not None else None)})
        if blob is not None:
            runs[i]["_blob"] = blob

    identical = True
    diffs = []
    base = runs[0].get("_blob") if runs else None
    for r in runs:
        if r["returncode"] != 0:
            identical = False
            diffs.append({"run": r["run"], "kind": "nonzero-exit",
                          "detail": "returncode=%d stderr=%s" % (r["returncode"], r["stderr_tail"])})
        if r.get("_blob") is None:
            identical = False
            diffs.append({"run": r["run"], "kind": "missing-result",
                          "detail": "result.json 未生成"})
    if base is not None:
        for r in runs[1:]:
            blob = r.get("_blob")
            if blob is None or blob == base:
                continue
            identical = False
            off = next((i for i, (a, b) in enumerate(zip(base, blob)) if a != b),
                       min(len(base), len(blob)))
            udiff = list(difflib.unified_diff(
                base.decode("utf-8", "replace").splitlines(),
                blob.decode("utf-8", "replace").splitlines(),
                fromfile="run0/result.json", tofile="run%d/result.json" % r["run"], lineterm=""))
            diffs.append({"run": r["run"], "kind": "bytes-differ",
                          "first_diff_offset": off,
                          "len_run0": len(base), "len_runN": len(blob),
                          "unified_diff_head": udiff[:60]})

    report = {"identical": identical, "runs": [{k: v for k, v in r.items() if k != "_blob"}
                                               for r in runs],
              "diffs": diffs, "generated_at": datetime.now(timezone.utc).isoformat(),
              "note": "仅比较 result.json 字节；run_log.json 时间戳差异属预期，不参与比较。"}
    (workdir / "reproduce_report.json").write_text(canon(report), encoding="utf-8")

    if not args.keep_dirs:
        import shutil
        for r in runs:
            shutil.rmtree(r["dir"], ignore_errors=True)
    else:
        for r in report["runs"]:
            r["kept"] = True

    print("identical=%s runs=%d diffs=%d" % (str(identical).lower(), len(runs), len(diffs)))
    for d in diffs[:5]:
        print("  diff: run=%s kind=%s %s" % (d["run"], d["kind"], str(d.get("detail", ""))[:200]))
    return 0 if identical else 1


if __name__ == "__main__":
    sys.exit(main())
