#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_draft.py — 三态数字核验 + result.json 装配（仅 Python3 标准库）

对成稿中的每一个数字做三态（四种判定）核验：
  RAW-SUPPORTED        数字原文出现在材料行中（逐行边界匹配）；
  DERIVED-SUPPORTED    数字与某条重算派生量在容差内一致（相对容差默认 0.5%，
                       或把重算值按稿件数字的小数位数 round 后相等），注明公式；
  UNSUPPORTED          两者皆否，给出最接近的重算值提示，
                       必须删除 / 改写 / 标【待确认】；
  UNSUPPORTED-PVALUE   p 值不做计算（无 scipy、不做统计推断）；材料里查不到
                       该 p 值字符串时判为此类，必须删除或标【待确认】。

同时装配 result.json：原样包含 case.json 中 output_contract 的全部字段
与 case_id，并附诚实的 status / sources / uncertainty / change_log /
recalc_summary（重算派生量总数、各判定计数、核验通过率）。
无内容的字段填 "PENDING"。

可编辑产物（deliverable）会复制到输出目录；如本机存在 pandoc 则尽力渲染
PDF 预览，不存在时如实记录，不伪造。

退出码：0 成功（含部分完成）；2 硬失败（缺草稿 / case.json 无法解析等）。
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# 数字抽取：整数/小数/科学计数，避免吞掉单词与相邻小数点
NUM_RE = re.compile(r"(?<![\w.])([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(?![\w.])")
# p 值上下文：数字前 12 字符内出现 p = / p< / P 值= 等
PCTX_RE = re.compile(r"[pPＰ]\s*(?:值)?\s*[=<>≤≥＜＝＞]\s*$")
# 材料文本扩展名（用于 RAW 原文匹配）
TEXT_SUFFIXES = {".csv", ".tsv", ".md", ".txt", ".json"}


def fmt(x):
    if x is None:
        return "NA"
    if isinstance(x, float):
        return f"{x:.6g}"
    return str(x)


def decimals_of(s):
    """稿件数字字符串的小数位数（用于舍入容差）。"""
    s = s.lstrip("+-")
    if "e" in s.lower():
        return 0  # 科学计数法不参与小数位舍入容差
    if "." in s:
        return len(s.split(".", 1)[1])
    return 0


def load_materials(input_dir, exclude):
    """读入全部材料文本行，排除草稿自身，防止草稿数字自我佐证。
    返回 [(文件名, 行号, 行文本), ...]"""
    corpus = []
    for p in sorted(Path(input_dir).rglob("*")):
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if exclude and p.resolve() == exclude:
            continue
        try:
            for i, line in enumerate(
                    p.read_text(encoding="utf-8", errors="replace")
                    .splitlines(), 1):
                corpus.append((p.name, i, line))
        except OSError:
            continue
    return corpus


def raw_match(num_str, corpus):
    """RAW 匹配：数字原文（带边界）出现在任一材料行中。"""
    pat = re.compile(r"(?<![\d.])" + re.escape(num_str.lstrip("+"))
                     + r"(?![\d.])")
    for fname, lineno, line in corpus:
        if pat.search(line):
            return fname, lineno, line.strip()
    return None


# 语义线索 → 期望的派生量 kind（按优先级；命中后只在该 kind 内匹配，
# 防止"均值 4.79"这类错误数字误中 max=4.8 等同值不同义的重算量）
KIND_CUES = [
    (("pct_change",), ("%", "％", "百分比", "变化")),
    (("mean",), ("均值", "平均", "mean", "average")),
    (("sem",), ("sem", "标准误")),
    (("sd",), ("标准差", "sd")),
    (("median",), ("中位", "median")),
    (("max",), ("最大", "最高", "max")),
    (("min",), ("最小", "最低", "min")),
    (("ratio",), ("比值", "倍")),
    (("diff",), ("差值",)),
    (("n",), ("n=", "n =", "样本量", "例数")),
]


def expected_kinds(context, pos=None):
    """根据数字上下文推断期望的派生量 kind；无线索返回 None（全部候选）。

    给定数字在 context 中的位置 pos 时，取离数字最近的语义线索，
    避免上一句的 "%" 等跨句线索误配（如"均值 4.79"误配 pct_change）。
    """
    ctx = context.lower()
    if pos is None:
        for kinds, cues in KIND_CUES:
            if any(c.lower() in ctx for c in cues):
                return set(kinds)
        return None
    best = None  # (距离, 优先级序号, kinds)
    for idx, (kinds, cues) in enumerate(KIND_CUES):
        for cue in cues:
            cl = cue.lower()
            start = 0
            while True:
                i = ctx.find(cl, start)
                if i < 0:
                    break
                d = abs(i - pos)
                if best is None or d < best[0] or (d == best[0] and idx < best[1]):
                    best = (d, idx, kinds)
                start = i + 1
    return set(best[2]) if best else None


