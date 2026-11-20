#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""quote_audit.py — 确定性引文回核（引文闸控的第二道闸）。

读取证据账本（JSONL），逐条打开被引文件，核验 quote 是否逐字存在于来源文本：

1. 严格模式（默认）：先做空白规范化（连续空白折叠为单空格），再要求引文是
   来源文本（或其声明页码对应页）的子串。
2. OCR 容忍模式（--ocr-tolerant）：对 source_kind 含 ocr 的记录，启用
   大小写折叠、连字符/换行合并、以及基于编辑相似度的近似匹配
   （--ocr-threshold，默认 0.92）。容忍匹配通过的前提是该记录已声明
   allow_ocr_tolerance=true；凡以容忍模式通过的记录，报告中一律标注
   match_mode="ocr_tolerant"，且结论侧必须降级处理（见 risk_grade.py）。

页码核验：若 locator 带 page 且文件含换页符 \\f（pdftotext 输出），
则仅在该页内核验；页码越界视为定位错误。

退出码：0 全部通过；1 存在伪造引文 / 定位错误 / 未标注的容忍匹配。
仅依赖 Python 标准库。
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

# 允许直接 import evidence_ledger（同一 scripts 目录）
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence_ledger import load_ledger, normalize_text, compute_quote_hash  # noqa: E402


def tolerant_normalize(s: str) -> str:
    """OCR 容忍规范化：大小写折叠 + 连字符/换行合并 + 空白折叠。"""
    s = s.casefold()
    s = re.sub(r"\s+", " ", s)          # 先折叠空白（含换行）
    s = re.sub(r"-\s+", "", s)          # 去连字符断词："exam- ple" -> "example"
    s = re.sub(r"\s*-\s*", "-", s)      # 其余连字符两侧空白归一
    return s.strip()


