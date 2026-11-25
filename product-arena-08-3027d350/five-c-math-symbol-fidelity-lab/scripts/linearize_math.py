#!/usr/bin/env python3
"""linearize_math.py — 数学区线性化核心(math-symbol-fidelity-lab 第 3 步)

做法:
1. 基线分组: 组内以 origin.y(真实基线)为锚, 主组 = 字号 > 0.8×行中位字号的字符;
   组字高 H = 主组字符 bbox 高度中位。
   注: rawdict 的 bbox 是字体 ascent/descent 盒而非紧包字形盒, 故基线锚用 origin.y
       (推导见 references/method.md)。
2. 上标: 字号 ≤0.8×中位 且 基线高于主组 ≥0.25×H  → ^(...)
   下标: 字号 ≤0.8×中位 且 基线低于主组 ≥0.25×H  → _(...)
3. 字体映射: font 名含 Symbol 且字符仍为 ASCII 原始码位 → 按内嵌 Adobe Symbol
   编码映射表(核心 0x20–0x7E + 常用高位码, 完整表见 references/symbol-map.md);
   抽取器已解出非 ASCII 码位 → 信任并计入 trusted_decoded。
   ZapfDingbats 仅信任内嵌常见映射表内的码位, 其余 → unmapped。
4. 无映射 codepoint、U+FFFD、非 BMP(>U+FFFF) → unmapped 台账(页码/坐标/字体/原始码位),
   linear 中以 ⟦U+XXXX⟧ 占位, 绝不静默替换。
5. 编号配对: 行右端 "(n)"(首字符 x0 ≥ 行跨度的 60%)与公式体分离, 存 number。

用法:
  python3 linearize_math.py glyphs.jsonl math_zones.json \
      --out equations.json --report fidelity_report.json [--extract-report extract_report.json]

退出码: 0=干净, 2=存在 unmapped/基线异常/word 级降级, 3=失败。
仅标准库。
"""

import argparse
import json
import re
import sys
import time
from statistics import median

SCRIPT_SIZE_RATIO = 0.8
SCRIPT_OFFSET_RATIO = 0.25
BASELINE_TOL_RATIO = 0.3
EQ_NUMBER_RE = re.compile(r"\((\d{1,4})\)$")

# ---------------------------------------------------------------------------
# Adobe Symbol 编码映射(核心内嵌表; 完整表与判据见 references/symbol-map.md)
# 键: 字体原始码位(内容流字节); 值: Unicode 字符。
# ---------------------------------------------------------------------------
SYMBOL_MAP = {
    0x20: " ", 0x21: "!", 0x22: "∀", 0x23: "#", 0x24: "∃", 0x25: "%",
    0x26: "&", 0x27: "∍", 0x28: "(", 0x29: ")", 0x2A: "∗", 0x2B: "+",
    0x2C: ",", 0x2D: "−", 0x2E: ".", 0x2F: "/",
    0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4", 0x35: "5",
    0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9",
    0x3A: ":", 0x3B: ";", 0x3C: "<", 0x3D: "=", 0x3E: ">", 0x3F: "?",
    0x40: "≅", 0x41: "Α", 0x42: "Β", 0x43: "Χ", 0x44: "Δ", 0x45: "Ε",
    0x46: "Φ", 0x47: "Γ", 0x48: "Η", 0x49: "Ι", 0x4A: "ϑ", 0x4B: "Κ",
    0x4C: "Λ", 0x4D: "Μ", 0x4E: "Ν", 0x4F: "Ο", 0x50: "Π", 0x51: "Θ",
    0x52: "Ρ", 0x53: "Σ", 0x54: "Τ", 0x55: "Υ", 0x56: "ς", 0x57: "Ω",
    0x58: "Ξ", 0x59: "Ψ", 0x5A: "Ζ", 0x5B: "[", 0x5C: "∴", 0x5D: "]",
    0x5E: "⊥", 0x5F: "_", 0x60: "‾",
    0x61: "α", 0x62: "β", 0x63: "χ", 0x64: "δ", 0x65: "ε", 0x66: "φ",
    0x67: "γ", 0x68: "η", 0x69: "ι", 0x6A: "ϕ", 0x6B: "κ", 0x6C: "λ",
    0x6D: "μ", 0x6E: "ν", 0x6F: "ο", 0x70: "π", 0x71: "θ", 0x72: "ρ",
    0x73: "σ", 0x74: "τ", 0x75: "υ", 0x76: "ϖ", 0x77: "ω", 0x78: "ξ",
    0x79: "ψ", 0x7A: "ζ", 0x7B: "{", 0x7C: "|", 0x7D: "}", 0x7E: "∼",
    # 常用高位码位
    0xA2: "′", 0xA3: "≤", 0xA5: "∞", 0xAB: "↔", 0xAC: "←", 0xAD: "↑",
    0xAE: "→", 0xAF: "↓", 0xB0: "°", 0xB1: "±", 0xB2: "″", 0xB3: "≥",
    0xB4: "×", 0xB5: "∝", 0xB6: "∂", 0xB7: "•", 0xB8: "÷", 0xB9: "≠",
    0xBA: "≡", 0xBB: "≈", 0xBC: "…", 0xC0: "ℵ", 0xC1: "ℑ", 0xC2: "ℜ",
    0xC3: "℘", 0xC4: "⊗", 0xC5: "⊕", 0xC6: "∅", 0xC7: "∩", 0xC8: "∪",
    0xC9: "⊃", 0xCA: "⊇", 0xCB: "⊄", 0xCC: "⊂", 0xCD: "⊆", 0xCE: "∈",
    0xCF: "∉", 0xD0: "∠", 0xD1: "∇", 0xD5: "∏", 0xD6: "√", 0xD7: "⋅",
    0xD8: "¬", 0xD9: "∧", 0xDA: "∨", 0xDB: "⇔", 0xDC: "⇐", 0xDD: "⇑",
    0xDE: "⇒", 0xDF: "⇓", 0xE0: "◊", 0xE1: "⟨", 0xE5: "∑", 0xF1: "⟩",
}

