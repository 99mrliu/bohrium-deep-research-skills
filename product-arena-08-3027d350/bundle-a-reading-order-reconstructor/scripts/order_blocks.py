#!/usr/bin/env python3
"""order_blocks.py — 版面结构重建层（阅读顺序重建技能 A 的第 2 步）。

读取 words.tsv（+ 可选 pages_meta.json），完成四件事：
    1. 词→行→块 聚类（行高容差、纵间距切分）；
    2. 页眉页脚识别（页面边缘 + 跨页重复，忽略页码数字差异）；
    3. 每页分栏（x 向空白带直方图，支持 1/2/3 栏，整宽块视作分栏屏障）；
    4. 块类型启发式标注（title/heading/abstract/body/caption/equation/
       reference/header/footer）与跨页续接标记（不合并文本，只记关系）。

输出 blocks.jsonl，每块带 page/column/order/kind/bbox/text，全部可指回原文坐标。
退出码 0=成功；2=部分（如某页无法判栏，按单栏降级并记 uncertainty）；3=输入不可用。
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

CAPTION_RE = re.compile(r"^(figure|fig\.?|table|表\s*\d|图\s*\d|scheme|algorithm)\b",
                        re.I)
HEADING_RE = re.compile(
    r"^((\d+(\.\d+)*\.?)|[IVX]+\.|[A-Z]\.)\s+\S")
REF_HEAD_RE = re.compile(r"^(references|bibliography|参考文献)\s*$", re.I)
REF_ITEM_RE = re.compile(r"^(\[\d+\]|\d+\.\s|\(\d{4}\))")
EQUATION_HINT_RE = re.compile(r"[=∑∫√≤≥±×÷∂∇∞∈≈≠]|\(\d+(\.\d+)?\)\s*$")
SENTENCE_END = tuple("。！？.!?;:：")


def load_words(path):
    words = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        header = f.readline()
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 6:
                continue
            pno, x0, y0, x1, y1 = int(parts[0]), *map(float, parts[1:5])
            words[pno].append({"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                               "text": parts[5]})
    return words


def cluster_lines(page_words):
    """词→行：先按 y 重叠聚成"行带"，行带内再按 x 间隙（>1.8×行高，即栏缝）
    断成独立行——这一步直接消除同高度双栏行被拼接的串栏错误。"""
    ws = sorted(page_words, key=lambda w: (w["y0"], w["x0"]))
    bands = []
    for w in ws:
        h = max(w["y1"] - w["y0"], 1e-6)
        placed = False
        for bd in bands[-4:]:
            overlap = min(w["y1"], bd["y1"]) - max(w["y0"], bd["y0"])
            if overlap > 0.5 * min(h, bd["y1"] - bd["y0"]):
                bd["words"].append(w)
                bd["y0"] = min(bd["y0"], w["y0"])
                bd["y1"] = max(bd["y1"], w["y1"])
                placed = True
                break
        if not placed:
            bands.append({"y0": w["y0"], "y1": w["y1"], "words": [w]})
    lines = []
    for bd in bands:
        wss = sorted(bd["words"], key=lambda w: w["x0"])
        h = sum(w["y1"] - w["y0"] for w in wss) / len(wss)
        cur = [wss[0]]
        for w in wss[1:]:
            if w["x0"] - cur[-1]["x1"] > 1.8 * h:
                lines.append(cur)
                cur = [w]
            else:
                cur.append(w)
        lines.append(cur)
    out = []
    for ws2 in lines:
        out.append({
            "x0": ws2[0]["x0"], "x1": max(w["x1"] for w in ws2),
            "y0": min(w["y0"] for w in ws2), "y1": max(w["y1"] for w in ws2),
            "text": " ".join(w["text"] for w in sorted(ws2, key=lambda w: w["x0"])),
            "height": sum(w["y1"] - w["y0"] for w in ws2) / len(ws2),
        })
    return sorted(out, key=lambda l: (l["y0"], l["x0"]))


def detect_columns(lines, page_w):
    """两遍法找栏缝：先剔除宽度 > 55% 版心的通栏行（标题/摘要/通栏题注），
    再在剩余行的 x 覆盖度剖面上取覆盖度最低的连续区（≥10pt）作为栏缝。
    两侧各 ≥3 行才确认双栏。返回栏边界 [0, (cut,) page_w]。"""
    if not lines:
        return [0.0, page_w]
    min_x = min(l["x0"] for l in lines)
    max_x = max(l["x1"] for l in lines)
    span = max_x - min_x
    if span < 0.4 * page_w:
        return [0.0, page_w]
    narrow = [l for l in lines if l["x1"] - l["x0"] <= 0.55 * span]
    if len(narrow) < 6:
        return [0.0, page_w]
    step = 2.0
    xs = []
    x = min_x + 0.12 * span
    end = max_x - 0.12 * span
    while x < end:
        xs.append(x)
        x += step
    if not xs:
        return [0.0, page_w]
    cov = [sum(1 for l in narrow if l["x0"] < px < l["x1"]) for px in xs]
    lo = min(cov)
    if lo > 1:
        return [0.0, page_w]  # 没有真正干净的栏缝
    i = cov.index(lo)
    a = i
    while a > 0 and cov[a - 1] <= lo + 1:
        a -= 1
    b = i
    while b < len(cov) - 1 and cov[b + 1] <= lo + 1:
        b += 1
    if xs[b] - xs[a] + step < 10.0:
        return [0.0, page_w]
    mid = (xs[a] + xs[b] + step) / 2
    left_n = sum(1 for l in narrow if l["x1"] <= mid)
    right_n = sum(1 for l in narrow if l["x0"] >= mid)
    if left_n < 3 or right_n < 3:
        return [0.0, page_w]
    return [0.0, mid, page_w]


def segment_blocks(lines, bounds):
    """行→块：栏内按纵间距切分；跨越全部栏缝（两侧各 ≥15pt）的整宽行
    自成一块并充当阅读顺序屏障。"""
    cuts = bounds[1:-1]
    full_w, col_local = [], []
    for l in lines:
        crosses = sum(1 for c in cuts
                      if l["x0"] < c - 15 and l["x1"] > c + 15)
        if cuts and crosses == len(cuts):
            full_w.append(l)
        else:
            col_local.append(l)
    heights = sorted(l["height"] for l in lines)
    med_h = heights[len(heights) // 2] if heights else 10.0
    gap_thresh = 1.35 * med_h
    blocks = []
    cur = None
    for l in sorted(full_w, key=lambda l: l["y0"]):
        if cur is None or l["y0"] - cur["lines"][-1]["y1"] > gap_thresh:
            cur = {"span": "full", "column": 0, "lines": [l]}
            blocks.append(cur)
        else:
            cur["lines"].append(l)
    # 栏内行按 (column, y) 排序后切分
    def col_of(l):
        cx = (l["x0"] + l["x1"]) / 2
        return max(i for i in range(len(bounds) - 1)
                   if cx >= bounds[i]) + 1
    col_local.sort(key=lambda l: (col_of(l), l["y0"]))
    cur = None
    for l in col_local:
        c = col_of(l)
        heading_like = (HEADING_RE.match(l["text"].strip())
                        and l["height"] > 1.1 * med_h)
        if heading_like:
            blocks.append({"span": "col", "column": c, "lines": [l]})
            cur = None
        elif (cur is None or c != cur["column"]
                or l["y0"] - cur["lines"][-1]["y1"] > gap_thresh):
            cur = {"span": "col", "column": c, "lines": [l]}
            blocks.append(cur)
        else:
            cur["lines"].append(l)
    return blocks


def norm_repeat(text):
    return re.sub(r"\d+", "#", re.sub(r"\s+", "", text)).lower()


def classify_blocks(all_pages_blocks, page_meta):
    counts = Counter()
    for pno, blocks in all_pages_blocks.items():
        ph = page_meta.get(pno, {}).get("height", 800.0)
        for b in blocks:
            y0 = b["lines"][0]["y0"]
            y1 = b["lines"][-1]["y1"]
            edge = y0 < 0.09 * ph or y1 > 0.93 * ph
            if edge:
                counts[norm_repeat(" ".join(l["text"] for l in b["lines"]))] += 1
    n_pages = max(len(all_pages_blocks), 1)
    repeat_set = {t for t, c in counts.items() if c >= max(2, 0.4 * n_pages)}

    classified = []
    for pno in sorted(all_pages_blocks):
        ph = page_meta.get(pno, {}).get("height", 800.0)
        heights = [l["height"] for b in all_pages_blocks[pno] for l in b["lines"]]
        med_h = sorted(heights)[len(heights) // 2] if heights else 10.0
        for b in all_pages_blocks[pno]:
            text = "\n".join(l["text"] for l in b["lines"])
            y0 = b["lines"][0]["y0"]
            y1 = b["lines"][-1]["y1"]
            bh = b["lines"][0]["height"]
            edge = y0 < 0.09 * ph or y1 > 0.93 * ph
            kind = "body"
            if edge and norm_repeat(text) in repeat_set:
                kind = "header" if y0 < 0.09 * ph else "footer"
            elif CAPTION_RE.match(text.strip()):
                kind = "caption"
            elif HEADING_RE.match(text.strip()) and len(b["lines"]) <= 2 \
                    and bh > 1.02 * med_h:
                kind = "heading"
            elif b["span"] == "full" and pno == 1 and y0 < 0.3 * ph \
                    and bh > 1.3 * med_h:
                kind = "title"
            elif len(b["lines"]) <= 3 and EQUATION_HINT_RE.search(text) \
                    and len(text) < 200:
                kind = "equation"
            classified.append({
                "page": pno, "column": b["column"], "span": b["span"],
                "kind": kind,
                "bbox": [round(min(l["x0"] for l in b["lines"]), 2),
                         round(min(l["y0"] for l in b["lines"]), 2),
                         round(max(l["x1"] for l in b["lines"]), 2),
                         round(max(l["y1"] for l in b["lines"]), 2)],
                "text": text,
                "n_lines": len(b["lines"]),
            })
    return classified


def reading_order(blocks_by_page, page_meta):
    """整宽块作屏障分带；带内先左栏后右栏；跨栏/跨页 body 续接标记。
    续接只从"阅读顺序中紧邻的前一个正文块"发出：同页时必须是相邻下一栏、
    跨页时必须是下一页，且源块为栏内块、末行非句读——避免标题→作者这类
    顶部相邻被误判为续段。"""
    ordered, seq = [], 0
    prev_body = None
    for pno in sorted(blocks_by_page):
        blocks = blocks_by_page[pno]
        bands, cur = [], []
        for b in sorted(blocks, key=lambda b: b["bbox"][1]):
            if b["span"] == "full":
                if cur:
                    bands.append(cur)
                    cur = []
                bands.append([b])
            else:
                cur.append(b)
        if cur:
            bands.append(cur)
        for band in bands:
            if len(band) == 1 and band[0]["span"] == "full":
                group = band
            else:
                group = sorted(band, key=lambda b: (b["column"], b["bbox"][1]))
            for b in group:
                seq += 1
                b["order"] = seq
                b["block_id"] = f"p{b['page']}.c{b['column']}.b{seq}"
                if (prev_body is not None and b["kind"] == "body"
                        and prev_body["span"] == "col"
                        and not prev_body["text"].rstrip().endswith(SENTENCE_END)
                        and not HEADING_RE.match(b["text"])
                        and ((b["page"] == prev_body["page"]
                              and b["column"] == prev_body["column"] + 1)
                             or b["page"] == prev_body["page"] + 1)):
                    b["continues_from"] = prev_body["block_id"]
                if b["kind"] == "body":
                    prev_body = b
                ordered.append(b)
    return ordered


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--words", required=True, help="extract_words.py 产出的 words.tsv")
    ap.add_argument("--meta", help="pages_meta.json（缺省时从词坐标估计页尺寸）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    if not os.path.exists(args.words):
        print(json.dumps({"status": "failed", "reason": "words_tsv_missing"}))
        return 3
    words = load_words(args.words)
    if not words:
        print(json.dumps({"status": "failed", "reason": "words_tsv_empty"}))
        return 3

    page_meta = {}
    if args.meta and os.path.exists(args.meta):
        for m in json.load(open(args.meta, encoding="utf-8")):
            page_meta[m["page"]] = m
    for pno, ws in words.items():
        if pno not in page_meta:
            page_meta[pno] = {
                "width": max(w["x1"] for w in ws) * 1.12,
                "height": max(w["y1"] for w in ws) * 1.12,
                "estimated": True}

    blocks_by_page, degraded = {}, []
    for pno in sorted(words):
        lines = cluster_lines(words[pno])
        bounds = detect_columns(lines, page_meta[pno]["width"])
        if len(bounds) == 2 and len(lines) > 20:
            degraded.append(pno)  # 行数多却只判出单栏，可能是复杂版面
        blocks_by_page[pno] = segment_blocks(lines, bounds)
    classified = classify_blocks(blocks_by_page, page_meta)
    by_page = defaultdict(list)
    for b in classified:
        by_page[b["page"]].append(b)
    ordered = reading_order(by_page, page_meta)

    # 参考文献区后处理：按阅读顺序找到首个 References 标题块，
    # 其后的块（论文末段）标记为 reference——必须按顺序做，避免
    # 双栏页面中右栏正文被先到的左栏 References 误吞。
    seen_ref = False
    for b in ordered:
        first_line = b["text"].strip().splitlines()[0]
        if not seen_ref and REF_HEAD_RE.match(first_line):
            seen_ref = True
            b["kind"] = "reference"
        elif seen_ref and b["kind"] not in ("header", "footer"):
            b["kind"] = "reference"

    out_path = os.path.join(args.out, "blocks.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for b in ordered:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")
    kinds = Counter(b["kind"] for b in ordered)
    report = {"status": "ok" if not degraded else "partial",
              "blocks": len(ordered), "kinds": dict(kinds),
              "blocks_jsonl": out_path}
    if degraded:
        report["uncertainty"] = [
            f"第 {p} 页按单栏降级处理，复杂版面可能串栏" for p in degraded]
    print(json.dumps(report, ensure_ascii=False))
    return 0 if not degraded else 2


if __name__ == "__main__":
    sys.exit(main())
