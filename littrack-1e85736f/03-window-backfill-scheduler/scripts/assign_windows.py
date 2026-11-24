#!/usr/bin/env python3
"""assign_windows.py — 条目窗口归属判定。

归属规则（写死，见 references/window-semantics.md）：
- 入库（indexed）时间决定**增量归属**（是不是本轮新到）；
- 发表（published）时间决定**内容窗口**；
- 边界一律左闭右开 [start, end)：published 恰好等于窗口 start -> 归该窗口；
  恰好等于 end -> 归下一窗口（本窗不收，进 deferred_items）。

分类结果 classification ∈
  current_addition   内容窗口 == 当前窗口
  backfill           内容窗口为已关闭窗口（延迟入库，交 backfill.py 生成事件）
  deferred           内容窗口为未来窗口（含恰好等于右端点者）
  low_precision      日期区间跨越多个窗口 / 超出链覆盖范围，无法唯一定窗，
                     且 indexed 在当前窗口 -> 计入本轮新增但单独标记
  undated            缺少可用 published 日期，诚实进入 undated 清单

用法：
  python3 assign_windows.py --case-dir <dir> --work-dir <dir> --out assigned_items.json
（work-dir 中需已有 window_plan.json 与 normalized_items.json）
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from window_common import dump_json, find_window, load_json, parse_instant  # noqa: E402


def window_span(chain, norm):
    """返回 (earliest 所在窗口, latest 所在窗口)。norm 为归一化日期 dict。"""
    e = parse_instant(norm["earliest"])
    l = parse_instant(norm["latest"])
    return find_window(chain, e), find_window(chain, l)


def classify_item(item, chain, current_ids):
    pub = item.get("published")
    idx = item.get("indexed")
    flags = []
    if pub is None:
        reason = "no_published_date"
        if item.get("unparseable_published"):
            reason = "unparseable_published_date"
        return {"classification": "undated", "reason": reason, "flags": flags}

    w_e, w_l = window_span(chain, pub)
    pe = parse_instant(pub["earliest"])
    idx_inst = parse_instant(idx["earliest"]) if idx else None
    arrival_w = find_window(chain, idx_inst) if idx_inst else None
    arrival_in_current = bool(arrival_w and arrival_w["id"] in current_ids)
    if idx is None:
        flags.append("no_indexed_date_assumed_current_round")

    if w_e is not None and w_l is not None and w_e["id"] == w_l["id"]:
        content = w_e
        if content["id"] in current_ids:
            cls = "current_addition"
            if pe == parse_instant(content["start"]):
                flags.append("boundary_left")  # 恰好等于 start -> 归本窗口
        elif content["status"] == "closed":
            cls = "backfill"
        else:  # future_reference
            cls = "deferred"
            # 恰好等于当前窗口右端点（== 未来窗口起点）的显式标记
            for cid in current_ids:
                cw = next((w for w in chain if w["id"] == cid), None)
                if cw and pe == parse_instant(cw["end"]):
                    flags.append("boundary_right")  # 恰好等于 end -> 归下一窗口
        return {
            "classification": cls,
            "content_window": content["id"],
            "arrival_window": arrival_w["id"] if arrival_w else None,
            "arrival_in_current_window": arrival_in_current,
            "flags": flags,
        }

    # 区间跨越多个窗口或超出链覆盖范围：低精度，无法唯一定窗
    spanned = sorted({w["id"] for w in (w_e, w_l) if w is not None})
    flags.append("low_precision_date")
    return {
        "classification": "low_precision",
        "content_window": "indeterminate",
        "spanned_windows": spanned,
        "arrival_window": arrival_w["id"] if arrival_w else None,
        "arrival_in_current_window": arrival_in_current,
        "note": "published 精度为 %s，UTC 区间 [%s, %s] 跨越多个窗口或超出窗口链覆盖，"
                "无法唯一定窗；因 indexed 落在本轮而计入新增并单独标记"
                % (pub["precision"], pub["earliest"], pub["latest"]),
        "flags": flags,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="条目窗口归属判定（左闭右开）")
    ap.add_argument("--case-dir", required=True)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    plan = load_json(os.path.join(args.work_dir, "window_plan.json"))
    normalized = load_json(os.path.join(args.work_dir, "normalized_items.json"))
    chain = plan["chain"]
    current_ids = plan.get("current_window_ids") or [
        w["id"] for w in chain if w["status"] == "current"]

    assigned = []
    counts = {}
    for item in normalized["items"]:
        rec = classify_item(item, chain, current_ids)
        rec.update({
            "doi": item.get("doi"),
            "title": item.get("title"),
            "source": item.get("source"),
            "item_locator": item.get("item_locator"),
            "published": item.get("published"),
            "indexed": item.get("indexed"),
            "unparseable_published": item.get("unparseable_published"),
        })
        assigned.append(rec)
        counts[rec["classification"]] = counts.get(rec["classification"], 0) + 1
    out = {
        "current_window_ids": current_ids,
        "counts": counts,
        "items": assigned,
    }
    dump_json(out, args.out)
    print("assigned -> %s | %s" % (args.out, counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