# ITC ZapfDingbats 常见映射(保守子集; 其余码位一律进 unmapped, 不猜)
ZAPF_COMMON = {
    0x6C: "●",   # 黑圆
    0x6E: "■",   # 黑方块
    0x25: "☞",   # 指向手
}

UNMAPPED_PLACEHOLDER = "⟦U+{cp:04X}⟧"


def classify_baseline(chars):
    """返回 (cls: {gid: 'base'|'sup'|'sub'}, anomalies[list])。"""
    sizes = [c["size"] for c in chars if c.get("size")]
    if not sizes:
        return {}, [{"kind": "no-size-info", "detail": "word 级或无字号, 跳过基线判定"}]
    med_size = median(sizes)
    base = [c for c in chars if c.get("size") and c["size"] > SCRIPT_SIZE_RATIO * med_size
            and c.get("origin")]
    anomalies = []
    if not base:
        return {}, [{"kind": "no-baseline-group", "detail": "无主导字号字符, 无法建立基线"}]
    H = median([c["bbox"][3] - c["bbox"][1] for c in base])
    base_y = median([c["origin"][1] for c in base])
    cls = {}
    for c in chars:
        if not c.get("size") or not c.get("origin"):
            cls[c["gid"]] = "base"
            continue
        dy = base_y - c["origin"][1]  # >0: 高于基线(上标方向)
        if c["size"] <= SCRIPT_SIZE_RATIO * med_size:
            if dy >= SCRIPT_OFFSET_RATIO * H:
                cls[c["gid"]] = "sup"
            elif -dy >= SCRIPT_OFFSET_RATIO * H:
                cls[c["gid"]] = "sub"
            else:
                cls[c["gid"]] = "base"
                anomalies.append({
                    "kind": "small-size-no-offset", "char": c["c"], "gid": c["gid"],
                    "size": c["size"], "median_size": med_size, "dy": round(dy, 2),
                    "detail": "小字号但基线偏移不足阈值, 按基线处理并告警",
                })
        else:
            if abs(dy) > BASELINE_TOL_RATIO * H:
                anomalies.append({
                    "kind": "baseline-drift", "char": c["c"], "gid": c["gid"],
                    "dy": round(dy, 2), "tol": round(BASELINE_TOL_RATIO * H, 2),
                    "detail": "主字号字符偏离基线超 0.3×组字高",
                })
            cls[c["gid"]] = "base"
    return cls, anomalies


