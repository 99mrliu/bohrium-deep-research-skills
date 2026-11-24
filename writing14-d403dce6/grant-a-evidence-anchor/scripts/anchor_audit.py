#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""anchor_audit.py — 证据锚定核验：每条 quote 必须是其声明来源文本的逐字子串。

输入：
  --evidence   evidence_map.json（{"entries": [...]} 或直接条目数组；条目 schema
               见 references/evidence_map.schema.json）
  --src-text   src_text 目录（extract_sources.py 的产物，默认 ./src_text）
  --inventory  materials_inventory.json（可选；用于 source_class 兜底判定）
  --out        报告输出路径（默认 ./anchor_audit_report.json）

校验规则（确定性，规则全文见 references/status_taxonomy.md 与 references/citation_rules.md）：
  1. quote 与来源文本分别经 NFKC 归一化 + 空白折叠后，quote 必须是来源文本的
     逐字子串；命中报告 char_offset，未命中给出最接近匹配的诊断（最长公共片段、
     其在来源中的偏移与上下文片段）。未命中 = error。
  2. status 必须属于 {已完成, 外部工作, 拟开展, 待确认}，否则 error。
  3. status=已完成 的条目，其来源类别必须判定为 applicant（申请人证据类）：
     优先取条目 source_class 字段；缺省时查 inventory 的 source_class_guess。
     判定为 external -> error（原论文/既有成果归外部作者，不得记为申请人已完成）；
     判定为 unknown -> warning（需人工确认）。
  4. citation（可选字段）若存在，需含作者/年份/标题要件（对象形式按键检查；
     字符串形式按启发式检查 4 位年份、文字与长度）；缺件 = warning（不判 error，
     无法核实的引用应标"未核验"，见 references/citation_rules.md）。

