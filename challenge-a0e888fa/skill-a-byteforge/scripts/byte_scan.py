#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""byte_scan.py — 存储/编码层故障取证扫描器（Python 3 标准库，确定性，只读输入）。

对一个数据表文件做字节级诊断，输出三份产物到 --out 目录：
  fault_report.json          机器可读故障清单（每项含证据与评分）
  fault_report.md            人读紧凑摘要（供 Agent 一次读完）
  suggested_repair_map.json  修复草案（全部 approved=false，须人工/Agent 审批）

不做任何语义判断：哨兵缺失码只报告"出现位置与计数"，其语义（未检测/低于检出限/
录入缺失/真值 0）由数据字典与工单决定，本脚本绝不插补。
退出码：0 正常；2 参数/文件错误；3 文件无法以任何候选编码解码。
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys

CANDIDATE_CODECS = ["utf-8", "utf-8-sig", "gb18030", "big5", "latin-1"]
DELIMITERS = [",", "\t", ";", "|"]
SENTINEL_TOKENS = ["-999", "-9999", "-99", "NA", "N/A", "null", "NULL",
                   "None", "nan", "NaN", "ND", "n.d.", "—", "–", "空白", "缺失"]
INVISIBLE = {" ": "NBSP", "​": "ZWSP", "‌": "ZWNJ", "‍": "ZWJ",
             "﻿": "BOM-in-body", "　": "IDEOGRAPHIC-SPACE"}
RE_FULLWIDTH = re.compile(r"[０-９Ａ-Ｚａ-ｚ．，％]")
RE_SCI = re.compile(r"^[+-]?\d+(\.\d+)?[eE][+-]?\d+$")
RE_THOUSAND = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$")
RE_DECIMAL_COMMA = re.compile(r"^[+-]?\d+,\d+$")
RE_NUM_WITH_UNIT = re.compile(r"^[+-]?\d+(\.\d+)?\s*[a-zA-Zμµ%/]+[a-zA-Zμµ%/0-9.·^-]*$")
RE_DATE = re.compile(r"^(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{8})$")
RE_LT_LOD = re.compile(r"^<\s*\d")
MOJIBAKE_HINT = re.compile(
    r"[À-Åà-åÂÃÄÅæçèéêðñòóôõöøùúûüýþÿµ¹º»¼½¾¿"
    r"€‚ƒ„…†‡ˆ‰Š‹ŒŽ''""•–—˜™š›œžŸ]")


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def score_decode(text):
    """打分解码结果：替换符与控制字符扣分，CJK/可打印比例加分。"""
    if text is None:
        return -1.0
    bad = text.count("�")
    ctrl = sum(1 for c in text if ord(c) < 32 and c not in "\t\n\r")
    printable = sum(1 for c in text if c.isprintable() or c in "\t\n\r")
    ratio = printable / max(1, len(text))
    return ratio - 2.0 * (bad + ctrl) / max(1, len(text))


def try_decodes(raw):
    results = []
    for codec in CANDIDATE_CODECS:
        try:
            text = raw.decode(codec)
        except (UnicodeDecodeError, LookupError):
            results.append({"codec": codec, "ok": False, "score": -1.0})
            continue
        results.append({"codec": codec, "ok": True, "score": round(score_decode(text), 6),
                        "text": text})
    ok = [r for r in results if r["ok"]]
    ok.sort(key=lambda r: -r["score"])
    # 严格 UTF-8 优先：UTF-8 结构自同步，长文本偶然合法的概率极低；
    # 若 UTF-8 可严格解码，永远优先于 gb18030/big5/latin-1 的"巧合解码"。
    utf8_ok = [r for r in ok if r["codec"] in ("utf-8", "utf-8-sig")]
    if utf8_ok:
        best_utf8 = max(utf8_ok, key=lambda r: r["score"])
        rest = [r for r in ok if r is not best_utf8]
        return [best_utf8] + rest
    return ok


