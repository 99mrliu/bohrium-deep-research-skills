#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""second_rater.py — 双人独立判定复现性比对包。

用法:
    python3 second_rater.py --rater-a A.jsonl --rater-b B.jsonl --workdir /app/work

行为契约:
    - 按 (doc_id, dimension) 对齐两份判定; 给出逐维度与总体的一致率 (%) 和
      Cohen's kappa (纯标准库实现, 无任何第三方依赖)。
    - 分歧条目 (两位评定者等级不同) 全量列出, 供裁决 (adjudication)。
    - 未配对判定 (仅一方给出) 显式报告, 绝不静默丢弃。
    - 输出: workdir/reliability.json, workdir/reliability_report.md。

退出码: 0 = 正常完成; 1 = 运行期错误; 2 = 用法/输入文件错误。
仅依赖 Python 3 标准库。
"""

import argparse
import json
import os
import sys
import datetime

EXIT_OK, EXIT_ERROR, EXIT_USAGE = 0, 1, 2


def log(msg):
    sys.stderr.write("[second_rater] %s\n" % msg)


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_rater(path, tag):
    """读取一位评定者的 verdicts.jsonl。

    返回 (verdicts, invalid):
      verdicts: dict (doc_id, dimension) -> level
      invalid:  无法解析或缺键的行列表 (显式报告, 不丢弃)
    重复 (doc_id, dimension) 保留首条并记入 invalid。
    """
    verdicts, invalid = {}, {}
    bad_rows = []
    try:
        f = open(path, "r", encoding="utf-8")
    except FileNotFoundError:
        log("%s 判定文件不存在: %s" % (tag, path))
        sys.exit(EXIT_USAGE)
    except OSError as e:
        log("%s 判定文件读取失败: %s: %s" % (tag, path, e))
        sys.exit(EXIT_USAGE)
    with f:
        for lineno, line in enumerate(f, 1):
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as e:
                bad_rows.append({"rater": tag, "line": lineno,
                                 "reason": "invalid_json: %s" % e})
                continue
            if not isinstance(row, dict):
                bad_rows.append({"rater": tag, "line": lineno,
                                 "reason": "not_a_json_object"})
                continue
            key = (row.get("doc_id"), row.get("dimension"))
            level = row.get("level")
            if not all(isinstance(x, str) and x for x in key) or not isinstance(level, str):
                bad_rows.append({"rater": tag, "line": lineno,
                                 "reason": "missing doc_id/dimension/level"})
                continue
            if key in verdicts:
                bad_rows.append({"rater": tag, "line": lineno,
                                 "reason": "duplicate_verdict %s, 保留首条" % (key,)})
                continue
            verdicts[key] = level
    return verdicts, bad_rows


def cohens_kappa(pairs, categories):
    """pairs: list of (a_level, b_level)。直接按定义计算, 无依赖。

    kappa = (po - pe) / (1 - pe); pe 由两边际分布计算。
    若 pe == 1 (边际完全集中) 则 kappa 无定义, 返回 None。
    """
    n = len(pairs)
    if n == 0:
        return None, 0.0, 0.0
    po = sum(1 for a, b in pairs if a == b) / n
    pa = {c: 0 for c in categories}
    pb = {c: 0 for c in categories}
    for a, b in pairs:
        pa[a] = pa.get(a, 0) + 1
        pb[b] = pb.get(b, 0) + 1
    pe = sum(pa.get(c, 0) * pb.get(c, 0) for c in categories) / (n * n)
    if pe >= 1.0:
        return None, po, pe
    return (po - pe) / (1.0 - pe), po, pe


def kappa_interpretation(k):
    if k is None:
        return "undefined (边际分布完全集中或样本为 0)"
    for lo, label in [(0.80, "almost perfect (几乎完全一致)"),
                      (0.60, "substantial (高度一致)"),
                      (0.40, "moderate (中度一致)"),
                      (0.20, "fair (一般一致)"),
                      (0.00, "slight (轻微一致)")]:
        if k >= lo:
            return label
    return "poor (低于随机水平)"


def append_change_record(workdir, detail):
    rec = {"ts": now_iso(), "actor": "d-grade-engine/scripts/second_rater.py",
           "action": "compute_reliability", "detail": detail}
    try:
        with open(os.path.join(workdir, "change_records.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as e:
        log("change_records 写入失败 (不致命): %s" % e)


def render_report(res):
    lines = ["# 双人评定复现性报告 (reliability report)", "",
             "- 评定者 A 文件: `%s`" % res["rater_a_file"],
             "- 评定者 B 文件: `%s`" % res["rater_b_file"],
             "- 配对判定数: %d" % res["paired"],
             "- 总体一致率: %.1f%% (%d/%d)" % (
                 res["overall"]["agreement_pct"], res["overall"]["agree"], res["paired"]),
             "- Cohen's kappa: %s (%s)" % (
                 ("%.4f" % res["overall"]["kappa"]) if res["overall"]["kappa"] is not None else "N/A",
                 res["overall"]["kappa_interpretation"]), "",
             "## 逐维度一致性", "",
             "| 维度 | 配对数 | 一致数 | 一致率 | kappa |", "|---|---|---|---|---|"]
    for dim, s in sorted(res["per_dimension"].items()):
        k = ("%.4f" % s["kappa"]) if s["kappa"] is not None else "N/A"
        lines.append("| %s | %d | %d | %.1f%% | %s |" % (
            dim, s["paired"], s["agree"], s["agreement_pct"], k))
    lines.append("")
    if res["disagreements"]:
        lines.append("## 分歧列表 (待裁决, %d 条)" % len(res["disagreements"]))
        for d in res["disagreements"]:
            lines.append("- `%s` / `%s`: A=**%s** vs B=**%s**" % (
                d["doc_id"], d["dimension"], d["rater_a_level"], d["rater_b_level"]))
        lines.append("")
    if res["unpaired"]:
        lines.append("## 未配对判定 (%d 条, 未参与一致性计算)" % len(res["unpaired"]))
        for u in res["unpaired"]:
            lines.append("- 仅 %s 给出: `%s` / `%s` = %s" % (
                u["only_in"], u["doc_id"], u["dimension"], u["level"]))
        lines.append("")
    if res["invalid_rows"]:
        lines.append("## 无效行 (%d 条)" % len(res["invalid_rows"]))
        for r in res["invalid_rows"]:
            lines.append("- %s 行 %s: %s" % (r.get("rater"), r.get("line"), r.get("reason")))
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="双人独立判定一致性比对 (agreement %% + Cohen's kappa)")
    ap.add_argument("--rater-a", required=True, help="评定者 A 的 verdicts.jsonl")
    ap.add_argument("--rater-b", required=True, help="评定者 B 的 verdicts.jsonl")
    ap.add_argument("--workdir", required=True, help="工作目录 (输出写于此)")
    args = ap.parse_args(argv)  # argparse 用法错误自动 exit 2

    os.makedirs(args.workdir, exist_ok=True)
    a, bad_a = read_rater(args.rater_a, "A")
    b, bad_b = read_rater(args.rater_b, "B")

    keys_a, keys_b = set(a), set(b)
    paired_keys = sorted(keys_a & keys_b)
    unpaired = ([{"only_in": "A", "doc_id": k[0], "dimension": k[1], "level": a[k]}
                 for k in sorted(keys_a - keys_b)] +
                [{"only_in": "B", "doc_id": k[0], "dimension": k[1], "level": b[k]}
                 for k in sorted(keys_b - keys_a)])

    pairs = [(a[k], b[k]) for k in paired_keys]
    categories = sorted(set(a[k] for k in paired_keys) | set(b[k] for k in paired_keys))
    disagreements = [{"doc_id": k[0], "dimension": k[1],
                      "rater_a_level": a[k], "rater_b_level": b[k]}
                     for k in paired_keys if a[k] != b[k]]

    per_dim = {}
    for dim in sorted({k[1] for k in paired_keys}):
        sub = [(a[k], b[k]) for k in paired_keys if k[1] == dim]
        k_sub, po_sub, _ = cohens_kappa(sub, categories)
        agree = sum(1 for x, y in sub if x == y)
        per_dim[dim] = {"paired": len(sub), "agree": agree,
                        "agreement_pct": 100.0 * agree / len(sub),
                        "kappa": k_sub}
    k_all, po_all, pe_all = cohens_kappa(pairs, categories)
    agree_all = sum(1 for x, y in pairs if x == y)

    res = {"rater_a_file": os.path.abspath(args.rater_a),
           "rater_b_file": os.path.abspath(args.rater_b),
           "paired": len(pairs),
           "overall": {"agree": agree_all,
                       "agreement_pct": (100.0 * agree_all / len(pairs)) if pairs else 0.0,
                       "observed_agreement": po_all,
                       "expected_agreement": pe_all,
                       "kappa": k_all,
                       "kappa_interpretation": kappa_interpretation(k_all)},
           "per_dimension": per_dim,
           "disagreements": disagreements,
           "unpaired": unpaired,
           "invalid_rows": bad_a + bad_b,
           "generated_at": now_iso()}
    with open(os.path.join(args.workdir, "reliability.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(os.path.join(args.workdir, "reliability_report.md"), "w", encoding="utf-8") as f:
        f.write(render_report(res))
    append_change_record(args.workdir,
                         "paired=%d, agree=%d, kappa=%s, unpaired=%d"
                         % (len(pairs), agree_all,
                            ("%.4f" % k_all) if k_all is not None else "N/A",
                            len(unpaired)))
    log("完成: 配对 %d, 分歧 %d, 未配对 %d; kappa=%s" % (
        len(pairs), len(disagreements), len(unpaired),
        ("%.4f" % k_all) if k_all is not None else "N/A"))
    return EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        log("未预期错误: %s" % e)
        sys.exit(EXIT_ERROR)
