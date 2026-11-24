#!/usr/bin/env python3
"""replay_pack.py — 交接重走包：让第三方凭日志与哈希清单独立复核（确定性）。

从 journal.jsonl 生成 /app/output/replay/ 下的交接包：
  replay_steps.md   人读的重走步骤（按日志顺序还原：扫了什么、搜了什么、
                    每个决定的依据、核验结果），每步带哈希坐标；
  manifest.json     机器可读的清单：日志条目哈希链摘要 + /app/output 全部
                    交付物的 SHA-256 —— 评审重算哈希即可确认交付物未被调换。
退出码恒 0。
"""
import argparse
import hashlib
import json
import os
import sys
import time


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()
    replay_dir = os.path.join(a.out, "replay")
    os.makedirs(replay_dir, exist_ok=True)

    entries = []
    jp = os.path.join(a.work, "journal.jsonl")
    if os.path.exists(jp):
        with open(jp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))

    lines = ["# 重走步骤（由操作日志自动生成）", "",
             "复核方法：对照每步的文件哈希坐标重新计算，结果应一致；"
             "任何一步对不上即说明交付物或输入已被改动。", ""]
    for e in entries:
        files = "；".join("`%s`(sha256:%s)" % (f.get("path"), (f.get("sha256") or "?")[:12])
                          for f in e.get("files", []))
        detail = json.dumps(e.get("detail", {}), ensure_ascii=False)
        lines.append("%d. **%s** (%s) %s%s" % (
            e.get("seq"), e.get("op"), e.get("ts"),
            ("对象：" + files + " " if files else ""),
            ("依据：" + detail[:300] if detail not in ("{}", "") else "")))
    with open(os.path.join(replay_dir, "replay_steps.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    artifacts = []
    for root, dirs, names in os.walk(a.out):
        dirs.sort()
        for n in sorted(names):
            p = os.path.join(root, n)
            if os.path.isfile(p):
                artifacts.append({"path": os.path.relpath(p, a.out),
                                  "sha256": sha256_of(p)})
    manifest = {"schema": "kbqa-replay-ledger/manifest/v1",
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "journal_entries": len(entries),
                "journal_head": (hashlib.sha256(json.dumps(
                    entries[-1], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
                    if entries else None),
                "artifacts": artifacts}
    with open(os.path.join(replay_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(json.dumps({"steps": len(entries), "artifacts": len(artifacts)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
