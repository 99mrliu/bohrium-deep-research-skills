#!/usr/bin/env python3
"""rejudge_plan.py — 标准升版后的回溯重判计划（步骤 8 可选，脚本环节）。

对比两个版本 criteria_table（--old --new），列出新增/删除/变更的 criterion_id，
并从 judgments.jsonl 找出触及被改/被删标准的 record_id（强制重判对象），
输出 rejudge_plan.json。杜绝标准漂移：改了标准必须重判受影响记录。

退出码：0=通过；2=输入不足；3=校验失败。幂等。
"""
import argparse
import json
import sys
from pathlib import Path

COMPARE_FIELDS = ["type", "statement", "predicate", "evidence_required",
                  "reason_code", "boundary_notes"]


def load(path, what):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[rejudge_plan] {what} 读取失败({path}): {e}", file=sys.stderr)
        sys.exit(2)


def index_criteria(table):
    return {c.get("criterion_id"): c for c in (table.get("criteria") or [])
            if c.get("criterion_id")}


def main(argv=None):
    ap = argparse.ArgumentParser(description="对比两版 criteria_table，生成重判计划")
    ap.add_argument("--old", required=True, help="旧版 criteria_table.json")
    ap.add_argument("--new", required=True, help="新版 criteria_table.json")
    ap.add_argument("--judgments", default="/app/work/judgments.jsonl",
                    help="已有判定（默认 /app/work/judgments.jsonl）")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    args = ap.parse_args(argv)

    old = index_criteria(load(args.old, "旧版 criteria_table"))
    new = index_criteria(load(args.new, "新版 criteria_table"))
    old_table = load(args.old, "旧版 criteria_table")
    new_table = load(args.new, "新版 criteria_table")

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = []
    for cid in sorted(set(old) & set(new)):
        diffs = {f: {"old": old[cid].get(f), "new": new[cid].get(f)}
                 for f in COMPARE_FIELDS if old[cid].get(f) != new[cid].get(f)}
        if diffs:
            changed.append({"criterion_id": cid, "field_diffs": diffs})

    touch_ids = {c["criterion_id"] for c in changed} | set(removed)
    affected = set()
    jpath = Path(args.judgments)
    if jpath.exists():
        for line in jpath.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                j = json.loads(line)
            except json.JSONDecodeError:
                continue
            if j.get("criterion_id") in touch_ids and j.get("record_id"):
                affected.add(j["record_id"])
    else:
        print(f"[rejudge_plan] 警告：{jpath} 不存在，受影响记录为空。", file=sys.stderr)

    plan = {
        "old_version": old_table.get("version"),
        "new_version": new_table.get("version"),
        "added_criteria": added,
        "removed_criteria": removed,
        "changed_criteria": changed,
        "affected_record_ids": sorted(affected),
        "required_action": (
            "对 affected_record_ids 中记录，按新版标准重新判定被改/被删标准，"
            "更新 judgments.jsonl 后重跑 screen_engine.py；added_criteria 需对全部"
            "在筛记录补判定。"),
        "generated_by": "rejudge_plan.py",
        "stage": "rejudge_planning",
    }
    out = Path(args.work) / "rejudge_plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[rejudge_plan] added={len(added)} removed={len(removed)} "
          f"changed={len(changed)} affected_records={len(affected)} -> {out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"[rejudge_plan] 未预期错误（诚实降级）: {e}", file=sys.stderr)
        sys.exit(2)
