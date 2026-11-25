#!/usr/bin/env python3
"""detect_math_zones.py — 公式行判定(math-symbol-fidelity-lab 第 2 步)

行分组: 按 y 区间重叠聚合(上/下标与基线行垂直区间相交, 会并入同一行)。
公式行判定: 一行内命中 ≥2 个信号即判为 math zone:
  S1 greek_letter   : 希腊字母码位或 Symbol 字体字符
  S2 math_operator  : ∈∑∫√≤≥±×·=<> 等数学符号
  S3 script_layout  : 存在上下标结构(字号 ≤0.8×行中位 且 基线偏移 ≥0.25×行字高)
  S4 equation_number: 行右端出现独立编号 "(n)"
word 级降级页: 只能检测 S1/S2/S4(无字号信息), 该页 zones 标 partial=true。

用法:
  python3 detect_math_zones.py glyphs.jsonl --out math_zones.json [--report zones_report.json]

退出码: 0=成功, 2=存在 partial 页, 3=失败。
仅标准库。
"""

import argparse
import json
import re
import sys
import time
from statistics import median

SCRIPT_SIZE_RATIO = 0.8      # 上下标字号 ≤ 0.8 × 行中位字号
SCRIPT_OFFSET_RATIO = 0.25   # 上下标基线偏移 ≥ 0.25 × 行字高
MIN_SIGNALS = 2              # 判为公式行所需的最少信号数

MATH_OPERATORS = set("=<>+-±×÷*/∈∉∑∏∫√≤≥≠≈≡∝∞∂∇∩∪⊂⊃⊆⊇∧∨¬∀∃∴∠⊥→←↑↓↔⇒⇐⇔⟨⟩·")
EQ_NUMBER_RE = re.compile(r"\((\d{1,4})\)\s*$")


def is_greek(cp: int) -> bool:
    return (0x0370 <= cp <= 0x03FF) or (0x1F00 <= cp <= 0x1FFF)


def group_lines(items):
    """按 y 区间重叠聚合为行。items: 带 bbox 的 char/word 记录。返回 [ [item,...], ... ]"""
    lines = []  # 每个元素: {"y0":, "y1":, "items": []}
    for it in sorted(items, key=lambda r: (r["bbox"][1], r["bbox"][0])):
        y0, y1 = it["bbox"][1], it["bbox"][3]
        best = None
        for ln in lines:
            if y0 < ln["y1"] and ln["y0"] < y1:  # 区间相交
                best = ln
                break
        if best is None:
            lines.append({"y0": y0, "y1": y1, "items": [it]})
        else:
            best["items"].append(it)
            best["y0"] = min(best["y0"], y0)
            best["y1"] = max(best["y1"], y1)
    # 合并仍相交的行(区间扩张后可能链式相接)
    merged = True
    while merged:
        merged = False
        lines.sort(key=lambda l: l["y0"])
        i = 0
        while i < len(lines) - 1:
            a, b = lines[i], lines[i + 1]
            if b["y0"] < a["y1"]:
                a["items"].extend(b["items"])
                a["y0"] = min(a["y0"], b["y0"])
                a["y1"] = max(a["y1"], b["y1"])
                del lines[i + 1]
                merged = True
            else:
                i += 1
    for ln in lines:
        ln["items"].sort(key=lambda r: r["bbox"][0])
    lines.sort(key=lambda l: l["y0"])
    return lines


