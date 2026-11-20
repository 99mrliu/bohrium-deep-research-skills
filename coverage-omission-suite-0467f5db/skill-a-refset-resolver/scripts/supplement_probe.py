#!/usr/bin/env python3
"""supplement_probe.py — 步骤⑨：定向补检（诊断探针与归因）。

对每条漏检（miss_list.csv / coverage.json 的 miss）在本地材料语料上运行四类
诊断探针，产出具体到查询要素的归因与证据摘录：

  1. vocabulary 探针：该漏检记录标题中的核心术语，是否以变体形式出现在
     本地语料（其他检索结果、响应文件）而未被查询词覆盖；
  2. field 探针：该记录的作者/期刊/年份字段是否在本地响应文件中存在、
     说明检索字段（如仅题名检索）可能漏掉它；
  3. time_window 探针：该记录出版年是否落在查询声明的时间窗之外；
  4. source 探针：该记录所属期刊是否在本地响应中出现、检索是否限定了来源。

探针只给诊断证据，不声称"补检已消除遗漏"——是否消除须以补充检索的
结果重新运行 coverage_check.py 为准（增量对比）。

退出码：0 正常；2 漏检清单缺失（诚实降级）；3 参考集缺失。仅标准库。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

SCRIPT_NAME = "supplement_probe.py"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from refset_build import norm_doi, norm_pmid, norm_title_key  # noqa: E402


def load_corpus(workdir, materials_index):
    """收集本地语料片段：响应文件中记录的标题/期刊/年份，用于探针证据。"""
    corpus = []  # 每项：{file, ptr, title, journal, year, authors}
    for m in materials_index.get("materials", []):
        fpath = m.get("abs_path") or os.path.join(
            materials_index.get("materials_dir", ""), m["path"])
        if not os.path.isfile(fpath) or not fpath.lower().endswith(".json"):
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        items = []
        if isinstance(data, dict):
            msg = data.get("message", {})
            if isinstance(msg, dict) and isinstance(msg.get("items"), list):
                items = msg["items"]
            elif isinstance(data.get("resultList"), dict):
                items = data["resultList"].get("result", [])
            elif isinstance(data.get("results"), list):
                items = data["results"]
        elif isinstance(data, list):
            items = data
        for j, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            title = it.get("title") or it.get("titleString") or ""
            if isinstance(title, list):
                title = title[0] if title else ""
            journal = it.get("container-title") or \
                ((it.get("journalInfo", {}) or {}).get("journal", {}) or {}).get("title", "") or ""
            if isinstance(journal, list):
                journal = journal[0] if journal else ""
            authors = it.get("author") or it.get("authorString") or ""
            if isinstance(authors, list):
                authors = "; ".join(a.get("family", "") if isinstance(a, dict)
                                    else str(a) for a in authors)
            year = str(it.get("pubYear") or it.get("year") or "")
            if isinstance(it.get("issued"), dict):
                parts = it["issued"].get("date-parts", [[""]])
                if parts and parts[0]:
                    year = str(parts[0][0])
            corpus.append({"file": m["path"], "ptr": f"[{j}]",
                           "title": str(title), "journal": str(journal),
                           "year": year[:4], "authors": str(authors)[:200]})
    return corpus


def snippet(text, needle, width=80):
    idx = text.lower().find(needle.lower())
    if idx < 0:
        return ""
    start = max(0, idx - width // 2)
    return text[start: idx + len(needle) + width // 2].replace("\n", " ").strip()


def probe_miss(miss, corpus, task_time_window=None):
    findings = []

    # ---- vocabulary 探针 ----
    tk = norm_title_key(miss.get("title", ""))
    rare_terms = sorted(set(tk), key=len, reverse=True)[:5]
    variant_hits = []
    for term in rare_terms[:3]:
        for c in corpus:
            if term and term in norm_title_key(c["title"]):
                variant_hits.append({
                    "term": term,
                    "evidence_file": c["file"], "evidence_ptr": c["ptr"],
                    "evidence_quote": snippet(c["title"], term, 120)})
                break
    if variant_hits:
        findings.append({
            "probe": "vocabulary",
            "attribution": "漏检记录的核心术语在本地语料中存在（可能存在词形变体），"
                           "原查询词表可能未覆盖该词形。",
            "evidence": variant_hits[:3]})

    # ---- field 探针 ----
    field_ev = []
    tk_set = set(tk)
    for c in corpus:
        sim = len(tk_set & set(norm_title_key(c["title"]))) / max(1, len(tk_set | set(norm_title_key(c["title"]))))
        if sim >= 0.5 and c["title"].strip().lower() != miss.get("title", "").strip().lower():
            field_ev.append({
                "similarity": round(sim, 3),
                "evidence_file": c["file"], "evidence_ptr": c["ptr"],
                "evidence_quote": snippet(c["title"], list(tk_set & set(norm_title_key(c["title"])))[0] if tk_set & set(norm_title_key(c["title"])) else c["title"][:20], 120)})
            break
    if field_ev:
        findings.append({
            "probe": "field",
            "attribution": "本地响应中存在与该记录高度近似的条目，说明该文献在库中可及；"
                           "漏检更可能源于检索字段限制（如仅检索题名/摘要而非全字段）。",
            "evidence": field_ev})

    # ---- time_window 探针 ----
    if task_time_window and miss.get("year"):
        try:
            y = int(miss["year"])
            lo, hi = task_time_window
            inside = lo <= y <= hi
            findings.append({
                "probe": "time_window",
                "attribution": (f"该记录出版年 {y} 处于查询声明时间窗 [{lo}, {hi}] "
                                + ("之内，时间窗非归因要素。" if inside else
                                   "之外，时间窗可能是漏检归因要素。")),
                "evidence": [{"publication_year": y, "window": [lo, hi],
                              "inside_window": inside}]})
        except (ValueError, TypeError):
            pass

    # ---- source 探针 ----
    if miss.get("journal"):
        src_hits = [c for c in corpus
                    if c["journal"] and c["journal"].strip().lower()
                    == miss["journal"].strip().lower()][:2]
        if src_hits:
            findings.append({
                "probe": "source",
                "attribution": "该记录所属期刊在本地响应中有其他条目出现，说明来源可被覆盖；"
                               "漏检可能源于来源限定或该条目的收录差异。",
                "evidence": [{"evidence_file": c["file"], "evidence_ptr": c["ptr"],
                              "evidence_quote": f"{c['journal']} | {c['title'][:100]}"}
                             for c in src_hits]})
    if not findings:
        findings.append({
            "probe": "none_conclusive",
            "attribution": "本地语料中未找到可支持的归因证据；请勿臆断，"
                           "建议人工结合检索式复核。",
            "evidence": []})
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="对每条漏检运行诊断探针并输出归因。")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--outdir", default="/app/output")
    ap.add_argument("--time-window", default=None,
                    help="查询声明的时间窗，形如 2018-2024；缺省跳过该探针")
    args = ap.parse_args(argv)

    miss_path = os.path.join(args.outdir, "miss_list.csv")
    cov_path = os.path.join(args.outdir, "coverage.json")
    idx_path = os.path.join(args.workdir, "materials_index.json")
    if not os.path.isfile(cov_path):
        print(f"[{SCRIPT_NAME}] 缺少 coverage.json，请先运行 coverage_check.py",
              file=sys.stderr)
        return 3
    with open(cov_path, "r", encoding="utf-8") as fh:
        coverage = json.load(fh)
    case_id = coverage.get("case_id", "unknown_case")

    misses = []
    if os.path.isfile(miss_path):
        with open(miss_path, "r", encoding="utf-8-sig", newline="") as fh:
            misses = list(csv.DictReader(fh))
    else:
        misses = [r for r in coverage.get("records", []) if r["status"] == "miss"]
        if not misses:
            print(f"[{SCRIPT_NAME}] 无漏检记录，补检探针跳过。", file=sys.stderr)

    materials_index = {}
    if os.path.isfile(idx_path):
        with open(idx_path, "r", encoding="utf-8") as fh:
            materials_index = json.load(fh)
    corpus = load_corpus(args.workdir, materials_index)

    tw = None
    if args.time_window:
        m = re.fullmatch(r"(\d{4})-(\d{4})", args.time_window.strip())
        if m:
            tw = (int(m.group(1)), int(m.group(2)))

    reports = []
    for miss in misses:
        findings = probe_miss(miss, corpus, tw)
        reports.append({
            "ref_id": miss.get("ref_id", ""),
            "title": miss.get("title", "")[:160],
            "probe_findings": findings,
        })

    # 增量对比说明：本脚本不声称消除遗漏；补充检索后须重跑 coverage_check.py
    payload = {
        "case_id": case_id,
        "generated_by": SCRIPT_NAME,
        "miss_count": len(reports),
        "corpus_size": len(corpus),
        "time_window": list(tw) if tw else None,
        "reports": reports,
        "note": ("探针仅提供诊断证据，不代表遗漏已被消除；遗漏是否减少须以补充检索"
                 "结果重新运行 coverage_check.py 并与基线 coverage.json 对比为准。"),
        "status": "complete" if reports else "partial",
    }
    out_path = os.path.join(args.outdir, "miss_attribution.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    # 同步 CSV 便于人工编辑
    csv_path = os.path.join(args.outdir, "miss_attribution.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ref_id", "title", "probe", "attribution", "evidence_pointer"])
        for r in reports:
            for f in r["probe_findings"]:
                ev = f["evidence"][0] if f["evidence"] else {}
                ptr = (ev.get("evidence_file", "") + ev.get("evidence_ptr", "")) or \
                      str(ev)[:120]
                w.writerow([r["ref_id"], r["title"][:120], f["probe"],
                            f["attribution"][:200], ptr[:200]])

    print(f"[{SCRIPT_NAME}] miss={len(reports)} corpus={len(corpus)} "
          f"out={out_path}")
    return 0 if reports else 2


if __name__ == "__main__":
    sys.exit(main())
