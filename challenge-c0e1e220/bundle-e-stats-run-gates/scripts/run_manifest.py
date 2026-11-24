#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_manifest — 构建/校验一次统计运行的 manifest.json（重心脚本 1）。

用途：
  build（由 pipeline_e 调用，也可命令行）：登记输入文件 sha256、环境（python/platform/utc）、
      阶段产物状态表（来自 work/seq.log 与 stage_*.json）、交付物哈希、pipeline 参数。
  check：重算任一输入/阶段/交付物的 sha256，与 manifest 对比，任何变化即报告并 exit 1。

确定性约定：除 generated_at_utc 外所有字段均由输入决定（replay_diff 据此逐字节比对）。
"""
import argparse
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone

MANIFEST_NAME = "manifest.json"
SEQ_LOG = "seq.log"
# 与 replay_diff.DEFAULT_VOLATILE 保持一致：含易变字段的 JSON 以剥离后规范字节登记哈希
VOLATILE_JSON_PATHS = ("reproducibility.timestamp_utc", "generated_at_utc")


def _strip_volatile(obj, paths):
    def rec(o, parts):
        if isinstance(o, dict):
            return {k: rec(v, parts + [k]) for k, v in o.items()
                    if ".".join(parts + [k]) not in paths}
        if isinstance(o, list):
            return [rec(v, parts + ["*"]) for v in o]
        return o
    return rec(obj, [])


def registered_hash(path):
    """登记用哈希：JSON 文件剥离易变字段后取规范字节 sha256（保证跨次运行确定）；
    非 JSON 取原始字节 sha256。"""
    if path.endswith(".json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            canon = json.dumps(_strip_volatile(obj, set(VOLATILE_JSON_PATHS)),
                               ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
            return hashlib.sha256(canon).hexdigest()
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    return sha256_file(path)
STAGE_FILES = [
    "stage_01_ingest.json",
    "stage_02_clean.json",
    "stage_03_descriptive.json",
    "stage_04_inference.json",
    "stage_05_result_draft.json",
]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(obj, path):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")


def normalize_argv(argv, input_dir, work_dir, output_dir):
    """把 argv 中的目录路径替换为占位符，保证复跑目录不同但 manifest 一致。"""
    out = []
    skip_next = False
    dir_opts = {"--input": "<INPUT>", "--work": "<WORK>", "--output": "<OUTPUT>", "--plan": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in dir_opts and i + 1 < len(argv):
            if dir_opts[a] is not None:
                out.extend([a, dir_opts[a]])
            else:
                out.extend([a, os.path.basename(argv[i + 1])])
            i += 2
            continue
        out.append(a)
        i += 1
    return out


def build_manifest(input_dir, work_dir, output_dir, case_id, argv):
    inputs = []
    if os.path.isdir(input_dir):
        for name in sorted(os.listdir(input_dir)):
            p = os.path.join(input_dir, name)
            if os.path.isfile(p):
                inputs.append({"file": name, "sha256": sha256_file(p), "bytes": os.path.getsize(p)})

    seq = []
    seq_path = os.path.join(work_dir, SEQ_LOG)
    if os.path.isfile(seq_path):
        with open(seq_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split("\t")
                    seq.append({"seq": int(parts[0]), "event": parts[1], "file": parts[2] if len(parts) > 2 else ""})

    stages = []
    for ev in seq:
        if ev["event"] != "write":
            continue
        p = os.path.join(work_dir, ev["file"])
        if os.path.isfile(p):
            stages.append({"seq": ev["seq"], "file": ev["file"], "sha256": registered_hash(p), "status": "written"})

    outputs = []
    if os.path.isdir(output_dir):
        for name in sorted(os.listdir(output_dir)):
            p = os.path.join(output_dir, name)
            if os.path.isfile(p):
                outputs.append({"file": name, "sha256": registered_hash(p)})

    dec_path = os.path.join(work_dir, "decisions.json")
    manifest = {
        "manifest_version": 1,
        "generated_at_utc": utc_now(),
        "case_id": case_id,
        "inputs": inputs,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "pipeline": {
            "script": "pipeline_e.py",
            "argv": normalize_argv(argv, input_dir, work_dir, output_dir),
            "decisions_sha256": registered_hash(dec_path) if os.path.isfile(dec_path) else None,
        },
        "stages": stages,
        "outputs": outputs,
    }
    write_json(manifest, os.path.join(work_dir, MANIFEST_NAME))
    return manifest


def check_manifest(input_dir, work_dir, output_dir):
    mpath = os.path.join(work_dir, MANIFEST_NAME)
    if not os.path.isfile(mpath):
        print("MANIFEST_MISSING: %s" % mpath)
        return 1
    m = load_json(mpath)
    problems = []

    known = {e["file"]: e for e in m["inputs"]}
    current = {}
    if os.path.isdir(input_dir):
        for name in sorted(os.listdir(input_dir)):
            p = os.path.join(input_dir, name)
            if os.path.isfile(p):
                current[name] = p
    for name, e in sorted(known.items()):
        if name not in current:
            problems.append("INPUT_MISSING: %s" % name)
        else:
            actual = sha256_file(current[name])
            if actual != e["sha256"]:
                problems.append("INPUT_CHANGED: %s manifest=%s actual=%s" % (name, e["sha256"][:16], actual[:16]))
    for name in sorted(current):
        if name not in known:
            problems.append("INPUT_ADDED: %s（未登记）" % name)

    for st in m["stages"]:
        p = os.path.join(work_dir, st["file"])
        if not os.path.isfile(p):
            problems.append("STAGE_MISSING: %s" % st["file"])
        elif registered_hash(p) != st["sha256"]:
            problems.append("STAGE_CHANGED: %s（阶段产物被篡改或未复跑）" % st["file"])

    for o in m["outputs"]:
        p = os.path.join(output_dir, o["file"])
        if not os.path.isfile(p):
            problems.append("OUTPUT_MISSING: %s" % o["file"])
        elif registered_hash(p) != o["sha256"]:
            problems.append("OUTPUT_CHANGED: %s" % o["file"])

    dec_path = os.path.join(work_dir, "decisions.json")
    dec_hash = registered_hash(dec_path) if os.path.isfile(dec_path) else None
    if dec_hash != m["pipeline"].get("decisions_sha256"):
        problems.append("DECISIONS_CHANGED: decisions.json 与登记不一致（改裁决后必须 finalize 复跑）")

    if problems:
        for p in problems:
            print(p)
        return 1
    print("MANIFEST_CHECK PASS: %d inputs, %d stage entries, %d outputs 全部一致"
          % (len(m["inputs"]), len(m["stages"]), len(m["outputs"])))
    return 0


def main():
    ap = argparse.ArgumentParser(description="构建/校验运行 manifest")
    ap.add_argument("mode", choices=["build", "check"])
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--case-id", default=None)
    ap.add_argument("--argv-json", default=None, help="build 模式：JSON 数组形式的原始 argv")
    args = ap.parse_args()
    if args.mode == "build":
        argv = json.loads(args.argv_json) if args.argv_json else []
        case_id = args.case_id
        if case_id is None:
            cj = os.path.join(args.input, "case.json")
            if os.path.isfile(cj):
                case_id = load_json(cj).get("case_id")
        build_manifest(args.input, args.work, args.output, case_id, argv)
        print("MANIFEST_BUILD OK: %s" % os.path.join(args.work, MANIFEST_NAME))
        return 0
    return check_manifest(args.input, args.work, args.output)


if __name__ == "__main__":
    sys.exit(main())
