#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""coverage_check.py — 覆盖矩阵 ↔ 回复信 ↔ 稿件改动 三对齐机器核验。

检查项:
  (a) 每个子要求编号在回复信中出现，且该块非空（到下一编号/章节标题之间有实质内容）
  (b) 每个 CHG 有子要求归属（sub_ids 非空且均存在于矩阵）
  (c) 每个「修改文本 + 采纳」子要求至少关联一个已落稿 CHG，或填了 no_change_explanation
  (d) 回复信中每个子要求块的裁决表述与 matrix 一致
  (e) 证据清单与 matrix 中补做类条目一致（每个补做类子要求都出现在证据清单中）

失败写 coverage_report.json 并 exit 1；全部通过 exit 0。

用法:
  python3 coverage_check.py --matrix matrix.json --letter response-letter.md \
      [--changes changes.json] [--evidence evidence-checklist.md] --out coverage_report.json
"""
import argparse, json, os, re, sys
from datetime import datetime, timezone

EVIDENCE_ACTIONS = {"补实验", "补数据", "补文献", "重做分析"}
MIN_BLOCK_CHARS = 30  # 子要求块去除空白后的最少字符数


def extract_block(letter, sid, all_sids):
    """从 sid 首次出现处，到下一个编号/二级标题/文末之间的文本块。"""
    start = letter.find(sid)
    if start < 0:
        return None
    end = len(letter)
    for other in all_sids:
        if other == sid:
            continue
        p = letter.find(other, start + len(sid))
        if 0 <= p < end:
            end = p
    h = letter.find("\n## ", start + len(sid))
    if 0 <= h < end:
        end = h
    return letter[start:end]


def decision_consistent(block, decision):
    if decision == "部分采纳":
        return "部分采纳" in block
    if decision == "不采纳":
        return "不采纳" in block
    if decision == "采纳":
        return ("采纳" in block) and ("部分采纳" not in block) and ("不采纳" not in block)
    return False


def main():
    ap = argparse.ArgumentParser(description="矩阵↔信↔改动 三对齐核验")
    ap.add_argument("--matrix", required=True)
    ap.add_argument("--letter", required=True)
    ap.add_argument("--changes", default=None)
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    matrix = json.load(open(a.matrix, encoding="utf-8"))
    letter = open(a.letter, encoding="utf-8").read() if os.path.exists(a.letter) else None
    changes = {"changes": []}
    if a.changes and os.path.exists(a.changes):
        changes = json.load(open(a.changes, encoding="utf-8"))
    ev_text = None
    if a.evidence and os.path.exists(a.evidence):
        ev_text = open(a.evidence, encoding="utf-8").read()

    checks = []  # {id, item, ok, detail}
    subs = [(c.get("comment_id", "?"), s) for c in matrix.get("comments", [])
            for s in c.get("subrequirements", [])]
    all_sids = [s["sub_id"] for _, s in subs]
    sid_set = set(all_sids)

    # (a) 编号出现且块非空
    for _, s in subs:
        sid = s["sub_id"]
        if letter is None:
            checks.append({"check": "a", "item": sid, "ok": False, "detail": "回复信文件不存在"})
            continue
        block = extract_block(letter, sid, all_sids)
        if block is None:
            checks.append({"check": "a", "item": sid, "ok": False, "detail": "编号未在回复信中出现"})
        else:
            n = len(re.sub(r'\s+', '', block))
            checks.append({"check": "a", "item": sid, "ok": n >= MIN_BLOCK_CHARS,
                           "detail": "块内容 %d 字符（要求 ≥%d）" % (n, MIN_BLOCK_CHARS)})

    # (b) 每个 CHG 有子要求归属
    chg_list = changes.get("changes", [])
    chg_ids = set()
    for ch in chg_list:
        cid = ch.get("chg_id", "?")
        chg_ids.add(cid)
        sids = ch.get("sub_ids") or []
        bad = [x for x in sids if x not in sid_set]
        ok = bool(sids) and not bad
        detail = "归属 %s" % sids if ok else ("sub_ids 为空" if not sids else "归属不存在: %s" % bad)
        checks.append({"check": "b", "item": cid, "ok": ok, "detail": detail})

    # (c) 采纳的修改文本类子要求必须有已落稿 CHG 或说明
    chg_by_sub = {}
    for ch in chg_list:
        for x in ch.get("sub_ids") or []:
            chg_by_sub.setdefault(x, []).append(ch.get("chg_id"))
    for _, s in subs:
        if s.get("action") == "修改文本" and s.get("decision") == "采纳":
            sid = s["sub_id"]
            locs = [l.get("chg_id") for l in s.get("locations", []) if l.get("chg_id") in chg_ids]
            via_changes = chg_by_sub.get(sid, [])
            expl = (s.get("no_change_explanation") or "").strip()
            ok = bool(locs or via_changes or expl)
            detail = ("关联 CHG: %s" % (locs or via_changes)) if (locs or via_changes) else \
                     ("无 CHG，说明: %s" % expl[:60] if expl else "既无 CHG 也无 no_change_explanation")
            checks.append({"check": "c", "item": sid, "ok": ok, "detail": detail})

    # (d) 信与矩阵裁决一致
    if letter is not None:
        for _, s in subs:
            sid = s["sub_id"]
            block = extract_block(letter, sid, all_sids)
            if block is None:
                continue  # (a) 已报
            ok = decision_consistent(block, s.get("decision"))
            checks.append({"check": "d", "item": sid, "ok": ok,
                           "detail": "块内裁决表述与矩阵（%s）%s" % (s.get("decision"), "一致" if ok else "不一致或缺失")})

    # (e) 证据清单与补做类一致
    ev_subs = [s for _, s in subs if s.get("action") in EVIDENCE_ACTIONS]
    if ev_text is None:
        if ev_subs:
            for s in ev_subs:
                checks.append({"check": "e", "item": s["sub_id"], "ok": False, "detail": "存在补做类子要求但未提供证据清单文件"})
    else:
        for s in ev_subs:
            ok = s["sub_id"] in ev_text
            st = (s.get("evidence") or {}).get("status", "")
            if ok and st and st not in ev_text:
                ok = False
                checks.append({"check": "e", "item": s["sub_id"], "ok": False,
                               "detail": "编号在清单中但证据状态 %s 未出现" % st})
                continue
            checks.append({"check": "e", "item": s["sub_id"], "ok": ok,
                           "detail": "证据清单已覆盖（状态 %s）" % st if ok else "证据清单缺少该补做类子要求"})

    failed = [c for c in checks if not c["ok"]]
    report = {
        "result": "PASS" if not failed else "FAIL",
        "total_checks": len(checks), "failed": len(failed),
        "subrequirements": len(all_sids), "changes": len(chg_list),
        "checks": checks,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    if failed:
        print("[coverage_check] FAIL: %d/%d 项未过 -> %s" % (len(failed), len(checks), a.out), file=sys.stderr)
        for c in failed:
            print("  FAIL(%s) %s: %s" % (c["check"], c["item"], c["detail"]), file=sys.stderr)
        sys.exit(1)
    print("[coverage_check] PASS: %d 项核验全部通过（子要求 %d 个，CHG %d 处）-> %s"
          % (len(checks), len(all_sids), len(chg_list), a.out))


if __name__ == "__main__":
    main()