def mojibake_candidates(text, sample_lines=3):
    """检测经典双重编码 mojibake：UTF-8 字节被按 latin-1 解码后再存为 UTF-8。"""
    cands = []
    hint = len(MOJIBAKE_HINT.findall(text))
    if hint == 0:
        return cands
    try:
        repaired = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return cands
    hint_after = len(MOJIBAKE_HINT.findall(repaired))
    cjk_before = sum(1 for c in text if "一" <= c <= "鿿")
    cjk_after = sum(1 for c in repaired if "一" <= c <= "鿿")
    gain = (hint - hint_after) + 0.5 * (cjk_after - cjk_before)
    if gain > 0:
        before = [l for l in text.splitlines() if MOJIBAKE_HINT.search(l)][:sample_lines]
        after = []
        for l in before:
            try:
                after.append(l.encode("latin-1").decode("utf-8"))
            except (UnicodeEncodeError, UnicodeDecodeError):
                after.append("<无法修复该行>")
        score = min(0.99, 0.5 + 0.5 * (hint - hint_after) / max(1, hint))
        cands.append({"via": "latin1_utf8", "score": round(score, 3),
                      "mojibake_chars_before": hint, "mojibake_chars_after": hint_after,
                      "cjk_before": cjk_before, "cjk_after": cjk_after,
                      "before_sample": before, "after_sample": after})
    return cands


def eol_stats(text):
    return {"CRLF": text.count("\r\n"), "LF": text.count("\n") - text.count("\r\n"),
            "CR": len(re.findall(r"\r(?!\n)", text))}


def delimiter_stats(text):
    lines = [l for l in text.splitlines() if l.strip()]
    best = None
    for d in DELIMITERS:
        counts = [len(l.split(d)) for l in lines[:200]]
        if not counts:
            continue
        mode = max(set(counts), key=counts.count)
        consistency = counts.count(mode) / len(counts)
        cand = {"delimiter": d, "fields": mode, "consistency": round(consistency, 4),
                "score": round(consistency * mode, 4)}
        if best is None or cand["score"] > best["score"]:
            best = cand
    return best, lines


