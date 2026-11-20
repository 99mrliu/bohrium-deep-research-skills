#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evidence_ledger.py — 证据账本：数据结构与校验（可导入库 + CLI）。

引文闸控（quote-gated）的第一道闸：所有关于专利保护范围、法律状态、同族关系、
文献结论的论断，必须先登记为一条证据记录，才能出现在最终输出中。

每条证据记录（JSONL，每行一条 JSON 对象）字段：
  claim_id    : 论断编号（非空字符串，如 "C1"）
  statement   : 论断全文（自然语言）
  quote       : 逐字引文（必须与来源文本逐字一致；空白差异由审计器规范化处理）
  locator     : 定位对象 {file, page?, line?, offset?, source_kind}
                  file        被引文件路径（相对或绝对）
                  page        页码（1 起，可选；pdftotext -layout 输出按 \\f 分页）
                  line        行号（1 起，可选）
                  offset      字符偏移（可选）
                  source_kind 来源类别（见 KNOWN_SOURCE_KINDS）
  quote_hash  : 规范化引文的 SHA-256，格式 "sha256:<hex>"（由本脚本计算）
  allow_ocr_tolerance : 可选布尔。true 表示该引文来自 OCR 文本，
                        允许 quote_audit 在 --ocr-tolerant 下用容忍匹配回核，
                        且审计报告必须标注 match_mode=ocr_tolerant。
  note        : 可选备注。

CLI：
  append    追加一条记录（quote_hash 自动计算并写入）
  validate  校验账本结构与哈希，任何违例 exit 1
  show      打印账本概要

仅依赖 Python 标准库。
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

LEDGER_SCHEMA_VERSION = "1.0"

KNOWN_SOURCE_KINDS = {
    "patent_pdf_text",      # 专利 PDF 抽取文本（含传真原件）
    "patent_pdf_ocr",       # 专利 PDF 经 OCR 得到的文本
    "patent_record",        # 结构化专利著录记录
    "scientific_paper",     # 科学对比论文
    "official_register",    # 官方登记簿
    "official_gazette",     # 官方公报
    "aggregation_page",     # 聚合页（仅作线索）
    "ocr_merged",           # OCR 合并文本（如 WO 文献合并，边界已保留）
    "other",
}

REQUIRED_FIELDS = ["claim_id", "statement", "quote", "locator", "quote_hash"]


def normalize_text(s: str) -> str:
    """空白规范化：所有连续空白（含换行、制表）折叠为单个空格，去首尾空白。"""
    return re.sub(r"\s+", " ", s).strip()


def compute_quote_hash(quote: str) -> str:
    """对规范化后的引文计算 SHA-256，返回 'sha256:<hex>'。"""
    return "sha256:" + hashlib.sha256(normalize_text(quote).encode("utf-8")).hexdigest()


def make_record(claim_id, statement, quote, locator, allow_ocr_tolerance=False, note=None):
    """构造一条证据记录（自动计算 quote_hash）。"""
    rec = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "claim_id": claim_id,
        "statement": statement,
        "quote": quote,
        "locator": locator,
        "quote_hash": compute_quote_hash(quote),
        "allow_ocr_tolerance": bool(allow_ocr_tolerance),
    }
    if note:
        rec["note"] = note
    return rec


def validate_record(rec, index=None):
    """校验单条记录，返回错误列表（空列表表示通过）。"""
    errors = []
    tag = "记录[%s]" % (index if index is not None else "?")
    if not isinstance(rec, dict):
        return ["%s: 不是 JSON 对象" % tag]
    for f in REQUIRED_FIELDS:
        if f not in rec:
            errors.append("%s: 缺少必需字段 %s" % (tag, f))
    if errors:
        return errors
    if not isinstance(rec["claim_id"], str) or not rec["claim_id"].strip():
        errors.append("%s: claim_id 必须是非空字符串" % tag)
    if not isinstance(rec["statement"], str) or not rec["statement"].strip():
        errors.append("%s: statement 必须是非空字符串" % tag)
    if not isinstance(rec["quote"], str) or not rec["quote"].strip():
        errors.append("%s: quote 必须是非空字符串（逐字引文）" % tag)
    loc = rec["locator"]
    if not isinstance(loc, dict):
        errors.append("%s: locator 必须是对象 {file, page?, line?, offset?, source_kind}" % tag)
    else:
        if not isinstance(loc.get("file"), str) or not loc.get("file", "").strip():
            errors.append("%s: locator.file 缺失或为空" % tag)
        if not isinstance(loc.get("source_kind"), str) or not loc.get("source_kind", "").strip():
            errors.append("%s: locator.source_kind 缺失或为空" % tag)
        elif loc["source_kind"] not in KNOWN_SOURCE_KINDS:
            errors.append("%s: locator.source_kind=%r 不在已知类别 %s 中"
                          % (tag, loc["source_kind"], sorted(KNOWN_SOURCE_KINDS)))
        for k in ("page", "line", "offset"):
            if k in loc and not isinstance(loc[k], int):
                errors.append("%s: locator.%s 必须是整数" % (tag, k))
    if isinstance(rec.get("quote"), str):
        expected = compute_quote_hash(rec["quote"])
        if rec["quote_hash"] != expected:
            errors.append("%s: quote_hash 与 quote 不一致（期望 %s，实际 %s）"
                          % (tag, expected, rec["quote_hash"]))
    if "allow_ocr_tolerance" in rec and not isinstance(rec["allow_ocr_tolerance"], bool):
        errors.append("%s: allow_ocr_tolerance 必须是布尔值" % tag)
    return errors


