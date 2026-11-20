#!/usr/bin/env python3
"""scan_corpus.py — 自动发现语料、抽取专利号建索引、按查询号匹配（仅标准库）。

用法：
  python3 scan_corpus.py index  --roots /input /app/work --out /app/work/num_index.json
  python3 scan_corpus.py query  --index /app/work/num_index.json --numbers "US10293847B2" ...
  python3 scan_corpus.py query  --index ... --keywords "催化剂" "涂层"   # 主题降级模式
退出码：0 正常（含零命中，会在结果中标注）；2 语料为空或索引缺失。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patent_numbers

EXTS = (".json", ".jsonl", ".csv", ".tsv", ".txt", ".md", ".xml")
SKIP_DIR_HINTS = ("output",)  # 跳过自身产物目录，防止自匹配


def discover(roots):
    files = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".") and d not in SKIP_DIR_HINTS]
            for fn in filenames:
                if fn.lower().endswith(EXTS) and fn != "num_index.json":
                    files.append(os.path.join(dirpath, fn))
    return sorted(files)


def _walk_json(obj, path, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            _walk_json(v, path + "." + str(k), out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk_json(v, "%s[%d]" % (path, i), out)
    elif isinstance(obj, str):
        out.append((path, obj))


def iter_strings(filepath):
    """产出 (locator, text)。JSON 用 JSON 路径，其余用行号。"""
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError) as e:
        return [(" unreadable: %s" % e, "")]
    if filepath.lower().endswith(".json"):
        try:
            pairs = []
            _walk_json(json.loads(content), "$", pairs)
            if pairs:
                return pairs
        except json.JSONDecodeError:
            pass  # 退化为行模式
    if filepath.lower().endswith(".jsonl"):
        pairs = []
        for n, line in enumerate(content.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                _walk_json(json.loads(line), "$.line%d" % n, pairs)
            except json.JSONDecodeError:
                pairs.append(("line %d" % n, line))
        return pairs
    return [("line %d" % n, ln) for n, ln in enumerate(content.splitlines(), 1) if ln.strip()]


def build_index(roots):
    files = discover(roots)
    entries = []
    unreadable = []
    for fp in files:
        for loc, text in iter_strings(fp):
            if loc.startswith(" unreadable"):
                unreadable.append({"file": fp, "error": loc})
                continue
            for hit in patent_numbers.find_numbers(text):
                p = hit["parsed"]
                if not p.get("ok"):
                    continue
                e = {"file": fp, "locator": loc, "raw": hit["raw"],
                     "key": p["key"], "country": p["country"],
                     "ntype": p["ntype"], "serial": p["serial"],
                     "kind": p.get("kind"), "confidence": p.get("confidence"),
                     "warnings": p.get("warnings", [])}
                if hit.get("split_event"):
                    e["split_event"] = hit["split_event"]
                entries.append(e)
    return {"roots": roots, "files_scanned": len(files), "entries": entries,
            "unreadable": unreadable,
            "warnings": ([] if files else ["未发现任何语料文件"]) +
                        (["部分文件不可读，见 unreadable"] if unreadable else [])}


def query(index, numbers=None, keywords=None):
    entries = index.get("entries", [])
    hits, qmeta = [], []
    for q in numbers or []:
        qp = patent_numbers.normalize(q)
        qm = {"query": q, "parsed": qp}
        if not qp["ok"]:
            qm["error"] = "查询号未匹配已知模式，跳过匹配"
            qmeta.append(qm)
            continue
        exact, serial_only = [], []
        for e in entries:
            if e["key"] == qp["key"]:
                exact.append(e)
            elif (e["country"] == qp["country"] and e["serial"] == qp["serial"]
                  and e["ntype"] != qp["ntype"]):
                serial_only.append(e)
        qm["exact_hits"] = exact
        qm["related_hits"] = serial_only  # 同序号不同文献种类（公开/授权/申请）
        if serial_only:
            qm["note"] = ("related_hits 为同序号不同种类的号码（如公开号↔授权号↔申请号），"
                          "是否同一专利需以著录项为准，见 rules/number_formats.md")
        qmeta.append(qm)
        hits.extend(exact)
    kw_hits = []
    for kw in keywords or []:
        # 主题降级模式：字面大小写不敏感匹配，不做语义扩展，局限见 SKILL.md
        rx = re.compile(re.escape(kw), re.IGNORECASE)
        seen = set()
        for fp in index.get("_keyword_files", []):
            for loc, text in iter_strings(fp):
                if rx.search(text) and (fp, loc, kw) not in seen:
                    seen.add((fp, loc, kw))
                    kw_hits.append({"file": fp, "locator": loc, "keyword": kw,
                                    "excerpt": text[:200]})
    return {"number_queries": qmeta, "keyword_hits": kw_hits,
            "warnings": index.get("warnings", [])}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("index")
    pi.add_argument("--roots", nargs="+", required=True)
    pi.add_argument("--out", required=True)
    pq = sub.add_parser("query")
    pq.add_argument("--index", required=True)
    pq.add_argument("--numbers", nargs="*", default=[])
    pq.add_argument("--keywords", nargs="*", default=[])
    pq.add_argument("--out")
    args = ap.parse_args(argv[1:])

    if args.cmd == "index":
        idx = build_index(args.roots)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False, indent=2)
        print(json.dumps({"files_scanned": idx["files_scanned"],
                          "entries": len(idx["entries"]),
                          "warnings": idx["warnings"]}, ensure_ascii=False))
        return 0 if idx["files_scanned"] else 2
    with open(args.index, encoding="utf-8") as f:
        idx = json.load(f)
    if args.keywords:
        idx["_keyword_files"] = discover(idx.get("roots", []))
    res = query(idx, args.numbers, args.keywords)
    res.pop("_keyword_files", None)
    out = json.dumps(res, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
