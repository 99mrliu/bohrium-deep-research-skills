#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""quote_audit.py — 引文保真机检（本 Skill 的核心保真门）

对 result.json（或任何含证据 quote 的 JSON）中每条 evidence quote 做机检：

1. 归一化（详见 references/normalization-spec.md）：
   NFKC → 弯引号→直引号 → 跨行连字符拼接（"exam-\\nple"→"example"）→ 空白折叠。
2. 子串匹配：归一化后的 quote 是否为某一页归一化文本的子串。
3. 子串失败时：用 difflib.SequenceMatcher 做页内最佳模糊匹配并报告 ratio：
     ratio >= 0.95          → verbatim_ok（标注 normalized）
     0.80 <= ratio < 0.95   → near_match（警告，需人工核对）
     ratio < 0.80           → not_found（ERROR，必须修复/降级/剔除）
4. 页码一致性：quote 实际命中页 vs 标注 page；不符报 page_drift（ERROR）。

输入约定
--------
--result：任意 JSON；递归查找所有含 "quote" 字段的对象作为证据条目，
          沿路径继承最近的 claim_id；page/printed_page 取自条目自身字段。
--pages ：extract_pages.py 产出的 pages.jsonl（首行可为 _meta 元信息行）。

输出
----
fidelity-report.json + stdout 人类可读摘要。

