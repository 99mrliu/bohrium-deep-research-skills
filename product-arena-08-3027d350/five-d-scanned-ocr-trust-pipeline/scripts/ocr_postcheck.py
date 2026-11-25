#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ocr_postcheck.py — OCR 文本后处理校验与保守纠错（纯标准库）。

输入：OCR 纯文本（--ocr）。页与页之间以换页符 \\f 分隔（ocr-tool 输出
常见格式；无 \\f 时全文按 1 页处理）。真实评测时该文件来自 ocr-tool
对 handoff_ocr.json 所列页面的识别结果，获取方式见 SKILL.md。

规则（与 references/ocr-confusion-table.md 一致）：
  1. 混淆对单点替换：l/1/I/|、O/0、rn/m、cl/d、5/S、vv/w；
  2. 词典校验：token 小写命中 references/lexicon-en.txt 即视为正确；
  3. 保守修正：原 token 不在词典，单点替换后恰有【唯一】小写形式命中
     词典 → 改正并记 corrections 台账（page/line/from/to/rule）；
  4. 数字上下文：token 仅含一个非数字字符、两侧皆数字，且替换后全为
     数字 → 改正（rule=numeric_context）；
  5. 多解（≥2 种小写形式命中）或无解但 token 混入数字 → suspects
     列表原样保留，绝不改动。

输出（--outdir 下）：
  postcheck.json  corrections / suspects / 逐页统计
  corrected.txt   与原文同结构（\\f 分页），仅替换 corrections 台账处

