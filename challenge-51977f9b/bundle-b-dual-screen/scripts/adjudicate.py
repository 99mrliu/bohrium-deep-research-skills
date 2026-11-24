#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adjudicate.py — 分歧仲裁与纳入集冻结（SHA-256 可验篡）。

仲裁行（JSONL）schema：
  {"record_id": "R05", "round": 1, "final_decision": "include"|"exclude",
   "rationale": "不少于 20 个字符的仲裁理由", "arbitrator": "仲裁人标识"}

冻结模式（默认）：
  1. A1 每条分歧必须有且仅有一条仲裁（缺失/重复逐条列出）；
  2. A2 仲裁行字段合法：final_decision 取值合法、rationale ≥20 字符、
     arbitrator 非空；
  3. A3 不允许对不存在分歧的记录强加仲裁（防止无据改判）；
  4. 全部通过后生成 frozen_set.json：纳入 id 排序列表、计数、以及
     全部决策 + 仲裁内容 + 纳入列表 的 SHA-256。

终判规则：某记录取其最高轮次；该轮有仲裁 → 以仲裁为准；否则 A、B 均判
include 才纳入，其余一律排除（uncertain 不经仲裁永不纳入，落实 S4）。

验证模式（--verify frozen_set.json）：用 --decisions 与 --rulings 重算
纳入列表、计数与哈希，与冻结文件逐字段比对，任何篡改 → exit 3 并指出
不一致字段名。