def map_char(c, stats, unmapped, page):
    """单字符字体映射。返回 linear 用字符; verbatim 一律用原始 c。
    stats: dict 计数; unmapped: 台账列表。"""
    cp = c.get("codepoint")
    ch = c.get("c") or ""
    font = (c.get("font") or "").lower()
    raw_cp_hex = f"U+{cp:04X}" if cp is not None else "None"

    if cp is None or ch == "�" or (cp is not None and cp > 0xFFFF):
        unmapped.append({
            "page": page, "bbox": c.get("bbox"), "font": c.get("font"),
            "raw_codepoint": raw_cp_hex, "extracted_char": ch,
            "reason": "替换符/无码位/非 BMP 异常",
        })
        stats["unmapped"] += 1
        return UNMAPPED_PLACEHOLDER.format(cp=cp or 0)

    if "symbol" in font:
        if cp < 0x80:  # 抽取器未解码, 仍是原始字节 → 用编码映射表
            if cp in SYMBOL_MAP:
                mapped = SYMBOL_MAP[cp]
                if mapped != ch:
                    stats["replacements"] += 1
                    key = (c.get("font"), ch, mapped)
                    stats["replacement_detail"][key] = stats["replacement_detail"].get(key, 0) + 1
                else:
                    stats["symbol_passthrough"] += 1
                return mapped
            unmapped.append({
                "page": page, "bbox": c.get("bbox"), "font": c.get("font"),
                "raw_codepoint": raw_cp_hex, "extracted_char": ch,
                "reason": "Symbol 字体码位不在内嵌映射表",
            })
            stats["unmapped"] += 1
            return UNMAPPED_PLACEHOLDER.format(cp=cp)
        # 抽取器已按内置编码/ToUnicode 解出非 ASCII → 信任
        stats["trusted_decoded"] += 1
        return ch

    if "zapfdingbats" in font:
        if cp in ZAPF_COMMON:
            mapped = ZAPF_COMMON[cp]
            if mapped != ch:
                stats["replacements"] += 1
                key = (c.get("font"), ch, mapped)
                stats["replacement_detail"][key] = stats["replacement_detail"].get(key, 0) + 1
            return mapped
        unmapped.append({
            "page": page, "bbox": c.get("bbox"), "font": c.get("font"),
            "raw_codepoint": raw_cp_hex, "extracted_char": ch,
            "reason": "ZapfDingbats 码位不在保守映射子集(不猜测)",
        })
        stats["unmapped"] += 1
        return UNMAPPED_PLACEHOLDER.format(cp=cp)

    return ch  # 常规文本字体: 原样保留


def linearize_zone(zone, glyphs_by_gid, stats, unmapped, anomalies_out):
    """返回 equation 记录。"""
    page = zone["page"]
    if zone["mode"] != "char":
        words = [glyphs_by_gid[g] for g in zone["glyph_ids"] if g in glyphs_by_gid]
        raw = " ".join(w.get("text") or "" for w in words)
        return {
            "id": None, "page": page, "anchor": {"page": page, "bbox": [zone["x"], zone["y"]]},
            "verbatim": raw, "linear": raw, "number": zone.get("detected_number"),
            "unmapped": [], "mode": zone["mode"],
            "note": "word 级降级: 无字号/字体, 上下标与符号映射不可用, 本区 partial",
        }, True

    chars = sorted((glyphs_by_gid[g] for g in zone["glyph_ids"] if g in glyphs_by_gid),
                   key=lambda c: c["bbox"][0])
    verbatim = "".join(c["c"] for c in chars)

    # 编号配对: 右端 "(n)"
    number = None
    body = chars
    stripped = verbatim.rstrip()
    m = EQ_NUMBER_RE.search(stripped)
    if m and zone.get("detected_number") == m.group(1):
        n_tail = len(m.group(0))
        tail_chars = chars[-n_tail:]
        if "".join(c["c"] for c in tail_chars) == m.group(0):
            x_min, x_max = chars[0]["bbox"][0], chars[-1]["bbox"][2]
            if tail_chars[0]["bbox"][0] >= x_min + 0.6 * (x_max - x_min):
                number = m.group(1)
                body = chars[:-n_tail]

    cls, anomalies = classify_baseline(body)
    for a in anomalies:
        a["zone_id"] = zone["id"]
        a["page"] = page
    anomalies_out.extend(anomalies)

    n_unmapped_before = len(unmapped)
    parts = []
    sup_buf, sub_buf = [], []

    def flush():
        # 上标先排(视觉更高), 同基元上下标按 x 序已由遍历保证大体有序
        if sup_buf:
            parts.append("^{" + "".join(sup_buf) + "}")
            sup_buf.clear()
        if sub_buf:
            parts.append("_{" + "".join(sub_buf) + "}")
            sub_buf.clear()

    for c in body:
        mapped = map_char(c, stats, unmapped, page)
        k = cls.get(c["gid"], "base")
        if k == "sup":
            if sub_buf:
                flush()
            sup_buf.append(mapped)
        elif k == "sub":
            if sup_buf:
                flush()
            sub_buf.append(mapped)
        else:
            flush()
            parts.append(mapped)
    flush()
    linear = "".join(parts).strip()

    return {
        "id": None,
        "page": page,
        "anchor": {"page": page, "bbox": [zone["x"], zone["y"]]},
        "verbatim": verbatim,
        "linear": linear,
        "number": number,
        "unmapped": unmapped[n_unmapped_before:],
        "mode": "char",
        "signals": zone.get("signals", []),
    }, len(unmapped) > n_unmapped_before or bool(anomalies)


