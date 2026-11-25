#!/usr/bin/env python3
"""source_audit.py — 阶段一：上游语料真实性与溯源审计。

递归扫描候选根（--roots 可追加；默认 /input、/app/work、cwd 中存在的），
识别并解析 .json/.jsonl/.csv/.tsv/.edgelist/.bib，判定格式
（crossref/europepmc/openalex/edge-list/node-table/generic-nodes/unknown），
为每个文件登记来源注册表（相对路径、sha1、字节数、判定格式、记录数、失败原因），
把规范化记录写入 <workdir>/records_norm.jsonl（每条带 locator {file, pointer}），
并输出 <workdir>/source_registry.json 与人读 <workdir>/audit_report.md。

解析失败的文件被登记而不是中断。仅标准库，默认离线，脚本位置无关。
"""
import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

CORPUS_EXTS = {".json", ".jsonl", ".csv", ".tsv", ".edgelist", ".bib"}

DOI_PREFIX_RE = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", re.I)
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.I)
PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
WS_RE = re.compile(r"\s+")


def norm_doi(value):
    """DOI 规范化：小写、去 doi.org 前缀、去首尾空白与尾部标点。"""
    if not value:
        return None
    d = str(value).strip()
    d = DOI_PREFIX_RE.sub("", d).strip().lower()
    d = d.rstrip(".,;)")
    return d or None


def norm_title(value):
    """标题规范化：小写、去标点、坍缩空白。"""
    if not value:
        return None
    t = PUNCT_RE.sub(" ", str(value).lower())
    t = WS_RE.sub(" ", t).strip()
    return t or None


