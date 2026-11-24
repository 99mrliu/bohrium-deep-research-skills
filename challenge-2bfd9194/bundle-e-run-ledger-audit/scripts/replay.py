#!/usr/bin/env python3
"""replay.py — 仅凭 journal 在空目录复放全部 begin→done 复制（stdlib only，独立脚本）。

"他人可按记录复跑" 的直接证明：不读 plan、不读 manifest，只读 journal 与 /input，
把每条 done 对应的 src 复制到 replay 目录的 dst 相对路径（跳过 failed/reconciled），
再把复放产物与原 library/ 逐文件比哈希，写 REPLAY_DIFF.json（应为空；非空如实记录）。

用法：
  python3 replay.py --journal operations_journal.jsonl --input /input \
      --out /app/work/replay --library /app/output/library \
      --diff-out /app/output/REPLAY_DIFF.json
退出码：diff 为空 = 0，非空 = 1，自身无法运行 = 2。
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import unicodedata
from datetime import datetime, timezone

CHUNK = 65536


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def nfc(s):
    return unicodedata.normalize("NFC", s)


def tree_hashes(base):
    out = {}
    if not os.path.isdir(base):
        return out
    for root, dirs, files in os.walk(base):
        dirs.sort()
        for name in sorted(files):
            ap = os.path.join(root, name)
            rel = nfc(os.path.relpath(ap, base))
            try:
                out[rel] = sha256_file(ap)
            except OSError:
                out[rel] = None
    return out


def safe_join(base, rel):
    """拒绝绝对路径与 .. 越界。"""
    rel = rel.replace("\\", "/").lstrip("/")
    parts = [p for p in rel.split("/") if p not in ("", ".", "..")]
    return os.path.join(base, *parts)


def main(argv=None):
    ap = argparse.ArgumentParser(description="按 journal 复放复制操作并对比 library")
    ap.add_argument("--journal", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True, help="复放产物目录（放 work/，不进 output）")
    ap.add_argument("--library", required=True, help="原 library/ 目录")
    ap.add_argument("--diff-out", required=True, help="REPLAY_DIFF.json 输出路径")
    a = ap.parse_args(argv)
    input_dir = os.path.abspath(a.input)

    recs, bad = [], []
    with open(a.journal, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                bad.append(i)

    skipped = {"failed": 0, "reconciled": 0, "corrupt_lines": bad}
    replayed, missing_src, errors = 0, [], []
    # 只复放 done（每个 id 取最后一条 done；failed/reconciled 一律跳过）
    dones = [r for r in recs if r.get("op") == "done" and r.get("src") and r.get("dst")]
    skipped["failed"] = sum(1 for r in recs if r.get("op") == "failed")
    skipped["reconciled"] = sum(1 for r in recs if r.get("op") == "reconciled")
    for r in sorted(dones, key=lambda x: x.get("seq", 0)):
        src = safe_join(input_dir, r["src"])
        dst_rel = r["dst"]  # 形如 library/papers/x.txt
        dst = safe_join(a.out, dst_rel)
        if not os.path.exists(src):
            missing_src.append({"id": r.get("id"), "src": r["src"]})
            continue
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            replayed += 1
        except OSError as e:
            errors.append({"id": r.get("id"), "src": r["src"], "error": str(e)})

    replay_lib = tree_hashes(os.path.join(a.out, "library"))
    orig_lib = tree_hashes(a.library)
    missing_in_replay = sorted(p for p in orig_lib if p not in replay_lib)
    extra_in_replay = sorted(p for p in replay_lib if p not in orig_lib)
    hash_mismatch = sorted(p for p in orig_lib
                           if p in replay_lib and orig_lib[p] != replay_lib[p])
    equal = not missing_in_replay and not extra_in_replay and not hash_mismatch \
        and not missing_src and not errors

    diff = {"replay": "journal-only replay vs library",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "journal": os.path.abspath(a.journal),
            "equal": equal,
            "replayed_done_ops": replayed,
            "skipped_records": skipped,
            "library_files": len(orig_lib), "replay_files": len(replay_lib),
            "missing_in_replay": missing_in_replay,
            "extra_in_replay": extra_in_replay,
            "hash_mismatch": hash_mismatch,
            "missing_source_in_input": missing_src,
            "errors": errors,
            "note": "equal=true 表示第三方仅凭 journal 与 /input 即可逐字节复现 library/"}
    os.makedirs(os.path.dirname(os.path.abspath(a.diff_out)), exist_ok=True)
    tmp = a.diff_out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(diff, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, a.diff_out)
    print(json.dumps({"equal": equal, "replayed": replayed,
                      "missing_in_replay": len(missing_in_replay),
                      "extra_in_replay": len(extra_in_replay),
                      "hash_mismatch": len(hash_mismatch)}, ensure_ascii=False))
    return 0 if equal else 1


if __name__ == "__main__":
    sys.exit(main())