def best_window_ratio(haystack: str, needle: str) -> float:
    """在 haystack 中滑动窗口，返回与 needle 的最高相似度（difflib ratio）。

    先用 needle 首词锚定候选位置以减少比较次数；找不到锚点时退化全扫。
    语料为单件专利/论文文本，规模有限，该复杂度可接受。
    """
    if not needle or not haystack:
        return 0.0
    n = len(needle)
    wmin, wmax = max(1, int(n * 0.9)), int(n * 1.1) + 1
    stride = max(1, n // 20)
    anchor = needle.split(" ", 1)[0]
    starts = [m.start() for m in re.finditer(re.escape(anchor), haystack)] if anchor else []
    if not starts:
        starts = range(0, max(1, len(haystack) - wmin + 1), stride)
    best = 0.0
    for s in starts:
        for w in (wmin, n, wmax):
            window = haystack[s:s + w]
            if not window:
                continue
            r = difflib.SequenceMatcher(None, needle, window).ratio()
            if r > best:
                best = r
            if best >= 0.999:
                return best
    return best


def audit_record(rec, base_dir, ocr_tolerant, ocr_threshold):
    """核验单条记录。返回结果 dict（含 passed / match_mode / detail）。"""
    loc = rec.get("locator", {})
    res = {
        "claim_id": rec.get("claim_id"),
        "file": loc.get("file"),
        "passed": False,
        "match_mode": None,
        "detail": "",
    }
    fpath = Path(loc.get("file", ""))
    if not fpath.is_absolute():
        fpath = Path(base_dir) / fpath
    if not fpath.exists():
        res["detail"] = "被引文件不存在: %s" % fpath
        return res
    raw = fpath.read_text(encoding="utf-8", errors="replace")
    quote = rec.get("quote", "")

    # 完整性自检：quote_hash 必须仍与 quote 一致（防账本被事后篡改）
    if rec.get("quote_hash") != compute_quote_hash(quote):
        res["detail"] = "quote_hash 与 quote 不一致，账本完整性校验失败"
        return res

    # 页码定位：pdftotext 输出按 \f 分页
    page = loc.get("page")
    scoped = raw
    if page is not None and "\f" in raw:
        pages = raw.split("\f")
        if not (1 <= page <= len(pages)):
            res["detail"] = "页码越界：文件共 %d 页，locator.page=%d" % (len(pages), page)
            return res
        scoped = pages[page - 1]

    # 1) 严格模式：空白规范化后的逐字子串
    if normalize_text(quote) in normalize_text(scoped):
        res["passed"] = True
        res["match_mode"] = "verbatim"
        res["detail"] = "逐字匹配通过（空白规范化后）"
        return res

    # 2) OCR 容忍模式
    if ocr_tolerant:
        if not rec.get("allow_ocr_tolerance"):
            res["detail"] = ("严格匹配失败；该记录未声明 allow_ocr_tolerance=true，"
                             "不允许以容忍模式通过（伪造或定位错误嫌疑）")
            return res
        tq, ts = tolerant_normalize(quote), tolerant_normalize(scoped)
        if tq in ts:
            res["passed"] = True
            res["match_mode"] = "ocr_tolerant"
            res["detail"] = "OCR 容忍匹配通过（规范化后子串）；已在报告中标注"
            return res
        ratio = best_window_ratio(ts, tq)
        if ratio >= ocr_threshold:
            res["passed"] = True
            res["match_mode"] = "ocr_tolerant"
            res["detail"] = ("OCR 近似匹配通过（相似度 %.3f ≥ %.2f）；"
                             "已在报告中标注，结论需降级" % (ratio, ocr_threshold))
            return res
        res["detail"] = "OCR 容忍匹配仍失败（最高相似度 %.3f < %.2f）" % (ratio, ocr_threshold)
        return res

    res["detail"] = "严格匹配失败且未启用 --ocr-tolerant"
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="确定性引文回核：伪造或定位错误即 exit 1")
    ap.add_argument("--ledger", required=True, help="证据账本 JSONL")
    ap.add_argument("--base-dir", default=None,
                    help="被引文件的相对路径基准目录（默认：账本所在目录）")
    ap.add_argument("--ocr-tolerant", action="store_true",
                    help="启用 OCR 容忍模式（大小写折叠/连字符合并/相似度阈值）")
    ap.add_argument("--ocr-threshold", type=float, default=0.92,
                    help="OCR 近似匹配相似度阈值（默认 0.92）")
    ap.add_argument("--report", default=None, help="审计报告 JSON 输出路径")
    args = ap.parse_args(argv)

    records, parse_errors = load_ledger(args.ledger)
    base_dir = args.base_dir or str(Path(args.ledger).resolve().parent)
    results = []
    failures = []
    for e in parse_errors:
        failures.append({"claim_id": None, "detail": "账本解析错误: " + e})
    for lineno, rec in records:
        r = audit_record(rec, base_dir, args.ocr_tolerant, args.ocr_threshold)
        r["ledger_line"] = lineno
        results.append(r)
        if not r["passed"]:
            failures.append(r)

    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        print("[%s] %s | %s | mode=%s | %s" % (
            mark, r["claim_id"], r["file"], r.get("match_mode") or "-", r["detail"]))

    report = {
        "ledger": str(args.ledger),
        "ocr_tolerant": bool(args.ocr_tolerant),
        "ocr_threshold": args.ocr_threshold,
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": len(failures),
        "tolerant_matches": [r["claim_id"] for r in results
                             if r["passed"] and r["match_mode"] == "ocr_tolerant"],
        "results": results,
    }
    if args.report:
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("审计报告已写入: %s" % args.report)

    if failures:
        print("\n引文审计失败 %d 项（伪造引文或定位错误，必须修正后重跑）：" % len(failures))
        for f in failures:
            print("  - claim_id=%s: %s" % (f.get("claim_id"), f.get("detail")))
        return 1
    print("\n引文审计全部通过（%d 条）。其中容忍匹配 %d 条（已在报告标注）。"
          % (len(results), len(report["tolerant_matches"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