def sha1_of(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def ref_ptr(doi=None, label=None, raw_id=None, pointer=None):
    return {"doi": norm_doi(doi), "label": label or None,
            "raw_id": raw_id or None, "pointer": pointer}


def work_record(title, authors, year, doi, venue, references, citations,
                alt_ids, fmt, rel_file, pointer):
    return {
        "kind": "work",
        "title": title or None,
        "authors": authors or [],
        "year": year,
        "doi": norm_doi(doi),
        "doi_raw": doi or None,
        "venue": venue or None,
        "references": references or [],
        "citations": citations or [],
        "alt_ids": alt_ids or [],
        "source_format": fmt,
        "locator": {"file": rel_file, "pointer": pointer},
    }


def edge_record(source, target, rel_file, pointer):
    return {"kind": "edge", "source": source, "target": target,
            "locator": {"file": rel_file, "pointer": pointer}}


def _year_from(value):
    if value is None:
        return None
    if isinstance(value, int):
        return value
    m = re.search(r"(19|20)\d{2}", str(value))
    return int(m.group(0)) if m else None


# ---------------------------------------------------------------- JSON 判定

def classify_json_obj(obj):
    """判定单个 JSON 值的语料格式。"""
    if isinstance(obj, dict):
        m = obj.get("message")
        if isinstance(m, dict) and (isinstance(m.get("items"), list)
                                    or "DOI" in m or "title" in m):
            return "crossref"
        rl = obj.get("resultList")
        if isinstance(rl, dict) and isinstance(rl.get("result"), list):
            return "europepmc"
        if isinstance(obj.get("results"), list):
            return "openalex"
        if "id" in obj and "referenced_works" in obj:
            return "openalex"
        for key in ("nodes", "papers", "records", "works", "data"):
            if isinstance(obj.get(key), list):
                return "generic-nodes"
        if "title" in obj or "doi" in obj or "DOI" in obj:
            return "generic-single"
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return "generic-nodes"
    return "unknown"


# ---------------------------------------------------------------- 各格式解析

def parse_crossref_item(item, rel_file, pointer):
    title = None
    t = item.get("title")
    if isinstance(t, list) and t:
        title = t[0]
    elif isinstance(t, str):
        title = t
    authors = []
    for a in item.get("author") or []:
        if isinstance(a, dict):
            name = " ".join(x for x in (a.get("given"), a.get("family")) if x)
            authors.append(name or a.get("name") or "")
        else:
            authors.append(str(a))
    authors = [a for a in authors if a]
    year = None
    for key in ("issued", "published-print", "published-online", "created"):
        dp = (item.get(key) or {}).get("date-parts") if isinstance(item.get(key), dict) else None
        if dp and dp[0]:
            year = _year_from(dp[0][0])
            if year:
                break
    venue = None
    ct = item.get("container-title")
    if isinstance(ct, list) and ct:
        venue = ct[0]
    elif isinstance(ct, str):
        venue = ct
    refs = []
    for i, r in enumerate(item.get("reference") or []):
        if isinstance(r, dict):
            label = r.get("article-title") or r.get("unstructured") or r.get("key")
            refs.append(ref_ptr(doi=r.get("DOI"), label=label,
                                raw_id=r.get("key"),
                                pointer="%s/reference/%d" % (pointer, i)))
    cits = []
    for i, r in enumerate(item.get("cited-by") or item.get("cited_by") or []):
        if isinstance(r, dict):
            cits.append(ref_ptr(doi=r.get("DOI"), label=r.get("article-title"),
                                pointer="%s/cited-by/%d" % (pointer, i)))
    return work_record(title, authors, year, item.get("DOI"), venue, refs, cits,
                       [item.get("URL")] if item.get("URL") else [],
                       "crossref", rel_file, pointer)


def parse_crossref(obj, rel_file):
    msg = obj.get("message")
    if isinstance(msg.get("items"), list):
        return [parse_crossref_item(it, rel_file, "/message/items/%d" % i)
                for i, it in enumerate(msg["items"]) if isinstance(it, dict)]
    return [parse_crossref_item(msg, rel_file, "/message")]


def parse_europepmc_item(item, rel_file, pointer):
    authors = []
    astr = item.get("authorString")
    if isinstance(astr, str):
        authors = [a.strip() for a in astr.split(";") if a.strip()]
    elif isinstance(item.get("authorList"), dict):
        for a in item["authorList"].get("author") or []:
            if isinstance(a, dict):
                authors.append(a.get("fullName") or "")
    refs = []
    rl = item.get("referenceList")
    if isinstance(rl, dict):
        for i, r in enumerate(rl.get("reference") or []):
            if isinstance(r, dict):
                refs.append(ref_ptr(doi=r.get("doi"),
                                    label=r.get("title") or r.get("citation"),
                                    raw_id=r.get("id"),
                                    pointer="%s/referenceList/reference/%d" % (pointer, i)))
    cits = []
    cl = item.get("citedByList")
    if isinstance(cl, dict):
        for i, r in enumerate(cl.get("citedBy") or []):
            if isinstance(r, dict):
                cits.append(ref_ptr(doi=r.get("doi"),
                                    label=r.get("title") or r.get("citation"),
                                    raw_id=r.get("id"),
                                    pointer="%s/citedByList/citedBy/%d" % (pointer, i)))
    alt = [x for x in (item.get("id"), item.get("pmid"), item.get("pmcid")) if x]
    return work_record(item.get("title"), authors, _year_from(item.get("pubYear")),
                       item.get("doi"), item.get("journalTitle"), refs, cits, alt,
                       "europepmc", rel_file, pointer)


def parse_europepmc(obj, rel_file):
    out = []
    for i, it in enumerate(obj["resultList"]["result"]):
        if isinstance(it, dict):
            out.append(parse_europepmc_item(it, rel_file, "/resultList/result/%d" % i))
    return out


def parse_openalex_item(item, rel_file, pointer):
    title = item.get("title") or item.get("display_name")
    authors = []
    for a in item.get("authorships") or []:
        if isinstance(a, dict):
            nm = (a.get("author") or {}).get("display_name") if isinstance(a.get("author"), dict) else None
            if nm:
                authors.append(nm)
    venue = None
    pl = item.get("primary_location")
    if isinstance(pl, dict) and isinstance(pl.get("source"), dict):
        venue = pl["source"].get("display_name")
    if not venue and isinstance(item.get("host_venue"), dict):
        venue = item["host_venue"].get("display_name")
    refs = []
    for i, w in enumerate(item.get("referenced_works") or []):
        refs.append(ref_ptr(label=str(w), raw_id=str(w),
                            pointer="%s/referenced_works/%d" % (pointer, i)))
    doi = item.get("doi")
    alt = [x for x in (item.get("id"),) if x]
    ids = item.get("ids")
    if isinstance(ids, dict):
        alt += [str(v) for v in ids.values() if v]
    return work_record(title, authors, _year_from(item.get("publication_year")),
                       doi, venue, refs, [], alt, "openalex", rel_file, pointer)


def parse_openalex(obj, rel_file):
    if isinstance(obj.get("results"), list):
        return [parse_openalex_item(it, rel_file, "/results/%d" % i)
                for i, it in enumerate(obj["results"]) if isinstance(it, dict)]
    return [parse_openalex_item(obj, rel_file, "/")]


def parse_generic_node(item, rel_file, pointer):
    refs = []
    for i, r in enumerate(item.get("references") or []):
        if isinstance(r, dict):
            refs.append(ref_ptr(doi=r.get("doi") or r.get("DOI"),
                                label=r.get("title") or r.get("label"),
                                raw_id=r.get("id"),
                                pointer="%s/references/%d" % (pointer, i)))
        else:
            refs.append(ref_ptr(doi=r if DOI_RE.match(str(r)) else None,
                                label=str(r),
                                pointer="%s/references/%d" % (pointer, i)))
    cits = []
    for i, r in enumerate(item.get("citations") or []):
        if isinstance(r, dict):
            cits.append(ref_ptr(doi=r.get("doi") or r.get("DOI"),
                                label=r.get("title") or r.get("label"),
                                raw_id=r.get("id"),
                                pointer="%s/citations/%d" % (pointer, i)))
        else:
            cits.append(ref_ptr(doi=r if DOI_RE.match(str(r)) else None,
                                label=str(r),
                                pointer="%s/citations/%d" % (pointer, i)))
    authors = item.get("authors")
    if isinstance(authors, str):
        authors = [a.strip() for a in re.split(r"[;|]", authors) if a.strip()]
    if not isinstance(authors, list):
        authors = []
    alt = [str(item[k]) for k in ("id", "pmid", "arxiv") if item.get(k)]
    return work_record(item.get("title"), authors,
                       _year_from(item.get("year") or item.get("pubYear")),
                       item.get("doi") or item.get("DOI"),
                       item.get("venue") or item.get("journal"),
                       refs, cits, alt, "generic-nodes", rel_file, pointer)


def parse_generic_nodes(obj, rel_file):
    if isinstance(obj, list):
        items, base = obj, ""
    else:
        items, base = [], ""
        for key in ("nodes", "papers", "records", "works", "data"):
            if isinstance(obj.get(key), list):
                items, base = obj[key], "/" + key
                break
    return [parse_generic_node(it, rel_file, "%s/%d" % (base or "", i) or "/%d" % i)
            for i, it in enumerate(items) if isinstance(it, dict)]


def parse_json_obj(obj, rel_file):
    fmt = classify_json_obj(obj)
    if fmt == "crossref":
        return fmt, parse_crossref(obj, rel_file)
    if fmt == "europepmc":
        return fmt, parse_europepmc(obj, rel_file)
    if fmt == "openalex":
        return fmt, parse_openalex(obj, rel_file)
    if fmt == "generic-nodes":
        return fmt, parse_generic_nodes(obj, rel_file)
    if fmt == "generic-single":
        return fmt, [parse_generic_node(obj, rel_file, "/")]
    return "unknown", []


# ---------------------------------------------------------------- 文件级解析

def parse_json_file(path, rel_file):
    text = path.read_text(encoding="utf-8", errors="replace")
    obj = json.loads(text)
    return parse_json_obj(obj, rel_file)


def parse_jsonl_file(path, rel_file):
    records, fmts = [], []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue  # 坏行跳过；文件本身仍可部分利用
            fmt, recs = parse_json_obj(obj, rel_file)
            fmts.append(fmt)
            for r in recs:
                r["locator"]["pointer"] = "/line/%d%s" % (i + 1, r["locator"]["pointer"])
            records.extend(recs)
    fmt = max(set(fmts), key=fmts.count) if fmts else "unknown"
    return fmt, records


def parse_table_file(path, rel_file, delimiter):
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        rows = list(csv.reader(fh, delimiter=delimiter))
    if not rows:
        return "unknown", []
    header = [h.strip().lower() for h in rows[0]]
    cols = set(header)
    records = []
    if {"source", "target"} <= cols:
        si, ti = header.index("source"), header.index("target")
        for n, row in enumerate(rows[1:], start=2):
            if len(row) > max(si, ti) and row[si].strip() and row[ti].strip():
                records.append(edge_record(row[si].strip(), row[ti].strip(),
                                           rel_file, "/row/%d" % n))
        return "edge-list", records
    if cols & {"title", "doi"}:
        idx = {h: i for i, h in enumerate(header)}
        for n, row in enumerate(rows[1:], start=2):
            def cell(*names):
                for nm in names:
                    if nm in idx and idx[nm] < len(row):
                        v = row[idx[nm]].strip()
                        if v:
                            return v
                return None
            refs = []
            raw_refs = cell("references", "refs")
            if raw_refs:
                for j, r in enumerate(re.split(r"[;|]", raw_refs)):
                    r = r.strip()
                    if r:
                        refs.append(ref_ptr(doi=r if DOI_RE.match(r) else None,
                                            label=r,
                                            pointer="/row/%d/references/%d" % (n, j)))
            records.append(work_record(
                cell("title"),
                [a.strip() for a in re.split(r"[;|]", cell("authors", "author") or "") if a.strip()],
                _year_from(cell("year", "pubyear")),
                cell("doi"), cell("venue", "journal"), refs, [], [],
                "node-table", rel_file, "/row/%d" % n))
        return "node-table", records
    return "unknown", []


def parse_edgelist_file(path, rel_file):
    records = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = re.split(r"[\s,\t]+", line)
            if len(parts) >= 2:
                records.append(edge_record(parts[0], parts[1], rel_file, "/line/%d" % n))
    return "edge-list", records


BIB_ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,]+),(.*?)\n?\}\s*(?=@|\Z)", re.S)
BIB_FIELD_RE = re.compile(r"(\w+)\s*=\s*[\{\"](.+?)[\}\"]\s*,?\s*(?=\w+\s*=|\Z)", re.S)


