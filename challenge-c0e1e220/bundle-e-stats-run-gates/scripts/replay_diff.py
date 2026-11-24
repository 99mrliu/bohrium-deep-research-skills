#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""replay_diff — 影子复跑确定性核验（重心脚本 4）。

把 pipeline 在临时目录完整重跑一遍（同一输入、同一 decisions.json、同一参数），
除易变字段（默认 result.json 的 reproducibility.timestamp_utc 与 manifest.json 的
generated_at_utc，可用 --volatile-json-path 显式追加）外，全部阶段产物与交付物
必须逐字节 sha256 一致；不一致即 exit 1 并打印 NONDETERMINISTIC_ARTIFACT 与漂移字段路径。

用法：python3 replay_diff.py [--input /input] [--work /app/work] [--output /app/output]
                             [--keep-tmp] [--volatile-json-path a.b.c]
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

DEFAULT_VOLATILE = ["reproducibility.timestamp_utc", "generated_at_utc"]
# 复跑目录不同但 manifest 必须一致：这些字段含目录名，需归一化后比较
PATH_BEARING_KEYS = ()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def strip_volatile(obj, paths):
    def rec(o, parts):
        if isinstance(o, dict):
            return {k: rec(v, parts + [k]) for k, v in o.items()
                    if ".".join(parts + [k]) not in paths}
        if isinstance(o, list):
            return [rec(v, parts + ["*"]) for v in o]
        return o
    return rec(obj, [])


def canon_bytes(obj, volatile):
    stripped = strip_volatile(obj, set(volatile))
    return json.dumps(stripped, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")


def drift_paths(a, b, prefix=""):
    """列出两个 JSON 结构的叶级差异路径。"""
    out = []
    if type(a) != type(b):
        out.append(prefix or "<root>")
        return out
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            p = "%s.%s" % (prefix, k) if prefix else k
            if k not in a:
                out.append(p + " <仅复跑侧存在>")
            elif k not in b:
                out.append(p + " <仅原运行侧存在>")
            else:
                out.extend(drift_paths(a[k], b[k], p))
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append((prefix or "<root>") + " <长度 %d vs %d>" % (len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            out.extend(drift_paths(x, y, "%s[%d]" % (prefix, i)))
    elif a != b:
        out.append("%s <%r vs %r>" % (prefix or "<root>", a, b))
    return out


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser(description="影子复跑逐字节确定性核验")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--volatile-json-path", action="append", default=[],
                    help="显式声明的额外易变 JSON 路径（点分）")
    ap.add_argument("--keep-tmp", action="store_true")
    args = ap.parse_args()
    volatile = DEFAULT_VOLATILE + list(args.volatile_json_path)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    manifest_path = os.path.join(args.work, "manifest.json")
    if not os.path.isfile(manifest_path):
        print("REPLAY_FAIL: manifest.json 不存在，无法取得原始参数（先跑 pipeline_e run）")
        return 1
    manifest = load_json(manifest_path)

    tmp = tempfile.mkdtemp(prefix="replay_e_")
    tmp_in = os.path.join(tmp, "input")
    tmp_work = os.path.join(tmp, "work")
    tmp_out = os.path.join(tmp, "output")
    shutil.copytree(args.input, tmp_in)
    os.makedirs(tmp_work, exist_ok=True)
    os.makedirs(tmp_out, exist_ok=True)
    dec_src = os.path.join(args.work, "decisions.json")
    if os.path.isfile(dec_src):
        shutil.copyfile(dec_src, os.path.join(tmp_work, "decisions.json"))

    extra_argv = list(manifest.get("pipeline", {}).get("argv", []))
    # 去掉目录参数（复跑时重新指定）；--plan 归一化为 basename，重定位到副本内
    fixed = []
    i = 0
    while i < len(extra_argv):
        a = extra_argv[i]
        if a in ("--input", "--work", "--output"):
            i += 2
            continue
        if a == "--plan" and i + 1 < len(extra_argv):
            base = extra_argv[i + 1]
            cand = os.path.join(tmp_in, base)
            if os.path.isfile(cand):
                fixed.extend(["--plan", cand])
            else:
                src_w = os.path.join(args.work, base)
                if os.path.isfile(src_w):
                    dst = os.path.join(tmp_work, base)
                    shutil.copyfile(src_w, dst)
                    fixed.extend(["--plan", dst])
                else:
                    print("REPLAY_FAIL: 无法重定位 --plan 文件 %s" % base)
                    shutil.rmtree(tmp, ignore_errors=True)
                    return 1
            i += 2
            continue
        fixed.append(a)
        i += 1

    cmd = [sys.executable, os.path.join(script_dir, "pipeline_e.py"), "run",
           "--input", tmp_in, "--work", tmp_work, "--output", tmp_out] + fixed
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("REPLAY_FAIL: 影子复跑未成功 exit=%d\n%s\n%s" % (r.returncode, r.stdout[-2000:], r.stderr[-2000:]))
        if not args.keep_tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        return 1

    problems = []
    compared = 0
    for dirpair in ((args.work, tmp_work), (args.output, tmp_out)):
        d_orig, d_new = dirpair
        names_a = sorted(f for f in os.listdir(d_orig) if os.path.isfile(os.path.join(d_orig, f)))
        names_b = sorted(f for f in os.listdir(d_new) if os.path.isfile(os.path.join(d_new, f)))
        if names_a != names_b:
            problems.append("NONDETERMINISTIC_ARTIFACT: 文件集合不一致 %s vs %s" % (names_a, names_b))
            continue
        for name in names_a:
            pa, pb = os.path.join(d_orig, name), os.path.join(d_new, name)
            with open(pa, "rb") as f:
                ba = f.read()
            with open(pb, "rb") as f:
                bb = f.read()
            compared += 1
            if name.endswith(".json"):
                try:
                    ca = canon_bytes(load_json(pa), volatile)
                    cb = canon_bytes(load_json(pb), volatile)
                except json.JSONDecodeError:
                    ca, cb = ba, bb
                if sha256_bytes(ca) != sha256_bytes(cb):
                    paths = drift_paths(strip_volatile(load_json(pa), set(volatile)),
                                        strip_volatile(load_json(pb), set(volatile)))
                    problems.append("NONDETERMINISTIC_ARTIFACT: %s 漂移字段: %s"
                                    % (os.path.join(os.path.basename(d_orig), name), paths[:10]))
            else:
                if ba != bb:
                    problems.append("NONDETERMINISTIC_ARTIFACT: %s 字节不一致"
                                    % os.path.join(os.path.basename(d_orig), name))
    if problems:
        for p in problems:
            print(p)
        print("REPLAY_DIFF FAIL: %d 处漂移（%d 个文件参与比对）" % (len(problems), compared))
        if args.keep_tmp:
            print("复跑目录保留于: %s" % tmp)
        else:
            shutil.rmtree(tmp, ignore_errors=True)
        return 1
    print("REPLAY_DIFF PASS: %d 个产物除易变字段 %s 外逐字节一致" % (compared, volatile))
    if not args.keep_tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
