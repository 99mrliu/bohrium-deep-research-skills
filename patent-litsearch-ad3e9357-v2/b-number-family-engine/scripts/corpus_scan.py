#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""corpus_scan.py — 语料号码索引与命中查询（确定性，stdlib only）。

子命令：
  index --roots DIR... --out index.json [--workdir DIR]
      递归扫描文本文件（.txt/.md/.csv/.tsv/.json/.html/.htm/.xml/.log），
      抽取所有匹配专利号码形态的 token，经 patent_numbers 确定性校验后，
      记录 文件+行号 定位符。对 .pdf：若 pdftotext 可用则
      `pdftotext -layout` 抽取到 workdir 后扫描；否则记入 unavailable
      并继续处理其余文件（不中断、不猜测 PDF 内容）。
  query --index index.json --numbers N... [--keywords K...] --out hits.json
      号码匹配为"种类容忍"：同国别+同数字但不同种类/种类代码的命中列入
      related_hits 并附"需核对书目字段"提示。关键词为字面包含匹配，
      仅作召回级退路（recall-only fallback），不表示相关性判断。

退出码：0 正常；2 用法/输入错误。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patent_numbers as pn

TEXT_EXTS = {".txt", ".md", ".csv", ".tsv", ".json",
             ".html", ".htm", ".xml", ".log"}

# 宽松候选 token：国别码开头 + 数字/分隔符主体 + 可选种类代码；
# 是否为合法号码完全由 patent_numbers.normalize_token 决定。
TOKEN_RE = re.compile(
    r"(?<![0-9A-Za-z])(?:US|WO|EP|CN|JP|KR|XX)\s?"
    r"[0-9][0-9,./\- ]{0,26}[0-9](?:\s?[A-Z]\d?)?")

INDEX_VERSION = 1


def _iter_files(roots):
    for root in roots:
        if os.path.isfile(root):
            yield root
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for fn in sorted(filenames):
                if fn.startswith("."):
                    continue
                yield os.path.join(dirpath, fn)


