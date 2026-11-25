#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""checkpoint.py — 检查点写入 / 恢复（sha256 链式完整性）。

检查点文件 <workdir>/checkpoint.json，结构见 references/checkpoint_format.md：
  - result_draft 与其 sha256；
  - completed / pending 任务 id 列表；
  - ledger_head：写入时账本链头哈希；
  - prev_chain：上一检查点的 state_hash（无则为创世 64×"0"）；
  - state_hash：对上述全部字段的规范 JSON 之 sha256。

restore 会重算并比对：任何不一致 → 退出码 1，绝不静默地从被篡改状态恢复。
退出码：0 正常；1 违反（完整性校验失败）；2 用法错误。
仅使用 Python 标准库。
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

GENESIS = "0" * 64
CK_NAME = "checkpoint.json"


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def ledger_head(path):
    if not path or not os.path.exists(path):
        return GENESIS
    last = None
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if raw:
                last = json.loads(raw)
    return last["line_hash"] if last else GENESIS


def cmd_write(args):
    try:
        result_draft = load_json(args.result)
        completed = [str(x) for x in load_json(args.completed)]
        pending = [str(x) for x in load_json(args.pending)]
    except (ValueError, OSError) as exc:
        print("错误：输入文件不可读或不是合法 JSON：%s" % exc, file=sys.stderr)
        return 2

    ck_path = os.path.join(args.workdir, CK_NAME)
    prev_chain = GENESIS
    if os.path.exists(ck_path):
        try:
            old = load_json(ck_path)
            prev_chain = old.get("state_hash", GENESIS)
        except ValueError:
            print("违反：既有检查点不是合法 JSON，疑似损坏；拒绝覆盖，"
                  "请先审计 %s" % ck_path, file=sys.stderr)
            return 1

    body = {
        "version": 1,
        "kind": "checkpoint",
        "created_at": now_iso(),
        "completed": completed,
        "pending": pending,
        "result_draft": result_draft,
        "result_draft_sha256": sha(canon(result_draft)),
        "ledger_head": ledger_head(args.ledger),
        "prev_chain": prev_chain,
    }
    rec = dict(body)
    rec["state_hash"] = sha(canon(body))
    os.makedirs(args.workdir, exist_ok=True)
    with open(ck_path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps({"checkpoint": ck_path, "state_hash": rec["state_hash"],
                      "completed": len(completed), "pending": len(pending)},
                     ensure_ascii=False))
    return 0


def cmd_restore(args):
    ck_path = os.path.join(args.workdir, CK_NAME)
    if not os.path.exists(ck_path):
        print("违反：检查点不存在：%s" % ck_path, file=sys.stderr)
        return 1
    try:
        rec = load_json(ck_path)
    except ValueError as exc:
        print("违反：检查点不是合法 JSON：%s" % exc, file=sys.stderr)
        return 1

    required = ("version", "kind", "created_at", "completed", "pending",
                "result_draft", "result_draft_sha256", "ledger_head",
                "prev_chain", "state_hash")
    for key in required:
        if key not in rec:
            print("违反：检查点缺少字段 %s" % key, file=sys.stderr)
            return 1
    if rec["kind"] != "checkpoint":
        print("违反：kind 字段不是 checkpoint", file=sys.stderr)
        return 1

    # 1) result_draft 自身哈希。
    if sha(canon(rec["result_draft"])) != rec["result_draft_sha256"]:
        print("违反：result_draft 与其 sha256 不符（疑似篡改）", file=sys.stderr)
        return 1
    # 2) 整体 state_hash。
    body = {k: rec[k] for k in required if k != "state_hash"}
    if sha(canon(body)) != rec["state_hash"]:
        print("违反：state_hash 与载荷不符（疑似篡改）", file=sys.stderr)
        return 1
    # 3) 与账本链头对齐（若提供账本）。
    if args.ledger:
        head = ledger_head(args.ledger)
        if head != rec["ledger_head"]:
            print("违反：检查点记录的账本链头与当前账本不符"
                  "（账本或检查点被改动）", file=sys.stderr)
            return 1

    restored = {
        "completed": rec["completed"],
        "pending": rec["pending"],
        "result_draft": rec["result_draft"],
        "restored_from": ck_path,
        "state_hash": rec["state_hash"],
    }
    out = args.out or os.path.join(args.workdir, "restored_state.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(restored, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps({"restored": out, "completed": len(rec["completed"]),
                      "pending": len(rec["pending"])}, ensure_ascii=False))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="检查点写入/恢复（sha256 链）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_w = sub.add_parser("write", help="写入检查点")
    p_w.add_argument("--workdir", required=True)
    p_w.add_argument("--result", required=True, help="result.json 草稿路径")
    p_w.add_argument("--completed", required=True, help="已完成 id JSON 数组文件")
    p_w.add_argument("--pending", required=True, help="待办 id JSON 数组文件")
    p_w.add_argument("--ledger", help="ledger.jsonl（记录链头哈希）")

    p_r = sub.add_parser("restore", help="校验并恢复检查点")
    p_r.add_argument("--workdir", required=True)
    p_r.add_argument("--ledger", help="ledger.jsonl（校验链头一致性）")
    p_r.add_argument("--out", help="恢复状态输出路径")

    args = ap.parse_args(argv)
    if args.cmd == "write":
        return cmd_write(args)
    if args.cmd == "restore":
        return cmd_restore(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