def derived_match(value, num_str, candidates, rel_tol):
    """DERIVED 匹配：相对容差内，或按稿件小数位数 round 后相等。"""
    dec = decimals_of(num_str)
    for v in candidates:
        dv = v.get("value")
        if not isinstance(dv, (int, float)):
            continue
        rel = abs(value - dv) / max(abs(dv), 1e-12)
        if rel <= rel_tol or round(dv, dec) == value:
            return v
    return None


def nearest_hint(value, candidates):
    """UNSUPPORTED 提示：候选池内相对偏差最小的重算值。"""
    best, best_rel = None, None
    for v in candidates:
        dv = v.get("value")
        if not isinstance(dv, (int, float)):
            continue
        rel = abs(value - dv) / max(abs(dv), 1e-12)
        if best is None or rel < best_rel:
            best, best_rel = v, rel
    if best is None:
        return "（无任何重算值可参照）"
    return (f"最接近的重算值为 {fmt(best['value'])}"
            f"（{best['kind']}，公式：{best['formula']}；"
            f"输入：{json.dumps(best['inputs'], ensure_ascii=False)}）")


def assemble_result(case, verdicts, derived, sources, mode_notes,
                    deliverable_name, preview_note):
    """按 output_contract 装配 result.json；无内容字段填 PENDING。"""
    contract = case.get("output_contract", {})
    keys = list(contract.keys()) if isinstance(contract, dict) else \
        list(contract) if isinstance(contract, list) else []
    counts = {"RAW-SUPPORTED": 0, "DERIVED-SUPPORTED": 0,
              "UNSUPPORTED": 0, "UNSUPPORTED-PVALUE": 0}
    for v in verdicts:
        counts[v["verdict"]] += 1
    total = len(verdicts)
    passed = counts["RAW-SUPPORTED"] + counts["DERIVED-SUPPORTED"]
    bad = [v for v in verdicts if v["verdict"].startswith("UNSUPPORTED")]

    preserved = [
        f"{v['text']} — {v['verdict']} — {v.get('evidence', '')}"
        for v in verdicts if v["verdict"] in
        ("RAW-SUPPORTED", "DERIVED-SUPPORTED")
    ]
    evidence_map = {
        v["text"]: {"verdict": v["verdict"],
                    "evidence": v.get("evidence", ""),
                    "context": v["context"]}
        for v in verdicts
    }
    change_log = [
        {"number": v["text"], "verdict": v["verdict"],
         "action": "删除 / 改写 / 标【待确认】", "hint": v.get("hint", "")}
        for v in bad
    ]

    result = {
        "case_id": case.get("case_id", "PENDING"),
        "deliverable": deliverable_name or "PENDING",
        "preserved_facts": preserved or "PENDING",
        "evidence_map": evidence_map or "PENDING",
        "change_log": change_log or "PENDING",
        "status": "complete" if not bad else "partial",
        "sources": sources or "PENDING",
        "uncertainty": mode_notes or "PENDING",
        "recalc_summary": {
            "derived_total": derived.get("derived_count", 0),
            "numbers_extracted": total,
            "raw_supported": counts["RAW-SUPPORTED"],
            "derived_supported": counts["DERIVED-SUPPORTED"],
            "unsupported": counts["UNSUPPORTED"],
            "unsupported_pvalue": counts["UNSUPPORTED-PVALUE"],
            "verify_pass_rate": round(passed / total, 4) if total else None,
        },
        "preview": preview_note,
    }
    # 契约字段兜底：output_contract 声明但上方未覆盖的键补 PENDING
    for k in keys:
        result.setdefault(k, "PENDING")
    return result, counts


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="三态数字核验并装配 result.json（仅标准库）")
    ap.add_argument("--draft", required=True, help="待核验的成稿（md/txt）")
    ap.add_argument("--input-dir", default="/input", help="输入材料目录")
    ap.add_argument("--derived", default="/app/output/derived_values.json",
                    help="recalc.py 生成的 derived_values.json")
    ap.add_argument("--case", default="/input/case.json",
                    help="案例 case.json（含 output_contract 与 case_id）")
    ap.add_argument("--output-dir", default="/app/output", help="输出目录")
    ap.add_argument("--rel-tol", type=float, default=0.005,
                    help="相对容差，默认 0.005（0.5%%）")
    args = ap.parse_args(argv)

    draft_path = Path(args.draft)
    out_dir = Path(args.output_dir)
    if not draft_path.is_file():
        print(f"[硬失败] 草稿不存在: {draft_path}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    draft_text = draft_path.read_text(encoding="utf-8", errors="replace")

    # —— case.json ——
    case = {}
    case_path = Path(args.case)
    if case_path.is_file():
        try:
            case = json.loads(case_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[硬失败] case.json 解析失败: {e}", file=sys.stderr)
            return 2
    else:
        print(f"[警告] 未找到 case.json: {case_path}，"
              "result.json 仅含默认字段", file=sys.stderr)

    # —— 重算派生量 ——
    derived = {"derived_count": 0, "values": []}
    dpath = Path(args.derived)
    mode_notes = ["本工具不计算 p 值与统计显著性（无 scipy，不做统计推断）；"
                  "p 值仅核对字符串是否与材料一致。"]
    if dpath.is_file():
        try:
            derived = json.loads(dpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            mode_notes.append(f"derived_values.json 解析失败（{e}），"
                              "降级为仅原文数字核对。")
    else:
        mode_notes.append("未找到 derived_values.json，"
                          "降级为仅原文数字核对（RAW / UNSUPPORTED 两态）。")
    values = derived.get("values", [])

    # —— 材料语料（排除草稿自身）——
    corpus = load_materials(args.input_dir, draft_path.resolve())
    sources = sorted({c[0] for c in corpus})

    # —— 三态核验 ——
    verdicts = []
    for m in NUM_RE.finditer(draft_text):
        s = m.group(1)
        try:
            value = float(s)
        except ValueError:
            continue
        start, end = m.span(1)
        context = draft_text[max(0, start - 60):end + 60].replace("\n", " ")
        is_pct = draft_text[end:end + 1] in ("%", "％")
        is_p = bool(PCTX_RE.search(draft_text[max(0, start - 12):start]))
        entry = {"text": s + ("%" if is_pct else ""), "context": context}
        hit = raw_match(s, corpus)
        if is_p and not hit:
            entry["verdict"] = "UNSUPPORTED-PVALUE"
            entry["evidence"] = "材料中查不到该 p 值字符串"
            entry["hint"] = "本环境不计算 p 值；材料未给出的 p 值必须删除或标【待确认】"
        elif hit:
            entry["verdict"] = "RAW-SUPPORTED"
            entry["evidence"] = f"{hit[0]} 第{hit[1]}行原文：{hit[2][:80]}"
        else:
            # 按上下文语义过滤候选 kind，避免同值不同义的容差误报
            kinds = expected_kinds(context, start - max(0, start - 60))
            candidates = ([v for v in values if v.get("kind") in kinds]
                          if kinds else values)
            rec = derived_match(value, s, candidates, args.rel_tol)
            if rec:
                entry["verdict"] = "DERIVED-SUPPORTED"
                entry["evidence"] = (f"重算值 {fmt(rec['value'])}（{rec['id']}，"
                                     f"公式：{rec['formula']}；输入："
                                     f"{json.dumps(rec['inputs'], ensure_ascii=False)}）")
            else:
                entry["verdict"] = "UNSUPPORTED"
                entry["evidence"] = ("材料原文与重算派生量均不匹配"
                                     + (f"（已按上下文限定 kind={sorted(kinds)}）"
                                        if kinds else ""))
                entry["hint"] = nearest_hint(value, candidates)
        verdicts.append(entry)

    # —— verify_report.md ——
    rep = ["# 数字核验报告（verify_report）", "",
           f"草稿：`{draft_path.name}`；抽取数字 {len(verdicts)} 个；"
           f"相对容差 {args.rel_tol:.4%}。", "",
           "| 数字 | 判定 | 依据 / 提示 |", "|---|---|---|"]
    for v in verdicts:
        detail = v.get("evidence", "")
        if v.get("hint"):
            detail += "；" + v["hint"]
        rep.append(f"| {v['text']} | **{v['verdict']}** | {detail} |")
    rep += ["", "UNSUPPORTED / UNSUPPORTED-PVALUE 必须删除、改写为账上数字，"
            "或标注【待确认】后方可交付。", ""]
    (out_dir / "verify_report.md").write_text("\n".join(rep), encoding="utf-8")

    # —— 可编辑产物 + 尽力渲染预览 ——
    deliverable_name = ""
    preview_note = "PENDING"
    try:
        shutil.copyfile(draft_path, out_dir / draft_path.name)
        deliverable_name = draft_path.name
        pandoc = shutil.which("pandoc")
        if pandoc:
            pdf = out_dir / (draft_path.stem + ".pdf")
            r = subprocess.run([pandoc, str(out_dir / draft_path.name),
                                "-o", str(pdf)],
                               capture_output=True, timeout=120)
            preview_note = ("pandoc 渲染 PDF 预览成功: " + pdf.name) \
                if r.returncode == 0 else \
                "pandoc 存在但渲染失败: " + r.stderr.decode("utf-8", "replace")[:200]
        else:
            preview_note = "本机无 pandoc，未渲染 PDF/PNG 预览（如实记录，未伪造）。"
    except OSError as e:
        mode_notes.append(f"deliverable 复制失败: {e}")

    # —— result.json 装配 ——
    result, counts = assemble_result(case, verdicts, derived, sources,
                                     mode_notes, deliverable_name, preview_note)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[核验完成] RAW={counts['RAW-SUPPORTED']} "
          f"DERIVED={counts['DERIVED-SUPPORTED']} "
          f"UNSUPPORTED={counts['UNSUPPORTED']} "
          f"UNSUPPORTED-PVALUE={counts['UNSUPPORTED-PVALUE']} → "
          f"{out_dir}/verify_report.md, result.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
