#!/usr/bin/env python3
"""机器核验 evidence 的 (locator, quote)，不允许人工豁免。"""
import argparse
import json
import os
import re
import sys

from source_index import atomic_json, normalize_with_map


def read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def collect_evidence(root):
    found = []

    def walk(node, owner, path):
        if isinstance(node, dict):
            current = str(node.get("id") or node.get("item_id") or node.get("question_id") or owner or "unowned")
            if "locator" in node or "quote" in node:
                found.append({"owner": current, "path": path, "locator": node.get("locator"), "quote": node.get("quote")})
                return
            for key in sorted(node):
                walk(node[key], current, path + "." + key)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, owner, path + "[%d]" % index)

    walk(root, None, "$")
    return found


def canonical(token):
    token = str(token or "").strip().lower()
    token = re.sub(r"^doc\d+\.", "", token)
    token = re.sub(r"^p\.?", "p", token)
    return token


def resolve(index, locator):
    if not isinstance(locator, str) or "#" not in locator:
        return None, None, "locator 必须为 <文件名>#<锚点ID>。"
    filename, token = locator.rsplit("#", 1)
    docs = [doc for doc in index.get("documents", []) if doc.get("file") == filename]
    if not docs:
        return None, None, "索引中找不到声称文件：" + filename
    candidates = [anchor for anchor in docs[0].get("anchors", []) if canonical(anchor.get("anchor_id")) == canonical(token) or str(anchor.get("anchor_id", "")).lower() == token.strip().lower()]
    if not candidates:
        return docs[0], None, "文件中找不到声称锚点：" + token
    return docs[0], candidates[0], ""


def defect_classifier(index, quote):
    defects, advice = [], "先修复标注的抽取缺陷并重建 source_index.json；不可修复时提交人工粘贴文本与争议说明，不得自行改写引文。"
    for doc in index.get("documents", []):
        if doc.get("degraded"):
            defects.append(doc.get("file", "?") + ":extraction_degraded")
        for anchor in doc.get("anchors", []):
            raw = anchor.get("raw_text", "")
            if not raw.strip():
                defects.append(anchor.get("anchor_id", "?") + ":empty_page_or_anchor")
            if any(char in raw for char in "ﬀﬁﬂﬃﬄ") or any(char in quote for char in "ﬀﬁﬂﬃﬄ"):
                defects.append(anchor.get("anchor_id", "?") + ":ligature_risk")
            if quote.count("|") >= 2 and raw.count("|") >= 2:
                defects.append(anchor.get("anchor_id", "?") + ":table_alignment_risk")
    return sorted(set(defects)), advice


def verify(index, record):
    owner, quote, locator = record["owner"], record["quote"], record["locator"]
    base = {"item_id": owner, "evidence_path": record["path"], "locator": locator, "quote": quote}
    if not isinstance(quote, str) or not quote.strip():
        return dict(base, verdict="fail", reason="quote 缺失或为空。", machine_code="empty_quote")
    normalized_quote = normalize_with_map(quote)[0]
    doc, anchor, error = resolve(index, locator)
    if anchor is None:
        return dict(base, verdict="fail", reason=error, machine_code="bad_locator")
    normalized_anchor = anchor.get("normalized_text", "")
    position = normalized_anchor.find(normalized_quote)
    if position >= 0:
        offsets = anchor.get("offset_map", [])
        start = offsets[position] if position < len(offsets) else None
        last = position + len(normalized_quote) - 1
        end = offsets[last] + 1 if last < len(offsets) else None
        raw = anchor.get("raw_text", "")
        return dict(base, verdict="pass", reason="归一化引文在声称锚点内逐字命中。", machine_code="anchored_exact_match", matched_anchor=anchor.get("anchor_id"), normalized_span=[position, position + len(normalized_quote)], original_span=[start, end], original_match=raw[start:end] if start is not None and end is not None else None)
    elsewhere = []
    for other_doc in index.get("documents", []):
        for other in other_doc.get("anchors", []):
            if normalized_quote in other.get("normalized_text", ""):
                elsewhere.append(other_doc.get("file", "?") + "#" + other.get("anchor_id", "?"))
    if elsewhere:
        return dict(base, verdict="fail", reason="引文仅在别的锚点命中，属于页码/锚点漂移。", machine_code="locator_drift", found_elsewhere=sorted(elsewhere))
    defects, advice = defect_classifier(index, normalized_quote)
    if defects:
        return dict(base, verdict="degraded", reason="全库未命中，但检测到可能的源抽取缺陷；不能视为已核验。", machine_code="possible_extraction_defect", defects=defects, dispute_advice=advice)
    return dict(base, verdict="fail", reason="归一化引文在全库都找不到，疑似幻觉或改写。", machine_code="not_in_corpus", dispute_advice="回到原文复制连续片段并修正锚点；若原文不支持，删除该论断或显式标记无法判断。")


def default_work_file():
    for name in ("items_validated.json", "items.json", "answers_validated.json", "answers.json"):
        path = os.path.join("/app/work", name)
        if os.path.isfile(path):
            return path
    return "/app/work/items.json"


def main():
    parser = argparse.ArgumentParser(description="逐条验证引文锚点；输出 pass/fail/degraded 及机器理由。")
    parser.add_argument("--work-file", default=None, help="answers.json 或 items.json；默认自动探测 /app/work")
    parser.add_argument("--index", default="/app/work/source_index.json", help="source_index.json 路径")
    parser.add_argument("--output", default="/app/work/verdicts.json", help="裁决输出路径")
    parser.add_argument("--strict", action="store_true", help="存在 fail/degraded 时退出码为 2")
    args = parser.parse_args()
    work_path = args.work_file or default_work_file()
    try:
        index = read_json(args.index)
        work = read_json(work_path)
        records = collect_evidence(work)
        verdicts = [verify(index, record) for record in records]
        defects = []
    except Exception as exc:
        verdicts = [{"item_id": "quote_gate", "evidence_path": "$", "locator": None, "quote": None, "verdict": "fail", "machine_code": "input_error", "reason": "输入缺失或 JSON 畸形：" + str(exc)}]
        defects = ["工作文件或索引不可解析；已写缺陷记录，未执行语义猜测。"]
    counts = {key: sum(1 for row in verdicts if row["verdict"] == key) for key in ("pass", "fail", "degraded")}
    result = {"schema_version": "1.0", "work_file": os.path.basename(work_path), "verdicts": verdicts, "summary": counts, "defects": defects, "delivery_allowed": counts["fail"] == 0 and counts["degraded"] == 0}
    atomic_json(args.output, result)
    print("quote_gate: pass=%d fail=%d degraded=%d delivery_allowed=%s" % (counts["pass"], counts["fail"], counts["degraded"], result["delivery_allowed"]))
    if args.strict and not result["delivery_allowed"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