def main() -> int:
    ap = argparse.ArgumentParser(description="数学区线性化 → equations.json + fidelity_report.json")
    ap.add_argument("glyphs", help="glyphs.jsonl")
    ap.add_argument("zones", help="math_zones.json")
    ap.add_argument("--out", required=True, help="equations.json")
    ap.add_argument("--report", required=True, help="fidelity_report.json")
    ap.add_argument("--extract-report", default=None, help="可选: extract_report.json, 串联引擎信息")
    args = ap.parse_args()

    try:
        glyphs = [json.loads(l) for l in open(args.glyphs, encoding="utf-8") if l.strip()]
        zones_doc = json.load(open(args.zones, encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: 读取输入失败: {e}", file=sys.stderr)
        return 3
    glyphs_by_gid = {g["gid"]: g for g in glyphs}

    stats = {"replacements": 0, "replacement_detail": {}, "trusted_decoded": 0,
             "symbol_passthrough": 0, "unmapped": 0}
    unmapped, anomalies = [], []
    equations = []
    partial_zones = 0
    for zone in zones_doc.get("zones", []):
        eq, is_partial = linearize_zone(zone, glyphs_by_gid, stats, unmapped, anomalies)
        eq["id"] = f"eq-{len(equations) + 1:03d}"
        eq["partial"] = is_partial
        partial_zones += 1 if is_partial else 0
        equations.append(eq)

    # 全局特殊字体扫描: Symbol/ZapfDingbats 字体只承载特殊符号,
    # 即使不在公式区(如正文里的 dingbat 标记)也必须过映射台账, 绝不静默放过。
    zone_gids = {g for z in zones_doc.get("zones", []) for g in z.get("glyph_ids", [])}
    for g in glyphs:
        if g["gid"] in zone_gids or g["mode"] != "char":
            continue
        font = (g.get("font") or "").lower()
        if "symbol" in font or "zapfdingbats" in font:
            before = len(unmapped)
            map_char(g, stats, unmapped, g["page"])
            if len(unmapped) > before:
                unmapped[-1]["zone_id"] = None
                unmapped[-1]["context"] = "outside-math-zone"

    engine_info = None
    if args.extract_report:
        try:
            er = json.load(open(args.extract_report, encoding="utf-8"))
            engine_info = {"engine": er.get("engine"), "degrade_reason": er.get("degrade_reason"),
                           "degraded_pages": er.get("degraded_pages")}
        except Exception as e:
            engine_info = {"error": f"读取 extract_report 失败: {e}"}

    status = "clean"
    if unmapped or anomalies or partial_zones:
        status = "partial"

    report = {
        "tool": "linearize_math",
        "thresholds": {
            "script_size_ratio": SCRIPT_SIZE_RATIO,
            "script_offset_ratio": SCRIPT_OFFSET_RATIO,
            "baseline_tolerance_ratio": BASELINE_TOL_RATIO,
        },
        "engine": engine_info,
        "counts": {
            "equations": len(equations),
            "numbered": sum(1 for e in equations if e.get("number")),
            "replacements": stats["replacements"],
            "trusted_decoded": stats["trusted_decoded"],
            "unmapped": stats["unmapped"],
            "baseline_anomalies": len(anomalies),
            "partial_zones": partial_zones,
        },
        "notes": ["unmapped 台账覆盖公式区及全局 Symbol/ZapfDingbats 字体字符"],
        "replacement_detail": [
            {"font": k[0], "from": k[1], "to": k[2], "count": v}
            for k, v in sorted(stats["replacement_detail"].items())
        ],
        "unmapped_symbols": unmapped,
        "baseline_anomalies": anomalies,
        "status": status,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"tool": "linearize_math", "equations": equations}, f,
                  ensure_ascii=False, indent=2)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"equations": len(equations), "status": status,
                      "unmapped": stats["unmapped"], "anomalies": len(anomalies)},
                     ensure_ascii=False))
    return 0 if status == "clean" else 2


if __name__ == "__main__":
    sys.exit(main())
