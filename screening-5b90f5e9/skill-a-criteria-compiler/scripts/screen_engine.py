#!/usr/bin/env python3
"""screen_engine.py — 核心引擎（步骤 7，脚本环节；判定来自模型，合成与校验由脚本做）。

输入（默认均在 /app/work）：normalized.jsonl + dedup_ledger.jsonl +
criteria_table.json + judgments.jsonl（模型逐记录×逐标准判定）。

三件事：
(1) 证据锚定校验门：每个 evidence_snippet 经 NFKC/小写/空白归一后，必须是该记录
    title 或 abstract 的子串（verdict 为 pass/fail 且 evidence_required 时必须引用；
    uncertain 可免引用但须给 note；若给了 snippet 同样校验）。任一失败 →
    写 anchor_failures.json 并 exit 3，模型必须重新锚定后重跑，直到全过。
(2) 确定性判定合成（固定规则，见下）→ decisions.jsonl。
(3) 计数 → screening_summary.json。

合成规则（按序适用，先中先得）：
  R1 摘要为空/缺失          → needs_human / EX-NO-ABSTRACT（边界 no_abstract）
  R2 语言不符 eligible_languages → needs_human / EX-LANGUAGE（边界 language_mismatch）
  R3 排除标准 fail（非边界码）→ excluded，主理由码=表中第一个失败排除标准的 reason_code
  R4 纳入标准 fail（非边界码）→ excluded，主理由码=第一个失败纳入标准的 reason_code
  R5 带边界码的 fail / 任一 uncertain → needs_human（不强行判定）
  R6 标准缺判定             → needs_human / BND-UNRESOLVED
  R7 全部通过               → included / IN-ALL-MET

退出码：0=通过；2=输入不足（如 criteria 未填充），诚实降级；3=锚定/结构校验失败。
幂等：重跑覆盖同名产物。
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

WS_RE = re.compile(r"\s+")
# 这些码的 fail 不自动排除，强制转人工（本方向的红线边界）
BOUNDARY_FAIL_CODES = {"EX-LANGUAGE", "EX-NO-ABSTRACT"}


def norm_anchor(s):
    """证据锚定归一化：NFKC、小写、压缩所有空白为单空格、去首尾；中文原样保留。"""
    s = unicodedata.normalize("NFKC", s or "")
    s = s.lower()
    return WS_RE.sub(" ", s).strip()


def load_json(path, what):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"{what} 读取失败({path}): {e}")


def load_jsonl(path, what):
    out = []
    try:
        for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise RuntimeError(f"{what} 第 {i} 行 JSON 解析失败: {e}")
    except FileNotFoundError:
        raise RuntimeError(f"{what} 不存在: {path}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="证据锚定校验 + 确定性判定合成")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--judgments", default=None, help="判定文件（默认 <work>/judgments.jsonl）")
    args = ap.parse_args(argv)
    work = Path(args.work)
    judgments_path = Path(args.judgments) if args.judgments else work / "judgments.jsonl"

    try:
        records = load_jsonl(work / "normalized.jsonl", "normalized.jsonl")
        ledger = load_jsonl(work / "dedup_ledger.jsonl", "dedup_ledger.jsonl")
        criteria_table = load_json(work / "criteria_table.json", "criteria_table.json")
    except RuntimeError as e:
        print(f"[screen_engine] 输入不足: {e}", file=sys.stderr)
        return 2
    if not judgments_path.exists():
        print(f"[screen_engine] 缺少 {judgments_path}（模型判定尚未落盘），输入不足。",
              file=sys.stderr)
        return 2
    try:
        judgments = load_jsonl(judgments_path, "judgments.jsonl")
    except RuntimeError as e:
        print(f"[screen_engine] 输入不足: {e}", file=sys.stderr)
        return 2

    criteria = criteria_table.get("criteria") or []
    if not criteria:
        print("[screen_engine] criteria_table.criteria 为空（模型尚未编译标准），"
              "输入不足，诚实降级。", file=sys.stderr)
        return 2
    criteria_version = criteria_table.get("version", "v0.0.0")
    eligible_languages = [str(l).lower() for l in (criteria_table.get("eligible_languages") or [])]
    crit_by_id = {}
    for c in criteria:
        if not c.get("criterion_id") or c.get("type") not in ("inclusion", "exclusion"):
            print(f"[screen_engine] 标准结构非法: {c}", file=sys.stderr)
            return 3
        crit_by_id[c["criterion_id"]] = c

    rec_by_id = {r["record_id"]: r for r in records}
    # record_id -> group 解析（判定可用 group_id 或任一副本 record_id）
    rid_to_group = {}
    for g in ledger:
        rid_to_group[g["group_id"]] = g["group_id"]
        for rid in g.get("member_record_ids", []):
            rid_to_group[rid] = g["group_id"]
    group_by_id = {g["group_id"]: g for g in ledger}

    # ---------- (1) 证据锚定校验门 ----------
    failures = []
    jmap = {}  # (group_id, criterion_id) -> judgment（后写覆盖先写）
    for idx, j in enumerate(judgments, 1):
        rid = j.get("record_id")
        cid = j.get("criterion_id")
        verdict = j.get("verdict")
        snippet = j.get("evidence_snippet") or ""
        note = j.get("note") or ""
        gid = rid_to_group.get(rid)
        if gid is None:
            failures.append({"judgment_index": idx, "record_id": rid, "criterion_id": cid,
                             "problem": "record_id 无法解析到任何 study_group"})
            continue
        if cid not in crit_by_id:
            failures.append({"judgment_index": idx, "record_id": rid, "criterion_id": cid,
                             "problem": "criterion_id 不在 criteria_table 中"})
            continue
        if verdict not in ("pass", "fail", "uncertain"):
            failures.append({"judgment_index": idx, "record_id": rid, "criterion_id": cid,
                             "problem": f"verdict 非法: {verdict!r}（须 pass/fail/uncertain）"})
            continue
        crit = crit_by_id[cid]
        evidence_required = crit.get("evidence_required", True)
        if verdict == "uncertain":
            if not note.strip():
                failures.append({"judgment_index": idx, "record_id": rid, "criterion_id": cid,
                                 "problem": "uncertain 必须给 note"})
                continue
        elif evidence_required and not snippet.strip():
            failures.append({"judgment_index": idx, "record_id": rid, "criterion_id": cid,
                             "problem": f"verdict={verdict} 且 evidence_required，缺 evidence_snippet"})
            continue
        if snippet.strip():
            canonical_id = group_by_id[gid]["canonical_record_id"]
            rec = rec_by_id.get(canonical_id, {})
            hay_title = norm_anchor(rec.get("title"))
            hay_abs = norm_anchor(rec.get("abstract"))
            needle = norm_anchor(snippet)
            if not needle or (needle not in hay_title and needle not in hay_abs):
                failures.append({"judgment_index": idx, "record_id": rid, "criterion_id": cid,
                                 "problem": "evidence_snippet 归一后不是该记录 title/abstract 的子串",
                                 "snippet": snippet})
                continue
        jmap[(gid, cid)] = j

    if failures:
        af = work / "anchor_failures.json"
        af.write_text(json.dumps({"failures": failures, "count": len(failures),
                                  "action": "模型必须重新锚定证据后重跑"},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[screen_engine] 锚定校验失败 {len(failures)} 处 -> {af}（exit 3）",
              file=sys.stderr)
        return 3

    # ---------- (2) 确定性判定合成 ----------
    def per_criterion_detail(gid):
        detail = []
        for c in criteria:
            cid = c["criterion_id"]
            j = jmap.get((gid, cid))
            if j is None:
                detail.append({"criterion_id": cid, "type": c["type"], "verdict": "missing",
                               "reason_code": c.get("reason_code"), "evidence_snippet": "",
                               "note": "模型未给出该标准判定"})
            else:
                detail.append({"criterion_id": cid, "type": c["type"],
                               "verdict": j["verdict"],
                               "reason_code": j.get("reason_code") or c.get("reason_code"),
                               "evidence_snippet": j.get("evidence_snippet") or "",
                               "note": j.get("note") or ""})
        return detail

    decisions = []
    for g in ledger:
        gid = g["group_id"]
        canonical = rec_by_id[g["canonical_record_id"]]
        notes = []
        boundary_types = []
        decision = primary = None

        abstract = norm_anchor(canonical.get("abstract"))
        lang = (canonical.get("language") or "").strip().lower()
        # R1 摘要为空 → 强制人工
        if not abstract:
            decision, primary = "needs_human", "EX-NO-ABSTRACT"
            boundary_types.append("no_abstract")
            notes.append("摘要为空/缺失，强制转人工队列")
        # R2 语言不符 → 强制人工
        elif eligible_languages and lang and lang not in eligible_languages:
            decision, primary = "needs_human", "EX-LANGUAGE"
            boundary_types.append("language_mismatch")
            notes.append(f"记录语言 {lang} 不在 eligible_languages={eligible_languages}，"
                         "强制转人工队列")
        else:
            fails, uncertains, missing = [], [], []
            for c in criteria:
                cid = c["criterion_id"]
                j = jmap.get((gid, cid))
                if j is None:
                    missing.append(cid)
                elif j["verdict"] == "fail":
                    fails.append((c, j))
                elif j["verdict"] == "uncertain":
                    uncertains.append((c, j))
            boundary_fails = [(c, j) for c, j in fails
                              if (j.get("reason_code") or c.get("reason_code")) in BOUNDARY_FAIL_CODES
                              or str(j.get("reason_code") or "").startswith("BND-")]
            exc_fails = [(c, j) for c, j in fails if c["type"] == "exclusion"
                         and (c, j) not in boundary_fails]
            inc_fails = [(c, j) for c, j in fails if c["type"] == "inclusion"
                         and (c, j) not in boundary_fails]
            if exc_fails:  # R3
                c, j = exc_fails[0]
                decision = "excluded"
                primary = j.get("reason_code") or c.get("reason_code")
                notes.append(f"第一个失败的排除标准: {c['criterion_id']}")
            elif inc_fails:  # R4
                c, j = inc_fails[0]
                decision = "excluded"
                primary = j.get("reason_code") or c.get("reason_code")
                notes.append(f"第一个失败的纳入标准: {c['criterion_id']}")
            elif boundary_fails or uncertains:  # R5
                decision = "needs_human"
                src = (boundary_fails or uncertains)[0]
                c, j = src
                code = j.get("reason_code") or c.get("reason_code") or "BND-UNRESOLVED"
                primary = code if str(code).startswith(("BND-", "EX-")) else "BND-UNRESOLVED"
                for c2, j2 in boundary_fails + uncertains:
                    rc = j2.get("reason_code") or ""
                    if rc.startswith("BND-"):
                        boundary_types.append(rc[4:].lower())
                notes.append("存在边界/不确定判定，不强行纳入或排除")
            elif missing:  # R6
                decision, primary = "needs_human", "BND-UNRESOLVED"
                notes.append(f"缺判定标准: {','.join(missing)}")
            else:  # R7
                decision, primary = "included", "IN-ALL-MET"

        decisions.append({
            "group_id": gid,
            "decision": decision,
            "primary_reason_code": primary,
            "boundary_types": boundary_types,
            "canonical_record_id": g["canonical_record_id"],
            "member_record_ids": g.get("member_record_ids", []),
            "title": canonical.get("title"),
            "criteria_version": criteria_version,
            "per_criterion": per_criterion_detail(gid),
            "notes": notes,
        })

    dec_path = work / "decisions.jsonl"
    with dec_path.open("w", encoding="utf-8") as out:
        for d in decisions:
            out.write(json.dumps(d, ensure_ascii=False) + "\n")

    # ---------- (3) 计数 ----------
    counter = Counter(d["decision"] for d in decisions)
    by_reason = Counter(d["primary_reason_code"] for d in decisions)
    summary = {
        "screened": len(decisions),
        "included": counter.get("included", 0),
        "excluded": counter.get("excluded", 0),
        "needs_human": counter.get("needs_human", 0),
        "by_reason_code": dict(by_reason),
        "judgments_total": len(judgments),
        "criteria_version": criteria_version,
        "decisions_file": str(dec_path),
        "generated_by": "screen_engine.py",
        "stage": "screening",
    }
    (work / "screening_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[screen_engine] screened={summary['screened']} included={summary['included']} "
          f"excluded={summary['excluded']} needs_human={summary['needs_human']} (exit 0)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"[screen_engine] 未预期错误（诚实降级）: {e}", file=sys.stderr)
        sys.exit(2)
