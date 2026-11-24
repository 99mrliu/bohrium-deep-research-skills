#!/usr/bin/env python3
"""quote_bind.py — finding 原文锚定的机械核验器

对每条 finding 的 location.quote 做纯机械的逐字核验：
  1. exact：quote 逐字（区分大小写、含原始空白）出现在声称页的页文本中；
  2. normalized：先做空白归一化（任意连续空白 -> 单个空格）后能匹配；
  3. cross_page_exact / cross_page_normalized：声称页未命中，但命中
     "声称页 + 下一页" 的拼接文本（跨页摘录场景，references/anchoring_rules.md）；
  4. none：以上全部失败 —— 自动把 verdict_status 改为 "待复核"，
     并在 verdict_reasons 追加 "锚定核验未通过"，杜绝"编定位"。
  quote 为空/缺失（"全文缺失 X 声明"类 absence finding）不参与匹配，
  记 match_level=skipped_absence_claim，不降级，但需人工确认。

额外诊断：found_on_pages 列出 quote（归一化后）实际命中的全部页码，
帮助发现"写错页码"与"凭印象改写 quote"两类常见错误。

输入 findings 可以是 JSON 数组，也可以是含 "findings" 键的对象；
缺键不崩（exit 0），坏记录在 warnings 中如实报告。

仅 Python3 标准库；确定性输出；单次运行远低于 5 秒。
"""
import argparse
import json
import os
import re
import sys

WS_RE = re.compile(r"\s+")


def normalize(text):
    """空白归一化：任意连续空白（含换行）折叠为单个空格。"""
    return WS_RE.sub(" ", text or "").strip()


def load_json(path, default, warnings):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        warnings.append("文件不存在：%s（按空处理）" % path)
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append("无法解析 %s：%s（按空处理）" % (path, exc))
    return default


def match_on_text(quote, text):
    """返回 'exact' / 'normalized' / None。"""
    if not text:
        return None
    if quote in text:
        return "exact"
    if normalize(quote) in normalize(text):
        return "normalized"
    return None