def parse_bib_file(path, rel_file):
    text = path.read_text(encoding="utf-8", errors="replace")
    records = []
    for m in BIB_ENTRY_RE.finditer(text):
        key = m.group(2).strip()
        fields = {fm.group(1).lower(): WS_RE.sub(" ", fm.group(2)).strip()
                  for fm in BIB_FIELD_RE.finditer(m.group(3))}
        authors = [a.strip() for a in fields.get("author", "").split(" and ") if a.strip()]
        records.append(work_record(
            fields.get("title"), authors, _year_from(fields.get("year")),
            fields.get("doi"), fields.get("journal") or fields.get("booktitle"),
            [], [], ["bibkey:" + key], "bibtex", rel_file, "/entry/%s" % key))
    return ("bibtex", records) if records else ("unknown", [])


PARSERS = {
    ".json": parse_json_file,
    ".jsonl": parse_jsonl_file,
    ".csv": lambda p, r: parse_table_file(p, r, ","),
    ".tsv": lambda p, r: parse_table_file(p, r, "\t"),
    ".edgelist": parse_edgelist_file,
    ".bib": parse_bib_file,
}


# ---------------------------------------------------------------- 冲突台账

def detect_conflicts(records):
    """冲突线索：同 DOI 不同标题；同标题不同 DOI。"""
    conflicts = []
    by_doi, by_title = {}, {}
    for r in records:
        if r.get("kind") != "work":
            continue
        loc = r["locator"]
        if r.get("doi"):
            by_doi.setdefault(r["doi"], []).append(r)
        nt = norm_title(r.get("title"))
        if nt:
            by_title.setdefault(nt, []).append(r)
    for doi, rs in sorted(by_doi.items()):
        titles = {norm_title(r.get("title")) for r in rs if r.get("title")}
        if len(titles) > 1:
            conflicts.append({
                "type": "same-doi-different-title",
                "doi": doi,
                "titles": sorted({r["title"] for r in rs if r.get("title")}),
                "locators": [r["locator"] for r in rs],
            })
    for nt, rs in sorted(by_title.items()):
        dois = {r["doi"] for r in rs if r.get("doi")}
        if len(dois) > 1:
            conflicts.append({
                "type": "same-title-different-doi",
                "title": rs[0].get("title"),
                "dois": sorted(dois),
                "locators": [r["locator"] for r in rs],
            })
    return conflicts


