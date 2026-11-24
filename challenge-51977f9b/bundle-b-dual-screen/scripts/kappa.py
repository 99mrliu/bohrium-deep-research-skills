#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kappa.py — 双人筛选一致性量化（观测一致率 po + Cohen's kappa）。

按 "include vs 非include"（exclude/uncertain 均归入非include）二分类，
对指定轮次计算：

  po = 双方判定一致的记录数 / 总记录数
  pe = p(A判include)·p(B判include) + p(A判非)·p(B判非)   （期望一致率）
  kappa = (po - pe) / (1 - pe)                              （Cohen's kappa）

输出 agreement_report_round<N>.json：po、pe、kappa、逐条一致/分歧清单
（分歧含双方 decision + reason）。kappa < threshold 时：--enforce → exit 3；
否则 exit 0，但报告写入 requires_extended_adjudication=true（须扩大仲裁
或澄清条款，并如实记入 uncertainty——kappa 存在患病率悖论，见
references/kappa_guide.md）。

退出码：0=通过（含低 kappa 未 enforce 情形）；2=配对数据不足；3=校验失败。
"""
import argparse
import json
import os
import sys

EPILOG = """公式：
  po = 一致条数 / N
  pe = (nA+/N)(nB+/N) + (nA-/N)(nB-/N)
  kappa = (po - pe) / (1 - pe)
其中 + 表示判 include，- 表示判非 include（exclude 或 uncertain）。
退出码：0=通过；2=配对数据不足（缺 A 或 B 判定，请先跑 screen_check.py）；
3=kappa 低于阈值且指定了 --enforce。"""


def eprint(msg):
    print(msg, file=sys.stderr)


def load_decisions(paths, round_no):
    """从若干 JSONL 文件收集指定轮次的 {record_id: {screener: row}}。"""
    by_record = {}
    for path in paths:
        if not os.path.isfile(path):
            return None, f"decisions 文件不存在：{path}"
        with open(path, "r", encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError as exc:
                    return None, f"{path} 第 {ln} 行不是合法 JSON（{exc}）"
                if d.get("round") != round_no:
                    continue
                rid = str(d.get("record_id"))
                sc = d.get("screener")
                if sc not in ("A", "B"):
                    return None, f"{path} 第 {ln} 行：screener={sc!r} 非法"
                by_record.setdefault(rid, {})[sc] = d
    return by_record, None


def main():
    ap = argparse.ArgumentParser(
        description="计算某轮双人筛选的 po / pe / Cohen's kappa 并输出分歧清单。",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--decisions", nargs="+", required=True,
                    help="一份（含双人）或两份决策 JSONL")
    ap.add_argument("--round", type=int, required=True, help="轮次 N")
    ap.add_argument("--threshold", type=float, default=0.6,
                    help="kappa 阈值（默认 0.6，解读见 references/kappa_guide.md）")
    ap.add_argument("--enforce", action="store_true",
                    help="kappa 低于阈值时以 exit 3 强制阻断")
    ap.add_argument("--out", default=None,
                    help="报告输出路径（默认 ./agreement_report_round<N>.json）")
    args = ap.parse_args()

    by_record, err = load_decisions(args.decisions, args.round)
    if err:
        eprint(f"[E-INPUT] {err}")
        return 2
    if not by_record:
        eprint(f"[E-INPUT] 第 {args.round} 轮没有任何决策记录")
        return 2

    unpaired = [rid for rid, m in sorted(by_record.items())
                if "A" not in m or "B" not in m]
    if unpaired:
        eprint(f"[K1] 以下记录缺少 A 或 B 的判定，无法配对（请先运行 "
               f"screen_check.py 补齐）：{unpaired}")
        return 2

    n = len(by_record)
    agree_ids, disagreements = [], []
    n_a_pos = n_b_pos = 0
    for rid in sorted(by_record):
        da, db = by_record[rid]["A"], by_record[rid]["B"]
        a_pos = da["decision"] == "include"
        b_pos = db["decision"] == "include"
        n_a_pos += a_pos
        n_b_pos += b_pos
        if a_pos == b_pos:
            agree_ids.append(rid)
        else:
            disagreements.append({
                "record_id": rid,
                "round": args.round,
                "A": {"decision": da["decision"],
                      "reason_code": da.get("reason_code"),
                      "reason_text": da.get("reason_text")},
                "B": {"decision": db["decision"],
                      "reason_code": db.get("reason_code"),
                      "reason_text": db.get("reason_text")},
            })

    po = len(agree_ids) / n
    pe = (n_a_pos / n) * (n_b_pos / n) + ((n - n_a_pos) / n) * ((n - n_b_pos) / n)
    if pe >= 1.0:
        kappa = 1.0 if po >= 1.0 else 0.0  # 边际分布极端退化
    else:
        kappa = (po - pe) / (1.0 - pe)

    meets = kappa >= args.threshold
    report = {
        "schema": "slr-dual-screen/agreement_report/v1",
        "round": args.round,
        "n_records": n,
        "n_agree": len(agree_ids),
        "n_disagree": len(disagreements),
        "marginals": {"A_include": n_a_pos, "B_include": n_b_pos},
        "po": round(po, 6),
        "pe": round(pe, 6),
        "kappa": round(kappa, 6),
        "threshold": args.threshold,
        "meets_threshold": meets,
        "requires_extended_adjudication": (not meets),
        "agreements": agree_ids,
        "disagreements": disagreements,
        "note": ("kappa 低于阈值：建议澄清纳排条款→加轮筛选→扩大仲裁，"
                 "并将 kappa 局限性（患病率悖论）写入 uncertainty。"
                 if not meets else "一致性达标。"),
    }
    out = args.out or f"agreement_report_round{args.round}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[第 {args.round} 轮] N={n}，po={po:.4f}，pe={pe:.4f}，kappa={kappa:.4f}"
          f"（阈值 {args.threshold}）→ {out}")
    if disagreements:
        print(f"  分歧 {len(disagreements)} 条："
              + "、".join(d["record_id"] for d in disagreements))
    if not meets:
        print(f"  [K2] kappa < {args.threshold}：requires_extended_adjudication=true")
        if args.enforce:
            eprint(f"[K3] --enforce 生效：kappa={kappa:.4f} 低于阈值 {args.threshold}，阻断。")
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