def bind_one(finding, pages_by_no, ordered_pages, source_file, warnings):
    """对单条 finding 做锚定核验，原地补充 anchor 字段并可能降级。"""
    fid = finding.get("id", "<no-id>")
    loc = finding.get("location") or {}
    if not isinstance(loc, dict):
        warnings.append("finding %s 的 location 不是对象，按空处理" % fid)
        loc = {}
    quote = loc.get("quote")
    page_no = loc.get("page")
    claimed_file = loc.get("file")

    anchor = {
        "claimed_file": claimed_file,
        "claimed_page": page_no,
        "match_level": None,
        "cross_page": False,
        "found_on_pages": [],
    }

    # 0) absence 类 finding：无 quote 可核验
    if not quote or not str(quote).strip():
        anchor["match_level"] = "skipped_absence_claim"
        anchor["note"] = "quote 为空（缺失声明类 finding），锚定核验不适用，需人工复核全文"
        finding["anchor"] = anchor
        return finding, "skipped"

    quote = str(quote)

    # 1) 文件一致性
    if claimed_file and source_file and os.path.basename(str(claimed_file)) != source_file:
        anchor["file_mismatch"] = True

    # 2) 全库诊断：quote 实际出现在哪些页（归一化口径）
    for pg in ordered_pages:
        if normalize(quote) in normalize(pg["text"]):
            anchor["found_on_pages"].append(pg["page_no"])

    # 3) 声称页核验
    level = None
    claimed_page_text = None
    if isinstance(page_no, int) and page_no in pages_by_no:
        claimed_page_text = pages_by_no[page_no]["text"]
        level = match_on_text(quote, claimed_page_text)
    else:
        anchor["page_invalid"] = True

    # 4) 跨页兜底：声称页 + 下一页拼接
    if level is None and isinstance(page_no, int):
        nxt = pages_by_no.get(page_no + 1)
        cur = pages_by_no.get(page_no)
        if cur is not None and nxt is not None:
            joined = cur["text"] + "\n" + nxt["text"]
            level = match_on_text(quote, joined)
            if level is not None:
                anchor["cross_page"] = True
                level = "cross_page_" + level

    if level is None:
        anchor["match_level"] = "none"
    else:
        anchor["match_level"] = level
    finding["anchor"] = anchor

    # 5) 降级纪律：锚定失败 -> verdict_status=待复核 + 理由
    if anchor["match_level"] == "none":
        finding["verdict_status"] = "待复核"
        reasons = finding.get("verdict_reasons")
        if not isinstance(reasons, list):
            reasons = [] if reasons is None else [str(reasons)]
        detail = "锚定核验未通过：quote 未逐字出现在声称位置（file=%s, page=%s）" % (
            claimed_file, page_no)
        if anchor.get("page_invalid"):
            detail += "；声称页码无效或超出抽取页范围"
        if anchor.get("file_mismatch"):
            detail += "；声称文件与抽取来源文件不一致（source=%s）" % source_file
        if anchor["found_on_pages"]:
            detail += "；该 quote 实际命中页：%s" % anchor["found_on_pages"]
        reasons.append(detail)
        finding["verdict_reasons"] = reasons
        return finding, "none"

    if anchor.get("file_mismatch"):
        # quote 命中但文件声称有误：不降级，但如实标注
        finding.setdefault("verdict_reasons", [])
        if isinstance(finding["verdict_reasons"], list):
            finding["verdict_reasons"].append(
                "锚定提示：声称文件与抽取来源不一致（claimed=%s, source=%s），请人工确认"
                % (claimed_file, source_file))
    return finding, "verified"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="机械核验每条 finding 的 location.quote 是否逐字出现在声称页；"
                    "核验失败自动降级 verdict_status=待复核。"
    )
    ap.add_argument("--pages", required=True, help="extract_text.py 产出的 pages.json")
    ap.add_argument("--findings", required=True, help="findings 草稿 JSON（数组或含 findings 键的对象）")
    ap.add_argument("--out", required=True, help="绑定后的 findings 输出路径")
    ap.add_argument("--stats", default=None, help="锚定统计输出路径（可选）")
    args = ap.parse_args(argv)

    warnings = []
    pages_doc = load_json(args.pages, {}, warnings)
    if not isinstance(pages_doc, dict):
        pages_doc = {}
    ordered_pages = pages_doc.get("pages") or []
    ordered_pages = [p for p in ordered_pages
                     if isinstance(p, dict) and isinstance(p.get("page_no"), int)]
    pages_by_no = {p["page_no"]: p for p in ordered_pages}
    source_file = pages_doc.get("source_file") or ""

    findings_doc = load_json(args.findings, [], warnings)
    if isinstance(findings_doc, dict):
        findings = findings_doc.get("findings") or []
    elif isinstance(findings_doc, list):
        findings = findings_doc
    else:
        findings = []
    findings = [f for f in findings if isinstance(f, dict)]

    stats = {"total_findings": 0, "verified": 0, "exact": 0, "normalized": 0,
             "cross_page": 0, "skipped_absence_claim": 0, "downgraded": 0,
             "downgraded_ids": []}

    bound = []
    for finding in findings:
        stats["total_findings"] += 1
        finding, outcome = bind_one(finding, pages_by_no, ordered_pages,
                                    source_file, warnings)
        ml = (finding.get("anchor") or {}).get("match_level")
        if outcome == "verified":
            stats["verified"] += 1
            if ml == "exact":
                stats["exact"] += 1
            elif ml == "normalized":
                stats["normalized"] += 1
            elif ml and ml.startswith("cross_page"):
                stats["cross_page"] += 1
        elif outcome == "skipped":
            stats["skipped_absence_claim"] += 1
        else:
            stats["downgraded"] += 1
            stats["downgraded_ids"].append(finding.get("id", "<no-id>"))
        bound.append(finding)

    for w in (pages_doc.get("warnings") or []):
        warnings.append("pages.json: " + str(w))

    out_payload = {"findings": bound, "warnings": warnings}
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out_payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    stats["warnings"] = warnings
    if args.stats:
        s_dir = os.path.dirname(os.path.abspath(args.stats))
        os.makedirs(s_dir, exist_ok=True)
        with open(args.stats, "w", encoding="utf-8") as fh:
            json.dump(stats, fh, ensure_ascii=False, indent=2)
            fh.write("\n")

    print("quote_bind: total=%d verified=%d (exact=%d normalized=%d cross_page=%d) "
          "skipped=%d downgraded=%d %s"
          % (stats["total_findings"], stats["verified"], stats["exact"],
             stats["normalized"], stats["cross_page"],
             stats["skipped_absence_claim"], stats["downgraded"],
             stats["downgraded_ids"]))
    for w in warnings:
        print("  WARNING: " + w, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
