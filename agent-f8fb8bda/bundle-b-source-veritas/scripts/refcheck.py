#!/usr/bin/env python3
"""refcheck.py — 文献身份一致性核验（reference identity gate）。

读取 --refs 指定的 references.json（Agent 从材料或检索整理的文献清单，
每条 {ref_id,title,authors,year,doi,venue,origin}，
origin ∈ {material, search}），执行规则 R1–R5：

  R1 DOI 语法：严格校验 10.\\d{4,9}/\\S+；不合法时尝试宽松提取并标注。
  R2 年份合理性：1900..当年+1；查年份冲突前先把 DOI 串从文本剔除，
     避免 DOI 内嵌数字被误报为年份。
  R3 origin=material 的文献必须在 corpus_index.json 中有对应文档
     （按标题归一化匹配），否则 material_phantom（材料幻影）。
  R4 同一文献（同 ref_id 或同归一化标题）多条目元数据冲突
     → metadata_conflict。
  R5 可选 --online：urllib 查 Crossref（api.crossref.org/works/<doi>），
     5 秒超时；无网/超时降级 not_checked，不影响其它检查；Crossref
     404 同样降级为 not_checked（可能是 DataCite/预印本 DOI）并留痕。

状态（每篇文献一个终态）：
  verified / metadata_conflict / material_phantom /
  suspected_fabricated（DOI malformed 且无任何匹配）/ not_checked

产物：refcheck_report.json（写入 --outdir，默认与 refs 同目录）。
退出码：0 无硬状态；1 存在硬状态（material_phantom /
suspected_fabricated / metadata_conflict，stdout 逐项失败清单）；
2 用法/IO 错误。仅标准库；--online 离线优雅降级。
"""
import argparse
import datetime
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request

DOI_STRICT_RE = re.compile(r"^10\.\d{4,9}/\S+$")
DOI_LENIENT_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>)\]}]+")
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
HARD_STATUS = ("material_phantom", "suspected_fabricated",
               "metadata_conflict")


