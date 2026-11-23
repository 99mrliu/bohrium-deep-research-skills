#!/usr/bin/env python3
"""manifest.py — 阶段登记与断点续跑判断。

work/manifest.json 记录每个阶段的：状态、输入文件 sha256、输出清单。
重跑时若某阶段已完成且输入 hash 未变、产物齐全，则自动跳过（幂等续跑）。

子命令：
  begin       登记阶段开始（status=in_progress，记录输入 hash）
  end         登记阶段完成（status=done，记录输出清单）
  should-skip 查询是否可跳过：退出码 0=可跳过, 1=需重跑
  status      打印 manifest 内容

注意：输入路径以字符串形式登记，请以一致的方式（建议同样的相对/绝对路径）调用，
否则同一文件因路径写法不同会被视为输入已变化。仅标准库，无网络。
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_path(workdir):
    return Path(workdir) / "manifest.json"


def load(workdir):
    p = manifest_path(workdir)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"stages": {}}


def save(workdir, m):
    Path(workdir).mkdir(parents=True, exist_ok=True)
    manifest_path(workdir).write_text(
        json.dumps(m, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def hash_inputs(inputs):
    d = {}
    for p in inputs:
        p = Path(p)
        d[str(p)] = sha256_file(p) if p.exists() else "MISSING"
    return d


def begin_stage(workdir, name, inputs):
    m = load(workdir)
    prev = m["stages"].get(name, {})
    m["stages"][name] = {
        "status": "in_progress",
        "inputs": hash_inputs(inputs),
        "outputs": prev.get("outputs", []),
    }
    save(workdir, m)


def end_stage(workdir, name, outputs):
    m = load(workdir)
    st = m["stages"].get(name, {"inputs": {}})
    st["status"] = "done"
    st["outputs"] = [str(o) for o in outputs]
    m["stages"][name] = st
    save(workdir, m)


def should_skip(workdir, name, inputs):
    """输入 hash 未变且登记产物全部存在 => True（可跳过）。"""
    m = load(workdir)
    st = m["stages"].get(name)
    if not st or st.get("status") != "done":
        return False
    if st.get("inputs") != hash_inputs(inputs):
        return False
    for o in st.get("outputs", []):
        if not Path(o).exists():
            return False
    return True


def main():
    ap = argparse.ArgumentParser(description="manifest：阶段登记与断点续跑判断")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_common(p, outputs=False):
        p.add_argument("--workdir", default="/app/work")
        p.add_argument("--stage", required=True)
        p.add_argument("--inputs", nargs="*", default=[])
        if outputs:
            p.add_argument("--outputs", nargs="*", default=[])

    add_common(sub.add_parser("begin"))
    add_common(sub.add_parser("end"), outputs=True)
    add_common(sub.add_parser("should-skip"))
    sp = sub.add_parser("status")
    sp.add_argument("--workdir", default="/app/work")

    args = ap.parse_args()
    if args.cmd == "begin":
        begin_stage(args.workdir, args.stage, args.inputs)
        print(f"[manifest] begin stage={args.stage} inputs={len(args.inputs)}")
    elif args.cmd == "end":
        end_stage(args.workdir, args.stage, args.outputs)
        print(f"[manifest] end   stage={args.stage} outputs={len(args.outputs)}")
    elif args.cmd == "should-skip":
        skip = should_skip(args.workdir, args.stage, args.inputs)
        print(f"[manifest] stage={args.stage}: {'SKIP（输入未变且产物齐全）' if skip else 'RUN（需执行）'}")
        sys.exit(0 if skip else 1)
    elif args.cmd == "status":
        print(json.dumps(load(args.workdir), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
