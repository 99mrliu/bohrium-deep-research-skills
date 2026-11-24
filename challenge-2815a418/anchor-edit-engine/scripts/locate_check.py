#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""locate_check.py — 三方核验：回复信 ↔ changes.json ↔ 修订稿 必须一致。

核验项（任一失败即整体 FAIL，退出码 1）：
  (a) 回复信中引用的每个 CHG 编号必须存在于 changes.json；
  (b) 每个被引用的 CHG 编号，修订稿中必须确有
      <!-- CHG-xx begin: ... --> 与 <!-- CHG-xx end --> 成对标记；
  (c) 每条「定位行」（含 定位 + CHG 编号的行）中：
      - 锚点 quote 必须与 changes.json 登记的 quote 一致
        （逐字全等，或作为其中 ≥12 字的逐字片段）；
      - 章节文字必须出现在登记的章节路径中；
      - 段序数字必须等于登记的 paragraph_index；
  (d) changes.json 中每个条目都必须被回复信引用（无孤儿改动）；
  (e) decisions.json 中每个子要求编号（如 R1.1）必须在回复信中出现。

定位行格式（见 references/location_format.md）：
  - 定位：CHG-01 ｜ 章节：2 数据与方法 ｜ 段序：第 2 段 ｜ 锚点："逐字原文"