def norm_title(t):
    if not t:
        return ""
    t = unicodedata.normalize("NFKC", str(t)).casefold()
    t = re.sub(r"[^0-9a-z一-鿿]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def titles_match(a, b):
    na, nb = norm_title(a), norm_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    short, long = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(short) >= 12 and short in long


def strip_dois(text):
    return DOI_LENIENT_RE.sub(" ", text or "")


def check_doi(doi):
    """R1：返回 (r1_status, cleaned_doi_or_None)。"""
    if not doi:
        return "absent", None
    d = str(doi).strip()
    for pre in ("https://doi.org/", "http://doi.org/", "doi:", "DOI:"):
        if d.lower().startswith(pre.lower()):
            d = d[len(pre):]
    d = d.rstrip(".,;:")
    if DOI_STRICT_RE.match(d):
        return "ok", d
    m = DOI_LENIENT_RE.search(d)
    if m:
        return "lenient_extracted", m.group(0).rstrip(".,;:")
    return "malformed", None


def crossref_lookup(doi, timeout=5):
    """R5：返回 (status, title_or_None)。status ∈ ok/not_found/unavailable。"""
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    req = urllib.request.Request(
        url, headers={"User-Agent": "dr-source-veritas/1.0 (refcheck)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        msg = data.get("message", {})
        tl = msg.get("title") or []
        return "ok", (tl[0] if tl else None)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "not_found", None
        return "unavailable", None
    except Exception:
        return "unavailable", None


def load_corpus_titles(corpus_dir):
    titles = []
    index_path = os.path.join(corpus_dir, "corpus_index.json")
    if not os.path.isfile(index_path):
        return None
    with open(index_path, encoding="utf-8") as f:
        index = json.load(f)
    ident = {}
    ipath = os.path.join(corpus_dir, "identity_candidates.json")
    if os.path.isfile(ipath):
        with open(ipath, encoding="utf-8") as f:
            ident = json.load(f)
    for d in index.get("docs", []):
        if d.get("parse_status") != "ok":
            continue
        cand = (ident.get(d["doc_id"]) or {}).get("title_candidate")
        titles.append((d["doc_id"], cand or d["source_file"]))
    return titles


def main():
    ap = argparse.ArgumentParser(description="文献身份一致性核验（reference identity gate）")
    ap.add_argument("--refs", default="/app/work/references.json",
                    help="文献清单 JSON（默认 /app/work/references.json）")
    ap.add_argument("--corpus", default="/app/work/corpus",
                    help="语料目录（默认 /app/work/corpus）")
    ap.add_argument("--online", action="store_true",
                    help="启用 Crossref 在线核验（R5）；无网自动降级 not_checked")
    ap.add_argument("--outdir", default=None,
                    help="产物目录（默认与 refs 同目录）")
    args = ap.parse_args()

    if not os.path.isfile(args.refs):
        print(f"[IO ERROR] references 文件不存在: {args.refs}")
        return 2
    try:
        with open(args.refs, encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[IO ERROR] references JSON 解析失败: {e}")
        return 2
    refs = payload.get("references") if isinstance(payload, dict) else payload
    if not isinstance(refs, list):
        print("[IO ERROR] references.json 结构非法："
              "应为列表或含 references 列表的对象")
        return 2

    corpus_titles = load_corpus_titles(args.corpus)
    if corpus_titles is None:
        print(f"[WARN] 语料索引缺失，R3 降级为 not_checked:"
              f" {os.path.join(args.corpus, 'corpus_index.json')}")
        corpus_titles = []

    this_year = datetime.date.today().year
    results = []
    failures = []

    # R4 预分组：同 ref_id 或同归一化标题
    groups = {}
    for r in refs:
        if not isinstance(r, dict):
            continue
        keys = {f"id:{r.get('ref_id')}"} if r.get("ref_id") else set()
        nt = norm_title(r.get("title"))
        if nt:
            keys.add(f"t:{nt}")
        for k in keys:
            groups.setdefault(k, []).append(r)
    conflict_ids = set()
    for k, members in groups.items():
        if len(members) < 2:
            continue
        sigs = set()
        for m in members:
            _, cd = check_doi(m.get("doi"))
            sigs.add((str(m.get("year") or ""), cd or "",
                      norm_title((m.get("authors") or "")).split(" ")[0]))
        if len(sigs) > 1:
            for m in members:
                conflict_ids.add(id(m))

    for r in refs:
        if not isinstance(r, dict):
            results.append({"ref": r, "status": "metadata_conflict",
                            "checks": {"R0": "条目不是对象"}})
            failures.append(f"<非对象条目>: metadata_conflict")
            continue
        rid = r.get("ref_id") or r.get("title") or "?"
        origin = str(r.get("origin", "search")).lower()
        checks = {}

        # R1 DOI 语法
        r1, clean_doi = check_doi(r.get("doi"))
        checks["R1_doi"] = r1 + (f" -> {clean_doi}"
                                 if r1 == "lenient_extracted" else "")

        # R2 年份合理性（先剔除 DOI 串再查年份冲突）
        r2_notes = []
        yr = r.get("year")
        try:
            yr_i = int(str(yr).strip()) if yr is not None else None
        except ValueError:
            yr_i = None
        if yr is not None and (yr_i is None
                               or not (1900 <= yr_i <= this_year + 1)):
            r2_notes.append(f"year={yr} 超出 1900..{this_year + 1}")
        blob = strip_dois(" ".join(str(r.get(k) or "")
                                   for k in ("title", "venue", "doi")))
        years_in_text = {int(y) for y in YEAR_RE.findall(blob)}
        if yr_i is not None:
            conflicts = {y for y in years_in_text if abs(y - yr_i) > 1}
            if conflicts:
                r2_notes.append(
                    f"文本内嵌年份 {sorted(conflicts)} 与 year={yr_i} 冲突")
        checks["R2_year"] = "ok" if not r2_notes else "warn: " + "; ".join(r2_notes)

        # R3 材料幻影：origin=material 必须在语料中
        corpus_hit = None
        for doc_id, cand in corpus_titles:
            if titles_match(r.get("title"), cand):
                corpus_hit = doc_id
                break
        if origin == "material":
            checks["R3_material"] = ("ok: 匹配语料文档 " + corpus_hit
                                     if corpus_hit else
                                     "FAIL: 语料中无对应文档 -> material_phantom")
        else:
            checks["R3_material"] = ("n/a (origin=search)"
                                     + (f"；语料内亦匹配 {corpus_hit}"
                                        if corpus_hit else ""))

        # R4 元数据冲突
        checks["R4_conflict"] = ("FAIL: 同文献多条目元数据冲突"
                                 if id(r) in conflict_ids else "ok")

        # R5 Crossref 在线核验（可选，优雅降级）
        r5_status = "skipped"
        crossref_hit = False
        if args.online and clean_doi:
            r5_status, cr_title = crossref_lookup(clean_doi)
            if r5_status == "ok":
                crossref_hit = True
                if cr_title and not titles_match(r.get("title"), cr_title):
                    r5_status = "ok_title_mismatch: " + str(cr_title)[:80]
        checks["R5_crossref"] = r5_status

        # 终态裁定（优先级：conflict > phantom > fabricated > not_checked > verified）
        if id(r) in conflict_ids:
            status = "metadata_conflict"
        elif origin == "material" and corpus_titles and not corpus_hit:
            status = "material_phantom"
        elif origin == "material" and not corpus_titles:
            status = "not_checked"
        elif r1 == "malformed" and not corpus_hit and not crossref_hit:
            status = "suspected_fabricated"
        elif r1 == "malformed":
            status = "verified"  # 有语料/Crossref 匹配，DOI 标注为异常
        elif args.online and clean_doi and checks["R5_crossref"] in (
                "unavailable", "not_found"):
            # Crossref 未收录不单独定罪（可能为 DataCite/预印本 DOI），
            # 降级为软状态 not_checked 并在 checks 中留痕。
            status = "not_checked"
        else:
            status = "verified"
        checks["status_reason"] = (
            "material_phantom: origin=material 但语料无此标题" if status == "material_phantom"
            else "suspected_fabricated: DOI malformed 且语料/Crossref 均无匹配" if status == "suspected_fabricated"
            else "metadata_conflict: 同文献多条目元数据冲突" if status == "metadata_conflict"
            else "not_checked: 本地检查通过，在线核验不可用或未覆盖" if status == "not_checked"
            else "verified: R1–R5 通过")

        results.append({"ref_id": rid, "title": r.get("title"),
                        "origin": origin, "status": status,
                        "checks": checks})
        if status in HARD_STATUS:
            failures.append(f"{rid}: {status} — {checks['status_reason']}")

    summary = {}
    for res in results:
        summary[res["status"]] = summary.get(res["status"], 0) + 1
    report = {"refs_file": os.path.abspath(args.refs),
              "corpus": os.path.abspath(args.corpus),
              "online": bool(args.online),
              "total": len(results), "summary": summary,
              "results": results}
    outdir = args.outdir or os.path.dirname(os.path.abspath(args.refs))
    os.makedirs(outdir, exist_ok=True)
    rpath = os.path.join(outdir, "refcheck_report.json")
    with open(rpath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[refcheck] 文献 {len(results)} 条，状态分布: {summary}")
    print(f"[refcheck] 产物: {rpath}")
    if failures:
        print("[refcheck] 硬状态清单（门控违例）:")
        for item in failures:
            print("  - " + item)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