退出码
------
0  全部通过（verbatim_ok，可含 near_match 警告）
1  存在 not_found 或 page_drift（或输入文件缺失/损坏）
2  命令行用法错误（argparse）
"""

import argparse
import difflib
import json
import os
import re
import sys
import unicodedata

VERBATIM_THRESHOLD = 0.95
NEAR_THRESHOLD = 0.80

# 弯引号/弯撇号 → 直引号
QUOTE_MAP = {
    "“": '"', "”": '"', "„": '"', "‟": '"', "〝": '"', "〞": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "«": '"', "»": '"', "‹": "'", "›": "'",
}


def normalize_text(s):
    """保真机检统一归一化。规范见 references/normalization-spec.md。"""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", s)
    for k, v in QUOTE_MAP.items():
        s = s.replace(k, v)
    # 跨行连字符拼接："exam-\nple" → "example"（仅拉丁字母场景）
    s = re.sub(r"([A-Za-z])[-\u2010\u2011]\s*\r?\n\s*([a-z])", r"\1\2", s)
    # CJK 相邻空白直接删除（中文排版换行不产生词间空格）
    cjk = r"\u2e80-\u9fff\uf900-\ufaff\u3000-\u303f"
    s = re.sub(r"(?<=[" + cjk + r"])\s+|\s+(?=[" + cjk + r"])", "", s)
    # 其余空白折叠（换行/制表/不间断空格 → 单空格）
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def load_pages(path):
    pages = {}
    printed = {}
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            rec = json.loads(ln)
            if "_meta" in rec or "text" not in rec or "page" not in rec:
                continue
            p = int(rec["page"])
            pages[p] = rec["text"]
            if rec.get("printed_page") is not None:
                printed[p] = rec["printed_page"]
    return pages, printed


def iter_evidence(obj, claim_id=None, path="$"):
    """递归产出 (claim_id, evidence_dict, json_path)。"""
    if isinstance(obj, dict):
        cid = obj.get("claim_id", claim_id)
        if isinstance(obj.get("quote"), str) and obj["quote"].strip():
            yield cid, obj, path
        for k, v in obj.items():
            if k == "quote":
                continue
            yield from iter_evidence(v, cid, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_evidence(v, claim_id, f"{path}[{i}]")


def best_window_ratio(needle, haystack):
    """在 haystack 内找与 needle 最相似的窗口，返回 (ratio, window)。"""
    m, n = len(needle), len(haystack)
    if m == 0 or n == 0:
        return 0.0, ""
    if n <= m + 40:
        r = difflib.SequenceMatcher(None, needle, haystack, autojunk=False).ratio()
        return r, haystack
    sm = difflib.SequenceMatcher(None, needle, haystack, autojunk=False)
    starts = set()
    for blk in sm.get_matching_blocks():
        for off in (blk.b, blk.b + blk.size):
            for delta in (-8, -4, 0, 4, 8):
                start = max(0, min(n - m, off - m // 2 + delta))
                starts.add(start)
    best_r, best_w = 0.0, ""
    for start in sorted(starts):
        # 尝试多种窗口长度，避免长窗口内无关文本稀释相似度
        for extra in (0, 12, 24, 40):
            window = haystack[start:start + m + extra]
            r = difflib.SequenceMatcher(None, needle, window, autojunk=False).ratio()
            if r > best_r:
                best_r, best_w = r, window
    return best_r, best_w


def audit_one(idx, claim_id, ev, path, pages_norm, printed):
    quote_raw = ev["quote"]
    quote_norm = normalize_text(quote_raw)
    ann_page = ev.get("page")
    ann_printed = ev.get("printed_page")

    entry = {
        "index": idx,
        "claim_id": claim_id,
        "json_path": path,
        "quote_preview": quote_raw[:80],
        "annotated_page": ann_page,
        "annotated_printed_page": ann_printed,
        "normalized": normalize_text(quote_raw) != quote_raw.strip(),
        "found_pages": [],
        "verdict": None,
        "ratio": None,
        "issues": [],
    }

    # 1) 子串匹配
    for p, ptext in pages_norm.items():
        if quote_norm and quote_norm in ptext:
            entry["found_pages"].append(p)

    if entry["found_pages"]:
        entry["verdict"] = "verbatim_ok"
        entry["ratio"] = 1.0
    else:
        # 2) 页内模糊匹配
        best = (0.0, "", None)
        for p, ptext in pages_norm.items():
            r, w = best_window_ratio(quote_norm, ptext)
            if r > best[0]:
                best = (r, w, p)
        entry["ratio"] = round(best[0], 4)
        entry["best_match_page"] = best[2]
        entry["best_match_preview"] = best[1][:120]
        if best[0] >= VERBATIM_THRESHOLD:
            entry["verdict"] = "verbatim_ok"
            if best[2] is not None:
                entry["found_pages"] = [best[2]]
        elif best[0] >= NEAR_THRESHOLD:
            entry["verdict"] = "near_match"
            entry["issues"].append("near_match: 需人工核对差异（可能为断词/标点漂移）")
            if best[2] is not None:
                entry["found_pages"] = [best[2]]
        else:
            entry["verdict"] = "not_found"
            entry["issues"].append(
                "not_found: quote 在全文任何页均无 ≥0.80 的匹配，疑似编造或严重改写")

    # 3) 页码一致性
    if entry["found_pages"]:
        if ann_page is None and ann_printed is None:
            entry["issues"].append("page_missing: 未标注 page，定位链不完整（请补页码）")
        else:
            ok = False
            if ann_page is not None:
                try:
                    ok = int(ann_page) in entry["found_pages"]
                except (TypeError, ValueError):
                    entry["issues"].append(f"page_invalid: 标注页码无法解析：{ann_page!r}")
            if not ok and ann_printed is not None:
                try:
                    ok = any(printed.get(p) == int(ann_printed)
                             for p in entry["found_pages"])
                except (TypeError, ValueError):
                    pass
            if not ok and "page_invalid" not in " ".join(entry["issues"]):
                found_printed = [printed.get(p) for p in entry["found_pages"]]
                entry["issues"].append(
                    f"page_drift: 标注页={ann_page}/{ann_printed}，实际命中页="
                    f"{entry['found_pages']}（印刷页 {found_printed}）")

    return entry


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="引文保真机检：核验 evidence quote 是否真实存在于原文并定位正确",
        epilog="退出码：0 全部通过；1 存在 not_found/page_drift 或输入损坏；2 用法错误。",
    )
    ap.add_argument("--result", "-r", required=True,
                    help="result.json 或任意含 evidence quote 的 JSON")
    ap.add_argument("--pages", "-p", required=True,
                    help="extract_pages.py 产出的 pages.jsonl")
    ap.add_argument("--output", "-o", default="fidelity-report.json",
                    help="报告输出路径（默认 ./fidelity-report.json）")
    args = ap.parse_args(argv)

    for pth in (args.result, args.pages):
        if not os.path.isfile(pth):
            print(f"错误：文件不存在：{pth}", file=sys.stderr)
            return 1
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            result = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"错误：无法解析 JSON {args.result}：{e}", file=sys.stderr)
        return 1
    try:
        pages, printed = load_pages(args.pages)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"错误：无法解析 pages.jsonl：{e}", file=sys.stderr)
        return 1
    if not pages:
        print("错误：pages.jsonl 中没有可用页面。", file=sys.stderr)
        return 1

    pages_norm = {p: normalize_text(t) for p, t in pages.items()}

    entries = []
    for i, (cid, ev, path) in enumerate(iter_evidence(result), start=1):
        entries.append(audit_one(i, cid, ev, path, pages_norm, printed))

    n_ok = sum(1 for e in entries if e["verdict"] == "verbatim_ok"
               and not any("page_drift" in i for i in e["issues"]))
    n_warn = sum(1 for e in entries if e["verdict"] == "near_match"
                 or any("page_missing" in i or "page_invalid" in i for i in e["issues"]))
    n_fail = sum(1 for e in entries if e["verdict"] == "not_found"
                 or any("page_drift" in i for i in e["issues"]))

    report = {
        "generator": "quote_audit.py",
        "input_result": os.path.abspath(args.result),
        "input_pages": os.path.abspath(args.pages),
        "thresholds": {"verbatim_ok": VERBATIM_THRESHOLD, "near_match": NEAR_THRESHOLD},
        "summary": {"total": len(entries), "pass": n_ok,
                    "warnings": n_warn, "failures": n_fail},
        "entries": entries,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[quote_audit] 证据条目={len(entries)} 通过={n_ok} "
          f"警告={n_warn} 失败={n_fail} → {args.output}")
    for e in entries:
        if e["verdict"] == "not_found" or any("page_drift" in i for i in e["issues"]):
            tag = "ERROR"
        elif e["verdict"] == "near_match" or e["issues"]:
            tag = "WARN"
        else:
            tag = "OK"
        line = (f"  [{tag}] #{e['index']} claim={e['claim_id']} "
                f"ratio={e['ratio']} 标注页={e['annotated_page']} "
                f"命中页={e['found_pages']} | {e['quote_preview']}")
        print(line)
        for iss in e["issues"]:
            print(f"       └─ {iss}")
    if n_fail:
        print("保真门未通过：存在 not_found / page_drift。处置见 "
              "references/fidelity-rules.md（修复 / 降级 / 剔除并留痕）。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
