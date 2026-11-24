#!/usr/bin/env python3
"""apply_fixes.py — 对台账中 open 条目执行机器可修的自动修复。

机器可修：
  R1 删除含无出处数值的 bullet / claim（宁删不假），剩余文本若无出处数值一并清除；
  R2 从 figures[] 删除悬空引用，正文中 "Figure N"/"Table N" 提及降级为 "the cited figure"。
其余规则（R3/R4/R5/R6/R7/R8）写入 fixes_report.needs_agent，交给 Agent 人工处理。
每处自动修复回写台账（status -> fixed，history 追加 auto-fix 记录）。

用法：apply_fixes.py deck.json --ledger tribunal.json --out deck_fixed.json --report fixes_report.json
退出码：0 成功；2 输入错误。
"""
import argparse
import json
import re
import sys

MACHINE_FIXABLE = ("R1", "R2")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def find_slide(deck, n):
    for s in deck.get("slides", []):
        if s.get("slide") == n:
            return s
    return None


def fix_r1(deck, entry):
    token = entry["evidence"].get("token")
    slide = find_slide(deck, entry["slide"])
    if slide is None or not token:
        return None
    removed = []
    bullets = slide.get("bullets", [])
    keep = [b for b in bullets if token not in b]
    removed.extend(b for b in bullets if token in b)
    slide["bullets"] = keep
    claims = slide.get("claims", [])
    keep_c = [c for c in claims if token not in c.get("text", "")]
    removed.extend(c.get("text", "") for c in claims if token in c.get("text", ""))
    slide["claims"] = keep_c
    if token in slide.get("title", ""):
        slide["title"] = slide["title"].replace(token, "[needs-quote]")
        removed.append(slide["title"])
    return f"删除含无出处数值 {token} 的 {len(removed)} 处文本" if removed else None


def fix_r2(deck, entry):
    ref = entry["evidence"].get("ref")
    slide = find_slide(deck, entry["slide"])
    if slide is None or not ref:
        return None
    actions = []
    if ref in (slide.get("figures") or []):
        slide["figures"] = [f for f in slide["figures"] if f != ref]
        actions.append(f"figures[] 移除 {ref}")
    new_bullets = []
    for b in slide.get("bullets", []):
        if ref in b:
            new_bullets.append(b.replace(ref, "the cited figure"))
            actions.append(f"bullet 中 {ref} 降级为文字描述")
        else:
            new_bullets.append(b)
    slide["bullets"] = new_bullets
    if slide.get("table") and slide["table"].get("ref") == ref:
        slide["table"] = None
        actions.append(f"table 引用 {ref} 置空")
    return "; ".join(actions) if actions else None


def main(argv=None):
    ap = argparse.ArgumentParser(description="机器可修条目自动修复并回写台账")
    ap.add_argument("deck", help="deck.json 路径")
    ap.add_argument("--ledger", required=True, help="tribunal.json 路径（就地更新）")
    ap.add_argument("--out", required=True, help="修复后的 deck 输出路径")
    ap.add_argument("--report", required=True, help="fixes_report.json 输出路径")
    args = ap.parse_args(argv)

    try:
        deck = load_json(args.deck)
        ledger = load_json(args.ledger)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: 无法读取输入: {e}", file=sys.stderr)
        return 2

    fixed, needs_agent = [], []
    for entry in ledger.get("entries", {}).values():
        if entry.get("status") != "open":
            continue
        detail = None
        if entry["rule"] == "R1":
            detail = fix_r1(deck, entry)
        elif entry["rule"] == "R2":
            detail = fix_r2(deck, entry)
        if detail:
            entry["status"] = "fixed"
            entry["history"].append({
                "seq": len(entry["history"]) + 1,
                "action": "auto-fix",
                "actor": "apply_fixes",
                "note": detail,
            })
            fixed.append({"id": entry["id"], "rule": entry["rule"],
                          "slide": entry["slide"], "action": detail})
        elif entry["rule"] not in MACHINE_FIXABLE:
            needs_agent.append({"id": entry["id"], "rule": entry["rule"],
                                "slide": entry["slide"],
                                "suggested_fix": entry["suggested_fix"]})

    ledger["summary"] = {
        "total": len(ledger["entries"]),
        "open": sum(1 for e in ledger["entries"].values() if e["status"] == "open"),
        "fixed": sum(1 for e in ledger["entries"].values() if e["status"] == "fixed"),
        "dispositioned": sum(1 for e in ledger["entries"].values() if e["status"] == "dispositioned"),
        "open_errors": sum(1 for e in ledger["entries"].values()
                           if e["status"] == "open" and e["severity"] == "error"),
    }
    save_json(ledger, args.ledger)
    save_json(deck, args.out)
    report = {
        "deck_in": args.deck,
        "deck_out": args.out,
        "fixed": fixed,
        "needs_agent": needs_agent,
    }
    save_json(report, args.report)
    print(f"auto-fixed={len(fixed)} needs_agent={len(needs_agent)} -> {args.out}, {args.report}")
    for f_ in fixed:
        print(f"  [fixed] {f_['id']}: {f_['action']}")
    for na in needs_agent:
        print(f"  [agent] {na['id']} ({na['rule']}) slide={na['slide']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