# ---------------------------------------------------------------- 主流程

def discover_files(roots):
    seen, files = set(), []
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix.lower() in CORPUS_EXTS and p.name != "records_norm.jsonl":
                rp = p.resolve()
                if rp not in seen:
                    seen.add(rp)
                    files.append(p)
    return files


def run_audit(roots, workdir, out_registry=None, out_report=None, out_records=None):
    """执行审计，写出三类产物；返回 registry dict。可被 build_result 复用。"""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    out_records = Path(out_records) if out_records else workdir / "records_norm.jsonl"
    out_registry = Path(out_registry) if out_registry else workdir / "source_registry.json"
    out_report = Path(out_report) if out_report else workdir / "audit_report.md"

    existing_roots = [Path(r) for r in roots if Path(r).is_dir()]
    files = discover_files(existing_roots)
    registry_files = []
    all_records = []

    for f in files:
        rel = None
        for root in existing_roots:
            try:
                rel = str(f.relative_to(root))
                rel = str(root) + "::" + rel if len(existing_roots) > 1 else rel
                break
            except ValueError:
                continue
        rel = rel or str(f)
        entry = {"file": rel, "abs_path": str(f.resolve()),
                 "sha1": None, "bytes": None, "format": "unknown",
                 "records": 0, "status": "ok", "error": None}
        try:
            entry["sha1"] = sha1_of(f)
            entry["bytes"] = f.stat().st_size
            fmt, recs = PARSERS[f.suffix.lower()](f, rel)
            entry["format"] = fmt
            entry["records"] = len(recs)
            if fmt == "unknown":
                entry["status"] = "unparsed"
                entry["error"] = "格式无法判定或不支持"
            all_records.extend(recs)
        except Exception as exc:  # 解析失败：登记而非中断
            entry["status"] = "failed"
            entry["error"] = "%s: %s" % (type(exc).__name__, exc)
        registry_files.append(entry)

    conflicts = detect_conflicts(all_records)
    parsed_ok = sum(1 for e in registry_files if e["status"] == "ok")
    coverage = (parsed_ok / len(registry_files)) if registry_files else 0.0

    registry = {
        "roots_scanned": [str(r) for r in existing_roots],
        "roots_missing": [str(r) for r in roots if not Path(r).is_dir()],
        "files_total": len(registry_files),
        "files_parsed_ok": parsed_ok,
        "parse_coverage": round(coverage, 4),
        "records_total": len(all_records),
        "work_records": sum(1 for r in all_records if r.get("kind") == "work"),
        "edge_records": sum(1 for r in all_records if r.get("kind") == "edge"),
        "files": registry_files,
        "conflicts": conflicts,
    }

    with open(out_records, "w", encoding="utf-8") as fh:
        for r in all_records:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    out_registry.write_text(json.dumps(registry, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    out_report.write_text(render_report(registry), encoding="utf-8")
    return registry


def render_report(reg):
    lines = []
    lines.append("# 来源审计报告（source_audit）")
    lines.append("")
    lines.append("## 概览")
    lines.append("")
    lines.append("- 扫描根：%s" % ("、".join(reg["roots_scanned"]) or "（无）"))
    if reg["roots_missing"]:
        lines.append("- 不存在的根（已跳过）：%s" % "、".join(reg["roots_missing"]))
    lines.append("- 语料文件总数：%d；解析成功：%d；解析覆盖率：%.1f%%"
                 % (reg["files_total"], reg["files_parsed_ok"],
                    reg["parse_coverage"] * 100))
    lines.append("- 规范化记录总数：%d（文献记录 %d，边记录 %d）"
                 % (reg["records_total"], reg["work_records"], reg["edge_records"]))
    lines.append("")
    lines.append("## 格式分布")
    lines.append("")
    lines.append("| 判定格式 | 文件数 | 记录数 |")
    lines.append("|---|---|---|")
    dist = {}
    for e in reg["files"]:
        d = dist.setdefault(e["format"], [0, 0])
        d[0] += 1
        d[1] += e["records"]
    for fmt, (nf, nr) in sorted(dist.items()):
        lines.append("| %s | %d | %d |" % (fmt, nf, nr))
    lines.append("")
    lines.append("## 文件级来源注册表")
    lines.append("")
    lines.append("| 文件 | sha1(前12) | 字节 | 格式 | 记录数 | 状态 | 失败/异常原因 |")
    lines.append("|---|---|---|---|---|---|---|")
    for e in reg["files"]:
        lines.append("| %s | %s | %s | %s | %d | %s | %s |"
                     % (e["file"], (e["sha1"] or "")[:12], e["bytes"],
                        e["format"], e["records"], e["status"], e["error"] or ""))
    lines.append("")
    lines.append("## 冲突线索")
    lines.append("")
    if not reg["conflicts"]:
        lines.append("（未检出同 DOI 不同标题 / 同标题不同 DOI 冲突）")
    for c in reg["conflicts"]:
        if c["type"] == "same-doi-different-title":
            lines.append("- **同 DOI 不同标题**：`%s`" % c["doi"])
            for t in c["titles"]:
                lines.append("  - 标题：%s" % t)
        else:
            lines.append("- **同标题不同 DOI**：%s" % c["title"])
            for d in c["dois"]:
                lines.append("  - DOI：`%s`" % d)
        for loc in c["locators"]:
            lines.append("  - 定位：`%s` `%s`" % (loc["file"], loc["pointer"]))
    lines.append("")
    return "\n".join(lines)


def default_roots():
    roots = [r for r in ("/input", "/app/work") if Path(r).is_dir()]
    cwd = Path.cwd()
    if cwd.is_dir():
        roots.append(str(cwd))
    return roots


def main(argv=None):
    ap = argparse.ArgumentParser(description="上游语料真实性与溯源审计（阶段一）")
    ap.add_argument("--roots", action="append", default=None,
                    help="候选语料根，可多次追加；默认 /input、/app/work、cwd 中存在的")
    ap.add_argument("--workdir", default="/app/work", help="工作目录")
    args = ap.parse_args(argv)
    roots = args.roots if args.roots else default_roots()
    if not roots:
        print("[source_audit] 警告：没有任何存在的候选根", file=sys.stderr)
    reg = run_audit(roots, args.workdir)
    print(json.dumps({
        "files_total": reg["files_total"],
        "files_parsed_ok": reg["files_parsed_ok"],
        "parse_coverage": reg["parse_coverage"],
        "records_total": reg["records_total"],
        "conflicts": len(reg["conflicts"]),
        "workdir": str(Path(args.workdir).resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
