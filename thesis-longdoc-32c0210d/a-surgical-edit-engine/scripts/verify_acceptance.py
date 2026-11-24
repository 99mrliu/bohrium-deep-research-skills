#!/usr/bin/env python3
"""verify_acceptance.py — 按 item.acceptance 自动生成可执行检查并逐项 PASS/FAIL。

检查来源（确定性生成）：
- term_unify        → 旧词在保护区外缺失断言 + 新词存在断言（保护区=参考文献节/文献条目行）
- float_ref_fix     → 旧编号不再作为正文引用出现 + 全局图表引用完整性
- replace           → 新文存在 + 旧文缺失
- delete            → 文本缺失
- format_normalize  → 数字-单位粘连扫描（number_unit_space）
- manual            → SKIP（不计 FAIL，但写入报告供 result.json 的 uncertainty）
- acceptance 文本中的 “不再出现“X”” → 追加缺失断言
- 全局附加检查：正文所有 图x-y/表x-y 引用必须存在于题注

任何 FAIL → 退出码 1；全部 PASS/SKIP → 0。仅使用 python3 标准库。
"""
import argparse
import json
import re
import sys
from pathlib import Path

QUOTE_RE = re.compile(r'[“"\'「『]([^”"\'」』]+)[”"\'」』]')
CAPTION_RE = re.compile(r'^\s*(?:\*\*)?\s*(图|表)\s*(\d+)\s*[-–—]\s*(\d+)')
REF_RE = re.compile(r'(图|表)\s*(\d+)\s*[-–—]\s*(\d+)')
HEADING_RE = re.compile(r'^#{1,6}\s+(.+?)\s*$')

UNITS = ["mAh", "min", "kPa", "MPa", "μm", "um", "nm", "mm", "cm", "kg", "mg",
         "μL", "mL", "mol", "ms", "g", "s", "h", "A", "V", "K", "L"]
UNIT_STUCK_RE = re.compile(r'\d(?:' + "|".join(UNITS) + r')(?![A-Za-z0-9])|\d(?:℃|°C)')


def load_chapters(chapters_dir):
    d = Path(chapters_dir)
    out = {}
    for p in sorted(d.glob("*.md")):
        if p.is_file():
            out[p.name] = p.read_text(encoding="utf-8").splitlines()
    if not out:
        sys.exit(f"[verify] 章节目录为空: {d}")
    return out


def protected_mask(lines, protect_sections, protect_patterns):
    pats = [re.compile(p) for p in protect_patterns]
    mask, in_prot = [], False
    for line in lines:
        h = HEADING_RE.match(line)
        if h:
            in_prot = any(s in h.group(1) for s in protect_sections)
        mask.append(in_prot or any(p.search(line) for p in pats))
    return mask


def find_unprotected(chapters, needle, protect_sections, protect_patterns):
    """返回 [(file, line_no, line)]：needle 在非保护区出现的全部位置。"""
    hits = []
    for fname, lines in chapters.items():
        mask = protected_mask(lines, protect_sections, protect_patterns)
        for i, (line, prot) in enumerate(zip(lines, mask)):
            if not prot and needle in line:
                hits.append((fname, i + 1, line.strip()))
    return hits


def float_integrity(chapters):
    """正文 图x-y/表x-y 引用必须存在于题注。返回 (ok, dangling, captions)。"""
    # 两遍扫描：先全量收集题注，再比对正文引用（允许前向引用）
    captions, dangling = set(), []
    for lines in chapters.values():
        for line in lines:
            cap = CAPTION_RE.match(line)
            if cap:
                captions.add((cap.group(1), f"{cap.group(2)}-{cap.group(3)}"))
    for fname, lines in chapters.items():
        for ln, line in enumerate(lines, 1):
            if CAPTION_RE.match(line):
                continue
            for m in REF_RE.finditer(line):
                key = (m.group(1), f"{m.group(2)}-{m.group(3)}")
                if key not in captions and key not in [(d["kind"], d["num"]) for d in dangling]:
                    dangling.append({"file": fname, "line": ln,
                                     "kind": key[0], "num": key[1]})
    return (not dangling), dangling, sorted(f"{k}{n}" for k, n in captions)


def check_absent(chapters, needle, prot_secs, prot_pats, desc):
    hits = find_unprotected(chapters, needle, prot_secs, prot_pats)
    detail = "未出现" if not hits else "; ".join(f"{f}:{ln}" for f, ln, _ in hits[:8])
    return {"desc": desc, "result": "PASS" if not hits else "FAIL", "detail": detail}


def check_present(chapters, needle, desc):
    hits = [(f, i + 1) for f, lines in chapters.items()
            for i, line in enumerate(lines) if needle in line]
    detail = "; ".join(f"{f}:{ln}" for f, ln in hits[:4]) if hits else "全文未出现"
    return {"desc": desc, "result": "PASS" if hits else "FAIL", "detail": detail}


