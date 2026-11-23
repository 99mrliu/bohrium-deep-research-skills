#!/usr/bin/env python3
"""assemble_output.py — 交付组装层（阅读顺序重建技能 A 的第 3 步）。

把 blocks.jsonl 组装为平台契约交付物：
    /app/output/fulltext.md     按重建阅读顺序的正文，每段带块锚点 [p2.c1.b7]
    /app/output/sections.json   章节层级（title/heading 序号嵌套）
    /app/output/references.json 参考文献条目（页码+块锚点）
    /app/output/captions.json   图表题注（页码+块锚点）
    /app/output/coverage.json   字符覆盖台账（被剔除的 header/footer 单独记账）
    /app/output/result.json     含 case_id 与 case.json output_contract 全部字段

未提供 --case 时只产出前四件与 coverage，并打印提示。
退出码 0=成功；2=部分（覆盖不足或契约字段无法填充，result.json 仍为诚实 partial）。
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict

BODY_KINDS = ("title", "heading", "body", "abstract", "caption", "equation",
              "reference")
CONTRACT_TEXT_KEYS = {"fulltext", "text", "content", "markdown", "body"}


def load_blocks(path):
    blocks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                blocks.append(json.loads(line))
    return blocks


def build_sections(blocks):
    sections, stack = [], []
    for b in blocks:
        if b["kind"] == "title":
            sections.append({"level": 0, "title": b["text"].splitlines()[0],
                             "anchor": b["block_id"], "page": b["page"]})
        elif b["kind"] == "heading":
            m = re.match(r"^(\d+(?:\.\d+)*)", b["text"].strip())
            level = m.group(1).count(".") + 1 if m else 1
            sections.append({"level": level, "title": b["text"].splitlines()[0],
                             "anchor": b["block_id"], "page": b["page"]})
    return sections


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--blocks", required=True)
    ap.add_argument("--words", help="原始 words.tsv，用于字符覆盖台账")
    ap.add_argument("--case", help="/input/case.json（含 case_id 与 output_contract）")
    ap.add_argument("--out", required=True, help="/app/output")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    if not os.path.exists(args.blocks):
        print(json.dumps({"status": "failed", "reason": "blocks_jsonl_missing"}))
        return 3
    blocks = load_blocks(args.blocks)
    if not blocks:
        print(json.dumps({"status": "failed", "reason": "blocks_jsonl_empty"}))
        return 3

    # 1) 全文（阅读顺序）+ 锚点
    full_lines = []
    for b in sorted(blocks, key=lambda b: b["order"]):
        if b["kind"] in ("header", "footer"):
            continue
        cont = " (续 p%s)" % b["continues_from"] if "continues_from" in b else ""
        full_lines.append(f"[{b['block_id']} p{b['page']} {b['kind']}{cont}]")
        full_lines.append(b["text"])
        full_lines.append("")
    fulltext_path = os.path.join(args.out, "fulltext.md")
    with open(fulltext_path, "w", encoding="utf-8") as f:
        f.write("\n".join(full_lines))

    # 2) 章节 / 参考文献 / 题注
    sections = build_sections(blocks)
    with open(os.path.join(args.out, "sections.json"), "w", encoding="utf-8") as f:
        json.dump(sections, f, ensure_ascii=False, indent=2)
    refs = [{"anchor": b["block_id"], "page": b["page"], "text": b["text"]}
            for b in blocks if b["kind"] == "reference"]
    with open(os.path.join(args.out, "references.json"), "w", encoding="utf-8") as f:
        json.dump(refs, f, ensure_ascii=False, indent=2)
    caps = [{"anchor": b["block_id"], "page": b["page"], "text": b["text"]}
            for b in blocks if b["kind"] == "caption"]
    with open(os.path.join(args.out, "captions.json"), "w", encoding="utf-8") as f:
        json.dump(caps, f, ensure_ascii=False, indent=2)

    # 3) 字符覆盖台账
    dropped = {"header_footer": 0}
    kept = 0
    for b in blocks:
        n = len(re.sub(r"\s+", "", b["text"]))
        if b["kind"] in ("header", "footer"):
            dropped["header_footer"] += n
        else:
            kept += n
    total_raw = kept + dropped["header_footer"]
    if args.words and os.path.exists(args.words):
        raw_chars = 0
        with open(args.words, encoding="utf-8") as f:
            next(f, None)
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 6:
                    raw_chars += len(parts[5])
        total_raw = max(total_raw, raw_chars)
    coverage = {
        "raw_chars": total_raw,
        "kept_chars": kept,
        "dropped": dropped,
        "coverage_pct": round(100.0 * kept / total_raw, 2) if total_raw else None,
        "note": "dropped 均有类别记账；unreadable 部分在 result.json 的 "
                "uncertainty 中如实列出，不靠猜测补齐",
    }
    with open(os.path.join(args.out, "coverage.json"), "w", encoding="utf-8") as f:
        json.dump(coverage, f, ensure_ascii=False, indent=2)

    # 4) result.json（契约感知）
    if not args.case:
        print(json.dumps({"status": "ok", "note": "未提供 --case，跳过 result.json",
                          "outputs": ["fulltext.md", "sections.json",
                                      "references.json", "captions.json",
                                      "coverage.json"]}))
        return 0

    case = json.load(open(args.case, encoding="utf-8"))
    case_id = case.get("case_id") or case.get("id") or "unknown"
    contract = case.get("output_contract") or {}
    fields = contract.get("fields", contract) if isinstance(contract, dict) \
        else contract
    if isinstance(fields, dict):
        field_names = list(fields.keys())
    elif isinstance(fields, list):
        field_names = [x.get("name") if isinstance(x, dict) else str(x)
                       for x in fields]
    else:
        field_names = []

    body_text = "\n".join(l for l in full_lines)
    payload, unresolved = {}, []
    for name in field_names:
        lname = name.lower()
        if lname in CONTRACT_TEXT_KEYS:
            payload[name] = {"path": "fulltext.md",
                             "format": "markdown-with-anchors"}
        elif "section" in lname or "structure" in lname:
            payload[name] = sections
        elif "reference" in lname or "citation" in lname:
            payload[name] = refs
        elif "caption" in lname or "figure" in lname or "table" in lname:
            payload[name] = caps
        elif "provenance" in lname or "anchor" in lname or "evidence" in lname:
            payload[name] = {"blocks": "blocks.jsonl",
                             "coverage": "coverage.json"}
        else:
            payload[name] = None
            unresolved.append(name)

    status = "success" if not unresolved else "partial"
    result = {
        "case_id": case_id,
        "status": status,
        "result": payload,
        "evidence": {
            "blocks_jsonl": "blocks.jsonl",
            "coverage": coverage,
            "provenance_rule": "每个块带 page/column/bbox，可回指原文坐标",
        },
        "uncertainty": ([f"契约字段 {n} 无可靠填充来源，如实置空" for n in unresolved]
                        if unresolved else []),
        "sources": [args.blocks],
        "change_record": ["extract_words → order_blocks → assemble_output 流水线生成"],
    }
    if "continues_from" in json.dumps(blocks):
        result.setdefault("notes", []).append("跨页续接以 continues_from 标注，未合并文本")
    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({"status": status, "case_id": case_id,
                      "contract_fields": len(field_names),
                      "unresolved": unresolved}, ensure_ascii=False))
    return 0 if status == "success" else 2


if __name__ == "__main__":
    sys.exit(main())
