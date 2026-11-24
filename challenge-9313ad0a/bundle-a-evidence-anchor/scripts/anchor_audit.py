#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""anchor_audit.py — 思维导图证据锚定审计工具（仅依赖 Python 3.10+ 标准库）。

用法：
    python3 scripts/anchor_audit.py \
        --map mindmap.json \
        --material /app/work/material/pages.jsonl \
        --report anchor_report.json \
        --quarantine quarantine.json

输入思维导图 schema：
    {"nodes": [{"id", "label", "kind", "basis": "fact"|"summary"|"inference",
                "note": 可选, "evidence": [{"file", "page", "section", "quote"}]}]}

逐节点核验规则：
  1. basis=fact 的每条证据引文，必须与所引 文件+页 的文本逐字一致
     （先规范化：压缩连续空白为单个空格，统一 Unicode 破折号/引号为 ASCII）。
     - 未出现于所引页、但出现于同文件其他页 → mislocated（给出真实页码）；
     - 在整个文件中均不出现 → fabricated。
  2. basis=fact 而无任何证据 → unanchored。
  3. 节点标签中的每个数字（正则 \\d+(\\.\\d+)?%?）必须出现于全部材料文本
     的并集中，否则 → number_not_found。
  4. 证据页码超出该文件页范围（或所引文件未入库）→ page_out_of_range。
  5. basis=inference 而无 note → warning。

输出：
  * anchor_report.json
    {"summary": {"nodes", "verified", "mislocated", "fabricated",
                  "unanchored", "number_not_found", "warnings"},
     "findings": [{"node_id", "check", "verdict", "detail", "evidence"?}]}
  * quarantine.json
    {"quarantine": [必须修正或删除的节点 id（fabricated / unanchored /
      number_not_found / page_out_of_range）], "rule": "..."}

