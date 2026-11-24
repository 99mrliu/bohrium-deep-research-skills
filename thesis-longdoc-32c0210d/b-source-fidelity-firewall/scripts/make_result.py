#!/usr/bin/env python3
"""make_result.py — 运行时读取 case.json 的 output_contract.fields 并逐字段
填充，原子写 result.json。

字段填充规则（按字段名子串匹配，不硬编码字段集合）：
  含 edited / chapter      → 改后章节文件清单（相对 --edited-chapters）
  含 change                → 变更记录（--changes JSON 内容）
  含 evidence / grounding  → evidence_map.json 路径 + 摘要统计
  含 consistency / guard   → guard_report 摘要
  含 uncertainty           → 未决事实清单
  含 source                → 来源清单
  其他                     → null，并记入 problems

status 自动判定：有任何 problems / guard FAIL / 未决事实 → "partial"，
否则 "complete"（--status 可强制）。

用法：
  python3 make_result.py --case case.json --evidence evidence_map.json \
      --guard guard_report.json --edited-chapters <目录> \
      [--changes changes.json] [--out result.json] [--note "..."] \
      [--status complete|partial]
"""
import argparse
import json
import os
import re
import sys


def load_json(path, default=None):
    if not path or not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def list_files(root):
    out = []
    if not root or not os.path.isdir(root):
        return out
    for r, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            out.append(os.path.relpath(os.path.join(r, name), root))
    return sorted(out)


def find_pending_confirmations(edited_root):
    """扫描改后章节中的 【待确认：…】 标注。"""
    hits = []
    if not edited_root or not os.path.isdir(edited_root):
        return hits
    for r, dirs, files in os.walk(edited_root):
        dirs.sort()
        for name in sorted(files):
            if not name.lower().endswith(".md"):
                continue
            path = os.path.join(r, name)
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, start=1):
                    for m in re.finditer(r"【待确认[：:](.*?)】", line):
                        hits.append({
                            "file": os.path.relpath(path, edited_root),
                            "line": i,
                            "note": m.group(1).strip(),
                        })
    return hits


def main():
    ap = argparse.ArgumentParser(description="按 output_contract 装配 result.json")
    ap.add_argument("--case", required=True)
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--guard", default=None)
    ap.add_argument("--edited-chapters", default=None)
    ap.add_argument("--changes", default=None, help="变更记录 JSON（可选）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--note", default=None)
    ap.add_argument("--status", default=None, choices=["complete", "partial"])
    args = ap.parse_args()

    case = load_json(args.case, {})
    evidence = load_json(args.evidence, None)
    guard = load_json(args.guard, None)
    changes = load_json(args.changes, None)

    problems = []
    fields = (case.get("output_contract") or {}).get("fields") or []
    if not fields:
        problems.append("case.json 缺少 output_contract.fields")

    ev_stats = (evidence or {}).get("stats") or {}
    unresolved = [e for e in (evidence or {}).get("entries", [])
                  if e.get("verification") == "FAIL"
                  or e.get("origin") == "unresolved"]
    pending = find_pending_confirmations(args.edited_chapters)
    uncertainty = []
    for e in unresolved:
        uncertainty.append({
            "fact_id": e.get("fact_id"),
            "claim": e.get("claim"),
            "reason": "无法在材料或原始工作稿中回源定位，需人工确认",
        })
    for p in pending:
        uncertainty.append({
            "fact_id": None,
            "claim": "%s:%s" % (p["file"], p["line"]),
            "reason": "人工确认标注【待确认：%s】" % p["note"],
        })

    sources = []
    if evidence and evidence.get("materials_dir"):
        sources.append({"kind": "materials", "path": evidence["materials_dir"]})
    if evidence and evidence.get("chapters_dir"):
        sources.append({"kind": "working_chapters",
                        "path": evidence["chapters_dir"]})
    for w in (evidence or {}).get("warnings", []):
        problems.append(w)

    edited_files = list_files(args.edited_chapters)
    guard_summary = None
    if guard:
        guard_summary = {
            "status": guard.get("status"),
            "flags": (guard.get("summary") or {}).get("flags"),
            "tokens_checked": (guard.get("summary") or {}).get("tokens_checked"),
        }
        if guard.get("status") != "PASS":
            problems.append("guard_report 状态为 %s，存在未解决的事实保真 flag"
                            % guard.get("status"))
    else:
        problems.append("缺少 guard_report（未执行编辑后把关）")

    change_records = changes if changes is not None else []

    def fill(name):
        low = name.lower()
        if "edited" in low or "chapter" in low:
            return edited_files
        if "change" in low:
            return change_records
        if "evidence" in low or "grounding" in low:
            return {"path": args.evidence, "stats": ev_stats,
                    "unresolved_count": len(unresolved)}
        if "consistency" in low or "guard" in low:
            return guard_summary
        if "uncertainty" in low:
            return uncertainty
        if "source" in low:
            return sources
        problems.append("未知 contract 字段 %r：无映射规则，填 null" % name)
        return None

    result = {
        "schema": "result/v1",
        "skill": "source-fidelity-firewall",
        "case_id": case.get("case_id"),
        "status": None,
        "sources": sources,
        "uncertainty": uncertainty,
        "change_records": change_records,
        "problems": problems,
    }
    if args.note:
        result["note"] = args.note
    for name in fields:
        result[name] = fill(name)

    status = args.status
    if status is None:
        status = "partial" if (problems or uncertainty) else "complete"
    result["status"] = status

    # 原子写
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, args.out)
    print("make_result: case_id=%s status=%s fields=%d problems=%d -> %s"
          % (result["case_id"], status, len(fields), len(problems), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
