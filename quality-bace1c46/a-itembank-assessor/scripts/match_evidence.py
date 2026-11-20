#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""match_evidence.py — 条目级证据检索辅助。

读取条目库（--itembank，默认探测脚本同级 ../itembank）、design.json 与页面文本，
对每个适用条目输出 top-N 候选段落（含页锚与命中词），写 candidates/<doc_id>.json。
候选仅供模型定位；判断与摘录须由模型回到原文完成。
仅标准库。
"""
import argparse
import json
import os
import re
import sys

ITEM_HEADER = re.compile(r"^## \[(?P<iid>[A-Z]+-\d+)\]\s*(?P<title>.*)$", re.M)
FIELD_LINE = re.compile(r"^-\s*(?P<key>维度|问题|所需证据|不可评价|核心|关键词)\s*[:：]\s*(?P<val>.*)$", re.M)

TYPE_FILE_MAP = {
    "rct": "rct.md",
    "cohort": "cohort.md",
    "case_control": "case_control.md",
    "cross_sectional": "cross_sectional.md",
    "diagnostic": "diagnostic.md",
    "systematic_review": "systematic_review.md",
}


def log(msg):
    print("[match_evidence] %s" % msg, file=sys.stderr)


def default_itembank():
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.normpath(os.path.join(here, "..", "itembank"))
    return cand if os.path.isdir(cand) else "itembank"


def split_paragraphs(text):
    """与 extract_corpus.py 保持一致的段落切分逻辑。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    if len(paras) <= 1 and (text or "").strip():
        lines = [l.rstrip() for l in text.splitlines() if l.strip()]
        paras, buf = [], []
        for l in lines:
            buf.append(l)
            if len(buf) >= 6:
                paras.append("\n".join(buf))
                buf = []
        if buf:
            paras.append("\n".join(buf))
    return paras


def parse_itembank(itembank_dir):
    """解析条目库 markdown，返回条目列表。"""
    items = []
    if not os.path.isdir(itembank_dir):
        log("条目库目录不存在: %s" % itembank_dir)
        return items
    for fn in sorted(os.listdir(itembank_dir)):
        if not fn.endswith(".md") or fn == "README.md":
            continue
        ftype = os.path.splitext(fn)[0]
        path = os.path.join(itembank_dir, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            log("条目库读取失败 %s: %s" % (path, e))
            continue
        matches = list(ITEM_HEADER.finditer(text))
        for i, m in enumerate(matches):
            block = text[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)]
            fields = {}
            for fl in FIELD_LINE.finditer(block):
                fields[fl.group("key")] = fl.group("val").strip()
            kws = [k.strip() for k in re.split(r"[,，;；]", fields.get("关键词", "")) if k.strip()]
            items.append({
                "item_id": m.group("iid"),
                "title": m.group("title").strip(),
                "type": ftype,
                "dimension": fields.get("维度", ""),
                "question": fields.get("问题", ""),
                "evidence_needed": fields.get("所需证据", ""),
                "na_condition": fields.get("不可评价", ""),
                "core": fields.get("核心", "").startswith("是"),
                "keywords": kws,
            })
    return items


def applicable_items(items, design_type):
    out = [it for it in items if it["type"] == "common"]
    fn = TYPE_FILE_MAP.get(design_type)
    if fn:
        out += [it for it in items if it["type"] == os.path.splitext(fn)[0]]
    return out


def find_candidates(pages, keywords, top_n):
    cands = []
    for pg in pages:
        for k, para in enumerate(split_paragraphs(pg["text"])):
            low = para.casefold()
            hits = [kw for kw in keywords if kw.casefold() in low]
            if hits:
                cands.append({
                    "anchor": "p%d.¶%d" % (pg["page"], k + 1),
                    "page": pg["page"],
                    "score": len(hits),
                    "hits": hits,
                    "text": para[:400],
                })
    cands.sort(key=lambda c: (-c["score"], c["page"]))
    return cands[:top_n]


def main():
    ap = argparse.ArgumentParser(description="条目级候选证据抽取")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--itembank", default=None)
    ap.add_argument("--top-n", type=int, default=5)
    args = ap.parse_args()

    itembank_dir = args.itembank or default_itembank()
    items = parse_itembank(itembank_dir)
    log("条目库共 %d 条（来源 %s）" % (len(items), itembank_dir))

    design = {"docs": {}}
    dpath = os.path.join(args.work, "design.json")
    if os.path.isfile(dpath):
        with open(dpath, "r", encoding="utf-8") as f:
            design = json.load(f)

    cand_dir = os.path.join(args.work, "candidates")
    os.makedirs(cand_dir, exist_ok=True)

    docs_path = os.path.join(args.work, "docs.jsonl")
    if not os.path.isfile(docs_path):
        log("docs.jsonl 不存在，退出")
        return 0

    with open(docs_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            doc_id = rec["doc_id"]
            if rec.get("tier") == "failed":
                continue
            dt = design.get("docs", {}).get(doc_id, {}).get("design_type", "other")
            pages = []
            ppath = os.path.join(args.work, "pages", doc_id + ".jsonl")
            try:
                with open(ppath, "r", encoding="utf-8") as pf:
                    for pl in pf:
                        pl = pl.strip()
                        if pl:
                            pages.append(json.loads(pl))
            except Exception as e:
                log("页面读取失败 %s: %s" % (ppath, e))
                continue
            out_items = []
            for it in applicable_items(items, dt):
                out_items.append({
                    "item_id": it["item_id"],
                    "dimension": it["dimension"],
                    "core": it["core"],
                    "question": it["question"],
                    "evidence_needed": it["evidence_needed"],
                    "na_condition": it["na_condition"],
                    "candidates": find_candidates(pages, it["keywords"], args.top_n),
                })
            out = {"doc_id": doc_id, "design_type": dt, "tier": rec.get("tier"),
                   "items": out_items}
            with open(os.path.join(cand_dir, doc_id + ".json"), "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            log("%s: %d 个条目候选已生成" % (doc_id, len(out_items)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
