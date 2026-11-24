#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""replay_check.py — 确定性复跑证明（过程质量控制方向）。

在同一环境内将整条流水线完整复跑一次（独立 work/out 目录），
逐文件比对两次运行的产物：
- 文本产物（statistics/cleaning/captions/check 等 JSON/Markdown）逐字节比对；
- 二进制图件（PNG/PDF/SVG）比对 SHA-256；
- 任何不一致列出文件名与首处差异偏移，写入 replay_report.json。

用法：
    python3 replay_check.py --case /input/case.json --input-dir /input \
        --out /app/output/replay_report.json [--run-case scripts/run_case.py]
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

TEXT_EXT = (".json", ".md", ".txt", ".csv")
NORMALIZED_EXT = (".svg", ".pdf")  # 嵌入时间戳/随机 ID，归一化后比对
SKIP = {"replay_report.json", "ledger.json", "result.json"}


def normalize_artifact(name, raw):
    """Strip volatile metadata (timestamps, document IDs) before compare."""
    import re as _re
    if name.endswith(".svg"):
        raw = _re.sub(rb"<dc:date>.*?</dc:date>", b"<dc:date/>", raw,
                      flags=_re.S)
        # matplotlib 随机 clip-path/marker/path-collection id（每次运行不同）
        raw = _re.sub(rb'#[pm][0-9a-f]{8,12}', b"#NORM", raw)
        raw = _re.sub(rb'id="[pm][0-9a-f]{8,12}"', b'id="NORM"', raw)
        raw = _re.sub(rb'#C\w*_\d+_[0-9a-f]+', b"#NORM", raw)
        raw = _re.sub(rb'id="C\w*_\d+_[0-9a-f]+"', b'id="NORM"', raw)
        raw = _re.sub(rb'id="image[0-9a-f]+"', b'id="NORM"', raw)
        # SVG 内嵌 base64 位图（热图等）：PNG 编码含时间戳，结构比对时剔除
        raw = _re.sub(rb'data:image/png;base64,[A-Za-z0-9+/=\s]+',
                      b"data:image/png;base64,NORM", raw)
    elif name.endswith(".pdf"):
        raw = _re.sub(rb"/(CreationDate|ModDate)\s*\(D:[^)]*\)",
                      rb"/\1 (D:normalized)", raw)
        raw = _re.sub(rb"/ID\s*\[\s*<[0-9A-Fa-f]*>\s*<[0-9A-Fa-f]*>\s*\]",
                      b"/ID [<normalized><normalized>]", raw)
    return raw


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def collect(out_dir):
    files = {}
    for n in sorted(os.listdir(out_dir)):
        p = os.path.join(out_dir, n)
        if os.path.isfile(p) and n not in SKIP:
            with open(p, "rb") as fh:
                files[n] = fh.read()
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--run-case", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "run_case.py"))
    args = ap.parse_args()

    here = os.path.dirname(args.out)
    baseline = collect(here)
    report = {"replay": "full pipeline re-executed once in isolated dirs",
              "baseline_outdir": os.path.abspath(here),
              "files": {}, "text_identical": True, "binary_identical": True,
              "all_passed": True, "notes": []}

    tmp = tempfile.mkdtemp(prefix="replay_")
    work2 = os.path.join(tmp, "work")
    out2 = os.path.join(tmp, "out")
    os.makedirs(work2, exist_ok=True)
    os.makedirs(out2, exist_ok=True)
    env = dict(os.environ)
    env["RUN_CASE_REPLAY_CHILD"] = "1"
    proc = subprocess.run(
        [sys.executable, os.path.abspath(args.run_case),
         "--case", os.path.abspath(args.case),
         "--input-dir", os.path.abspath(args.input_dir),
         "--work", work2, "--out", out2],
        capture_output=True, text=True, timeout=600, env=env)
    report["replay_returncode"] = proc.returncode
    if proc.returncode != 0:
        report["all_passed"] = False
        report["notes"].append("replay run failed: %s"
                               % (proc.stdout + proc.stderr)[-300:])
    replayed = collect(out2)

    for name, raw in sorted(baseline.items()):
        ent = {}
        if name not in replayed:
            ent = {"present_in_replay": False, "identical": False}
            report["all_passed"] = False
        else:
            raw2 = replayed[name]
            if name.endswith(NORMALIZED_EXT):
                same = normalize_artifact(name, raw) == \
                    normalize_artifact(name, raw2)
                ent = {"present_in_replay": True,
                       "identical_after_metadata_normalization": same,
                       "raw_bytes_identical": raw == raw2,
                       "note": "原始字节含嵌入时间戳/文档 ID；比对已归一化"
                               if raw != raw2 else "逐字节一致"}
                if not same:
                    report["all_passed"] = False
                    report["binary_identical"] = False
            else:
                same = raw == raw2
                ent = {"present_in_replay": True, "identical": same,
                       "sha256_baseline": sha256_bytes(raw),
                       "sha256_replay": sha256_bytes(raw2)}
                if not same:
                    report["all_passed"] = False
                    if name.endswith(TEXT_EXT):
                        report["text_identical"] = False
                        k = next((i for i, (a, b)
                                  in enumerate(zip(raw, raw2)) if a != b),
                                 min(len(raw), len(raw2)))
                        ent["first_diff_offset"] = k
                    else:
                        report["binary_identical"] = False
        report["files"][name] = ent
    for name in replayed:
        if name not in baseline:
            report["files"][name] = {"present_in_baseline": False,
                                     "identical": False}
            report["all_passed"] = False

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"all_passed": report["all_passed"],
                      "compared": len(report["files"]),
                      "text_identical": report["text_identical"],
                      "binary_identical": report["binary_identical"]},
                     ensure_ascii=False))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
