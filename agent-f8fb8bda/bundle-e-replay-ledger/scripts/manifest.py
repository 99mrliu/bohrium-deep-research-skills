#!/usr/bin/env python3
"""manifest.py — 运行清单（环境 + 输入/产物/skill 文件 SHA-256 清单）。

子命令：
  build   [--input-dir /input] [--out /app/output] [--skill-dir /skills/weekly-skill]
          [--checkpoints /app/work/checkpoints/stages.json]
          生成 <out>/run_manifest.json：
            - python 版本与平台
            - 输入文件清单 + SHA-256（相对 --input-dir 路径）
            - 输出产物清单 + SHA-256（相对 --out 路径，不含 run_manifest.json 自身）
            - skill 文件清单 + SHA-256（相对 --skill-dir 路径；目录不存在则记 null）
            - 阶段时间线（若 checkpoints 文件存在则并入；时间戳仅出现在本文件，
              不参与 journal 哈希链）
  verify  --manifest PATH
          重算输入与产物（以及存在的 skill）文件哈希并比对，任何改动 -> exit 1
          并逐个指出被改/缺失文件。

退出码：0 通过；1 门控违例；2 用法/IO 错误。
"""
import argparse
import hashlib
import json
import os
import platform
import sys
import time

CHUNK = 1024 * 1024


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def list_files(root):
    out = []
    if not root or not os.path.isdir(root):
        return None
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            out.append((rel, full))
    return out


def build_section(root, exclude=()):
    files = list_files(root)
    if files is None:
        return None
    sec = []
    for rel, full in files:
        if rel in exclude:
            continue
        sec.append({"path": rel, "sha256": sha256_file(full),
                    "bytes": os.path.getsize(full)})
    return sec


def cmd_build(args):
    input_dir, out_dir, skill_dir = args.input_dir, args.out, args.skill_dir
    if not os.path.isdir(input_dir):
        print(f"[ERROR] 输入目录不存在: {input_dir}", file=sys.stderr)
        sys.exit(2)
    os.makedirs(out_dir, exist_ok=True)

    manifest = {
        "manifest_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "roots": {"input_dir": os.path.abspath(input_dir),
                  "out_dir": os.path.abspath(out_dir),
                  "skill_dir": os.path.abspath(skill_dir)},
        "inputs": build_section(input_dir),
        "outputs": build_section(out_dir, exclude=("run_manifest.json",)),
        "skill_files": build_section(skill_dir),
        "phase_timeline": None,
    }
    ck = args.checkpoints
    if ck and os.path.exists(ck):
        try:
            with open(ck, "r", encoding="utf-8") as f:
                manifest["phase_timeline"] = json.load(f)
        except (json.JSONDecodeError, OSError):
            manifest["phase_timeline"] = {"error": "checkpoints 文件不可解析"}

    out_path = os.path.join(out_dir, "run_manifest.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    n_in = len(manifest["inputs"] or [])
    n_out = len(manifest["outputs"] or [])
    n_sk = len(manifest["skill_files"] or []) if manifest["skill_files"] is not None else "N/A"
    print(f"[OK] manifest written: {out_path}")
    print(f"     inputs={n_in} outputs={n_out} skill_files={n_sk}")
    sys.exit(0)


def verify_section(name, root, section, failures):
    if section is None:
        return
    if not os.path.isdir(root):
        failures.append(f"{name}: 根目录不存在: {root}")
        return
    seen = set()
    for item in section:
        rel, expect = item["path"], item["sha256"]
        seen.add(rel)
        full = os.path.join(root, rel)
        if not os.path.exists(full):
            failures.append(f"{name}: 文件缺失: {rel}")
            continue
        actual = sha256_file(full)
        if actual != expect:
            failures.append(f"{name}: 哈希不一致（文件被改动）: {rel} "
                            f"expect={expect[:16]}… actual={actual[:16]}…")
    extra = []
    for rel, _ in (list_files(root) or []):
        if rel not in seen and rel != "run_manifest.json":
            extra.append(rel)
    for rel in extra:
        failures.append(f"{name}: 清单外新增文件: {rel}")


def cmd_verify(args):
    if not os.path.exists(args.manifest):
        print(f"[ERROR] manifest 不存在: {args.manifest}", file=sys.stderr)
        sys.exit(2)
    with open(args.manifest, "r", encoding="utf-8") as f:
        m = json.load(f)
    roots = m.get("roots", {})
    failures = []
    verify_section("inputs", roots.get("input_dir", ""), m.get("inputs"), failures)
    verify_section("outputs", roots.get("out_dir", ""), m.get("outputs"), failures)
    verify_section("skill_files", roots.get("skill_dir", ""), m.get("skill_files"), failures)
    if failures:
        print("[GATE FAIL] manifest 校验未通过：")
        for f_ in failures:
            print(f"  - {f_}")
        sys.exit(1)
    print("[OK] manifest 校验通过：输入、产物、skill 文件哈希全部一致，无缺失无新增")
    sys.exit(0)


def main():
    p = argparse.ArgumentParser(description="运行清单 build/verify")
    sub = p.add_subparsers(dest="cmd", required=True)

    pb = sub.add_parser("build")
    pb.add_argument("--input-dir", default="/input")
    pb.add_argument("--out", default="/app/output")
    pb.add_argument("--skill-dir", default="/skills/weekly-skill")
    pb.add_argument("--checkpoints", default="/app/work/checkpoints/stages.json")
    pb.set_defaults(fn=cmd_build)

    pv = sub.add_parser("verify")
    pv.add_argument("--manifest", required=True)
    pv.set_defaults(fn=cmd_verify)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
