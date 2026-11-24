#!/usr/bin/env python3
"""reconcile.py — PRISMA 流程计数逐账轧平（签名引擎一）。

flow.json 结构：
{
  "identified": n, "duplicates_removed": n, "screened": n,
  "excluded_title_abstract": {"理由码": n, ...},
  "fulltext_assessed": n,
  "excluded_fulltext": {"理由码": n, ...},
  "included": n
}

轧账规则：
  F1 identified - duplicates_removed = screened
  F2 screened = Σ excluded_title_abstract + fulltext_assessed
  F3 fulltext_assessed = Σ excluded_fulltext + included
  F4 若声明 excluded_*_total，各排除理由计数和必须等于该阶段排除总数
  F5 若给 --decisions jsonl，逐阶段实际计数与 flow.json 声明值对账

任何不平衡 → exit 3，输出每个失衡环节与差值；flow.json 缺失/非法 → exit 2。
"""
import argparse
import json
import os
import sys

NUMERIC_KEYS = ["identified", "duplicates_removed", "screened",
                "fulltext_assessed", "included"]
DICT_KEYS = ["excluded_title_abstract", "excluded_fulltext"]


def eprint(*a):
    print(*a, file=sys.stderr)


def reason_sum(d):
    return sum(d.values())


def check_reason_dict(flow, key, problems):
    d = flow.get(key)
    if not isinstance(d, dict):
        problems.append(f"R2: flow.json 字段 {key} 必须是对象（理由码 → 篇数）")
        return None
    for k, v in d.items():
        if not isinstance(v, int) or v < 0:
            problems.append(f"R2: flow.json 字段 {key}.{k} 必须是非负整数，实际 {v!r}")
            return None
    return d


def main():
    ap = argparse.ArgumentParser(
        description="PRISMA 流程计数逐账轧平；不平衡时指名失衡环节与差值。")
    ap.add_argument("--flow", required=True, help="flow.json 路径")
    ap.add_argument("--decisions", default=None,
                    help="可选筛选决策 jsonl，逐条含 record_id/stage(ta|ft)/decision(include|exclude)/reason")
    args = ap.parse_args()

    if not os.path.isfile(args.flow):
        eprint(f"R1: flow.json 不存在: {args.flow}（输入不足，诚实降级）")
        return 2
    try:
        with open(args.flow, encoding="utf-8") as f:
            flow = json.load(f)
    except json.JSONDecodeError as e:
        eprint(f"R2: flow.json 解析失败: {e}")
        return 2
    if not isinstance(flow, dict):
        eprint("R2: flow.json 顶层必须是对象")
        return 2

    problems = []
    for k in NUMERIC_KEYS:
        if not isinstance(flow.get(k), int) or flow[k] < 0:
            problems.append(f"R2: flow.json 缺少非负整数字段 {k}（实际 {flow.get(k)!r}）")
    ta = check_reason_dict(flow, "excluded_title_abstract", problems)
    ft = check_reason_dict(flow, "excluded_fulltext", problems)
    if problems:
        for p in problems:
            eprint(p)
        return 2

    identified = flow["identified"]
    dup = flow["duplicates_removed"]
    screened = flow["screened"]
    fulltext = flow["fulltext_assessed"]
    included = flow["included"]
    ta_sum = reason_sum(ta)
    ft_sum = reason_sum(ft)

    imbalances = []
    # F1
    if identified - dup != screened:
        imbalances.append(
            f"F1: identified({identified}) - duplicates_removed({dup}) = {identified - dup} "
            f"≠ screened={screened}, diff={abs(identified - dup - screened)}")
    # F2
    if screened != ta_sum + fulltext:
        imbalances.append(
            f"F2: screened={screened} 但 excluded_ta({ta_sum})+fulltext({fulltext})={ta_sum + fulltext}, "
            f"diff={abs(screened - ta_sum - fulltext)}")
    # F3
    if fulltext != ft_sum + included:
        imbalances.append(
            f"F3: fulltext_assessed={fulltext} 但 excluded_ft({ft_sum})+included({included})={ft_sum + included}, "
            f"diff={abs(fulltext - ft_sum - included)}")
    # F4：声明了阶段排除总数时，理由计数和必须与之相等
    for key, total_key, label in (("excluded_title_abstract", "excluded_title_abstract_total", "题录"),
                                  ("excluded_fulltext", "excluded_fulltext_total", "全文")):
        declared = flow.get(total_key)
        if declared is not None:
            s = reason_sum(flow[key])
            if s != declared:
                imbalances.append(
                    f"F4: {label}阶段排除理由计数和({s}) ≠ 声明的排除总数 {total_key}={declared}, "
                    f"diff={abs(s - declared)}（常见原因：漏记理由或一篇多理由双计）")

    # F5：与 decisions jsonl 实际计数对账
    if args.decisions:
        if not os.path.isfile(args.decisions):
            eprint(f"R1: decisions 文件不存在: {args.decisions}")
            return 2
        actual = {"ta": {"n": 0, "excl": {}, "incl": 0},
                  "ft": {"n": 0, "excl": {}, "incl": 0}}
        with open(args.decisions, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError as e:
                    eprint(f"R2: decisions 第 {i} 行 JSON 非法: {e}")
                    return 2
                stage, dec = d.get("stage"), d.get("decision")
                if stage not in ("ta", "ft") or dec not in ("include", "exclude"):
                    eprint(f"R2: decisions 第 {i} 行 stage/decision 非法: {d}")
                    return 2
                a = actual[stage]
                a["n"] += 1
                if dec == "exclude":
                    r = d.get("reason") or "未注明理由"
                    a["excl"][r] = a["excl"].get(r, 0) + 1
                else:
                    a["incl"] += 1
        checks = [
            ("F5-ta-screened", actual["ta"]["n"], screened, "题录级实际判定总数 vs screened"),
            ("F5-ta-excluded", reason_sum(actual["ta"]["excl"]), ta_sum, "题录级实际排除 vs excluded_title_abstract 和"),
            ("F5-ta-passed", actual["ta"]["incl"], fulltext, "题录级实际通过 vs fulltext_assessed"),
            ("F5-ft-assessed", actual["ft"]["n"], fulltext, "全文级实际判定总数 vs fulltext_assessed"),
            ("F5-ft-excluded", reason_sum(actual["ft"]["excl"]), ft_sum, "全文级实际排除 vs excluded_fulltext 和"),
            ("F5-ft-included", actual["ft"]["incl"], included, "全文级实际纳入 vs included"),
        ]
        for code, got, want, label in checks:
            if got != want:
                imbalances.append(f"{code}: {label}: 实际 {got} ≠ 声明 {want}, diff={abs(got - want)}")
        for stage, declared, actual_excl in (("ta", ta, actual["ta"]["excl"]),
                                             ("ft", ft, actual["ft"]["excl"])):
            for reason in sorted(set(declared) | set(actual_excl)):
                g, w = actual_excl.get(reason, 0), declared.get(reason, 0)
                if g != w:
                    imbalances.append(
                        f"F5-{stage}-reason「{reason}」: 实际 {g} ≠ 声明 {w}, diff={abs(g - w)}")

    if imbalances:
        for m in imbalances:
            eprint(m)
        eprint(f"reconcile: {len(imbalances)} 处不平衡；排查顺序见 references/counts_reconciliation.md"
               f"（先 F4 理由漏记 → 再 F2 双计 → 再 duplicates）")
        return 3
    scope = "含 decisions 对账" if args.decisions else "仅 flow.json 内部"
    print(f"reconcile: 全部轧平（{scope}）：identified={identified} → screened={screened} "
          f"→ fulltext={fulltext} → included={included}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
