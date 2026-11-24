#!/usr/bin/env python3
"""gain_meter.py — 双通道增益计量器。

对比同一份输入下的两份 result.json 草稿（pass0=基线快速稿，pass1=严谨稿），
产出机器可复核的增益报告：契约字段填充率、证据锚点数、越界断言增减、
不确定性条目数、冲突登记数、带边界的新颖性断言数。

用法：
  python3 gain_meter.py --baseline pass0.json --final pass1.json \
      [--contract case.json] --out OUTDIR

产出 OUTDIR/gain_report.json 与 OUTDIR/gain_report.md。
退出码：0 正常；1 输入非法。
仅依赖 Python 3 标准库。
"""
import argparse
import json
import re
import sys
from pathlib import Path

ANCHOR_PATTERNS = [
    r"\[来源:[^\]]+\]", r"\[source:[^\]]+\]", r"\[证据:[^\]]+\]",
    r"p\.\s*\d+", r"pp\.\s*\d+", r"第\s*\d+\s*页", r"第\s*\d+\s*段",
    r"§\s*\d+", r"表\s*\d+", r"图\s*\d+",
    r"\bTable\s*\d+", r"\bFig(?:ure)?\.?\s*\d+", r"\bSection\s*\d+",
]
OVERCLAIM_PATTERNS = [
    r"尚无人研究", r"尚未有人研究", r"尚无人涉足",
    r"未见.{0,6}报道", r"未见.{0,6}研究",
    r"国内外首创", r"国际首创", r"世界首创", r"国内首创", r"全球首创",
    r"首次提出", r"首次报道", r"首次实现",
    r"填补.{0,8}空白", r"前所未有",
    r"\bfirst\s+ever\b", r"\bfirst\s+to\b", r"\bno\s+prior\s+work\b",
    r"\bunprecedented\b",
]
SCOPE_WORDS = ["边界", "范围", "文献集", "检索", "截至", "在本", "所给",
               "给定", "覆盖", "within", "scope", "bounded", "as of"]
CONFLICT_WORDS = ["冲突", "矛盾", "不一致", "相反", "conflict",
                  "contradict", "disagree"]
WINDOW = 60


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"输入非法 {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def flatten_strings(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from flatten_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from flatten_strings(v)
    elif isinstance(node, str):
        yield node


def is_empty(v):
    return v is None or v == "" or v == [] or v == {}


def metric_bundle(data, fields):
    texts = list(flatten_strings(data))
    blob = "\n".join(texts)
    anchors = sum(len(re.findall(p, blob)) for p in ANCHOR_PATTERNS)
    overclaims, bounded_oc = 0, 0
    for p in OVERCLAIM_PATTERNS:
        for m in re.finditer(p, blob, flags=re.IGNORECASE):
            overclaims += 1
            lo = max(0, m.start() - WINDOW)
            hi = min(len(blob), m.end() + WINDOW)
            if any(w.lower() in blob[lo:hi].lower() for w in SCOPE_WORDS):
                bounded_oc += 1
    conflicts = sum(blob.lower().count(w.lower()) for w in CONFLICT_WORDS)
    unc = data.get("uncertainties") if isinstance(data, dict) else None
    if isinstance(unc, list):
        unc_items = len([x for x in unc if not is_empty(x)])
    elif isinstance(unc, str) and unc.strip():
        unc_items = len([ln for ln in unc.splitlines() if ln.strip()])
    else:
        unc_items = 0
    filled = sum(1 for f in fields
                 if isinstance(data, dict) and not is_empty(data.get(f)))
    return {
        "contract_fields_total": len(fields),
        "contract_fields_filled": filled,
        "fill_rate": round(filled / max(1, len(fields)), 3),
        "evidence_anchors": anchors,
        "overclaims_total": overclaims,
        "overclaims_unbounded": overclaims - bounded_oc,
        "uncertainty_items": unc_items,
        "conflict_mentions": conflicts,
    }


def contract_fields_of(contract):
    if isinstance(contract, dict):
        return list(contract.keys())
    if isinstance(contract, list):
        return [str(x) for x in contract]
    if isinstance(contract, str):
        return [ln.strip() for ln in contract.splitlines() if ln.strip()]
    return []


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--final", required=True)
    ap.add_argument("--contract", default=None,
                    help="case.json；给出则按其 output_contract 计填充率，"
                         "否则用两稿键的并集")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    base, final = load_json(args.baseline), load_json(args.final)
    if args.contract:
        case = load_json(args.contract)
        fields = contract_fields_of(case.get("output_contract"))
    else:
        fields = sorted(set(base) | set(final))
    fields = [f for f in fields if f != "case_id"] or fields

    mb, mf = metric_bundle(base, fields), metric_bundle(final, fields)
    delta = {k: mf[k] - mb[k] for k in mb if isinstance(mb[k], (int, float))}
    verdicts = {
        "填充率提升": delta["contract_fields_filled"] > 0
        or mf["fill_rate"] >= mb["fill_rate"] == 1.0,
        "证据锚点增加": delta["evidence_anchors"] > 0,
        "越界断言减少或不增": delta["overclaims_unbounded"] <= 0,
        "不确定性登记增加": delta["uncertainty_items"] > 0,
        "冲突登记增加或不减": delta["conflict_mentions"] >= 0,
    }
    report = {
        "note": "双通道增益报告（机器生成）；指标定义见 "
                "references/metrics_format.md",
        "fields_compared": fields,
        "baseline": mb, "final": mf, "delta": delta,
        "verdicts": verdicts,
        "all_verdicts_pass": all(verdicts.values()),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "gain_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    rows = ["| 指标 | 基线稿 | 严谨稿 | 差值 |", "|-|-|-|-|"]
    labels = {
        "contract_fields_filled": "契约字段填充数",
        "fill_rate": "契约填充率",
        "evidence_anchors": "证据锚点数",
        "overclaims_unbounded": "无边界越界断言数",
        "uncertainty_items": "不确定性条目数",
        "conflict_mentions": "冲突登记数",
    }
    for k, label in labels.items():
        rows.append(f"| {label} | {mb[k]} | {mf[k]} | {delta[k]:+} |")
    md = ["# 双通道增益报告（机器生成）", "",
          "基线稿 = 限时快速通道（模拟未加载技能的写法）；严谨稿 = 完整协议通道。",
          "同一输入、同一契约，指标由 gain_meter.py 确定性计算。", "",
          *rows, "",
          "## 判定", ""]
    md += [f"- {'✓' if v else '✗'} {k}" for k, v in verdicts.items()]
    md += ["", f"总体：{'通过' if report['all_verdicts_pass'] else '未通过'}"
           "（任一 ✗ 都意味着严谨稿在该维度没有可证明的增益）"]
    (out / "gain_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(out),
                      "all_verdicts_pass": report["all_verdicts_pass"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