def checks_for_op(op, chapters):
    t, p = op["type"], op.get("params", {})
    checks = []
    if t == "term_unify":
        ps, pp = p.get("protect_sections", []), p.get("protect_patterns", [])
        checks.append(check_absent(chapters, p["from"], ps, pp,
                                   f"保护区（{','.join(ps) or '无'}）外不再出现 “{p['from']}”"))
        checks.append(check_present(chapters, p["to"], f"出现统一后术语 “{p['to']}”"))
    elif t == "float_ref_fix":
        for fix in p.get("fixes", []):
            a, b = fix["old_num"].split("-")
            pat = re.compile(r'(?<![0-9-])' + re.escape(fix["kind"]) +
                             rf'\s*{a}\s*[-–—]\s*{b}(?![0-9])')
            bad = []
            for fname, lines in chapters.items():
                for i, line in enumerate(lines):
                    if not CAPTION_RE.match(line) and pat.search(line):
                        bad.append(f"{fname}:{i + 1}")
            checks.append({"desc": f"正文不再引用旧编号 {fix['kind']}{fix['old_num']}",
                           "result": "PASS" if not bad else "FAIL",
                           "detail": "已清除" if not bad else "; ".join(bad[:8])})
        for u in p.get("unresolved", []):
            checks.append({"desc": f"候选不唯一待模型处理 {u['kind']}{u['num']}",
                           "result": "SKIP", "detail": u["reason"]})
    elif t == "replace":
        checks.append(check_present(chapters, p["new"], f"出现新文 “{p['new'][:30]}…”"))
        checks.append(check_absent(chapters, p["old"], [], [],
                                   f"不再出现旧文 “{p['old'][:30]}…”"))
    elif t == "delete":
        checks.append(check_absent(chapters, p["text"], [], [],
                                   f"不再出现已删除文本 “{p['text'][:30]}…”"))
    elif t == "format_normalize" and p.get("rule") == "number_unit_space":
        bad = []
        for fname, lines in chapters.items():
            in_code = False
            for i, line in enumerate(lines):
                if line.strip().startswith("```"):
                    in_code = not in_code
                if not in_code and UNIT_STUCK_RE.search(line):
                    bad.append(f"{fname}:{i + 1}")
        checks.append({"desc": "数字与单位之间均有空格",
                       "result": "PASS" if not bad else "FAIL",
                       "detail": "全部合规" if not bad else "; ".join(bad[:8])})
    elif t == "manual":
        checks.append({"desc": f"人工项（模型处理）: {op.get('reason', '')[:60]}",
                       "result": "SKIP", "detail": op.get("action", "")[:120]})
    return checks


def main():
    ap = argparse.ArgumentParser(description="按 acceptance 自动验收编辑结果")
    ap.add_argument("--workorder", required=True)
    ap.add_argument("--ops", required=True)
    ap.add_argument("--chapters", required=True, help="编辑后的章节目录")
    ap.add_argument("--out", required=True, help="acceptance_report.json 输出路径")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    workorder = json.loads(Path(args.workorder).read_text(encoding="utf-8"))
    ops_doc = json.loads(Path(args.ops).read_text(encoding="utf-8"))
    chapters = load_chapters(args.chapters)
    ops_by_item = {}
    for op in ops_doc.get("ops", []):
        ops_by_item.setdefault(op.get("item_id"), []).append(op)

    item_reports, any_fail = [], False
    for item in workorder.get("items", []):
        iid = item.get("id")
        checks = []
        related = ops_by_item.get(iid, [])
        for op in related:
            checks.extend(checks_for_op(op, chapters))
        # acceptance 文本的通用缺失断言：“不再出现“X””
        acc = item.get("acceptance", "") or ""
        for m in re.finditer(r'不再出现\s*[“"\'「『]([^”"\'」』]+)', acc):
            needle = m.group(1)
            if not any(needle in c["desc"] for c in checks):
                ps, pp = [], []
                if "参考文献" in acc or "引用标题" in acc:
                    ps, pp = ["参考文献"], [r"^\s*\[\d+\]"]
                checks.append(check_absent(chapters, needle, ps, pp,
                                           f"acceptance 断言：不再出现 “{needle}”"))
        if not checks:
            checks.append({"desc": "无对应 op 且 acceptance 无法自动解析",
                           "result": "SKIP", "detail": acc[:120]})
        status = "FAIL" if any(c["result"] == "FAIL" for c in checks) else \
                 ("SKIP" if all(c["result"] == "SKIP" for c in checks) else "PASS")
        any_fail |= (status == "FAIL")
        item_reports.append({"item_id": iid, "title": item.get("title", ""),
                             "acceptance": acc, "status": status, "checks": checks})

    ok, dangling, captions = float_integrity(chapters)
    float_report = {"desc": "全局图表引用完整性：正文引用必须存在于题注",
                    "result": "PASS" if ok else "FAIL",
                    "captions": captions, "dangling": dangling}
    any_fail |= not ok

    report = {"schema": "surgical-edit-acceptance/v1",
              "case_id": ops_doc.get("case_id", "UNKNOWN"),
              "overall": "FAIL" if any_fail else "PASS",
              "items": item_reports,
              "float_integrity": float_report}
    if args.note:
        report["note"] = args.note
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    for it in item_reports:
        print(f"[verify] item {it['item_id']} {it['status']}: {it['title']}")
        for c in it["checks"]:
            print(f"    {c['result']:<4} {c['desc']}  ({c['detail']})")
    print(f"[verify] float_integrity: {float_report['result']} "
          f"(captions={len(captions)}, dangling={len(dangling)})")
    print(f"[verify] overall: {report['overall']}")
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