退出码：0 无 error（可有 warning）；1 存在任一 error；2 参数/输入文件错误。
输出确定性：条目按输入顺序，JSON 排序键、无时间戳，二次运行字节一致。
"""
import argparse
import difflib
import json
import os
import re
import sys
import unicodedata

VALID_STATUS = ["已完成", "外部工作", "拟开展", "待确认"]


def normalize(s):
    """NFKC 归一化 + 空白折叠。"""
    return " ".join(unicodedata.normalize("NFKC", s).split())


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_text_path(src_dir, file_field):
    """按确定顺序尝试把 evidence_map 的 source.file 映射到 src_text 内的文本文件。"""
    base = os.path.basename(file_field)
    stem = os.path.splitext(base)[0]
    candidates = [file_field, base, base + ".txt", stem + ".txt"]
    for cand in candidates:
        p = os.path.join(src_dir, cand)
        if os.path.isfile(p):
            return p
    return None


def diagnose(src, quote):
    """quote 未逐字命中时，给出最接近匹配的诊断（确定性）。"""
    if not src or not quote:
        return {"reason": "来源文本或 quote 为空"}
    sm = difflib.SequenceMatcher(None, src, quote, autojunk=False)
    m = max(sm.get_matching_blocks(), key=lambda b: b.size)
    if m.size == 0:
        return {"longest_common_chars": 0,
                "hint": "与来源文本无任何公共片段，source.file 可能指向了错误的文件"}
    a, b, size = m.a, m.b, m.size
    snippet = src[max(0, a - 25): a + size + 25]
    return {
        "longest_common_chars": size,
        "quote_chars": len(quote),
        "source_offset": a,
        "source_snippet": snippet,
        "quote_unmatched_head": quote[max(0, b - 15):b] if b > 0 else "",
        "quote_unmatched_tail": quote[b + size: b + size + 15] if b + size < len(quote) else "",
        "hint": "quote 与来源在最长公共片段之外存在差异，疑似改写/凭印象引用；请复制原文",
    }


def check_citation(c):
    """返回 warning 列表。citation 不存在时不检查。"""
    warns = []
    if c is None:
        return warns
    if isinstance(c, dict):
        for key, label in (("authors", "作者"), ("year", "年份"), ("title", "标题")):
            if not c.get(key):
                warns.append("引用缺%s要件" % label)
    elif isinstance(c, str):
        if not re.search(r"(19|20)\d{2}", c):
            warns.append("引用缺年份要件")
        if not re.search(r"[A-Za-z一-鿿]", c):
            warns.append("引用缺作者/标题文字")
        if len(c.strip()) < 12:
            warns.append("引用过短，可能缺标题要件")
    else:
        warns.append("citation 字段类型无法识别（应为对象或字符串）")
    return warns


def build_inventory_index(inv):
    by_path, by_base = {}, {}
    for rec in inv.get("files", []):
        by_path[rec["path"]] = rec
        by_base[os.path.basename(rec["path"])] = rec
    return by_path, by_base


def resolve_source_class(entry, inv_index):
    """返回 (source_class, rule)。优先 evidence_map.source_class，其次 inventory。"""
    sc = entry.get("source_class")
    if isinstance(sc, str) and sc.strip():
        return sc.strip(), "evidence_map.source_class"
    if inv_index is not None:
        by_path, by_base = inv_index
        file_field = (entry.get("source") or {}).get("file", "")
        rec = by_path.get(file_field) or by_base.get(os.path.basename(file_field))
        if rec is not None:
            return rec.get("source_class_guess", "unknown"), "materials_inventory.source_class_guess"
    return "unknown", "none"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="核验 evidence_map：quote 逐字锚定、四态合法、已完成归属申请人、citation 要件。",
        epilog="退出码：0 无错误；1 存在错误；2 参数/输入错误。",
    )
    ap.add_argument("--evidence", required=True, help="evidence_map.json 路径")
    ap.add_argument("--src-text", default="src_text", help="src_text 目录（默认 ./src_text）")
    ap.add_argument("--inventory", default=None, help="materials_inventory.json（可选）")
    ap.add_argument("--out", default="anchor_audit_report.json", help="报告输出路径")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.evidence):
        print("错误：evidence_map 不存在：%s" % args.evidence, file=sys.stderr)
        return 2
    if not os.path.isdir(args.src_text):
        print("错误：src_text 目录不存在：%s" % args.src_text, file=sys.stderr)
        return 2
    try:
        data = load_json(args.evidence)
    except (OSError, json.JSONDecodeError) as exc:
        print("错误：evidence_map 解析失败：%s" % exc, file=sys.stderr)
        return 2
    entries = data.get("entries") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        print("错误：evidence_map 应为条目数组或含 entries 数组的对象", file=sys.stderr)
        return 2

    inv_index = None
    if args.inventory:
        if not os.path.isfile(args.inventory):
            print("错误：inventory 不存在：%s" % args.inventory, file=sys.stderr)
            return 2
        try:
            inv_index = build_inventory_index(load_json(args.inventory))
        except (OSError, json.JSONDecodeError) as exc:
            print("错误：inventory 解析失败：%s" % exc, file=sys.stderr)
            return 2

    text_cache = {}
    results = []
    n_err = n_warn = 0
    by_status = {s: 0 for s in VALID_STATUS}
    for i, entry in enumerate(entries):
        rid = entry.get("id", "#%d" % (i + 1))
        errs, warns = [], []
        status = entry.get("status")
        if status not in VALID_STATUS:
            errs.append("status 非法：%r（合法值：%s）" % (status, "/".join(VALID_STATUS)))
        else:
            by_status[status] += 1

        source = entry.get("source") or {}
        file_field = source.get("file", "")
        quote = entry.get("quote", "")
        quote_found, char_offset, diagnosis = False, None, None
        if not file_field:
            errs.append("缺 source.file")
        elif not quote:
            errs.append("缺 quote（每条论断必须给出逐字 quote）")
        else:
            tpath = resolve_text_path(args.src_text, file_field)
            if tpath is None:
                errs.append("来源文件未在 src_text 中找到：%s" % file_field)
            else:
                if tpath not in text_cache:
                    with open(tpath, "r", encoding="utf-8") as f:
                        text_cache[tpath] = f.read()
                norm_src = normalize(text_cache[tpath])
                norm_quote = normalize(quote)
                idx = norm_src.find(norm_quote)
                if idx >= 0:
                    quote_found, char_offset = True, idx
                else:
                    diagnosis = diagnose(norm_src, norm_quote)
                    errs.append("quote 未逐字命中来源文本（疑似改写/凭印象引用）")

        sclass, class_rule = resolve_source_class(entry, inv_index)
        if status == "已完成":
            if sclass == "external":
                errs.append("status=已完成 但来源类别为 external：原论文/既有成果归外部作者，"
                            "不得记为申请人已完成（应改为 外部工作）")
            elif sclass != "applicant":
                warns.append("status=已完成 但来源类别未知（%s）：需人工确认其为申请人证据" % class_rule)

        warns.extend(check_citation(entry.get("citation")))

        n_err += len(errs)
        n_warn += len(warns)
        results.append({
            "id": rid,
            "status": status,
            "source_file": file_field,
            "source_loc": source.get("loc"),
            "quote_found": quote_found,
            "char_offset": char_offset,
            "diagnosis": diagnosis,
            "source_class": sclass,
            "source_class_rule": class_rule,
            "errors": errs,
            "warnings": warns,
        })

    report = {
        "evidence_map": os.path.abspath(args.evidence),
        "src_text_dir": os.path.abspath(args.src_text),
        "summary": {
            "total": len(results),
            "errors": n_err,
            "warnings": n_warn,
            "quote_missing": sum(1 for r in results if not r["quote_found"]),
            "by_status": by_status,
        },
        "entries": results,
    }
    try:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
    except OSError as exc:
        print("错误：写入报告失败：%s" % exc, file=sys.stderr)
        return 2

    print("锚定核验：%d 条，error=%d，warning=%d -> %s" % (len(results), n_err, n_warn, args.out))
    for r in results:
        for e in r["errors"]:
            print("  [ERROR] %s: %s" % (r["id"], e))
        for w in r["warnings"]:
            print("  [WARN ] %s: %s" % (r["id"], w))
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