退出码：0=通过；2=输入/材料不足；3=校验失败（含验证发现篡改）。
"""
import argparse
import hashlib
import json
import os
import sys

MIN_RATIONALE_LEN = 20


def eprint(msg):
    print(msg, file=sys.stderr)


def load_jsonl(path, what):
    if not os.path.isfile(path):
        return None, f"{what} 文件不存在：{path}"
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                return None, f"{what} {path} 第 {ln} 行不是合法 JSON（{exc}）"
    return rows, None


def canonical_hash(decisions, rulings, included_ids):
    """对全部决策 + 仲裁 + 纳入列表计算 SHA-256（键排序、紧凑分隔，保证可复算）。"""
    payload = {
        "decisions": sorted(decisions,
                            key=lambda d: (str(d.get("record_id")),
                                           d.get("round", 0),
                                           str(d.get("screener", "")))),
        "rulings": sorted(rulings,
                          key=lambda r: (str(r.get("record_id")), r.get("round", 0))),
        "included_ids": sorted(included_ids),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def final_inclusion(decisions, rulings):
    """按终判规则推导纳入集；返回 (included_ids, per_record_resolution)。"""
    ruling_map = {(str(r["record_id"]), r["round"]): r for r in rulings}
    by_record = {}
    for d in decisions:
        by_record.setdefault(str(d["record_id"]), {}).setdefault(
            d["round"], {})[d["screener"]] = d["decision"]
    included, resolution = [], {}
    for rid, rounds in by_record.items():
        top = max(rounds)
        pair = rounds[top]
        if (rid, top) in ruling_map:
            final = ruling_map[(rid, top)]["final_decision"]
            src = "adjudication"
        elif pair.get("A") == "include" and pair.get("B") == "include":
            final, src = "include", "consensus"
        else:
            final, src = "exclude", "consensus"
        resolution[rid] = {"round": top, "final": final, "source": src}
        if final == "include":
            included.append(rid)
    return sorted(included), resolution


def build_counts(decisions, rulings, included_ids, resolution):
    rounds = {}
    for d in decisions:
        r = d["round"]
        rounds.setdefault(r, {"screened_records": set(), "decisions": 0})
        rounds[r]["screened_records"].add(str(d["record_id"]))
        rounds[r]["decisions"] += 1
    round_counts = {str(r): {"screened_records": len(v["screened_records"]),
                             "decisions": v["decisions"]}
                    for r, v in sorted(rounds.items())}
    return {
        "rounds": round_counts,
        "total_decisions": len(decisions),
        "total_rulings": len(rulings),
        "included": len(included_ids),
        "excluded": len(resolution) - len(included_ids),
    }


def validate_rulings(rulings, disagreements):
    """A1–A3 校验；返回违规列表（空=通过）。"""
    violations = []
    need = {(str(d["record_id"]), d["round"]) for d in disagreements}
    have = {}
    for i, r in enumerate(rulings):
        ln = f"仲裁第 {i + 1} 行"
        rid = str(r.get("record_id"))
        key = (rid, r.get("round"))
        # A2 字段合法
        if r.get("final_decision") not in ("include", "exclude"):
            violations.append(f"[A2] {ln}（{rid}）：final_decision 须为 include 或 exclude")
        rt = r.get("rationale")
        if not isinstance(rt, str) or len(rt.strip()) < MIN_RATIONALE_LEN:
            violations.append(f"[A2] {ln}（{rid}）：rationale 少于 {MIN_RATIONALE_LEN} 个字符")
        if not r.get("arbitrator"):
            violations.append(f"[A2] {ln}（{rid}）：缺 arbitrator")
        # A3 无分歧不得强加仲裁
        if key not in need:
            violations.append(f"[A3] {ln}（{rid}, round={r.get('round')}）："
                              f"该记录不在分歧清单中，禁止无据改判")
        have[key] = have.get(key, 0) + 1
    # A1 每条分歧恰好一条仲裁
    for key in sorted(need):
        n = have.get(key, 0)
        if n == 0:
            violations.append(f"[A1] 分歧 {key[0]}（round={key[1]}）缺仲裁")
        elif n > 1:
            violations.append(f"[A1] 分歧 {key[0]}（round={key[1]}）有 {n} 条仲裁（应恰好 1 条）")
    return violations


def cmd_freeze(args):
    disagreements = []
    for path in args.disagreements or []:
        if not os.path.isfile(path):
            eprint(f"[E-INPUT] 分歧报告不存在：{path}（请先运行 kappa.py）")
            return 2
        with open(path, "r", encoding="utf-8") as f:
            try:
                rep = json.load(f)
            except json.JSONDecodeError as exc:
                eprint(f"[E-INPUT] 分歧报告无法解析：{path}（{exc}）")
                return 2
        disagreements.extend(rep.get("disagreements") or [])

    rulings, err = load_jsonl(args.rulings, "rulings")
    if err:
        eprint(f"[E-INPUT] {err}")
        return 2
    decisions = []
    for path in args.decisions or []:
        rows, err = load_jsonl(path, "decisions")
        if err:
            eprint(f"[E-INPUT] {err}")
            return 2
        decisions.extend(rows)
    if not decisions:
        eprint("[E-INPUT] 未提供任何决策文件（--decisions），无法推导纳入集")
        return 2

    violations = validate_rulings(rulings, disagreements)
    if violations:
        print(f"[FAIL] 仲裁校验未通过，共 {len(violations)} 处违规：")
        for v in violations:
            print(f"  {v}")
        return 3

    included, resolution = final_inclusion(decisions, rulings)
    counts = build_counts(decisions, rulings, included, resolution)
    digest = canonical_hash(decisions, rulings, included)
    frozen = {
        "schema": "slr-dual-screen/frozen_set/v1",
        "hash_algorithm": "sha256",
        "hash_input": "canonical_json{decisions(sorted),rulings(sorted),included_ids(sorted)}",
        "content_sha256": digest,
        "included_ids": included,
        "counts": counts,
        "resolution": resolution,
        "note": "冻结后任何对决策/仲裁/纳入集的修改都会使 --verify 失败；"
                "确需修改请走解冻流程并写 change_records。",
    }
    if os.path.exists(args.out) and not args.force:
        eprint(f"[A4] 冻结文件已存在：{args.out}（重复冻结须显式 --force 并写 change_records）")
        return 3
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(frozen, f, ensure_ascii=False, indent=2)
    print(f"[OK] 纳入集已冻结：{args.out}")
    print(f"  纳入 {counts['included']} 条：{'、'.join(included) or '（无）'}")
    print(f"  SHA-256：{digest}")
    return 0


def cmd_verify(args):
    if not os.path.isfile(args.verify):
        eprint(f"[E-INPUT] 冻结文件不存在：{args.verify}")
        return 2
    with open(args.verify, "r", encoding="utf-8") as f:
        try:
            frozen = json.load(f)
        except json.JSONDecodeError as exc:
            eprint(f"[E-INPUT] 冻结文件无法解析（{exc}）")
            return 2
    rulings, err = load_jsonl(args.rulings, "rulings")
    if err:
        eprint(f"[E-INPUT] {err}")
        return 2
    decisions = []
    for path in args.decisions or []:
        rows, err = load_jsonl(path, "decisions")
        if err:
            eprint(f"[E-INPUT] {err}")
            return 2
        decisions.extend(rows)
    if not decisions:
        eprint("[E-INPUT] 未提供任何决策文件（--decisions），无法重算")
        return 2

    included, resolution = final_inclusion(decisions, rulings)
    recomputed = {
        "included_ids": included,
        "counts": build_counts(decisions, rulings, included, resolution),
        "content_sha256": canonical_hash(decisions, rulings, included),
    }
    mismatches = []
    for field, expect in recomputed.items():
        if frozen.get(field) != expect:
            mismatches.append(field)
    if mismatches:
        print(f"[V1] 验证失败：以下字段与重算结果不一致（疑似篡改）：{mismatches}")
        for field in mismatches:
            print(f"  {field}: 冻结值={json.dumps(frozen.get(field), ensure_ascii=False)[:120]}")
            print(f"  {field}: 重算值={json.dumps(recomputed[field], ensure_ascii=False)[:120]}")
        return 3
    print(f"[OK] 验证通过：included_ids、counts、content_sha256 均与重算一致，"
          f"纳入 {len(included)} 条，哈希未被篡改。")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="分歧仲裁 + 纳入集 SHA-256 冻结 / 验证。",
        epilog="退出码：0=通过；2=输入/材料不足；3=校验失败或验证发现篡改。",
    )
    ap.add_argument("--disagreements", nargs="*", default=[],
                    help="kappa.py 输出的 agreement_report_round<N>.json（可多份）")
    ap.add_argument("--rulings", required=True, help="仲裁 JSONL")
    ap.add_argument("--decisions", nargs="*", default=[],
                    help="全部决策 JSONL（推导纳入集与哈希输入）")
    ap.add_argument("--out", default="frozen_set.json", help="冻结文件输出路径")
    ap.add_argument("--verify", default=None, help="验证模式：指定待验证的 frozen_set.json")
    ap.add_argument("--force", action="store_true", help="允许覆盖已有冻结文件（须留痕）")
    args = ap.parse_args()

    if args.verify:
        return cmd_verify(args)
    if not args.disagreements:
        eprint("[E-INPUT] 冻结模式必须提供 --disagreements（kappa 报告，可为空清单的报告）")
        return 2
    return cmd_freeze(args)


if __name__ == "__main__":
    sys.exit(main())
