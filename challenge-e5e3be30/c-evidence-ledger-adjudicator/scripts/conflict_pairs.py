#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""conflict_pairs.py — 正反证据对撞检测与冲突记录生成。

扫描台账中 side=pro/strength=direct/polarity=same 与
side=con/strength=direct/polarity=opposite 且锚点覆盖重叠的证据对，
为每一对生成冲突记录（双方 quote + page/section 定位并列），
供 result.json 的 conflicts 字段逐字引用。

用法:
    python3 conflict_pairs.py PATH [PATH ...] [--out conflicts.json]

  PATH    台账 JSON 文件或目录（目录时扫描 ledger-*.json）
  --out   把冲突记录写到指定 JSON 文件（默认只打印到 stdout）

退出码: 0 成功（无冲突也是 0）; 1 台账 schema 错误; 2 IO/用法错误。
纯 Python3 标准库。
"""
import argparse
import glob
import json
import os
import sys


def iter_ledger_paths(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out.extend(sorted(glob.glob(os.path.join(p, "ledger-*.json"))))
        elif os.path.isfile(p):
            out.append(p)
        else:
            print("ERROR: 路径不存在: %s" % p, file=sys.stderr)
            sys.exit(2)
    if not out:
        print("ERROR: 未找到任何台账文件", file=sys.stderr)
        sys.exit(2)
    return out


def find_conflicts(ledger):
    evidence = [e for e in ledger.get("evidence", []) if isinstance(e, dict)]
    pro_direct = [e for e in evidence if e.get("side") == "pro"
                  and e.get("strength") == "direct"
                  and e.get("polarity") == "same"]
    con_direct = [e for e in evidence if e.get("side") == "con"
                  and e.get("strength") == "direct"
                  and e.get("polarity") == "opposite"]
    anchor_map = {a.get("id"): a for a in ledger.get("anchors", [])
                  if isinstance(a, dict)}
    records = []
    for ep in pro_direct:
        for ec in con_direct:
            shared = sorted(set(ep.get("covers") or [])
                            & set(ec.get("covers") or []))
            if not shared:
                continue
            records.append({
                "claim_id": ledger.get("claim_id"),
                "claim_text": ledger.get("claim_text"),
                "shared_anchors": [
                    {"anchor_id": aid,
                     "type": anchor_map.get(aid, {}).get("type"),
                     "text": anchor_map.get(aid, {}).get("text")}
                    for aid in shared],
                "pro": {"evidence_id": ep.get("evidence_id"),
                        "quote": ep.get("quote"),
                        "page": ep.get("page"),
                        "section": ep.get("section")},
                "con": {"evidence_id": ec.get("evidence_id"),
                        "quote": ec.get("quote"),
                        "page": ec.get("page"),
                        "section": ec.get("section")},
                "resolution_rule": "references/verdict-rules.md R7"
                                   "（双方 direct 对撞 → 判定降级一档；"
                                   "result.json 中必须并列双方原话与定位）",
            })
    return records


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="正反 direct 证据对撞检测：生成并列双方原话与定位的冲突记录。")
    ap.add_argument("paths", nargs="+", help="台账 JSON 文件或目录")
    ap.add_argument("--out", help="冲突记录输出 JSON 文件（默认仅打印）")
    args = ap.parse_args(argv)

    all_records = []
    for path in iter_ledger_paths(args.paths):
        try:
            with open(path, "r", encoding="utf-8") as f:
                ledger = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print("ERROR: 无法读取 %s: %s" % (path, e), file=sys.stderr)
            return 2
        if not isinstance(ledger.get("evidence"), list):
            print("ERROR: %s schema 错误（evidence 缺失）"
                  % os.path.basename(path), file=sys.stderr)
            return 1
        recs = find_conflicts(ledger)
        all_records.extend(recs)
        if recs:
            for r in recs:
                print("CONFLICT [%s] %s <-> %s 共享锚点 %s" % (
                    r["claim_id"], r["pro"]["evidence_id"],
                    r["con"]["evidence_id"],
                    [a["anchor_id"] for a in r["shared_anchors"]]))
                print("  pro (%s, p.%s): %s" % (
                    r["pro"]["section"], r["pro"]["page"],
                    (r["pro"]["quote"] or "")[:100]))
                print("  con (%s, p.%s): %s" % (
                    r["con"]["section"], r["con"]["page"],
                    (r["con"]["quote"] or "")[:100]))
        else:
            print("OK       [%s] 无 direct 对撞" % ledger.get("claim_id"))

    summary = {"conflicts": all_records, "count": len(all_records)}
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            print("已写入 %s（共 %d 条冲突记录）" % (args.out, len(all_records)))
        except OSError as e:
            print("ERROR: 写入 %s 失败: %s" % (args.out, e), file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
