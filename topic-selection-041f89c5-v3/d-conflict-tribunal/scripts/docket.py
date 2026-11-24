#!/usr/bin/env python3
"""docket.py — 冲突证据对抗裁决器。

把综述中的关键断言组织成"卷宗"（docket）：每个断言组（group）必须同时
登记支持证据、对抗检索记录与（如找到）反证；裁决按显式优先级
（直接性 > 证据类型 > 方法严谨度 > 时效）机械作出， unresolved 的冲突
双方并列保留，不许只留支持性证据。

子命令：
  lint        机检卷宗完整性（每组必须有支持证据 + 对抗检索记录；
              记录字段合法；found=true 的组必须有反证登记）
  adjudicate  对每组按优先级裁决，输出 tribunal_report.json/md 与
              contradiction_register.md

卷宗为 JSONL，两种记录（字段细节见 references/docket_format.md）：
  {"type":"evidence","group":"G1","side":"support|counter","claim":"...",
   "source_file":"...","quote":"...","locator":"...",
   "quality":{"directness":"direct|indirect",
              "evidence_kind":"experimental|observational|simulation|review",
              "method_rigor":"high|medium|low","year":2024}}
  {"type":"counter_search","group":"G1","scope":"检索范围描述",
   "found":true|false,"note":"..."}

退出码：lint 发现违例为 1；adjudicate 正常为 0（卷宗不可读为 1）。
仅依赖 Python 3 标准库。
"""
import argparse
import json
import sys
from pathlib import Path

DIRECTNESS = {"direct": 2, "indirect": 1}
KIND = {"experimental": 4, "observational": 3, "simulation": 2, "review": 1}
RIGOR = {"high": 3, "medium": 2, "low": 1}
CRITERIA = ["directness", "evidence_kind", "method_rigor", "year"]
CRITERIA_ZH = {"directness": "直接性", "evidence_kind": "证据类型",
               "method_rigor": "方法严谨度", "year": "时效"}


def load_docket(path):
    records = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        print(f"卷宗读取失败: {exc}", file=sys.stderr)
        sys.exit(1)
    for i, ln in enumerate(lines, 1):
        if not ln.strip():
            continue
        try:
            records.append((i, json.loads(ln)))
        except json.JSONDecodeError as exc:
            print(f"第 {i} 行不是合法 JSON: {exc}", file=sys.stderr)
            sys.exit(1)
    return records


def validate(records):
    errors = []
    groups = {}
    for i, r in records:
        t = r.get("type")
        g = r.get("group")
        if t not in ("evidence", "counter_search"):
            errors.append(f"第{i}行: type 非法 {t!r}")
            continue
        if not g:
            errors.append(f"第{i}行: 缺 group")
            continue
        groups.setdefault(g, []).append((i, r))
        if t == "evidence":
            if r.get("side") not in ("support", "counter"):
                errors.append(f"第{i}行: side 非法 {r.get('side')!r}")
            for f in ("claim", "source_file", "quote", "locator"):
                if not r.get(f):
                    errors.append(f"第{i}行: evidence 缺字段 {f}")
            q = r.get("quality") or {}
            if q.get("directness") not in DIRECTNESS:
                errors.append(f"第{i}行: quality.directness 非法")
            if q.get("evidence_kind") not in KIND:
                errors.append(f"第{i}行: quality.evidence_kind 非法")
            if q.get("method_rigor") not in RIGOR:
                errors.append(f"第{i}行: quality.method_rigor 非法")
            y = q.get("year")
            if not isinstance(y, int) or not 1900 <= y <= 2100:
                errors.append(f"第{i}行: quality.year 非法 {y!r}")
        else:
            if not r.get("scope"):
                errors.append(f"第{i}行: counter_search 缺 scope")
            if not isinstance(r.get("found"), bool):
                errors.append(f"第{i}行: counter_search.found 必须是布尔")
            if r.get("found") is False and \
                    len((r.get("note") or "").strip()) < 8:
                errors.append(f"第{i}行: found=false 必须附 ≥8 字符的"
                              f"检索说明 note")
    for g, items in groups.items():
        sides = [r.get("side") for _, r in items if r["type"] == "evidence"]
        searches = [r for _, r in items if r["type"] == "counter_search"]
        if "support" not in sides:
            errors.append(f"组 {g}: 缺支持证据")
        if not searches:
            errors.append(f"组 {g}: 缺对抗检索记录（不许只登记支持性证据）")
        for s in searches:
            if s.get("found") and "counter" not in sides:
                errors.append(f"组 {g}: counter_search.found=true 但"
                              f"无反证登记")
    return errors, groups


def rank_key(r):
    q = r["quality"]
    return (DIRECTNESS[q["directness"]], KIND[q["evidence_kind"]],
            RIGOR[q["method_rigor"]], q["year"])


