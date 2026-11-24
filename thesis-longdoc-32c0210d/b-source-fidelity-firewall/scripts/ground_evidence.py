#!/usr/bin/env python3
"""ground_evidence.py — 把 facts.json 逐条回源定位，产出 evidence_map.json。

定位策略（顺序）：
  1. 材料文本（--materials 目录，.txt/.md 直接读，.pdf 经 pdftotext 转换）：
     查找事实上下文句子的逐字（空白归一化后）包含匹配 → origin=materials。
  2. 回退到原始工作稿章节自身（W16 设定下原始工作稿即事实底稿）
     → origin=working_chapters。
  3. 两处都找不到 → origin=unresolved，verification=FAIL。

verification 由本脚本在写出前对 quote 重新做包含校验写回，不信任任何
人工声明。匹配时折叠空白以容忍 PDF/换行折行，但记录的 quote 为原文。

用法：
  python3 ground_evidence.py --facts facts.json --out evidence_map.json \
      [--materials <材料目录>] [--chapters <章节目录>] [--pdf-cache <目录>]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

RE_WS = re.compile(r"\s+")


def norm(text):
    return RE_WS.sub(" ", text).strip()


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def load_corpus(root, exts, warnings, label, pdf_cache):
    """返回 [(display_path, text, [lines])]，display_path 为相对 root 的路径。"""
    corpus = []
    if not root or not os.path.isdir(root):
        warnings.append("CORPUS_MISSING: %s 目录不存在或不可读：%s" % (label, root))
        return corpus
    for r, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(r, name)
            rel = os.path.relpath(path, root)
            low = name.lower()
            if low.endswith(tuple(exts)):
                text = read_text(path)
            elif low.endswith(".pdf"):
                text = convert_pdf(path, pdf_cache, warnings)
                if text is None:
                    continue
            else:
                continue
            corpus.append((rel, text, text.splitlines()))
    return corpus


def convert_pdf(path, cache_dir, warnings):
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        warnings.append(
            "PDF_UNREADABLE: 未找到 pdftotext，跳过 %s（应降级为 partial）" % path)
        return None
    os.makedirs(cache_dir, exist_ok=True)
    out = os.path.join(cache_dir, os.path.basename(path) + ".txt")
    try:
        subprocess.run([pdftotext, "-enc", "UTF-8", path, out],
                       check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        warnings.append("PDF_UNREADABLE: pdftotext 失败 %s: %s"
                        % (path, exc.stderr.decode("utf-8", "replace")[:200]))
        return None
    return read_text(out)


def find_quote(claim, corpus):
    """在语料中找 claim（空白归一化包含）。返回 (rel, quote, locator) 或 None。"""
    nclaim = norm(claim)
    if not nclaim:
        return None
    for rel, text, lines in corpus:
        if nclaim in norm(text):
            locator = rel
            for i, ln in enumerate(lines, start=1):
                if nclaim[:20] in norm(ln) or norm(ln) and norm(ln)[:20] in nclaim:
                    locator = "%s:%d" % (rel, i)
                    break
            return (rel, claim, locator)
    return None


def verify(quote, source_text):
    return norm(quote) in norm(source_text)


def main():
    ap = argparse.ArgumentParser(description="事实逐条回源定位 → evidence_map.json")
    ap.add_argument("--facts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--materials", default=None, help="材料目录（.txt/.md/.pdf）")
    ap.add_argument("--chapters", default=None,
                    help="原始工作稿章节目录（回退底稿；缺省用 facts 内 chapters_dir）")
    ap.add_argument("--pdf-cache", default=None, help="pdftotext 输出缓存目录")
    args = ap.parse_args()

    with open(args.facts, "r", encoding="utf-8") as fh:
        facts_doc = json.load(fh)

    warnings = []
    pdf_cache = args.pdf_cache or tempfile.mkdtemp(prefix="pdfcache_")
    materials = load_corpus(args.materials, [".txt", ".md"], warnings,
                            "materials", pdf_cache)
    chapters_root = args.chapters or facts_doc.get("chapters_dir")
    chapters = load_corpus(chapters_root, [".md", ".txt"], warnings,
                           "working_chapters", pdf_cache)

    source_texts = {}
    for rel, text, _ in materials:
        source_texts[("materials", rel)] = text
    for rel, text, _ in chapters:
        source_texts[("working_chapters", rel)] = text

    entries = []
    stats = {"total": 0, "grounded_materials": 0,
             "grounded_working_chapters": 0, "unresolved": 0}
    for fact in facts_doc.get("facts", []):
        stats["total"] += 1
        claim = fact.get("context") or fact.get("value", "")
        hit = find_quote(claim, materials)
        origin = "materials"
        if hit is None:
            hit = find_quote(claim, chapters)
            origin = "working_chapters"
        if hit is None:
            entries.append({
                "fact_id": fact.get("id"),
                "type": fact.get("type"),
                "claim": claim,
                "value": fact.get("value"),
                "evidence": [],
                "origin": "unresolved",
                "verification": "FAIL",
            })
            stats["unresolved"] += 1
            continue
        rel, quote, locator = hit
        ok = verify(quote, source_texts[(origin, rel)])
        entries.append({
            "fact_id": fact.get("id"),
            "type": fact.get("type"),
            "claim": claim,
            "value": fact.get("value"),
            "evidence": [{
                "source": "%s/%s" % (origin, rel),
                "quote": quote,
                "locator": locator,
                "verification": "PASS" if ok else "FAIL",
            }],
            "origin": origin,
            "verification": "PASS" if ok else "FAIL",
        })
        stats["grounded_materials" if origin == "materials"
              else "grounded_working_chapters"] += 1

    payload = {
        "schema": "evidence_map/v1",
        "facts_file": args.facts,
        "materials_dir": args.materials,
        "chapters_dir": chapters_root,
        "stats": stats,
        "warnings": warnings,
        "entries": entries,
    }
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("ground_evidence: %s -> %s" % (stats, args.out))
    for w in warnings:
        print("WARNING: %s" % w, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
