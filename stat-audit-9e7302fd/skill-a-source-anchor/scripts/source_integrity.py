#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""source_integrity.py — 提取保真度检测门:在审查【之前】评估上游文本是否可信。

对 pdf_to_anchored_text.py 的产物(原始提取文本或锚点文本,自动识别并剥离行首标记)
计算以下指标并给出三档判定:

  verdict = "ok"       提取保真,可进入五面审查
  verdict = "degraded" 部分受损,可审查但须逐条更严格核验,并在审查单中披露受损项
  verdict = "failed"   提取失败(如扫描件未 OCR/大面积乱码/内容过短),
                       审查必须走「材料不足」分支: result.json 中 status="failed",
                       如实填写 uncertainty,严禁凭空编造审查发现。

阈值常量(与 references/integrity_criteria.md 必须保持一致):
  MIN_TOTAL_CHARS      = 1500   全文最少字符数,低于此值疑似提取失败
  MAX_GARBLE_RATIO     = 0.001  替换字符 U+FFFD 占比上限(超过 → failed)
  WARN_GARBLE_RATIO    = 0.0002 乱码占比告警线(超过 → degraded)
  MAX_EMPTY_PAGE_RATIO = 0.30   空页占比上限(页数>=2 且超过 → failed)
  EMPTY_PAGE_MIN_CHARS = 5      非空白字符少于此数即判为空页
  LONG_LINE_LEN        = 400    超长行阈值(疑似段落粘连/换行丢失)
  MAX_LONG_LINE_RATIO  = 0.05   超长行占比上限(超过 → degraded)
  MIN_MEAN_LINE_LEN    = 8      平均行长下限(低于 → degraded,疑似断行/碎片)
  MAX_MEAN_LINE_LEN    = 300    平均行长上限(高于 → degraded,疑似换行结构丢失)
  MIN_CJK_LATIN_RATIO  = 0.30   (中日韩汉字+拉丁字母)占总字符比例下限(低于 → failed,疑似图像型扫描件)

退出码: 0 = 分析完成且 verdict 为 ok/degraded; 1 = verdict 为 failed(门是真实的);
        2 = 输入/运行错误。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# ---- 阈值常量(与 references/integrity_criteria.md 一致,改动须同步) ----
MIN_TOTAL_CHARS = 1500
MAX_GARBLE_RATIO = 0.001
WARN_GARBLE_RATIO = 0.0002
MAX_EMPTY_PAGE_RATIO = 0.30
EMPTY_PAGE_MIN_CHARS = 5
LONG_LINE_LEN = 400
MAX_LONG_LINE_RATIO = 0.05
MIN_MEAN_LINE_LEN = 8
MAX_MEAN_LINE_LEN = 300
MIN_CJK_LATIN_RATIO = 0.30
# ----------------------------------------------------------------------

PAGE_SEP = "\f"
MARKER_RE = re.compile(r"^\[P\d{3} L\d{3}\] ")


