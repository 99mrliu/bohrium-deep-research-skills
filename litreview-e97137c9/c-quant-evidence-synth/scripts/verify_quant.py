#!/usr/bin/env python3
"""verify_quant.py — 数字回链门控（bundle C 签名脚本 4）。

扫描草稿（work/review_draft.md）与证据表（work/evidence_table.md）中的每个数值
（与 extract_quant.py 共用同一套 find_tokens tokenizer，保证口径一致），
必须能匹配到某个 quant candidate：
  - 匹配候选的 value / value_canonical / ci 边界 / sd，绝对容差 1e-6；
  - 容忍单位换算后的 canonical 相等（草稿 0.35 s ≡ 候选 350 ms）；
  - 百分数与 ratio 等价（草稿 81% ≡ 候选 0.81）。
跳过 [E#] 等方括号标记与 p<页>.¶<段> 定位符内的数字。
无法回链的数字在文中就地标 [数值未定位]，明细写 out/quant_gate_report.json；
修订后的文件写入 out/ 目录。仅用标准库。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract_quant  # noqa: E402

TOL = 1e-6
SCAN_FILES = ("review_draft.md", "evidence_table.md")
RE_BRACKET = re.compile(r"\[[^\[\]]*\]")
RE_LOCATOR = re.compile(r"p\d+\s*\.\s*¶\s*\d+")


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def load_units():
    with open(os.path.join(HERE, "..", "vocab", "units.json"), encoding="utf-8") as f:
        return json.load(f)["units"]


def token_check_values(tok, units):
    """草稿中一个数值 token 的可匹配取值（原文值与 canonical 值）。"""
    vals = [tok["value"]]
    u = tok.get("unit")
    if u and u.lower() in units:
        vals.append(tok["value"] * units[u.lower()]["factor"])
    if tok.get("sd") is not None:
        vals.append(tok["sd"])
    return vals


def candidate_values(c):
    vals = [c.get("value"), c.get("value_canonical"),
            c.get("ci_low"), c.get("ci_high"),
            c.get("ci_low_canonical"), c.get("ci_high_canonical"), c.get("sd")]
    return [float(v) for v in vals if isinstance(v, (int, float))]


def gate_file(path, cand_vals, units):
    """返回 (修订后文本, 文件报告)。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    skip_spans = [(m.start(), m.end()) for m in RE_BRACKET.finditer(text)]
    skip_spans += [(m.start(), m.end()) for m in RE_LOCATOR.finditer(text)]

    def skipped(tok):
        return any(s <= tok["start"] < e for s, e in skip_spans)

    tokens, _ = extract_quant.find_tokens(text)
    linked, unlinked, n_skip = 0, [], 0
    marks = []  # (insert_pos, label)
    for tok in tokens:
        if skipped(tok):
            n_skip += 1
            continue
        vals = token_check_values(tok, units)
        hit = any(abs(v - cv) <= TOL for v in vals for cv in cand_vals)
        if hit:
            linked += 1
        else:
            snippet = text[max(0, tok["start"] - 40):tok["end"] + 40].replace("\n", " ")
            unlinked.append({"value": tok["value"], "unit": tok.get("unit"),
                             "kind": tok["kind"], "snippet": snippet})
            marks.append((tok["end"], "[数值未定位]"))
    for pos, label in sorted(marks, reverse=True):
        text = text[:pos] + label + text[pos:]
    return text, {"numbers": linked + len(unlinked), "linked": linked,
                  "unlinked": unlinked, "skipped": n_skip}


def run(work, out):
    cands = load_jsonl(os.path.join(work, "quant_normalized.jsonl")) or \
        load_jsonl(os.path.join(work, "quant_candidates.jsonl"))
    cand_vals = sorted({v for c in cands for v in candidate_values(c)})
    units = load_units()
    os.makedirs(out, exist_ok=True)

    files_report, total, linked_total, unlinked_total = {}, 0, 0, 0
    for name in SCAN_FILES:
        src = os.path.join(work, name)
        if not os.path.exists(src):
            continue
        revised, rep = gate_file(src, cand_vals, units)
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(revised)
        files_report[name] = rep
        total += rep["numbers"]
        linked_total += rep["linked"]
        unlinked_total += len(rep["unlinked"])

    report = {
        "files": files_report,
        "total_numbers": total,
        "linked": linked_total,
        "unlinked_count": unlinked_total,
        "tolerance": TOL,
        "equivalences": ["percent≡ratio（经 canonical）", "单位换算后 canonical 相等"],
        "gate_passed": unlinked_total == 0,
    }
    with open(os.path.join(out, "quant_gate_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    rep = run(args.work, args.out)
    print(json.dumps({"total_numbers": rep["total_numbers"], "linked": rep["linked"],
                      "unlinked": rep["unlinked_count"], "gate_passed": rep["gate_passed"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
