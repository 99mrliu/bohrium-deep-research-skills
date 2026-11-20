#!/usr/bin/env python3
"""extract_facsimile.py — 从 USPTO/WO/EP 传真首页按 INID 码抽取著录字段（仅标准库）。

用法：
  python3 extract_facsimile.py --pdf  path/to/facsimile.pdf --out fields.json
  python3 extract_facsimile.py --text path/to/pdftotext_output.txt --out fields.json
依赖 pdftotext（-layout）；不可用或失败时退出码 2 并打印说明（改用 OCR 工具后走 --text）。
对 OCR 粘连（INID 码与内容粘连、多字段并一行）按 rules/ocr_boundary.md 的确定性
规则拆分，每次拆分写入 evidence_events；无法可靠拆分时保留原文并告警，不猜测。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patent_numbers

INID_MAP = {
    "10": "document_id", "11": "document_number", "12": "document_kind",
    "19": "publishing_office", "21": "application_number", "22": "filing_date",
    "30": "priority_data", "43": "publication_date", "45": "grant_date",
    "51": "ipc", "52": "cpc_or_domestic_class", "54": "title",
    "56": "references_cited", "57": "abstract", "71": "applicant",
    "72": "inventors", "73": "assignee", "74": "attorney_agent",
}
INID_RE = re.compile(r"\((\d{2})\)")
DATE_RES = [
    (re.compile(r"([A-Z][a-z]{2})\.?\s+(\d{1,2}),?\s+(\d{4})"), "%b %d %Y"),
    (re.compile(r"(\d{4})\.(\d{2})\.(\d{2})"), "%Y %m %d"),
    (re.compile(r"(\d{2})\.(\d{2})\.(\d{4})"), "%d %m %Y"),
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "%Y %m %d"),
]
MONTHS = {m.lower(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def iso_date(raw, events):
    for rx, _ in DATE_RES:
        m = rx.search(raw)
        if m:
            g = m.groups()
            try:
                if g[0][:3].lower() in MONTHS:
                    return "%04d-%02d-%02d" % (int(g[2]), MONTHS[g[0][:3].lower()], int(g[1]))
                if len(g[0]) == 4:
                    return "%04d-%02d-%02d" % (int(g[0]), int(g[1]), int(g[2]))
                return "%04d-%02d-%02d" % (int(g[2]), int(g[1]), int(g[0]))
            except (ValueError, KeyError):
                pass
    events.append({"type": "date_unparsed", "raw": raw,
                   "warning": "日期无法解析为 ISO，保留原文"})
    return None


def pdftotext(pdf_path):
    if not shutil.which("pdftotext"):
        return None, "pdftotext 不在 PATH；请用 OCR/pdf 渲染工具产出文本后改用 --text"
    try:
        p = subprocess.run(["pdftotext", "-layout", pdf_path, "-"],
                           capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        return None, "pdftotext 超时"
    if p.returncode != 0:
        return None, "pdftotext 失败: " + p.stderr.decode("utf-8", "replace")[:300]
    try:
        return p.stdout.decode("utf-8"), None
    except UnicodeDecodeError:
        return p.stdout.decode("utf-8", "replace"), "pdftotext 输出含非法字节，已替换"


def split_segments(text, events):
    """按 INID 码切分首页文本。返回 {code: raw_segment}，页码以 \\f 计。"""
    page1 = text.split("\f", 1)[0]
    marks = list(INID_RE.finditer(page1))
    segs = {}
    for i, m in enumerate(marks):
        code = m.group(1)
        end = marks[i + 1].start() if i + 1 < len(marks) else len(page1)
        raw = page1[m.end():end].strip()
        if code in segs:
            # 同一 INID 出现两次：常见于 OCR 重影或续行误判，合并并记录
            segs[code] += " || " + raw
            events.append({"type": "inid_duplicate", "code": code,
                           "warning": "同一 INID 码出现多次，已合并，需人工核对"})
        else:
            segs[code] = raw
    if not segs:
        events.append({"type": "no_inid", "warning":
                       "首页未检出任何 INID 码（可能为图像 PDF 未 OCR 或版式异常）"})
    return segs


def parse_fields(segs, events, default_cc=None):
    fields = {}
    numbers_found = []
    for code, raw in segs.items():
        name = INID_MAP.get(code, "inid_" + code)
        value = raw.strip()
        if name in ("document_id", "document_number", "application_number"):
            hits = patent_numbers.find_numbers(value)
            if not hits and name == "application_number" and default_cc:
                # 传真件申请号常无国别码（如 15/654,321）：取数字段用文献国别回退
                mnum = re.search(r"(\d[\d\s.,/\-]{2,20}\d)", raw)
                p = patent_numbers.normalize(
                    default_cc + mnum.group(1)) if mnum else {"ok": False}
                if p["ok"]:
                    p = dict(p)
                    p["warnings"] = p.get("warnings", []) + [
                        "申请号无国别码，已按文献国别 %s 回退解释，需人工核对" % default_cc]
                    events.append({"type": "cc_fallback", "code": code, "raw": raw,
                                   "assumed_cc": default_cc})
                    hits = [{"parsed": p}]
            if hits:
                value = [h["parsed"] for h in hits]
                numbers_found.extend(h["parsed"] for h in hits if h["parsed"]["ok"])
            else:
                events.append({"type": "number_unparsed", "code": code, "raw": raw,
                               "warning": "号码字段未解析出规范号，保留原文"})
        elif name == "priority_data":
            hits = patent_numbers.find_numbers(value)
            value = {"raw": raw,
                     "priorities": [h["parsed"] for h in hits if h["parsed"]["ok"]]}
            if not value["priorities"]:
                events.append({"type": "priority_unparsed", "raw": raw,
                               "warning": "优先权字段未解析出号码，仅保留原文"})
        elif name in ("filing_date", "publication_date", "grant_date"):
            value = {"raw": raw, "iso": iso_date(raw, events)}
        elif name in ("ipc", "cpc_or_domestic_class"):
            value = re.findall(r"[A-HY]\d{2}[A-Z]\s?\d+[^\s,;]*|[A-HY]\d{2}[A-Z]", raw) or raw
        else:
            value = re.sub(r"\s+", " ", value)
        fields[name] = {"inid": code, "value": value, "raw_segment": raw}
    return fields, numbers_found


def _default_country(segs):
    """从文献号段推断国别码（用于无国别码申请号的回退）。"""
    raw = segs.get("11") or segs.get("10") or ""
    m = re.search(r"\b(US|WO|EP|CN|JP|KR)\b", raw.upper())
    if m:
        return m.group(1)
    if "Patent No" in raw or "United States" in raw:
        return "US"
    return None


def extract(text, source_label):
    events = []
    segs = split_segments(text, events)
    fields, numbers = parse_fields(segs, events, default_cc=_default_country(segs))
    return {"source": source_label, "fields": fields,
            "normalized_numbers": numbers,
            "evidence_events": events,
            "extraction_status": ("ok" if segs and not any(
                e["type"] == "no_inid" for e in events) else "degraded")}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pdf")
    src.add_argument("--text")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv[1:])
    if args.pdf:
        text, err = pdftotext(args.pdf)
        label = args.pdf
        if err:
            print(json.dumps({"source": args.pdf, "extraction_status": "failed",
                              "error": err}, ensure_ascii=False))
            return 2
    else:
        label = args.text
        try:
            with open(args.text, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            print(json.dumps({"source": args.text, "extraction_status": "failed",
                              "error": str(e)}, ensure_ascii=False))
            return 2
    result = extract(text, label)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({"out": args.out, "status": result["extraction_status"],
                      "fields": len(result["fields"]),
                      "events": len(result["evidence_events"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