def char_line_signals(items):
    """char 级行的信号判定。返回 (signals[list[str]], number, script_info)。"""
    signals = []
    cps = [r["codepoint"] for r in items if r.get("codepoint")]
    fonts = [r.get("font") or "" for r in items]
    text = "".join(r["c"] for r in items)

    if any(is_greek(cp) for cp in cps) or any("symbol" in f.lower() for f in fonts):
        signals.append("greek_letter")
    if any(ch in MATH_OPERATORS for ch in text):
        signals.append("math_operator")

    sizes = [r["size"] for r in items if r.get("size")]
    script_info = None
    if sizes:
        med_size = median(sizes)
        base = [r for r in items if r.get("size") and r["size"] > SCRIPT_SIZE_RATIO * med_size]
        if base:
            heights = [r["bbox"][3] - r["bbox"][1] for r in base]
            H = median(heights)
            base_y = median([r["origin"][1] for r in base if r.get("origin")] or [0.0])
            for r in items:
                if not r.get("size") or not r.get("origin"):
                    continue
                if r["size"] <= SCRIPT_SIZE_RATIO * med_size:
                    dy = base_y - r["origin"][1]  # >0: 高于基线(上标), <0: 低于基线(下标)
                    if abs(dy) >= SCRIPT_OFFSET_RATIO * H:
                        signals.append("script_layout")
                        script_info = {
                            "char": r["c"], "kind": "superscript" if dy > 0 else "subscript",
                            "size": r["size"], "median_size": med_size, "offset": round(dy, 2),
                        }
                        break

    number = None
    m = EQ_NUMBER_RE.search(text.rstrip())
    if m:
        # 编号需位于行右端: 编号串首字符 x0 ≥ 行 x 跨度的 60%
        x_min = min(r["bbox"][0] for r in items)
        x_max = max(r["bbox"][2] for r in items)
        tail = "".join(r["c"] for r in items[-len(m.group(0)):])
        if tail == m.group(0) and items[-len(m.group(0))]["bbox"][0] >= x_min + 0.6 * (x_max - x_min):
            number = m.group(1)
            signals.append("equation_number")
    return signals, number, script_info


def word_line_signals(items):
    """word 级行的信号判定(无字号/字体 → 无法检测上下标结构)。"""
    signals = []
    text = " ".join(r.get("text") or "" for r in items)
    if any(is_greek(ord(ch)) for ch in text):
        signals.append("greek_letter")
    if any(ch in MATH_OPERATORS for ch in text):
        signals.append("math_operator")
    number = None
    m = EQ_NUMBER_RE.search(text.rstrip())
    if m:
        number = m.group(1)
        signals.append("equation_number")
    return signals, number


def main() -> int:
    ap = argparse.ArgumentParser(description="公式行判定 → math_zones.json")
    ap.add_argument("glyphs", help="extract_glyphs.py 产出的 glyphs.jsonl")
    ap.add_argument("--out", required=True, help="math_zones.json 输出路径")
    ap.add_argument("--report", default=None, help="可选 zones_report.json")
    args = ap.parse_args()

    try:
        records = [json.loads(l) for l in open(args.glyphs, encoding="utf-8") if l.strip()]
    except Exception as e:
        print(f"ERROR: 读取 glyphs.jsonl 失败: {e}", file=sys.stderr)
        return 3

    pages = {}
    for r in records:
        pages.setdefault(r["page"], []).append(r)

    zones = []
    partial_pages = []
    n_lines_total = 0
    for pno in sorted(pages):
        items = pages[pno]
        mode = items[0]["mode"]
        if mode != "char":
            partial_pages.append(pno)
        lines = group_lines(items)
        n_lines_total += len(lines)
        for ln in lines:
            it = ln["items"]
            if mode == "char":
                signals, number, script_info = char_line_signals(it)
                raw = "".join(r["c"] for r in it)
            else:
                signals, number = word_line_signals(it)
                script_info = None
                raw = " ".join(r.get("text") or "" for r in it)
            if len(signals) >= MIN_SIGNALS:
                zones.append({
                    "id": f"zone-{len(zones) + 1:03d}",
                    "page": pno,
                    "y": [round(ln["y0"], 2), round(ln["y1"], 2)],
                    "x": [round(min(r["bbox"][0] for r in it), 2),
                          round(max(r["bbox"][2] for r in it), 2)],
                    "raw_chars": raw,
                    "detected_number": number,
                    "signals": signals,
                    "mode": mode,
                    "partial": mode != "char",
                    "script_evidence": script_info,
                    "glyph_ids": [r["gid"] for r in it],
                })

    out = {
        "tool": "detect_math_zones",
        "thresholds": {
            "min_signals": MIN_SIGNALS,
            "script_size_ratio": SCRIPT_SIZE_RATIO,
            "script_offset_ratio": SCRIPT_OFFSET_RATIO,
        },
        "counts": {
            "pages": len(pages),
            "lines": n_lines_total,
            "zones": len(zones),
            "numbered_zones": sum(1 for z in zones if z["detected_number"]),
        },
        "partial_pages": partial_pages,
        "zones": zones,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump({k: out[k] for k in ("tool", "thresholds", "counts", "partial_pages")},
                      f, ensure_ascii=False, indent=2)
    print(json.dumps({"zones": len(zones), "partial_pages": partial_pages}, ensure_ascii=False))
    return 2 if partial_pages else 0


if __name__ == "__main__":
    sys.exit(main())