def _scan_text(text_path, origin_path, via, entries):
    """扫描一个文本文件，把合法号码 token 追加到 entries。返回跳过数。"""
    skipped = 0
    seen = set()
    with open(text_path, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            for m in TOKEN_RE.finditer(line):
                raw = m.group(0).strip()
                res = pn.normalize_token(raw)
                if not res["ok"]:
                    skipped += 1
                    continue
                key = (origin_path, lineno, res["normalized"])
                if key in seen:
                    continue
                seen.add(key)
                entries.append({
                    "file": origin_path, "line": lineno, "raw": raw,
                    "normalized": res["normalized"], "kind": res["kind"],
                    "country": res["country"], "number": res["number"],
                    "kind_code": res["kind_code"], "via": via,
                })
    return skipped


def build_index(roots, out_path, workdir=None):
    entries, files, unavailable = [], [], []
    skipped_candidates = 0
    workdir = workdir or (out_path + ".workdir")
    pdftotext = shutil.which("pdftotext")

    for path in _iter_files(roots):
        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            if pdftotext:
                os.makedirs(workdir, exist_ok=True)
                safe = re.sub(r"[^\w]+", "_", os.path.abspath(path))
                txt = os.path.join(workdir, safe + ".txt")
                try:
                    subprocess.run([pdftotext, "-layout", path, txt],
                                   check=True, capture_output=True)
                except (subprocess.CalledProcessError, OSError) as exc:
                    unavailable.append({"file": path,
                                        "reason": "pdftotext 执行失败：%s" % exc})
                    files.append({"path": path, "type": "pdf",
                                  "status": "unavailable"})
                    continue
                skipped_candidates += _scan_text(txt, path,
                                                 "pdftotext -layout", entries)
                files.append({"path": path, "type": "pdf", "status": "ok",
                              "extracted_text": txt})
            else:
                unavailable.append({
                    "file": path,
                    "reason": "pdftotext 不可用：PDF 未抽取，跳过该文件并继续"})
                files.append({"path": path, "type": "pdf",
                              "status": "unavailable"})
        elif ext in TEXT_EXTS:
            skipped_candidates += _scan_text(path, path, "direct", entries)
            files.append({"path": path, "type": "text", "status": "ok"})
        else:
            files.append({"path": path, "type": ext or "(none)",
                          "status": "skipped"})

    index = {
        "version": INDEX_VERSION, "roots": list(roots),
        "files": files, "entries": entries, "unavailable": unavailable,
        "skipped_candidates": skipped_candidates,
        "note": "号码命中为确定性模式匹配；关键词命中为字面包含召回，"
                "均不代表相关性或法律状态判断。",
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=2)
    return index


def run_query(index_path, numbers=None, keywords=None, out_path=None):
    with open(index_path, "r", encoding="utf-8") as fh:
        index = json.load(fh)
    entries = index.get("entries", [])
    result = {"index": index_path, "queries": [], "keyword_hits": {},
              "unavailable_files": index.get("unavailable", [])}

    for q in numbers or []:
        res = pn.normalize_token(q)
        if not res["ok"]:
            result["queries"].append({
                "input": q, "ok": False, "normalized": None,
                "hits": [], "related_hits": [],
                "warnings": res["warnings"]
                + ["查询号无法解析：不猜测，原样记入 uncertainty"]})
            continue
        key = (res["country"], res["number"])
        hits, related = [], []
        for e in entries:
            if (e["country"], e["number"]) != key:
                continue
            if e["kind"] == res["kind"] and e["kind_code"] == res["kind_code"]:
                hits.append(e)
            else:
                related.append(dict(
                    e, note="同国别同号码但种类/种类代码不同："
                            "需核对书目字段确认是否同一文献族成员"))
        result["queries"].append({
            "input": q, "ok": True, "normalized": res["normalized"],
            "hits": hits, "related_hits": related,
            "warnings": res["warnings"]})

    for kw in keywords or []:
        kw_hits = []
        for f in index.get("files", []):
            if f.get("status") != "ok":
                continue
            path = f.get("extracted_text") or f["path"]
            try:
                fh = open(path, "r", encoding="utf-8", errors="replace")
            except OSError:
                continue
            with fh:
                for lineno, line in enumerate(fh, 1):
                    if kw in line:
                        kw_hits.append({
                            "file": f["path"], "line": lineno,
                            "excerpt": line.strip()[:200],
                            "note": "字面包含匹配，仅用于召回（recall-only）"})
        result["keyword_hits"][kw] = kw_hits

    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(prog="corpus_scan.py",
                                 description="语料号码索引与查询")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("index", help="构建号码索引")
    p1.add_argument("--roots", nargs="+", required=True)
    p1.add_argument("--out", required=True)
    p1.add_argument("--workdir", default=None,
                    help="PDF 抽取文本的工作目录（默认 <out>.workdir）")

    p2 = sub.add_parser("query", help="按号码/关键词查询索引")
    p2.add_argument("--index", required=True)
    p2.add_argument("--numbers", nargs="*", default=[])
    p2.add_argument("--keywords", nargs="*", default=[])
    p2.add_argument("--out", required=True)

    args = ap.parse_args(argv)
    if args.cmd == "index":
        missing = [r for r in args.roots if not os.path.exists(r)]
        if missing:
            sys.stderr.write("输入路径不存在：%s\n" % ", ".join(missing))
            return 2
        index = build_index(args.roots, args.out, args.workdir)
        sys.stderr.write("索引完成：%d 文件，%d 号码条目，%d 不可用\n"
                         % (len(index["files"]), len(index["entries"]),
                            len(index["unavailable"])))
    else:
        if not os.path.exists(args.index):
            sys.stderr.write("索引文件不存在：%s\n" % args.index)
            return 2
        result = run_query(args.index, args.numbers, args.keywords, args.out)
        n_hits = sum(len(q["hits"]) for q in result["queries"])
        sys.stderr.write("查询完成：%d 号码，%d 精确命中\n"
                         % (len(result["queries"]), n_hits))
    return 0


if __name__ == "__main__":
    sys.exit(main())
