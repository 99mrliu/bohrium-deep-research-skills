#!/usr/bin/env python3
"""window_planner.py — 从 previous_snapshot 无缝接续生成 UTC 固定边界窗口链。

规则：
- 新窗口起点 = 快照最后一个窗口的 end（prev.end == next.start，绝不重叠、不留缝）；
- 窗口长度与时区取自 case.json 的 window_config（默认 7 天，仅支持 UTC）；
- 额外生成 1 个 future 参考窗口，仅供"恰好落在右端点 / 未来日期"条目的归属判定，
  不属于本轮已开窗。

用法：
  python3 window_planner.py --case-dir <dir> [--case-file case.json]
      [--snapshot-file previous_snapshot.json] --out window_plan.json
"""
import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from window_common import UTC, dump_json, iso_z, load_json, parse_instant  # noqa: E402


def window_id(start_dt):
    return "W" + start_dt.strftime("%Y-%m-%d")


def build_plan(case, snapshot):
    cfg = case.get("window_config", {}) or {}
    length_days = int(cfg.get("window_length_days", 7))
    tz = str(cfg.get("timezone", "UTC"))
    n_new = int(cfg.get("new_windows", 1))
    if tz != "UTC":
        raise ValueError("仅支持 UTC 固定边界窗口；window_config.timezone=%r" % tz)
    prev_windows = list(snapshot.get("windows", []) or [])
    if not prev_windows:
        raise ValueError("previous_snapshot.windows 为空，无法确定接续起点")
    prev_windows.sort(key=lambda w: w.get("start", ""))
    last_end = parse_instant(prev_windows[-1].get("end"))
    if last_end is None:
        raise ValueError("previous_snapshot 最后一个窗口缺少可解析的 end")

    chain = []
    for w in prev_windows:
        chain.append({
            "id": w.get("id") or window_id(parse_instant(w["start"])),
            "start": w.get("start"),
            "end": w.get("end"),
            "status": "closed",
            "origin": "previous_snapshot",
        })
    start = last_end
    for i in range(n_new + 1):  # n_new 个本轮窗口 + 1 个 future 参考窗口
        end = start + dt.timedelta(days=length_days)
        chain.append({
            "id": window_id(start),
            "start": iso_z(start),
            "end": iso_z(end),
            "status": "current" if i < n_new else "future_reference",
            "origin": "planned",
        })
        start = end
    current_ids = [w["id"] for w in chain if w["status"] == "current"]
    return {
        "window_length_days": length_days,
        "timezone": "UTC",
        "boundary_rule": "[start, end) 左闭右开：恰好等于 start 归本窗口，恰好等于 end 归下一窗口",
        "chain": chain,
        "current_window_ids": current_ids,
        "continuity_note": "新窗口起点取自 previous_snapshot 最后窗口的 end，接缝证明见 seam_proof.py 产物",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成无缝接续的 UTC 窗口链")
    ap.add_argument("--case-dir", required=True, help="案例目录（含 case.json 与快照）")
    ap.add_argument("--case-file", default="case.json")
    ap.add_argument("--snapshot-file", default=None,
                    help="缺省用 case.json 的 previous_snapshot 字段，否则 previous_snapshot.json")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    case_path = os.path.join(args.case_dir, args.case_file)
    case = load_json(case_path)
    snap_rel = args.snapshot_file or case.get("previous_snapshot") or "previous_snapshot.json"
    snap_path = snap_rel if os.path.isabs(snap_rel) else os.path.join(args.case_dir, snap_rel)
    snapshot = load_json(snap_path)

    plan = build_plan(case, snapshot)
    plan["inputs"] = {"case": case_path, "previous_snapshot": snap_path}
    dump_json(plan, args.out)
    print("window_plan -> %s | current=%s" % (args.out, ",".join(plan["current_window_ids"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
