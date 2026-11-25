#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trust_ledger.py — 汇总扫描判定与 OCR 后处理，产出逐页可信分级台账（纯标准库）。

分级规则（写死，与 SKILL.md「方法要点」一致）：
  high      born_digital 且该页 suspects == 0
  medium    born_digital 且 0 < suspects <= SUSPECT_MAX；
            或 scanned/mixed/unknown 页已 OCR 且 correction_rate < RATE_MAX
            且 suspects <= SUSPECT_MAX（unknown 页附降级备注）
  low       任何已 OCR 页 correction_rate >= RATE_MAX 或 suspects > SUSPECT_MAX
  illegible scanned/mixed/unknown 页无 OCR 文本（无文字层且未识别）
  empty     页记 high 并备注「空白页无可读内容」

每页给出 verbatim / corrected 双写路径（有 OCR 文本时落到
--workdir/pages/page-NNN.verbatim.txt 与 page-NNN.corrected.txt）。

同时读取 case.json，产出契约感知 result.json：保留 case_id，
按 output_contract 字段逐一填充，无法填充置空并记入 uncertainty；
status 取值 success / partial / failed。

退出码：0=成功，2=部分（status=partial），3=失败。
"""
import argparse
import json
import sys
from pathlib import Path

EXIT_OK, EXIT_PARTIAL, EXIT_FAIL = 0, 2, 3

# ---- 阈值（与 SKILL.md「方法要点」一致，改动需同步文档） ----
RATE_MAX = 0.02    # 修正率阈值：>= 2% 降级 low
SUSPECT_MAX = 5    # 单页 suspects 数量阈值：> 5 降级 low

TRUST_ORDER = ("high", "medium", "low", "illegible")


def grade_page(cls, ocr_present, rate, suspects):
    """返回 (trust, note)。"""
    if cls == "empty":
        return "high", "空白页无可读内容"
    if cls == "born_digital":
        if not ocr_present:
            return "high", "原生数字页，文字层直接可读"
        if suspects == 0:
            return "high", "原生数字页，OCR 校验无疑点"
        if suspects > SUSPECT_MAX:
            return "low", "原生数字页但 suspects 超阈值（%d > %d）" % (suspects, SUSPECT_MAX)
        return "medium", "原生数字页，OCR 校验存在少量 suspects"
    # scanned / mixed / unknown
    if not ocr_present:
        return "illegible", "无文字层且未 OCR，本技能不猜测内容"
    note_prefix = ""
    if cls == "unknown":
        note_prefix = "页类 unknown（扫描判定失败或 OCR 页超出 PDF 页数），按扫描页规则降级处理；"
    if rate >= RATE_MAX:
        return "low", "%s修正率 %.2f%% >= %.0f%%" % (note_prefix, rate * 100, RATE_MAX * 100)
    if suspects > SUSPECT_MAX:
        return "low", "%ssuspects %d > %d" % (note_prefix, suspects, SUSPECT_MAX)
    return "medium", "%s已 OCR 且修正率 %.2f%% < %.0f%%" % (note_prefix, rate * 100, RATE_MAX * 100)


def main(argv=None):
    ap = argparse.ArgumentParser(description="逐页可信分级台账 + 契约感知 result.json")
    ap.add_argument("--scan", required=True, help="scan_report.json 路径")
    ap.add_argument("--post", required=True, help="postcheck.json 路径")
    ap.add_argument("--ocr", required=True, help="OCR 原文（verbatim 来源）")
    ap.add_argument("--corrected", required=True, help="corrected.txt 路径")
    ap.add_argument("--case", default=None, help="case.json 路径（可选，缺省则 result.json 标 partial）")
    ap.add_argument("--workdir", required=True, help="中间产物目录（逐页双写文件）")
    ap.add_argument("--outdir", required=True, help="交付目录（trust_ledger.json / result.json）")
    args = ap.parse_args(argv)

    outdir = Path(args.outdir)
    workdir = Path(args.workdir)
    pages_dir = workdir / "pages"
    outdir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)

    for name, p in [("scan", args.scan), ("post", args.post),
                    ("ocr", args.ocr), ("corrected", args.corrected)]:
        if not Path(p).is_file():
            print(json.dumps({"error": "input_not_found", "which": name, "path": p}))
            return EXIT_FAIL

    scan = json.loads(Path(args.scan).read_text(encoding="utf-8"))
    post = json.loads(Path(args.post).read_text(encoding="utf-8"))
    ocr_text = Path(args.ocr).read_text(encoding="utf-8")
    corrected_text = Path(args.corrected).read_text(encoding="utf-8")
    ocr_pages = ocr_text.split("\f")
    cor_pages = corrected_text.split("\f")

    scan_pages = {p["page"]: p for p in scan.get("pages", [])}
    per_page_stats = post.get("stats", {}).get("per_page", {})
    suspects_by_page = {}
    for s in post.get("suspects", []):
        suspects_by_page[s["page"]] = suspects_by_page.get(s["page"], 0) + 1

    uncertainty, change_record = [], []
    n_pdf_pages = scan.get("page_count", len(scan_pages))
    n_ocr_pages = len(ocr_pages) if ocr_text.strip() else 0
    if n_ocr_pages != n_pdf_pages:
        uncertainty.append(
            "OCR 文本页数（%d）与 PDF 页数（%d）不一致，超出页按 unknown 类降级处理"
            % (n_ocr_pages, n_pdf_pages))
    change_record.append("trust_ledger.py：合并 scan_report + postcheck，按写死规则分级")

    ledger_pages = []
    dist = {k: 0 for k in TRUST_ORDER}
    all_page_nums = sorted(set(scan_pages) | set(range(1, n_ocr_pages + 1)))
    for pno in all_page_nums:
        sp = scan_pages.get(pno)
        cls = sp["page_class"] if sp else "unknown"
        notes = []
        if sp is None:
            notes.append("该页不在 scan_report 中（OCR 页超出 PDF 页数）")
        ocr_present = pno <= n_ocr_pages and bool(ocr_pages[pno - 1].strip())
        st = per_page_stats.get(str(pno), {})
        rate = st.get("correction_rate", 0.0)
        n_corr = st.get("corrections", 0)
        n_tok = st.get("tokens", 0)
        n_susp = suspects_by_page.get(pno, 0)
        trust, note = grade_page(cls, ocr_present, rate, n_susp)
        notes.append(note)
        verbatim_path = corrected_path = None
        if ocr_present:
            verbatim_path = pages_dir / ("page-%03d.verbatim.txt" % pno)
            corrected_path = pages_dir / ("page-%03d.corrected.txt" % pno)
            verbatim_path.write_text(ocr_pages[pno - 1], encoding="utf-8")
            corrected_path.write_text(
                cor_pages[pno - 1] if pno - 1 < len(cor_pages) else ocr_pages[pno - 1],
                encoding="utf-8")
        ledger_pages.append({
            "page": pno,
            "page_class": cls,
            "ocr_present": ocr_present,
            "tokens": n_tok,
            "corrections": n_corr,
            "correction_rate": rate,
            "suspects": n_susp,
            "trust": trust,
            "verbatim": str(verbatim_path) if verbatim_path else None,
            "corrected": str(corrected_path) if corrected_path else None,
            "notes": notes,
        })
        dist[trust] += 1

    summary = {"trust_distribution": dist,
               "thresholds": {"rate_max": RATE_MAX, "suspect_max": SUSPECT_MAX},
               "n_pages": len(ledger_pages)}
    ledger = {
        "pdf": scan.get("pdf"),
        "ocr": str(args.ocr),
        "summary": summary,
        "pages": ledger_pages,
        "uncertainty": uncertainty,
    }
    (outdir / "trust_ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 契约感知 result.json ----
    case_id, contract_fields = None, []
    if args.case and Path(args.case).is_file():
        try:
            case = json.loads(Path(args.case).read_text(encoding="utf-8"))
            case_id = case.get("case_id")
            oc = case.get("output_contract", {})
            if isinstance(oc, dict):
                fields = oc.get("fields", [])
                contract_fields = list(fields.keys()) if isinstance(fields, dict) else list(fields)
            elif isinstance(oc, list):
                contract_fields = list(oc)
        except Exception as exc:
            uncertainty.append("case.json 解析失败：%s" % exc)
    else:
        uncertainty.append("未提供 case.json，result.json 无法对齐 output_contract")

    illegible_pages = [p["page"] for p in ledger_pages if p["trust"] == "illegible"]
    field_fillers = {
        "page_classes": {str(p["page"]): p["page_class"] for p in ledger_pages},
        "ocr_corrections": {
            "corrections": post.get("stats", {}).get("corrections", 0),
            "suspects": post.get("stats", {}).get("suspects", 0),
            "corrections_ledger": str(Path(args.post)),
        },
        "trust_ledger": str(outdir / "trust_ledger.json"),
        "corrected_text": str(Path(args.corrected)),
        "unreadable_pages": illegible_pages,
    }
    result = {
        "case_id": case_id,
        "status": "success",
        "sources": [str(Path(p)) for p in (args.scan, args.post, args.ocr, args.corrected)],
        "uncertainty": uncertainty,
        "change_record": change_record,
    }
    for f in contract_fields:
        if f in field_fillers:
            result[f] = field_fillers[f]
        else:
            result[f] = None
            result["uncertainty"].append("契约字段 %s 无法由本流水线填充，置空" % f)

    has_unknown_class = any(p["page_class"] == "unknown" for p in ledger_pages)
    empty_fields = [f for f in contract_fields if result.get(f) is None]
    if illegible_pages or has_unknown_class or empty_fields or not args.case:
        result["status"] = "partial"
        if illegible_pages:
            result["uncertainty"].append("存在 illegible 页：%s" % illegible_pages)
        if has_unknown_class:
            result["uncertainty"].append("存在 unknown 页类，相关页可信度按降级规则处理")
    if not ledger_pages:
        result["status"] = "failed"
        result["uncertainty"].append("无任何页面可入台账")

    (outdir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    code = EXIT_OK if result["status"] == "success" else \
        (EXIT_PARTIAL if result["status"] == "partial" else EXIT_FAIL)
    print(json.dumps({"status": result["status"],
                      "trust_ledger": str(outdir / "trust_ledger.json"),
                      "result": str(outdir / "result.json"),
                      "trust_distribution": dist,
                      "exit_code": code}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
