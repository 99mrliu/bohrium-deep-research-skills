#!/usr/bin/env python3
"""delivery_dedup.py — 幂等投递（离线，仅标准库）。

delivery_log.jsonl 是 append-only 的投递账本。每条记录携带投递键：
    delivery_key = case_id + "|" + window + "|" + item_key
其中 item_key 取题录的稳定标识（优先 DOI，其次源内 id）。
同一 key 重复投递一律抑制，保证「重跑零二次推送」。

典型崩溃场景：引擎在「已投递、尚未写 checkpoint」之间崩溃，重跑会
重新处理该源并再次尝试投递 —— 去重层在这里兜底，抑制重复投递。

CLI:
  python3 delivery_dedup.py count <delivery_log.jsonl>
  python3 delivery_dedup.py check <delivery_log.jsonl> <case_id> <window> <item_key>
"""
import json
import os
import sys
import time


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def delivery_key(case_id, window, item_key):
    return "%s|%s|%s" % (case_id, window, item_key)


def load_keys(path):
    """读出现有全部投递键。文件不存在返回空集。"""
    keys = set()
    if not os.path.exists(path):
        return keys
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                # 账本行损坏不阻断，跳过并继续（账本只增不改，可人工修复）
                continue
            k = rec.get("delivery_key")
            if k:
                keys.add(k)
    return keys


def append_if_new(path, record):
    """若 delivery_key 未出现过则追加并返回 True；否则抑制并返回 False。

    record 必须已含 delivery_key 字段。
    """
    key = record.get("delivery_key")
    if not key:
        raise ValueError("delivery record missing delivery_key")
    if key in load_keys(path):
        return False
    record.setdefault("delivered_at", utcnow())
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return True


def read_all(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main(argv):
    if len(argv) >= 3 and argv[1] == "count":
        print(len(read_all(argv[2])))
        return 0
    if len(argv) == 6 and argv[1] == "check":
        key = delivery_key(argv[3], argv[4], argv[5])
        print("exists" if key in load_keys(argv[2]) else "not_exists")
        return 0
    sys.stderr.write(
        "usage:\n"
        "  delivery_dedup.py count <log>\n"
        "  delivery_dedup.py check <log> <case_id> <window> <item_key>\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