def adjudicate_group(g, items):
    ev = [r for _, r in items if r["type"] == "evidence"]
    supports = [r for r in ev if r["side"] == "support"]
    counters = [r for r in ev if r["side"] == "counter"]
    searches = [r for _, r in items if r["type"] == "counter_search"]
    if not counters:
        return {"group": g, "verdict": "unchallenged",
                "deciding_criterion": None,
                "rationale": "对抗检索未找到反证；断言成立但置信度低于"
                             "经过对抗检验的结论，综述中必须如实标注",
                "support_count": len(supports), "counter_count": 0,
                "search_scope": "; ".join(s.get("scope", "")
                                          for s in searches)}
    best_s = max(supports, key=rank_key)
    best_c = max(counters, key=rank_key)
    ks, kc = rank_key(best_s), rank_key(best_c)
    for idx, crit in enumerate(CRITERIA):
        if ks[idx] != kc[idx]:
            winner = "support" if ks[idx] > kc[idx] else "counter"
            wb, lb = (best_s, best_c) if winner == "support" \
                else (best_c, best_s)
            wq, lq = wb["quality"], lb["quality"]
            return {"group": g, "verdict": winner,
                    "deciding_criterion": CRITERIA_ZH[crit],
                    "rationale": (
                        f"按{CRITERIA_ZH[crit]}裁决：{wb['source_file']}"
                        f"（{wq['directness']}/{wq['evidence_kind']}/"
                        f"{wq['method_rigor']}/{wq['year']}）优于 "
                        f"{lb['source_file']}（{lq['directness']}/"
                        f"{lq['evidence_kind']}/{lq['method_rigor']}/"
                        f"{lq['year']}）；取舍理由已登记，反方证据并列保留"),
                    "winner_source": wb["source_file"],
                    "loser_source": lb["source_file"],
                    "support_count": len(supports),
                    "counter_count": len(counters)}
    return {"group": g, "verdict": "unresolved",
            "deciding_criterion": None,
            "rationale": "四项裁决准则全部持平；冲突无法裁决，双方结论"
                         "在综述中并列保留并标注为未决冲突",
            "support_count": len(supports), "counter_count": len(counters)}


def cmd_lint(args):
    records = load_docket(args.docket)
    errors, _ = validate(records)
    print(json.dumps({"ok": not errors, "violations": errors},
                     ensure_ascii=False, indent=2))
    if errors:
        sys.exit(1)


def cmd_adjudicate(args):
    records = load_docket(args.docket)
    errors, groups = validate(records)
    if errors:
        print("卷宗未通过 lint，先修复再裁决：", file=sys.stderr)
        for e in errors:
            print(" -", e, file=sys.stderr)
        sys.exit(1)
    verdicts = [adjudicate_group(g, items)
                for g, items in sorted(groups.items())]
    report = {"note": "对抗裁决报告（机器生成）；准则优先级："
                      "直接性 > 证据类型 > 方法严谨度 > 时效",
              "verdicts": verdicts}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "tribunal_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    md = ["# 对抗裁决报告（机器生成）", "",
          "准则优先级：直接性 > 证据类型 > 方法严谨度 > 时效；"
          "反方证据无论胜负均并列保留。", "",
          "| 断言组 | 裁决 | 决定准则 | 支持/反证 | 理由 |",
          "|-|-|-|-|-|"]
    for v in verdicts:
        md.append("| %s | %s | %s | %d/%d | %s |"
                  % (v["group"], v["verdict"],
                     v.get("deciding_criterion") or "-",
                     v["support_count"], v["counter_count"],
                     v["rationale"]))
    (out / "tribunal_report.md").write_text("\n".join(md) + "\n",
                                            encoding="utf-8")

    conflicts = [v for v in verdicts if v["counter_count"] > 0]
    reg = ["# 冲突登记册（机器生成）", ""]
    if not conflicts:
        reg.append("本次卷宗无实质冲突（所有断言组均无反证登记）。")
    for v in conflicts:
        reg.append(f"## {v['group']} → {v['verdict']}")
        reg.append(f"- 决定准则：{v.get('deciding_criterion') or '（未决）'}")
        reg.append(f"- 取舍说明：{v['rationale']}")
        reg.append("")
    reg.append("规则：综述引用任何一组结论时，必须同句给出本登记册中的"
               "裁决状态；unresolved 组双方并列，unchallenged 组标注"
               "“未经对抗检验”。")
    (out / "contradiction_register.md").write_text(
        "\n".join(reg) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(out),
                      "groups": len(verdicts),
                      "conflicts": len(conflicts)}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lint")
    p.add_argument("--docket", required=True)
    p.set_defaults(fn=cmd_lint)
    p = sub.add_parser("adjudicate")
    p.add_argument("--docket", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_adjudicate)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