def load_text(path: str) -> str:
    if not os.path.isfile(path):
        sys.stderr.write("错误: 输入文件不存在: %s\n" % path)
        sys.exit(2)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except UnicodeDecodeError as exc:
        sys.stderr.write("错误: 输入文本不是合法 UTF-8: %s\n" % exc)
        sys.exit(2)
    # 若为锚点文本(行首带 [Pxxx Lxxx] 标记),剥离标记还原原始文本
    lines = raw.split("\n")
    if lines and sum(1 for ln in lines[:20] if MARKER_RE.match(ln)) >= max(1, len(lines[:20]) // 2):
        lines = [MARKER_RE.sub("", ln) for ln in lines]
        return "\n".join(lines)
    return raw


def analyze(text: str) -> dict:
    pages = text.split(PAGE_SEP)
    n_pages = len(pages)
    total_chars = len(text)

    garble_count = text.count("�")
    garble_ratio = garble_count / total_chars if total_chars else 1.0

    empty_pages = sum(
        1 for p in pages if len("".join(p.split())) < EMPTY_PAGE_MIN_CHARS
    )
    empty_page_ratio = empty_pages / n_pages if n_pages else 1.0

    lines = [ln for p in pages for ln in p.split("\n")]
    n_lines = len(lines)
    lengths = [len(ln) for ln in lines]
    mean_line_len = (sum(lengths) / n_lines) if n_lines else 0.0
    long_lines = sum(1 for ln in lines if len(ln) > LONG_LINE_LEN)
    long_line_ratio = long_lines / n_lines if n_lines else 0.0

    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    latin = sum(1 for ch in text if ("a" <= ch <= "z") or ("A" <= ch <= "Z"))
    cjk_latin_ratio = (cjk + latin) / total_chars if total_chars else 0.0

    fail_reasons = []
    warn_reasons = []

    if total_chars < MIN_TOTAL_CHARS:
        fail_reasons.append(
            "全文仅 %d 字符(< %d),疑似提取失败或只拿到首页/摘要" % (total_chars, MIN_TOTAL_CHARS)
        )
    if garble_ratio > MAX_GARBLE_RATIO:
        fail_reasons.append(
            "乱码(U+FFFD)占比 %.4f > %.4f,文本不可信" % (garble_ratio, MAX_GARBLE_RATIO)
        )
    elif garble_ratio > WARN_GARBLE_RATIO:
        warn_reasons.append(
            "存在少量乱码(U+FFFD 占比 %.4f > %.4f),引用相关段落须逐字复核" % (garble_ratio, WARN_GARBLE_RATIO)
        )
    if n_pages >= 2 and empty_page_ratio > MAX_EMPTY_PAGE_RATIO:
        fail_reasons.append(
            "空页占比 %.2f > %.2f(%d/%d 页),疑似大面积图像页未 OCR"
            % (empty_page_ratio, MAX_EMPTY_PAGE_RATIO, empty_pages, n_pages)
        )
    elif empty_pages > 0:
        warn_reasons.append(
            "检测到 %d 个空页(占比 %.2f),可能含纯图/表页,涉及这些页的内容须回查原件"
            % (empty_pages, empty_page_ratio)
        )
    if cjk_latin_ratio < MIN_CJK_LATIN_RATIO:
        fail_reasons.append(
            "可识别文字(汉字+拉丁字母)占比 %.3f < %.2f,疑似扫描图片未 OCR"
            % (cjk_latin_ratio, MIN_CJK_LATIN_RATIO)
        )
    if long_line_ratio > MAX_LONG_LINE_RATIO:
        warn_reasons.append(
            "超长行(>%d 字符)占比 %.3f > %.2f,换行结构可能丢失,行级锚点精度下降"
            % (LONG_LINE_LEN, long_line_ratio, MAX_LONG_LINE_RATIO)
        )
    if mean_line_len < MIN_MEAN_LINE_LEN:
        warn_reasons.append(
            "平均行长 %.1f < %d,文本碎片化,可能为竖排/双栏误切" % (mean_line_len, MIN_MEAN_LINE_LEN)
        )
    elif mean_line_len > MAX_MEAN_LINE_LEN:
        warn_reasons.append(
            "平均行长 %.1f > %d,疑似换行丢失" % (mean_line_len, MAX_MEAN_LINE_LEN)
        )

    if fail_reasons:
        verdict = "failed"
    elif warn_reasons:
        verdict = "degraded"
    else:
        verdict = "ok"

    return {
        "verdict": verdict,
        "fail_reasons": fail_reasons,
        "warn_reasons": warn_reasons,
        "metrics": {
            "total_chars": total_chars,
            "total_pages": n_pages,
            "total_lines": n_lines,
            "garble_count": garble_count,
            "garble_ratio": round(garble_ratio, 6),
            "empty_pages": empty_pages,
            "empty_page_ratio": round(empty_page_ratio, 4),
            "mean_line_len": round(mean_line_len, 2),
            "long_lines": long_lines,
            "long_line_ratio": round(long_line_ratio, 4),
            "cjk_chars": cjk,
            "latin_chars": latin,
            "cjk_latin_ratio": round(cjk_latin_ratio, 4),
        },
        "thresholds": {
            "MIN_TOTAL_CHARS": MIN_TOTAL_CHARS,
            "MAX_GARBLE_RATIO": MAX_GARBLE_RATIO,
            "WARN_GARBLE_RATIO": WARN_GARBLE_RATIO,
            "MAX_EMPTY_PAGE_RATIO": MAX_EMPTY_PAGE_RATIO,
            "EMPTY_PAGE_MIN_CHARS": EMPTY_PAGE_MIN_CHARS,
            "LONG_LINE_LEN": LONG_LINE_LEN,
            "MAX_LONG_LINE_RATIO": MAX_LONG_LINE_RATIO,
            "MIN_MEAN_LINE_LEN": MIN_MEAN_LINE_LEN,
            "MAX_MEAN_LINE_LEN": MAX_MEAN_LINE_LEN,
            "MIN_CJK_LATIN_RATIO": MIN_CJK_LATIN_RATIO,
        },
        "disposition": {
            "ok": "可进入五面审查。",
            "degraded": "可审查,但受损项须在审查单中披露,相关发现提高核验等级。",
            "failed": "材料不足:result.json 置 status=\"failed\" 并如实填写 uncertainty,严禁编造发现。",
        }[verdict],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="提取保真度检测门:输出 integrity report JSON;verdict=failed 时退出码为 1。"
    )
    ap.add_argument("input", help="原始提取文本或锚点文本路径(自动剥离锚点标记)")
    ap.add_argument("--out", default=None, help="报告 JSON 输出路径(默认打印到 stdout)")
    args = ap.parse_args(argv)

    text = load_text(args.input)
    report = analyze(text)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(payload + "\n")
        except OSError as exc:
            sys.stderr.write("错误: 报告写入失败: %s\n" % exc)
            return 2
        sys.stderr.write("完整性判定: %s -> %s\n" % (report["verdict"], args.out))
    else:
        print(payload)
    return 1 if report["verdict"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
