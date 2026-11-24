#!/usr/bin/env python3
"""checkpoint.py — 断点续跑状态（离线，仅标准库）。

checkpoint.json 按「源 × 窗口」粒度记录完成/降级状态：
{
  "case_id": "...",
  "version": 1,
  "completed": {
    "crossref_a|2026-W47": {"done_at": "...", "run_no": 1,
                            "delivered": 2, "dedup_skipped": 0,
                            "records_skipped": [...], "note": "ok"}
  },
  "degraded": {
    "eupmc_b|2026-W47": {"failure_class": "parse_error", "run_no": 1,
                         "attempts": 3, "reason": "...", "at": "..."}
  }
}

语义：
- completed 中的键在重跑时直接跳过，不重复处理、不重复投递；
- degraded 中的键不算完成，下一轮运行会重新尝试（这就是"续跑只补未完成部分"）；
- 每处理完一个源立即落盘，崩溃窗口最小化。

CLI:
  python3 checkpoint.py show <checkpoint.json>
"""
import json
import os
import sys
import time

VERSION = 1


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def make_key(source_id, window):
    return "%s|%s" % (source_id, window)


def init(case_id):
    return {"case_id": case_id, "version": VERSION,
            "completed": {}, "degraded": {}}


def load(path, case_id=None):
    """加载 checkpoint；不存在时按 case_id 初始化一份新的。"""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            cp = json.load(f)
        if case_id and cp.get("case_id") != case_id:
            raise ValueError(
                "checkpoint case_id mismatch: file=%s case=%s — "
                " refusing to reuse a checkpoint from another case"
                % (cp.get("case_id"), case_id))
        return cp
    return init(case_id)


def save(path, cp):
    """原子写：先写临时文件再 rename，避免崩溃留下半截 checkpoint。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cp, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def mark_completed(cp, source_id, window, run_no, delivered, dedup_skipped,
                   records_skipped=None, note="ok"):
    cp["completed"][make_key(source_id, window)] = {
        "done_at": utcnow(),
        "run_no": run_no,
        "delivered": delivered,
        "dedup_skipped": dedup_skipped,
        "records_skipped": records_skipped or [],
        "note": note,
    }
    # 完成后清除旧的降级记录（若有）
    cp["degraded"].pop(make_key(source_id, window), None)


def mark_degraded(cp, source_id, window, failure_class, reason, attempts,
                  run_no):
    cp["degraded"][make_key(source_id, window)] = {
        "failure_class": failure_class,
        "reason": reason,
        "attempts": attempts,
        "run_no": run_no,
        "at": utcnow(),
    }


def is_completed(cp, source_id, window):
    return make_key(source_id, window) in cp["completed"]


def main(argv):
    if len(argv) == 3 and argv[1] == "show":
        with open(argv[2], "r", encoding="utf-8") as f:
            json.dump(json.load(f), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    sys.stderr.write("usage: checkpoint.py show <checkpoint.json>\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