退出码：存在 fabricated 或 unanchored 的 fact 节点时为 1，否则为 0。
输出为确定性结果：不写入时间戳，节点与页码均按输入顺序处理。
"""

import argparse
import json
import os
import re
import sys

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")
_WS_RE = re.compile(r"\s+")

_UNICODE_DASHES = ["‐", "‑", "‒", "–", "—", "―", "−"]
_UNICODE_DQUOTES = ["“", "”", "″", "«", "»"]
_UNICODE_SQUOTES = ["‘", "’", "′"]

QUARANTINE_VERDICTS = {"fabricated", "unanchored", "number_not_found", "page_out_of_range"}
QUARANTINE_RULE = (
    "凡被判定为 fabricated / unanchored / number_not_found / page_out_of_range 的节点，"
    "必须修正或删除后方可进入最终交付的思维导图；mislocated 节点须更正定位"
    "（文件/页码/章节）后重新审计。"
)


def normalize(text):
    """规范化文本：统一破折号与引号为 ASCII，压缩连续空白，去除首尾空白。"""
    if text is None:
        return ""
    for ch in _UNICODE_DASHES:
        text = text.replace(ch, "-")
    for ch in _UNICODE_DQUOTES:
        text = text.replace(ch, '"')
    for ch in _UNICODE_SQUOTES:
        text = text.replace(ch, "'")
    return _WS_RE.sub(" ", text).strip()


def load_pages(path):
    """读取 pages.jsonl，返回 {file: {page: text}}（保持插入顺序）。

    pages.jsonl 记录的是调用 intake 时传入的路径（可能含目录），而
    思维导图证据中常写裸文件名；此处为基本文件名建立别名，使两种
    写法都能命中（同名不同目录时保留先出现者，属已知限制）。
    """
    pages_by_file = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            pages_by_file.setdefault(rec["file"], {})[int(rec["page"])] = rec.get("text", "")
    for name in list(pages_by_file):
        base = os.path.basename(name)
        if base and base != name:
            pages_by_file.setdefault(base, pages_by_file[name])
    return pages_by_file


def parse_page(value):
    """宽容地把证据页码解析为 int；失败返回 None。"""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def audit(nodes, pages_by_file):
    findings = []
    node_defects = {}     # node_id -> set(defect verdicts)
    verified_nodes = set()
    warning_count = 0

    # 全部材料的规范化文本并集，用于数字存在性核验
    corpus = normalize(" ".join(
        text for pages in pages_by_file.values() for text in pages.values()
    ))
    # 规范化页文本缓存：{(file, page): normalized_text}
    norm_cache = {}

    def norm_page(file_name, page_no):
        key = (file_name, page_no)
        if key not in norm_cache:
            norm_cache[key] = normalize(pages_by_file[file_name].get(page_no, ""))
        return norm_cache[key]

    def add_defect(node_id, verdict):
        node_defects.setdefault(node_id, set()).add(verdict)

    for node in nodes:
        node_id = node.get("id")
        label = node.get("label", "") or ""
        basis = node.get("basis", "")
        evidence = node.get("evidence") or []

        # 规则 5（以及 basis 合法性检查）
        if basis not in ("fact", "summary", "inference"):
            findings.append({
                "node_id": node_id,
                "check": "basis_valid",
                "verdict": "warning",
                "detail": "无法识别的 basis 取值：%r（应为 fact/summary/inference）" % basis,
            })
            warning_count += 1
        if basis == "inference" and not node.get("note"):
            findings.append({
                "node_id": node_id,
                "check": "inference_note",
                "verdict": "warning",
                "detail": "basis=inference 但未提供 note 说明推理依据",
            })
            warning_count += 1

        # 规则 1、2、4：证据核验（仅 basis=fact）
        if basis == "fact":
            if not evidence:
                findings.append({
                    "node_id": node_id,
                    "check": "anchoring",
                    "verdict": "unanchored",
                    "detail": "basis=fact 但未提供任何证据（evidence 为空）",
                })
                add_defect(node_id, "unanchored")
            else:
                for ev in evidence:
                    file_name = ev.get("file")
                    page_no = parse_page(ev.get("page"))
                    quote = ev.get("quote", "") or ""

                    if file_name not in pages_by_file:
                        findings.append({
                            "node_id": node_id,
                            "check": "evidence_page",
                            "verdict": "page_out_of_range",
                            "detail": "所引材料文件 %r 未入库" % file_name,
                            "evidence": ev,
                        })
                        add_defect(node_id, "page_out_of_range")
                        continue

                    pages = pages_by_file[file_name]
                    max_page = max(pages) if pages else 0
                    if page_no is None or page_no < 1 or page_no > max_page:
                        findings.append({
                            "node_id": node_id,
                            "check": "evidence_page",
                            "verdict": "page_out_of_range",
                            "detail": "页码 %r 超出文件 %r 的页范围 1–%d"
                                      % (ev.get("page"), file_name, max_page),
                            "evidence": ev,
                        })
                        add_defect(node_id, "page_out_of_range")
                        continue

                    norm_quote = normalize(quote)
                    if norm_quote and norm_quote in norm_page(file_name, page_no):
                        findings.append({
                            "node_id": node_id,
                            "check": "quote_verbatim",
                            "verdict": "verified",
                            "detail": "引文与 %s 第 %d 页文本逐字一致" % (file_name, page_no),
                            "evidence": ev,
                        })
                        verified_nodes.add(node_id)
                    else:
                        true_pages = [
                            p for p in sorted(pages)
                            if norm_quote and norm_quote in norm_page(file_name, p)
                        ]
                        if true_pages:
                            findings.append({
                                "node_id": node_id,
                                "check": "quote_verbatim",
                                "verdict": "mislocated",
                                "detail": "引文未出现于第 %d 页，实际出现于 %s 第 %d 页"
                                          % (page_no, file_name, true_pages[0]),
                                "evidence": ev,
                            })
                            add_defect(node_id, "mislocated")
                        else:
                            findings.append({
                                "node_id": node_id,
                                "check": "quote_verbatim",
                                "verdict": "fabricated",
                                "detail": "引文在文件 %s 的全部页面中均不存在，"
                                          "疑似改写或杜撰" % file_name,
                                "evidence": ev,
                            })
                            add_defect(node_id, "fabricated")

        # 规则 3：标签数字存在性核验（所有节点）
        numbers = NUMBER_RE.findall(normalize(label))
        missing = []
        for num in numbers:
            if num not in corpus and num not in missing:
                missing.append(num)
        if missing:
            findings.append({
                "node_id": node_id,
                "check": "label_number",
                "verdict": "number_not_found",
                "detail": "标签中的数字 %s 在全部材料文本中均未出现"
                          % "、".join(missing),
            })
            add_defect(node_id, "number_not_found")

    summary = {
        "nodes": len(nodes),
        "verified": sum(
            1 for n in nodes
            if n.get("id") in verified_nodes
            and not node_defects.get(n.get("id"), set())
        ),
        "mislocated": sum(1 for d in node_defects.values() if "mislocated" in d),
        "fabricated": sum(1 for d in node_defects.values() if "fabricated" in d),
        "unanchored": sum(1 for d in node_defects.values() if "unanchored" in d),
        "number_not_found": sum(1 for d in node_defects.values() if "number_not_found" in d),
        "warnings": warning_count,
    }

    quarantine = [
        node.get("id") for node in nodes
        if node_defects.get(node.get("id"), set()) & QUARANTINE_VERDICTS
    ]
    has_fatal = any(
        d & {"fabricated", "unanchored"} for d in node_defects.values()
    )
    return summary, findings, quarantine, has_fatal


def main(argv=None):
    parser = argparse.ArgumentParser(description="思维导图证据锚定审计")
    parser.add_argument("--map", required=True, help="思维导图 JSON 文件路径")
    parser.add_argument("--material", required=True, help="material_intake 生成的 pages.jsonl")
    parser.add_argument("--report", required=True, help="审计报告输出路径（JSON）")
    parser.add_argument("--quarantine", required=True, help="隔离清单输出路径（JSON）")
    args = parser.parse_args(argv)

    with open(args.map, "r", encoding="utf-8") as fh:
        mindmap = json.load(fh)
    nodes = mindmap.get("nodes", [])
    pages_by_file = load_pages(args.material)

    summary, findings, quarantine, has_fatal = audit(nodes, pages_by_file)

    report = {"summary": summary, "findings": findings}
    for path, obj in (
        (args.report, report),
        (args.quarantine, {"quarantine": quarantine, "rule": QUARANTINE_RULE}),
    ):
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2)
            fh.write("\n")

    print("审计完成：节点 %(nodes)d，verified %(verified)d，mislocated %(mislocated)d，"
          "fabricated %(fabricated)d，unanchored %(unanchored)d，"
          "number_not_found %(number_not_found)d，warnings %(warnings)d。" % summary)
    print("隔离节点 %d 个 -> %s" % (len(quarantine), args.quarantine))
    print("审计报告 -> %s" % args.report)

    return 1 if has_fatal else 0


if __name__ == "__main__":
    sys.exit(main())
