#!/usr/bin/env python3
"""replay.py — 复跑证明。

在临时目录中强制重跑 render_all（不登记 manifest），将重渲染产物与
/app/output 已交付产物逐字节比对，输出 out/replay-report.json：
每个产物是否 bytes_equal、两侧 sha256。全部一致则退出码 0，否则 1。

replay-report.json 本身只含确定性内容（无时间戳），且在比对之后写入，
不参与比对。仅标准库，无网络。
"""
import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_all  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="复跑证明：重渲染并逐字节比对已交付产物")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--outdir", default="/app/output")
    args = ap.parse_args()
    outdir = Path(args.outdir)

    files = {}
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        render_all.run(args.workdir, tmp, force=True, register=False)
        for name in render_all.ARTIFACTS:
            delivered = outdir / name
            replayed = Path(tmp) / name
            if not delivered.exists():
                files[name] = {"bytes_equal": False, "status": "missing_in_output"}
                ok = False
                continue
            b1 = delivered.read_bytes()
            b2 = replayed.read_bytes()
            equal = b1 == b2
            files[name] = {
                "bytes_equal": equal,
                "sha256_delivered": hashlib.sha256(b1).hexdigest(),
                "sha256_replayed": hashlib.sha256(b2).hexdigest(),
            }
            if not equal:
                ok = False
    report = {
        "replay": "render_all",
        "all_reproducible": ok,
        "files": files,
    }
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "replay-report.json").write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    for name, info in files.items():
        mark = "OK " if info.get("bytes_equal") else "DIFF"
        print(f"[replay] {mark} {name}")
    print(
        f"[replay] replay-report.json 已写入 {outdir}；"
        + ("全部产物可字节级复现。" if ok else "存在不可复现产物！")
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
