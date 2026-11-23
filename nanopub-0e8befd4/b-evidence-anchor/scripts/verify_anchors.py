#!/usr/bin/env python3
"""verify_anchors.py — 引文复定位与锚点计算（纯标准库）。

对每条断言的 evidence.quote 在 index_source.py 产出的索引中重新定位：
- 归一化匹配（NFKC + 空白折叠），保留到原文的字符映射；
- 唯一匹配 → verified，输出页/行/偏移锚点；
- 多匹配 → ambiguous（列出全部候选，禁止取第一个）；
- 零匹配 → 再试去连字符（-\n 修复）空间，命中则 verified 并写 change_record；
  仍零匹配 → not_found。
引文词数 >55 或跨行 >6 → W_BROAD_EVIDENCE 提示（不阻断）。
存在 not_found/ambiguous 时退出码 1（--allow-unverified 可放宽为 0）。
"""
import argparse
import json
import re
import sys
import unicodedata

VERSION = "1.0.0"
MAX_WORDS = 55
MAX_LINES = 6


def normalize_with_map(text):
    """NFKC + 空白折叠。返回 (norm_text, map[normal_idx] -> original_idx)。"""
    out = []
    mapping = []
    pending_ws = None
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            if pending_ws is None:
                pending_ws = i
            i += 1
            continue
        if pending_ws is not None and out:
            out.append(" ")
            mapping.append(pending_ws)
        pending_ws = None
        decomposed = unicodedata.normalize("NFKC", ch)
        for d in decomposed:
            out.append(d)
            mapping.append(i)
        i += 1
    return "".join(out), mapping


def dehyphenate(text):
    """去掉行尾连字符换行（inher-\nently → inherently）。返回 (variant, v→o 映射)。"""
    out = []
    mapping = []
    i = 0
    n = len(text)
    while i < n:
        if (text[i] == "-" and i + 1 < n and text[i + 1] == "\n"
                and i + 2 < n and text[i + 2].islower()):
            i += 2
            continue
        out.append(text[i])
        mapping.append(i)
        i += 1
    return "".join(out), mapping


class SearchSpace:
    def __init__(self, pages, page_hint=None):
        """pages: index['pages']。构建逐页 + 全局（跨页）两个搜索空间。"""
        self.segments = []  # (page, orig_start_offset_in_concat)
        concat_parts = []
        for p in pages:
            if page_hint is not None and p["page"] != page_hint:
                continue
            start = sum(len(x) for x in concat_parts)
            self.segments.append((p["page"], start, p))
            concat_parts.append(p["text"])
            concat_parts.append("\n")
        self.concat = "".join(concat_parts)
        self.norm, self.n2o = normalize_with_map(self.concat)
        variant, v2o = dehyphenate(self.concat)
        self.dnorm, dn2v = normalize_with_map(variant)
        self.dn2o = [v2o[x] for x in dn2v]

    def _find_all(self, haystack, needle):
        hits = []
        start = 0
        while True:
            k = haystack.find(needle, start)
            if k < 0:
                return hits
            hits.append(k)
            start = k + 1

    def _locate(self, o_start, o_end):
        """把原文偏移区间映射到页与行。"""
        seg = None
        for page, start, p in self.segments:
            if start <= o_start < start + len(p["text"]):
                seg = (page, start, p)
                break
        if seg is None:
            return None
        page, seg_start, p = seg
        lines = p["lines"]
        first = last = None
        for ln in lines:
            if ln["end"] > o_start - seg_start and first is None:
                first = ln["line"]
            if ln["start"] <= o_end - 1 - seg_start:
                last = ln["line"]
        return {"page": page, "line_start": first, "line_end": last,
                "char_start": o_start - seg_start, "char_end": o_end - seg_start}

    def search(self, quote):
        """返回 (status, matches, repair)。matches: 原文偏移区间列表。"""
        qnorm, _ = normalize_with_map(quote)
        if not qnorm:
            return "not_found", [], None
        hits = self._find_all(self.norm, qnorm)
        if hits:
            spans = [(self.n2o[k], self.n2o[min(k + len(qnorm) - 1, len(self.n2o) - 1)] + 1)
                     for k in hits]
            return ("verified" if len(spans) == 1 else "ambiguous"), spans, None
        dhits = self._find_all(self.dnorm, qnorm)
        if dhits:
            spans = [(self.dn2o[k],
                      self.dn2o[min(k + len(qnorm) - 1, len(self.dn2o) - 1)] + 1)
                     for k in dhits]
            return ("verified" if len(spans) == 1 else "ambiguous"), spans, "dehyphenation"
        return "not_found", [], None


def main():
    ap = argparse.ArgumentParser(description="引文锚点复定位")
    ap.add_argument("--source", required=True, help="index_source.py 产物")
    ap.add_argument("--claims", required=True, help="断言 JSONL（含 evidence.quote）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--allow-unverified", action="store_true",
                    help="存在 not_found/ambiguous 时仍以 0 退出（报告照旧）")
    args = ap.parse_args()

    with open(args.source, encoding="utf-8") as fh:
        index = json.load(fh)
    claims = []
    with open(args.claims, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                claims.append(json.loads(line))

    report = {"tool": "verify_anchors", "version": VERSION,
              "source_id": index["source"]["id"],
              "source_sha256": index["source"]["sha256"],
              "claims_total": len(claims), "results": [],
              "change_records": [], "summary": {}}
    counts = {"verified": 0, "ambiguous": 0, "not_found": 0}

    for c in claims:
        cid = str(c.get("id", "?"))
        ev = c.get("evidence", {}) or {}
        quote = ev.get("quote", "") or ""
        hint = ev.get("page_hint")
        space = SearchSpace(index["pages"], page_hint=hint)
        status, spans, repair = space.search(quote)
        anchors = []
        for s, e in spans:
            loc = space._locate(s, e)
            if loc:
                anchors.append(loc)
        words = len(re.findall(r"\S+", quote))
        lines_spanned = None
        if anchors:
            lines_spanned = max(a["line_end"] or 0 for a in anchors) - \
                min(a["line_start"] or 0 for a in anchors) + 1
        advisories = []
        if words > MAX_WORDS or (lines_spanned and lines_spanned > MAX_LINES):
            advisories.append({
                "code": "W_BROAD_EVIDENCE",
                "message": f"引文 {words} 词"
                           + (f"、跨 {lines_spanned} 行" if lines_spanned else "")
                           + "，超出最小充分性建议，先检查断言是否该再拆"})
        if hint:
            advisories.append({"code": "W_PAGE_HINT",
                               "message": f"使用 page_hint={hint} 限定搜索，"
                                          "仅在歧义消解后使用"})
        rec = {"id": cid, "status": status, "anchors": anchors,
               "quote_words": words, "advisories": advisories}
        if repair:
            rec["repair"] = repair
            report["change_records"].append(
                {"id": cid, "kind": "dehyphenation",
                 "detail": "去行尾连字符后定位成功；引文交付形态保持原文"})
        counts[status] += 1
        report["results"].append(rec)

    ok = counts["ambiguous"] == 0 and counts["not_found"] == 0
    report["summary"] = {**counts,
                         "gate": "pass" if ok else "fail"}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False))
    if ok or args.allow_unverified:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
