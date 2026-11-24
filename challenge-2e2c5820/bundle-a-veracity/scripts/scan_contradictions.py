#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan_contradictions.py <plans.json> <out.md>

启发式数值矛盾扫描（纯启发式，非语义理解，结果需人工复核）：
  1. 正则抽取数值提及：≤30 字符的前文上下文 + 数值 + 单位；
  2. 单位平凡归一化（µL/uL→ul, °C/摄氏度→C, mL→ml, min/分钟→min, 元/¥→yuan, h/小时→h 等）；
  3. 按上下文 token 重叠（中英文分词后的集合交集）聚类为"实体"；
  4. 标记：(a) 同一方案内同实体不同取值 → 矛盾表；
           (b) 跨版本同实体取值差异 → 版本差异表。
输出 markdown，含 plan_id 与行号定位。仅标准库，无网络。
"""
import json
import os
import re
import sys

NUM_RE = re.compile(
    r"(?P<ctx>[^\n]{0,30}?)"
    r"(?P<value>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    r"\s*(?P<unit>µL|uL|μL|mL|L|ng|µg|ug|mg|g|kg|nM|µM|uM|mM|M|"
    r"°C|℃|摄氏度|min|分钟|小时|h|s|秒|次|循环|cycles?|元|万元|¥|￥|"
    r"%|％|rpm|×|x|bp|kDa|人|小时|天|批|孔|管|样本|份)(?![A-Za-z])",
    re.IGNORECASE | re.UNICODE)

UNIT_NORM = {
    "µl": "ul", "ul": "ul", "μl": "ul", "ml": "ml", "l": "l",
    "ng": "ng", "µg": "ug", "ug": "ug", "mg": "mg", "g": "g", "kg": "kg",
    "nm": "nm", "µm": "um", "um": "um", "mm": "mm", "m": "m",
    "°c": "C", "℃": "C", "摄氏度": "C",
    "min": "min", "分钟": "min", "小时": "h", "h": "h", "s": "s", "秒": "s",
    "次": "次", "循环": "循环", "cycle": "循环", "cycles": "循环",
    "元": "yuan", "万元": "wanyuan", "¥": "yuan", "￥": "yuan",
    "%": "%", "％": "%", "rpm": "rpm", "×": "x", "x": "x",
    "bp": "bp", "kda": "kda", "人": "人", "天": "天", "批": "批",
    "孔": "孔", "管": "管", "样本": "样本", "份": "份",
}

CJK_TOKEN = re.compile(r"[一-鿿]{2,}")
EN_TOKEN = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")


def usage(msg):
    sys.stderr.write("用法: scan_contradictions.py <plans.json> <out.md>\n错误: %s\n" % msg)
    sys.exit(1)


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def context_tokens(ctx):
    toks = set(CJK_TOKEN.findall(ctx)) | set(t.lower() for t in EN_TOKEN.findall(ctx))
    # split long CJK runs into 2-char shingles for better overlap
    extra = set()
    for t in list(toks):
        if re.fullmatch(r"[一-鿿]{3,}", t):
            extra |= {t[i:i + 2] for i in range(len(t) - 1)}
    return toks | extra


def extract(plan):
    out = []
    text = plan["text"]
    for m in NUM_RE.finditer(text):
        unit = m.group("unit")
        unorm = UNIT_NORM.get(unit.lower())
        if unorm is None:
            continue
        try:
            val = float(m.group("value"))
        except ValueError:
            continue
        ctx = m.group("ctx").strip(" ：:，,、；;\t ")
        out.append({
            "plan_id": plan["plan_id"],
            "line": line_of(text, m.start("value")),
            "value": val,
            "raw_value": m.group("value"),
            "unit": unit, "unit_norm": unorm,
            "context": ctx[-30:],
            "tokens": context_tokens(ctx),
        })
    return out


def similar(a, b):
    """同单位 + token 重叠 ≥1（单位是硬约束，避免 58°C 撞 58 元）。"""
    if a["unit_norm"] != b["unit_norm"]:
        return False
    inter = a["tokens"] & b["tokens"]
    return len(inter) >= 1


def cluster(mentions):
    clusters = []
    for m in mentions:
        placed = False
        for c in clusters:
            if any(similar(m, o) for o in c):
                c.append(m)
                placed = True
                break
        if not placed:
            clusters.append([m])
    return clusters


def fmt(m):
    return "%s %s（%s 第%d行）" % (m["raw_value"], m["unit"], m["plan_id"], m["line"])


def main():
    if len(sys.argv) != 3:
        usage("需要两个参数：plans.json 与输出 markdown 路径")
    plans_path, out_md = sys.argv[1], sys.argv[2]
    if not os.path.isfile(plans_path):
        sys.stderr.write("错误: 找不到文件: %s\n" % plans_path)
        sys.exit(1)
    with open(plans_path, "r", encoding="utf-8") as f:
        plans = json.load(f)["plans"]

    mentions = []
    for p in plans:
        mentions.extend(extract(p))
    clusters = cluster(mentions)

    same_plan, cross_plan = [], []
    for c in clusters:
        by_plan = {}
        for m in c:
            by_plan.setdefault(m["plan_id"], []).append(m)
        for pid, ms in by_plan.items():
            vals = {(m["value"], m["unit_norm"]) for m in ms}
            if len(vals) > 1:
                same_plan.append((pid, ms))
        plans_in = sorted(by_plan)
        for i in range(len(plans_in)):
            for j in range(i + 1, len(plans_in)):
                a, b = by_plan[plans_in[i]], by_plan[plans_in[j]]
                va = {(m["value"], m["unit_norm"]) for m in a}
                vb = {(m["value"], m["unit_norm"]) for m in b}
                if va != vb:
                    cross_plan.append((plans_in[i], plans_in[j], a + b))

    lines = []
    lines.append("# 数值矛盾扫描报告（启发式，需人工复核）")
    lines.append("")
    lines.append("说明：本报告由 scan_contradictions.py 以正则+token 重叠聚类自动生成，"
                 "属纯启发式方法，可能漏报或误报；所有标记项须经人工回查原文确认。")
    lines.append("")
    lines.append("共扫描 %d 份方案，抽取 %d 处数值提及，聚成 %d 个上下文簇。"
                 % (len(plans), len(mentions), len(clusters)))
    lines.append("")
    lines.append("## (a) 同一方案内部矛盾（同实体不同取值）")
    lines.append("")
    if same_plan:
        for pid, ms in same_plan:
            ms = sorted(ms, key=lambda m: m["line"])
            lines.append("### 方案 `%s`" % pid)
            lines.append("")
            lines.append("| 行号 | 取值 | 前文上下文 |")
            lines.append("|---|---|---|")
            for m in ms:
                ctx = m["context"].replace("|", "\\|")
                lines.append("| %d | %s %s | …%s |" % (m["line"], m["raw_value"], m["unit"], ctx))
            lines.append("")
    else:
        lines.append("未发现。")
        lines.append("")
    lines.append("## (b) 跨版本取值差异")
    lines.append("")
    if cross_plan:
        for pa, pb, ms in cross_plan:
            ms = sorted(ms, key=lambda m: (m["plan_id"], m["line"]))
            lines.append("### `%s` ↔ `%s`" % (pa, pb))
            lines.append("")
            lines.append("| 方案 | 行号 | 取值 | 前文上下文 |")
            lines.append("|---|---|---|---|")
            for m in ms:
                ctx = m["context"].replace("|", "\\|")
                lines.append("| %s | %d | %s %s | …%s |"
                             % (m["plan_id"], m["line"], m["raw_value"], m["unit"], ctx))
            lines.append("")
    else:
        lines.append("未发现。")
        lines.append("")

    out_dir = os.path.dirname(os.path.abspath(out_md))
    os.makedirs(out_dir, exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    sys.stdout.write("OK: %d 项方案内矛盾, %d 项跨版本差异 -> %s\n"
                     % (len(same_plan), len(cross_plan), out_md))
    sys.exit(0)


if __name__ == "__main__":
    main()
