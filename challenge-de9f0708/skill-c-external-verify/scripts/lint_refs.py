#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lint_refs.py — 参考文献本地初筛（不联网）。

检查项（输出均为"候选问题"，候选 ≠ 结论，最终判定须经 crossref_check 与人工/模型复核）：
  1. duplicate_reference      标题归一化相似度 ≥ 0.85 的疑似重复条目
  2. missing_field            缺作者/标题/年份等关键字段；正文 [n] 指向不存在条目
  3. year_anomaly             年份晚于当前年
  4. doi_format_invalid       DOI 形态非法（如 10.xxxx 缺后缀）
  5. format_inconsistency     体例混用（编号体例混用 / 编号与作者-年份引文混用）
  6. claim_citation_mismatch  正文 [n] 语境句与文献主题零重叠（同语种启发式，低置信）

误报抑制纪律：
  * 无 DOI 不判违规：人文期刊、会议、书籍常无 DOI，仅记入 info_notes；
  * 跨语种（中文语境 vs 英文文献）不做主题重叠判定，标记 skipped_cross_language。

用法：
  python3 lint_refs.py --input refs.json --output lint.json
"""
import argparse
import datetime
import difflib
import json
import re
import sys

VALID_DOI = re.compile(r'^10\.\d{4,9}/\S+$', re.IGNORECASE)
AUTHOR_YEAR_CITE = re.compile(r'[\(（][A-Z][A-Za-z\-]+(\s+et\s+al\.?)?\s*[,，]\s*(?:19|20)\d{2}[\)）]')
CJK = re.compile(r'[\u4e00-\u9fff]')
STOPWORDS = {
    'the', 'of', 'and', 'in', 'a', 'an', 'for', 'from', 'with', 'by', 'to', 'on', 'at',
    'is', 'are', 'was', 'were', 'be', 'been', 'using', 'use', 'used', 'based', 'study',
    'studies', 'review', 'analysis', 'results', 'method', 'methods', 'between', 'effect',
    'effects', 'via', 'as', 'we', 'our', 'their', 'its', 'this', 'that', 'these', 'those',
    'an', 'or', 'its', 'into', 'over', 'under', 'than', 'then', 'they', 'them',
}


def norm_text(t):
    return re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', (t or '').lower())


def title_sim(a, b):
    na, nb = norm_text(a), norm_text(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def content_tokens(text):
    """英文实词（len>=4，去停用词）+ 中文滑动二元组。"""
    text = text or ''
    words = {w for w in re.findall(r'[a-zA-Z]{4,}', text.lower()) if w not in STOPWORDS}
    bigrams = set()
    for run in CJK.findall(text) and re.findall(r'[\u4e00-\u9fff]+', text):
        for i in range(len(run) - 1):
            bigrams.add(run[i:i + 2])
    return words, bigrams


def make_candidate(cid, ctype, sev, category, ref_index, rule, evidence, location, suggestion,
                   confidence="medium"):
    return {
        "id": cid,
        "type": ctype,
        "severity_candidate": sev,
        "category": category,
        "ref_index": ref_index,
        "rule": rule,
        "evidence": evidence,
        "location_hint": location,
        "suggestion": suggestion,
        "verdict_status": "待复核",
        "confidence": confidence,
        "note": "本地初筛候选，非结论；须结合 crossref_check 检索记录与人工/模型复核后定级。",
    }


def main():
    ap = argparse.ArgumentParser(
        description="参考文献本地初筛：重复/缺字段/年份异常/DOI 形态/体例混用/引文-主题错位候选。"
                    " 缺键不崩，exit 0。")
    ap.add_argument("--input", required=True, help="extract_refs.py 生成的 refs.json")
    ap.add_argument("--output", required=True, help="输出 lint.json")
    args = ap.parse_args()

    notes, info_notes, candidates = [], [], []
    try:
        data = json.load(open(args.input, encoding="utf-8"))
    except (OSError, ValueError) as e:
        data = {}
        notes.append("cannot read/parse input: %s" % e)

    refs = data.get("refs") or []
    citations = data.get("citations") or []
    if not isinstance(refs, list):
        refs, notes = [], notes + ["refs is not a list; treated as empty"]
    if not refs:
        notes.append("no references to lint")
    current_year = datetime.date.today().year
    n_cand = 0

    # --- 1. 重复条目：标题归一化相似度 ---
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            ta = (refs[i].get("fields") or {}).get("title")
            tb = (refs[j].get("fields") or {}).get("title")
            if not ta or not tb:
                continue
            sim = title_sim(ta, tb)
            if sim >= 0.85:
                n_cand += 1
                candidates.append(make_candidate(
                    "LINT-DUP-%03d" % n_cand, "duplicate_reference", "major", "norm_issue",
                    [refs[i].get("index"), refs[j].get("index")],
                    "title_similarity>=0.85",
                    {"similarity": round(sim, 3), "title_a": ta, "title_b": tb},
                    {"pages": [refs[i].get("page"), refs[j].get("page")]},
                    "核对两条文献是否为同一工作的重复著录；如是，删除其一并统一编号。",
                    confidence="medium"))

    # --- 2/3/4. 逐条字段检查 ---
    for r in refs:
        f = r.get("fields") or {}
        idx = r.get("index")
        missing = [k for k in ("authors", "title", "year") if not f.get(k)]
        if missing:
            n_cand += 1
            candidates.append(make_candidate(
                "LINT-MISS-%03d" % n_cand, "missing_field", "minor", "norm_issue", [idx],
                "required_field_empty",
                {"missing_fields": missing, "raw_excerpt": (r.get("raw") or "")[:200]},
                {"page": r.get("page"), "offset": r.get("offset")},
                "补全缺失字段；若为抽取失败，请对照原文手工著录。",
                confidence="high" if len(missing) >= 2 else "medium"))
        if not f.get("doi"):
            info_notes.append(
                "ref[%s] 无 DOI：人文/会议/书籍文献常见，按规程不判违规，仅记录。" % idx)
        elif not VALID_DOI.match(f["doi"]):
            n_cand += 1
            candidates.append(make_candidate(
                "LINT-DOI-%03d" % n_cand, "doi_format_invalid", "major", "norm_issue", [idx],
                "doi_shape!=10.\\d{4,9}/<suffix>",
                {"doi_found": f["doi"], "raw_excerpt": (r.get("raw") or "")[:200]},
                {"page": r.get("page"), "offset": r.get("offset")},
                "DOI 形态非法（缺后缀或注册号位数不足）；请核对原文 DOI 并改正。",
                confidence="high"))
        y = f.get("year")
        if isinstance(y, int) and y > current_year:
            n_cand += 1
            candidates.append(make_candidate(
                "LINT-YEAR-%03d" % n_cand, "year_anomaly", "major", "fact_error", [idx],
                "year>current_year(%d)" % current_year,
                {"year_found": y, "raw_excerpt": (r.get("raw") or "")[:200]},
                {"page": r.get("page"), "offset": r.get("offset")},
                "年份晚于当前年，疑似笔误或著录错误；请对照原文/出版记录改正。",
                confidence="high"))

    # --- 5. 体例混用 ---
    styles = {r.get("marker_style") for r in refs if r.get("marker_style")}
    if len(styles) > 1:
        n_cand += 1
        candidates.append(make_candidate(
            "LINT-FMT-%03d" % n_cand, "format_inconsistency", "minor", "norm_issue",
            [r.get("index") for r in refs], "mixed_entry_marker_styles",
            {"styles_found": sorted(styles)}, None,
            "文献表编号体例不统一（[n] 与 n. 混用）；请统一为目标期刊体例。", confidence="high"))
    ay_hits = [c for c in citations if AUTHOR_YEAR_CITE.search(c.get("context") or "")]
    if ay_hits and citations:
        n_cand += 1
        candidates.append(make_candidate(
            "LINT-FMT-%03d" % n_cand, "format_inconsistency", "minor", "norm_issue", [],
            "numeric_markers_mixed_with_author_year",
            {"author_year_contexts": [c.get("context") for c in ay_hits[:3]]}, None,
            "正文同时出现 [n] 与（作者， 年份）两种引文体例；请统一。", confidence="medium"))

    # --- 6. 引文 [n] 指向不存在条目 / 语境-主题错位（同语种启发式） ---
    ref_by_idx = {r.get("index"): r for r in refs}
    for c in citations:
        for n in c.get("numbers") or []:
            if n not in ref_by_idx:
                n_cand += 1
                candidates.append(make_candidate(
                    "LINT-DANG-%03d" % n_cand, "missing_field", "major", "norm_issue", [n],
                    "citation_points_to_nonexistent_entry",
                    {"marker": c.get("marker"), "context": c.get("context")},
                    {"page": c.get("page"), "offset": c.get("offset")},
                    "正文引用了文献表中不存在的条目 [%s]；请补条目或删引文。" % n,
                    confidence="high"))
    for c in citations:
        nums = c.get("numbers") or []
        if len(nums) != 1 or nums[0] not in ref_by_idx:
            continue
        r = ref_by_idx[nums[0]]
        title = ((r.get("fields") or {}).get("title")) or ""
        ctx = c.get("context") or ""
        cw, cb = content_tokens(ctx)
        tw, tb = content_tokens(title)
        ctx_is_cjk, title_is_cjk = bool(cb), bool(tb)
        if ctx_is_cjk != title_is_cjk:
            info_notes.append(
                "citation %s：语境与文献标题语种不同，跳过主题重叠判定（需模型/人工判读）。"
                % c.get("marker"))
            continue
        if len(tw) + len(tb) < 3 or len(cw) + len(cb) < 5:
            continue
        if not (cw & tw) and not (cb & tb):
            n_cand += 1
            candidates.append(make_candidate(
                "LINT-CITE-%03d" % n_cand, "claim_citation_mismatch", "major",
                "insufficient_evidence", [nums[0]],
                "zero_content_overlap(context_vs_title)",
                {"marker": c.get("marker"), "context": ctx,
                 "ref_title": title, "ref_raw": (r.get("raw") or "")[:200]},
                {"page": c.get("page"), "offset": c.get("offset")},
                "引文 %s 的语境句与文献 [%s] 主题零重叠，疑似张冠李戴；"
                "请人工通读语境与文献，确认是否错引。" % (c.get("marker"), nums[0]),
                confidence="low"))

    summary = {}
    for c in candidates:
        summary[c["type"]] = summary.get(c["type"], 0) + 1

    out = {
        "tool": "lint_refs.py",
        "version": "1.0",
        "input_file": args.input,
        "current_year": current_year,
        "checks_run": ["duplicate_reference", "missing_field", "year_anomaly",
                       "doi_format_invalid", "format_inconsistency",
                       "claim_citation_mismatch"],
        "candidate_count": len(candidates),
        "candidates": candidates,
        "info_notes": info_notes,
        "summary_by_type": summary,
        "notes": notes,
        "caveat": "全部输出为候选问题（candidate），不是结论；无 DOI 不判违规。",
    }
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print("cannot write output: %s" % e, file=sys.stderr)
    print("lint_refs: %d candidates (%s) -> %s" % (len(candidates), summary, args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