def load_ledger(path):
    """读取 JSONL 账本，返回 (records, parse_errors)。records 为 [(lineno, rec), ...]。"""
    records, parse_errors = [], []
    p = Path(path)
    if not p.exists():
        return [], ["账本文件不存在: %s" % path]
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append((lineno, json.loads(line)))
        except json.JSONDecodeError as e:
            parse_errors.append("第 %d 行: JSON 解析失败: %s" % (lineno, e))
    return records, parse_errors


def append_record(path, record):
    """校验通过后追加一条记录到账本。返回错误列表（空即成功）。"""
    errors = validate_record(record)
    if errors:
        return errors
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return []


def cmd_append(args):
    locator = {"file": args.file, "source_kind": args.source_kind}
    if args.page is not None:
        locator["page"] = args.page
    if args.line is not None:
        locator["line"] = args.line
    if args.offset is not None:
        locator["offset"] = args.offset
    rec = make_record(args.claim_id, args.statement, args.quote, locator,
                      allow_ocr_tolerance=args.allow_ocr_tolerance, note=args.note)
    errors = append_record(args.ledger, rec)
    if errors:
        for e in errors:
            print("ERROR: " + e, file=sys.stderr)
        return 1
    print("OK: 已追加证据记录 claim_id=%s quote_hash=%s" % (rec["claim_id"], rec["quote_hash"]))
    return 0


def cmd_validate(args):
    records, parse_errors = load_ledger(args.ledger)
    all_errors = list(parse_errors)
    for lineno, rec in records:
        all_errors.extend(validate_record(rec, index=lineno))
    if all_errors:
        print("校验失败，共 %d 处问题：" % len(all_errors))
        for e in all_errors:
            print("  - " + e)
        return 1
    print("校验通过：%d 条证据记录结构与哈希均合规。" % len(records))
    return 0


def cmd_show(args):
    records, parse_errors = load_ledger(args.ledger)
    for e in parse_errors:
        print("PARSE-ERROR: " + e, file=sys.stderr)
    print("账本: %s（%d 条）" % (args.ledger, len(records)))
    for lineno, rec in records:
        loc = rec.get("locator", {})
        print("  [行%d] %s | %s | %s:%s | %s" % (
            lineno, rec.get("claim_id"), loc.get("source_kind"),
            loc.get("file"), loc.get("page", "-"),
            (rec.get("statement") or "")[:40]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="证据账本：登记与校验（引文闸控第一道闸）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_a = sub.add_parser("append", help="追加一条证据记录")
    ap_a.add_argument("--ledger", required=True, help="账本 JSONL 路径")
    ap_a.add_argument("--claim-id", required=True)
    ap_a.add_argument("--statement", required=True)
    ap_a.add_argument("--quote", required=True, help="逐字引文")
    ap_a.add_argument("--file", required=True, help="被引文件路径")
    ap_a.add_argument("--source-kind", required=True, choices=sorted(KNOWN_SOURCE_KINDS))
    ap_a.add_argument("--page", type=int, default=None)
    ap_a.add_argument("--line", type=int, default=None)
    ap_a.add_argument("--offset", type=int, default=None)
    ap_a.add_argument("--allow-ocr-tolerant", action="store_true",
                      help="声明该引文允许 OCR 容忍匹配（须在审计中标注）")
    ap_a.add_argument("--note", default=None)
    ap_a.set_defaults(func=cmd_append)

    ap_v = sub.add_parser("validate", help="校验账本结构与哈希")
    ap_v.add_argument("--ledger", required=True)
    ap_v.set_defaults(func=cmd_validate)

    ap_s = sub.add_parser("show", help="打印账本概要")
    ap_s.add_argument("--ledger", required=True)
    ap_s.set_defaults(func=cmd_show)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