产物：locate_report.json（pass 布尔、逐项核验结果、精确错误清单）。
仅使用 Python 3 标准库。
"""
import argparse
import json
import re
import sys

CHG_RE = re.compile(r"CHG-\d+")
PARA_RE = re.compile(r"第\s*(\d+)\s*段")
MIN_EXCERPT = 12


def parse_location_lines(letter_text):
    """解析所有定位行：含「定位」且含 CHG 编号的行。"""
    claims = []
    for lineno, line in enumerate(letter_text.split("\n"), 1):
        if "定位" not in line:
            continue
        m = CHG_RE.search(line)
        if not m:
            continue
        rec = {"line": lineno, "chg": m.group(0),
               "section": None, "para": None, "quote": None, "raw": line.strip()}
        parts = re.split(r"[｜|]", line)
        for p in parts:
            p = p.strip().lstrip("- ").strip()
            for key, field in (("章节", "section"), ("段序", "para"), ("锚点", "quote")):
                if p.startswith(key):
                    val = p[len(key):].lstrip("：:").strip()
                    if field == "para":
                        pm = PARA_RE.search(val)
                        rec["para"] = int(pm.group(1)) if pm else None
                    elif field == "quote":
                        rec["quote"] = val.strip("“”\"'")
                    else:
                        rec["section"] = val
        claims.append(rec)
    return claims


def main():
    ap = argparse.ArgumentParser(description="回复信/改动/修订稿 三方核验")
    ap.add_argument("--letter", required=True, help="回复信 response-letter.md")
    ap.add_argument("--changes", required=True, help="apply_edits.py 产出的 changes.json")
    ap.add_argument("--revised", required=True, help="修订稿 revised-manuscript.md")
    ap.add_argument("--decisions", help="decisions.json（子要求全集，用于核验 e）")
    ap.add_argument("--report", required=True, help="locate_report.json 输出路径")
    args = ap.parse_args()

    with open(args.letter, "r", encoding="utf-8") as f:
        letter = f.read()
    with open(args.changes, "r", encoding="utf-8") as f:
        changes = json.load(f)
    with open(args.revised, "r", encoding="utf-8") as f:
        revised = f.read()

    by_id = {c["change_id"]: c for c in changes}
    cited = set(CHG_RE.findall(letter))
    claims = parse_location_lines(letter)
    errors = []
    checks = {"a_chg_exists": {"pass": True, "detail": []},
              "b_markers_in_revised": {"pass": True, "detail": []},
              "c_location_fields": {"pass": True, "detail": []},
              "d_no_orphan_changes": {"pass": True, "detail": []},
              "e_subrequests_covered": {"pass": True, "detail": []}}

    def fail(check, msg):
        checks[check]["pass"] = False
        checks[check]["detail"].append(msg)
        errors.append("[%s] %s" % (check, msg))

    # (a) 信中引用的 CHG 必须存在
    for cid in sorted(cited):
        if cid not in by_id:
            fail("a_chg_exists", "回复信引用了不存在的改动编号 %s" % cid)

    # (b) 被引用的 CHG 必须在修订稿中有成对标记
    for cid in sorted(cited & set(by_id)):
        has_begin = ("<!-- %s begin" % cid) in revised
        has_end = ("<!-- %s end -->" % cid) in revised
        if not (has_begin and has_end):
            fail("b_markers_in_revised",
                 "修订稿中缺少 %s 的成对 CHG 标记（begin=%s end=%s）"
                 % (cid, has_begin, has_end))

    # (c) 定位行四件套逐项核对
    claim_chgs = set()
    for c in claims:
        cid = c["chg"]
        claim_chgs.add(cid)
        if cid not in by_id:
            continue  # 已在 (a) 报告
        entry = by_id[cid]
        anchor = entry["anchor"]
        if c["quote"] is not None:
            reg = anchor["quote"]
            if c["quote"] == reg:
                pass  # 逐字全等
            elif len(c["quote"]) >= MIN_EXCERPT and c["quote"] in reg:
                pass  # 逐字片段（≥12 字）
            else:
                fail("c_location_fields",
                     "第 %d 行 %s：信中锚点 quote 与登记不一致。"
                     "信中=%r 登记=%r" % (c["line"], cid, c["quote"], reg))
        else:
            fail("c_location_fields", "第 %d 行 %s：定位行缺少锚点 quote" % (c["line"], cid))
        if c["section"] is not None:
            if c["section"] not in anchor["heading"]:
                fail("c_location_fields",
                     "第 %d 行 %s：章节 %r 不在登记章节路径 %r 中"
                     % (c["line"], cid, c["section"], anchor["heading"]))
        else:
            fail("c_location_fields", "第 %d 行 %s：定位行缺少章节" % (c["line"], cid))
        if c["para"] is not None:
            if c["para"] != anchor["paragraph_index"]:
                fail("c_location_fields",
                     "第 %d 行 %s：段序 第 %d 段 ≠ 登记段序 第 %d 段"
                     % (c["line"], cid, c["para"], anchor["paragraph_index"]))
        else:
            fail("c_location_fields", "第 %d 行 %s：定位行缺少段序" % (c["line"], cid))

    # (d) 无孤儿改动：changes.json 每条都被信中引用（正文或定位行）
    for cid in sorted(by_id):
        if cid not in cited:
            fail("d_no_orphan_changes",
                 "changes.json 条目 %s 未在回复信中引用（孤儿改动）" % cid)
        elif cid not in claim_chgs:
            fail("d_no_orphan_changes",
                 "changes.json 条目 %s 在信中被提及但没有规范定位行" % cid)

    # (e) 子要求编号全覆盖
    subrequests = []
    if args.decisions:
        with open(args.decisions, "r", encoding="utf-8") as f:
            decisions = json.load(f)
        subrequests = [d.get("sub_request", "") for d in decisions if d.get("sub_request")]
    else:
        for c in changes:
            subrequests.extend(c.get("comment_refs", []))
    for sub in sorted(set(subrequests)):
        if sub not in letter:
            fail("e_subrequests_covered",
                 "子要求 %s 未在回复信中出现" % sub)

    passed = not errors
    report = {
        "pass": passed,
        "checks": checks,
        "stats": {
            "changes_total": len(changes),
            "chg_cited_in_letter": len(cited),
            "location_lines": len(claims),
            "subrequests_expected": len(set(subrequests)),
        },
        "errors": errors,
    }
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    if passed:
        print("LOCATE CHECK PASS：回复信 ↔ changes.json ↔ 修订稿 三方一致"
              "（%d 处改动，%d 条定位行）" % (len(changes), len(claims)))
        return 0
    print("LOCATE CHECK FAIL（%d 个错误）：" % len(errors))
    for e in errors:
        print("  - %s" % e)
    return 1


if __name__ == "__main__":
    sys.exit(main())