def scan_cells(lines, delimiter, max_rows=5000):
    findings = {"invisible": {}, "fullwidth": 0, "sentinels": {}, "sci_notation": 0,
                "thousand_sep": 0, "decimal_comma": 0, "num_with_unit": 0,
                "date_like": 0, "below_lod": 0}
    reader = csv.reader(io.StringIO("\n".join(lines[:max_rows])), delimiter=delimiter)
    sentinel_set = set(SENTINEL_TOKENS)
    for r, row in enumerate(reader, 1):
        for c, cell in enumerate(row, 1):
            for ch, name in INVISIBLE.items():
                if ch in cell:
                    key = "%s@%d处" % (name, cell.count(ch))
                    findings["invisible"][key] = findings["invisible"].get(key, 0) + 1
            if RE_FULLWIDTH.search(cell):
                findings["fullwidth"] += 1
            tok = cell.strip()
            if tok in sentinel_set:
                findings["sentinels"][tok] = findings["sentinels"].get(tok, 0) + 1
            if RE_SCI.match(tok):
                findings["sci_notation"] += 1
            elif RE_NUM_WITH_UNIT.match(tok):
                findings["num_with_unit"] += 1
            if RE_THOUSAND.match(tok):
                findings["thousand_sep"] += 1
            elif RE_DECIMAL_COMMA.match(tok) and delimiter != ",":
                findings["decimal_comma"] += 1
            if RE_DATE.match(tok):
                findings["date_like"] += 1
            if RE_LT_LOD.match(tok):
                findings["below_lod"] += 1
    return findings


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="待诊断的数据表文件")
    ap.add_argument("--dict", dest="dictfile", default=None, help="数据字典文件（可选，仅用于交叉引用术语）")
    ap.add_argument("--out", required=True, help="产物输出目录")
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        print("ERROR: 文件不存在: %s" % args.file, file=sys.stderr)
        sys.exit(2)
    raw = open(args.file, "rb").read()
    os.makedirs(args.out, exist_ok=True)

    report = {"file": os.path.abspath(args.file), "bytes": len(raw),
              "sha256": sha256_bytes(raw), "faults": [], "structure": {}}

    # 1) BOM
    bom = None
    for sig, name in [(b"\xef\xbb\xbf", "UTF-8-BOM"), (b"\xff\xfe", "UTF-16LE-BOM"),
                      (b"\xfe\xff", "UTF-16BE-BOM")]:
        if raw.startswith(sig):
            bom = name
            break
    if bom:
        report["faults"].append({"type": "bom", "evidence": bom,
                                 "severity": "low", "score": 0.99})

    # 2) 解码候选
    ok = try_decodes(raw)
    if not ok:
        print("ERROR: 无法以任何候选编码解码: %s" % args.file, file=sys.stderr)
        sys.exit(3)
    best = ok[0]
    report["structure"]["decode"] = {"chosen": best["codec"], "score": best["score"],
                                     "alternatives": [{"codec": r["codec"], "score": r["score"]}
                                                      for r in ok[1:3]]}
    if (best["codec"] not in ("utf-8", "utf-8-sig")
            and len(ok) > 1 and ok[1]["score"] > best["score"] - 0.02):
        # 仅在无严格 UTF-8 可解时，两个非 UTF-8 候选才构成真歧义
        report["faults"].append({"type": "encoding_ambiguous",
                                 "evidence": {"chosen": best["codec"],
                                              "rival": ok[1]["codec"]},
                                 "severity": "medium", "score": 0.5, "ambiguous": True})
    if best["codec"] not in ("utf-8", "utf-8-sig"):
        report["faults"].append({"type": "non_utf8_encoding",
                                 "evidence": {"codec": best["codec"]},
                                 "severity": "high", "score": 0.9})
    text = best["text"]

    # 3) mojibake
    moj = mojibake_candidates(text)
    for m in moj:
        report["faults"].append({"type": "mojibake_double_encoding",
                                 "evidence": {k: m[k] for k in
                                              ("via", "mojibake_chars_before",
                                               "mojibake_chars_after",
                                               "before_sample", "after_sample")},
                                 "severity": "high", "score": m["score"]})

    # 4) 行尾
    eol = eol_stats(text)
    report["structure"]["eol"] = eol
    kinds = [k for k, v in eol.items() if v > 0]
    if len(kinds) > 1:
        report["faults"].append({"type": "mixed_eol", "evidence": eol,
                                 "severity": "low", "score": 0.95})

    # 5) 分隔符
    dbest, lines = delimiter_stats(text)
    report["structure"]["delimiter"] = {k: (v if k != "delimiter" else
                                            {"\t": "TAB"}.get(v, v))
                                        for k, v in dbest.items()}
    if dbest["consistency"] < 0.98:
        report["faults"].append({"type": "ragged_rows",
                                 "evidence": {"delimiter": dbest["delimiter"],
                                              "consistency": dbest["consistency"]},
                                 "severity": "medium", "score": 0.6, "ambiguous": True})

    # 6) 单元格级
    cellfind = scan_cells(lines, dbest["delimiter"])
    report["structure"]["cell_findings"] = cellfind
    if cellfind["invisible"]:
        report["faults"].append({"type": "invisible_chars",
                                 "evidence": cellfind["invisible"],
                                 "severity": "medium", "score": 0.9})
    if cellfind["fullwidth"]:
        report["faults"].append({"type": "fullwidth_chars",
                                 "evidence": {"cells": cellfind["fullwidth"]},
                                 "severity": "medium", "score": 0.9})
    if cellfind["sentinels"]:
        report["faults"].append({"type": "sentinel_tokens",
                                 "evidence": dict(sorted(cellfind["sentinels"].items())),
                                 "severity": "info", "score": 0.99,
                                 "note": "仅报告出现计数；语义判定须查数据字典，本工具不插补"})
    if cellfind["thousand_sep"] and cellfind["decimal_comma"]:
        report["faults"].append({"type": "thousand_vs_decimal_comma",
                                 "evidence": {"thousand": cellfind["thousand_sep"],
                                              "decimal_comma": cellfind["decimal_comma"]},
                                 "severity": "high", "score": 0.4, "ambiguous": True})
    elif cellfind["thousand_sep"]:
        report["faults"].append({"type": "thousand_separator",
                                 "evidence": {"cells": cellfind["thousand_sep"]},
                                 "severity": "medium", "score": 0.8})
    if cellfind["sci_notation"]:
        report["faults"].append({"type": "scientific_notation_text",
                                 "evidence": {"cells": cellfind["sci_notation"]},
                                 "severity": "low", "score": 0.9,
                                 "note": "保留字面值与精度，不得用浮点重写"})
    if cellfind["num_with_unit"]:
        report["faults"].append({"type": "number_with_embedded_unit",
                                 "evidence": {"cells": cellfind["num_with_unit"]},
                                 "severity": "medium", "score": 0.85})

    # 7) 修复草案
    repairs = {"input_file": os.path.abspath(args.file),
               "input_sha256": report["sha256"], "repairs": []}

    def add(op, score, evidence, ambiguous=False, reversible=True):
        repairs["repairs"].append({"id": "R%02d" % (len(repairs["repairs"]) + 1),
                                   "op": op, "score": score, "evidence": evidence,
                                   "approved": False, "ambiguous": ambiguous,
                                   "reversible": reversible})

    if best["codec"] not in ("utf-8",):
        add({"op": "decode", "from": best["codec"]}, 0.9,
            {"codec": best["codec"]})
    for m in moj:
        add({"op": "mojibake_fix", "via": m["via"]}, m["score"],
            {"before": m["before_sample"][:1], "after": m["after_sample"][:1]},
            ambiguous=m["score"] < 0.8)
    if bom == "UTF-8-BOM":
        add({"op": "strip_bom"}, 0.99, {"bom": bom})
    if len(kinds) > 1:
        add({"op": "normalize_eol", "to": "\\n"}, 0.95, eol)
    if dbest["delimiter"] != "," and dbest["consistency"] >= 0.98:
        add({"op": "set_delimiter", "delimiter": dbest["delimiter"]}, 0.9,
            {"consistency": dbest["consistency"], "fields": dbest["fields"]})
    if cellfind["invisible"]:
        add({"op": "strip_invisible", "chars": sorted(set(
            ch for key in cellfind["invisible"] for ch in INVISIBLE
            if key.startswith(INVISIBLE[ch])))}, 0.9, cellfind["invisible"])
    if cellfind["fullwidth"]:
        add({"op": "fullwidth_to_ascii"}, 0.9, {"cells": cellfind["fullwidth"]})

    # 8) 写产物
    with open(os.path.join(args.out, "fault_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "suggested_repair_map.json"), "w",
              encoding="utf-8") as f:
        json.dump(repairs, f, ensure_ascii=False, indent=2)

    md = ["# 故障取证报告（紧凑版）", "",
          "- 文件: `%s`" % report["file"],
          "- 字节: %d | sha256: `%s`" % (report["bytes"], report["sha256"][:16] + "…"),
          "- 解码: %s (score %.3f) | 行尾: %s | 分隔符: %s (%d 列, 一致性 %.3f)" % (
              best["codec"], best["score"], eol,
              {"\t": "TAB"}.get(dbest["delimiter"], dbest["delimiter"]),
              dbest["fields"], dbest["consistency"]), "",
          "## 故障清单（%d 项）" % len(report["faults"]), ""]
    for i, ft in enumerate(report["faults"], 1):
        ev = json.dumps(ft["evidence"], ensure_ascii=False)
        if len(ev) > 220:
            ev = ev[:220] + "…"
        md.append("%d. **%s** [%s, score=%.2f%s] %s" % (
            i, ft["type"], ft["severity"], ft["score"],
            ", 歧义" if ft.get("ambiguous") else "", ev))
    md += ["", "## 建议修复（草案，均未批准）", ""]
    for r in repairs["repairs"]:
        md.append("- %s `%s` score=%.2f%s" % (
            r["id"], json.dumps(r["op"], ensure_ascii=False), r["score"],
            " ⚠歧义" if r["ambiguous"] else ""))
    md += ["", "下一步：对照数据字典与工单审批 suggested_repair_map.json → repair_apply.py → roundtrip_check.py"]
    with open(os.path.join(args.out, "fault_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    print(json.dumps({"status": "ok", "faults": len(report["faults"]),
                      "decode": best["codec"],
                      "out": os.path.abspath(args.out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