退出码：0=成功，2=部分（OCR 文件为空等），3=失败。
"""
import argparse
import json
import re
import sys
from pathlib import Path

EXIT_OK, EXIT_PARTIAL, EXIT_FAIL = 0, 2, 3

# 单字符混淆对（双向按 OCR 真实出错方向列举，宁缺毋滥）
CONF_SINGLE = {
    "1": ["l", "i", "I"],
    "l": ["1", "I"],
    "I": ["1", "l"],
    "|": ["l", "1"],
    "0": ["o", "O"],
    "O": ["0"],
    "o": ["0"],
    "5": ["s", "S"],
    "S": ["5"],
    "s": ["5"],
}
# 多字符混淆对
CONF_MULTI = {
    "rn": ["m"], "m": ["rn"],
    "cl": ["d"], "d": ["cl"],
    "vv": ["w"], "w": ["vv"],
}
# 数字上下文回退：非数字字符 → 数字
CONF_TO_DIGIT = {"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "S": "5", "s": "5"}

TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")


def load_lexicon(path: Path):
    words = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        w = line.strip().lower()
        if w and not w.startswith("#"):
            words.add(w)
    return words


def candidates(token: str):
    """对 token 做全部单点混淆替换，返回 {小写形式: [替换形式,...]}（不含原 token）。"""
    cands = {}
    for i, ch in enumerate(token):
        for rep in CONF_SINGLE.get(ch, []):
            new = token[:i] + rep + token[i + 1:]
            if new != token:
                cands.setdefault(new.lower(), []).append(new)
    for pat, reps in CONF_MULTI.items():
        start = 0
        while True:
            j = token.find(pat, start)
            if j < 0:
                break
            for rep in reps:
                new = token[:j] + rep + token[j + len(pat):]
                if new != token:
                    cands.setdefault(new.lower(), []).append(new)
            start = j + 1
    return cands


def pick_case(variants, token):
    """同一小写形式的多个大小写变体中，按原 token 的大小写风格选择。"""
    if token.islower():
        for v in variants:
            if v.islower():
                return v
    return variants[0]


def numeric_context_fix(token: str):
    """token 仅一个非数字字符且两侧皆数字 → 返回替换后全数字串，否则 None。"""
    if len(token) < 3 or not any(c.isdigit() for c in token):
        return None
    nondigit = [i for i, c in enumerate(token) if not c.isdigit()]
    if len(nondigit) != 1:
        return None
    i = nondigit[0]
    rep = CONF_TO_DIGIT.get(token[i])
    if rep is None:
        return None
    left_ok = i > 0 and token[i - 1].isdigit()
    right_ok = i < len(token) - 1 and token[i + 1].isdigit()
    if left_ok and right_ok:
        return token[:i] + rep + token[i + 1:]
    return None


def has_confusable_shape(token: str):
    """用于无解 suspect 判定：字母中混入数字（典型 OCR 混淆残迹）。"""
    return any(c.isdigit() for c in token) and any(c.isalpha() for c in token)


def process_text(text: str, lexicon):
    pages = text.split("\f")
    corrections, suspects, unknown_words = [], [], []
    corrected_pages = []
    per_page = {}
    total_tokens = 0
    for pno, ptext in enumerate(pages, start=1):
        lines = ptext.split("\n")
        out_lines = []
        pg_tok = pg_corr = pg_susp = 0
        for lno, line in enumerate(lines, start=1):
            spans = []
            for m in TOKEN_RE.finditer(line):
                tok = m.group(0)
                if len(tok) < 2 or tok.isdigit():
                    continue
                if "@" in tok or "://" in tok:
                    continue
                total_tokens += 1
                pg_tok += 1
                low = tok.lower()
                if low in lexicon:
                    continue
                cands = candidates(tok)
                hits = {k: v for k, v in cands.items() if k in lexicon}
                if len(hits) == 1:
                    low_form, variants = next(iter(hits.items()))
                    new = pick_case(variants, tok)
                    corrections.append({"page": pno, "line": lno, "from": tok,
                                        "to": new, "rule": "confusion_unique"})
                    spans.append((m.start(), m.end(), new))
                    pg_corr += 1
                elif len(hits) > 1:
                    suspects.append({"page": pno, "line": lno, "token": tok,
                                     "candidates": sorted(hits.keys()),
                                     "reason": "ambiguous:多个单点替换均在词典，原文保留"})
                    pg_susp += 1
                else:
                    fixed = numeric_context_fix(tok)
                    if fixed is not None:
                        corrections.append({"page": pno, "line": lno, "from": tok,
                                            "to": fixed, "rule": "numeric_context"})
                        spans.append((m.start(), m.end(), fixed))
                        pg_corr += 1
                    elif has_confusable_shape(tok):
                        suspects.append({"page": pno, "line": lno, "token": tok,
                                         "candidates": [],
                                         "reason": "no_candidate:字母数字混排且无解，原文保留"})
                        pg_susp += 1
                    else:
                        unknown_words.append({"page": pno, "line": lno, "token": tok})
            if spans:
                buf = line
                for s, e, new in sorted(spans, reverse=True):
                    buf = buf[:s] + new + buf[e:]
                out_lines.append(buf)
            else:
                out_lines.append(line)
        corrected_pages.append("\n".join(out_lines))
        per_page[str(pno)] = {
            "tokens": pg_tok, "corrections": pg_corr, "suspects": pg_susp,
            "correction_rate": round(pg_corr / pg_tok, 6) if pg_tok else 0.0,
        }
    stats = {
        "pages": len(pages),
        "lines": sum(len(p.split("\n")) for p in pages),
        "tokens_checked": total_tokens,
        "corrections": len(corrections),
        "suspects": len(suspects),
        "unknown_words": len(unknown_words),
        "per_page": per_page,
    }
    return corrected_pages, corrections, suspects, unknown_words, stats


def main(argv=None):
    ap = argparse.ArgumentParser(description="OCR 文本校验与保守纠错")
    ap.add_argument("--ocr", required=True, help="OCR 文本文件（\\f 分页）")
    ap.add_argument("--outdir", required=True, help="输出目录")
    ap.add_argument("--lexicon", default=None, help="词典路径（默认 ../references/lexicon-en.txt）")
    args = ap.parse_args(argv)

    ocr_path = Path(args.ocr)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    if not ocr_path.is_file():
        print(json.dumps({"error": "ocr_file_not_found", "ocr": str(ocr_path)}))
        return EXIT_FAIL
    lex_path = Path(args.lexicon) if args.lexicon else \
        Path(__file__).resolve().parent.parent / "references" / "lexicon-en.txt"
    if not lex_path.is_file():
        print(json.dumps({"error": "lexicon_not_found", "lexicon": str(lex_path)}))
        return EXIT_FAIL
    lexicon = load_lexicon(lex_path)
    text = ocr_path.read_text(encoding="utf-8")
    if not text.strip():
        (outdir / "postcheck.json").write_text(json.dumps({
            "ocr": str(ocr_path), "status": "partial",
            "warning": "ocr_empty:OCR 输出为空，无内容可校验",
            "stats": {}, "corrections": [], "suspects": []}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        (outdir / "corrected.txt").write_text("", encoding="utf-8")
        print(json.dumps({"status": "partial", "reason": "ocr_empty"}))
        return EXIT_PARTIAL

    corrected_pages, corrections, suspects, unknown_words, stats = process_text(text, lexicon)
    corrected = "\f".join(corrected_pages)
    (outdir / "corrected.txt").write_text(corrected, encoding="utf-8")
    report = {
        "ocr": str(ocr_path),
        "engine": "stdlib-lexicon-rules",
        "lexicon": {"path": str(lex_path), "size": len(lexicon)},
        "policy": "保守纠错：仅唯一解改正并记账；多解/无解进 suspects 原文保留",
        "stats": stats,
        "corrections": corrections,
        "suspects": suspects,
        "unknown_words_sample": unknown_words[:50],
    }
    (outdir / "postcheck.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok",
                      "postcheck": str(outdir / "postcheck.json"),
                      "corrected": str(outdir / "corrected.txt"),
                      "corrections": len(corrections),
                      "suspects": len(suspects),
                      "exit_code": EXIT_OK}, ensure_ascii=False))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
