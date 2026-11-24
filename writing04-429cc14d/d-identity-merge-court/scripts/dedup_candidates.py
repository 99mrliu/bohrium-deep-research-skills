#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dedup_candidates.py — 去重候选挖掘（identity-merge-court / 方向 D：文献去重与身份归并）。

职责边界（重要）：本脚本只负责"可能是同一文献"的候选生成与证据分级，
绝不做合并裁决。裁决由 merge_adjudicate.py 依据 decisions.json 与 M1–M5 规则完成。

五类候选信号：
  S1 same_doi                    规范化 DOI 相同（大小写折叠、去 doi.org/doi: 前缀；可从 url 字段提取）→ strong
  S2 same_title                  规范化题名相同（NFKC + casefold + 去标点/空白 + 去停用冠词 the/a/an）；
                                 坐标（第一作者姓/年份/容器）一致数 ≥2 → moderate，否则 weak
  S3 translation_pair            中英题名对：仅通过材料内 translation_of 字段线索或共享标识符触发，
                                 绝不允许模型臆译判定；共享标识符 → strong，仅 translation_of → moderate
  S4 preprint_published          预印本↔正式版：规范化题名相同 + 一方为预印本（含 arXiv id）+
                                 容器/年份可不同；材料内 note 声明关系（含对方 DOI 或容器名）→ strong，否则 moderate
  S5 author_year_title_jaccard   同第一作者姓 + 同年 + 题名 token Jaccard ≥ 0.8；
                                 容器也一致 → moderate，否则 weak

输出 candidates.json：候选组（并查集连通分量）、逐信号证据、逐字段冲突表
（field -> {record_id: raw_value} + normalized_equal 标记）、组级证据分级 strong/moderate/weak。

确定性：同一输入必得同一输出（全部排序后输出）。仅标准库，无网络。

用法：
  python3 dedup_candidates.py --records records.jsonl --out OUTDIR [--bib library.bib]
  竞赛环境：python3 /skills/weekly-skill/scripts/dedup_candidates.py --records /app/work/records.jsonl --out /app/work/candidates
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

SCHEMA_VERSION = "1.0"
STOP_ARTICLES = {"the", "a", "an"}
GRADE_RANK = {"weak": 1, "moderate": 2, "strong": 3}
JACCARD_THRESHOLD = 0.8

# 参与逐字段冲突表比较的字段（first_author_family 为派生字段）
CONFLICT_FIELDS = [
    "title", "title_original", "year", "date", "type", "container",
    "volume", "issue", "pages", "article_number",
    "doi", "pmid", "arxiv", "url", "first_author_family",
]

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>}\])+,;]+")


# ---------------------------------------------------------------- 规范化原语

def norm_text(s):
    """NFKC + casefold + 去标点（Unicode 非字母数字全部折叠为空白）+ 空白折叠。"""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).casefold()
    s = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in s)
    return " ".join(s.split())


def title_tokens(s):
    """题名 token 集（去停用冠词 the/a/an），供规范化比较与 Jaccard。"""
    return [t for t in norm_text(s).split() if t not in STOP_ARTICLES]


def norm_title(s):
    return " ".join(title_tokens(s))


def norm_doi(d):
    """DOI 规范化：小写、去 doi.org / dx.doi.org / doi: 前缀、去首尾空白与句点。"""
    if not d:
        return ""
    d = str(d).strip().lower().rstrip(".")
    for p in ("https://doi.org/", "http://doi.org/",
              "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if d.startswith(p):
            d = d[len(p):]
    return d.strip()


def extract_doi(rec):
    """记录的身份 DOI：doi 字段优先；缺失时仅从 url 字段提取。

    绝不从 note 等自由文本字段提取身份 DOI（note 中引用的 DOI 可能是
    "正式版 DOI"等关系声明，不是本记录自身的标识符）。
    """
    d = norm_doi(rec.get("doi"))
    if d:
        return d
    url = str(rec.get("url") or "")
    m = DOI_RE.search(url.lower())
    if m:
        return norm_doi(m.group(0))
    return ""


def norm_year(v):
    if v is None or v == "":
        return ""
    try:
        return str(int(str(v).strip()[:4]))
    except ValueError:
        return norm_text(v)


def first_family(rec):
    authors = rec.get("authors") or []
    if not authors or not isinstance(authors, list):
        return ""
    fam = (authors[0] or {}).get("family", "")
    return norm_text(fam).replace(" ", "")


def is_preprint(rec):
    t = str(rec.get("type") or "").lower()
    if "preprint" in t:
        return True
    return bool(rec.get("arxiv")) and not str(rec.get("container") or "").strip()


# ---------------------------------------------------------------- 输入解析

def load_records_jsonl(path, warnings):
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                warnings.append(f"{path.name}:{lineno}: JSON 解析失败: {exc}")
                continue
            if not rec.get("record_id"):
                rec["record_id"] = f"AUTO-{lineno:04d}"
                warnings.append(f"{path.name}:{lineno}: 缺 record_id，自动指派 {rec['record_id']}")
            if not rec.get("title"):
                warnings.append(f"{rec['record_id']}: 缺 title 字段")
            if not rec.get("authors"):
                warnings.append(f"{rec['record_id']}: 缺 authors 字段")
            if rec.get("year") in (None, ""):
                warnings.append(f"{rec['record_id']}: 缺 year 字段")
            for w in rec.get("parse_warnings") or []:
                warnings.append(f"{rec['record_id']}: 上游解析警告: {w}")
            records.append(rec)
    return records


def _split_top_commas(body):
    """按顶层逗号切分 BibTeX 条目体（跟踪 {} 深度与引号）。"""
    parts, depth, in_q, cur = [], 0, False, []
    for ch in body:
        if ch == '"' and depth == 0:
            in_q = not in_q
        if not in_q:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(cur))
                cur = []
                continue
        cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return parts


def _strip_braces(v):
    v = v.strip()
    if len(v) >= 2 and ((v[0] == "{" and v[-1] == "}") or (v[0] == '"' and v[-1] == '"')):
        v = v[1:-1]
    v = v.replace("{", "").replace("}", "")
    return " ".join(v.split())


def parse_bib(path, warnings):
    """行级简易 BibTeX 解析：@type{key, field={...}}。保留 raw 原文。

    仅用于把 BibTeX 导出快速转成 records；复杂宏/嵌套请先在阶段 1 人工建档。
    """
    text = Path(path).read_text(encoding="utf-8")
    records = []
    i, n = 0, len(text)
    while True:
        at = text.find("@", i)
        if at < 0:
            break
        m = re.match(r"@(\w+)\s*\{", text[at:])
        if not m:
            i = at + 1
            continue
        rtype = m.group(1).lower()
        pos = at + m.end()
        depth, start = 1, pos
        while pos < n and depth:
            c = text[pos]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            pos += 1
        if depth:
            warnings.append(f"{Path(path).name}: @{rtype} 条目大括号不配对，截断于文件尾")
        body = text[start:pos - 1]
        raw = text[at:pos]
        parts = _split_top_commas(body)
        key = parts[0].strip() if parts else ""
        fields = {}
        for p in parts[1:]:
            fm = re.match(r"\s*(\w+)\s*=\s*(.*)\s*$", p, re.S)
            if fm:
                fields[fm.group(1).lower()] = _strip_braces(fm.group(2))
        rec = {"record_id": key or f"BIB-{len(records)+1:04d}", "cite_key": key,
               "source": "bibtex", "type": rtype, "raw": raw}
        if "title" in fields:
            rec["title"] = fields["title"]
        if "author" in fields:
            authors = []
            for name in fields["author"].split(" and "):
                name = name.strip()
                if "," in name:
                    fam, _, giv = name.partition(",")
                    authors.append({"family": fam.strip(), "given": giv.strip()})
                elif name:
                    toks = name.split()
                    authors.append({"family": toks[-1], "given": " ".join(toks[:-1])})
            rec["authors"] = authors
        if "year" in fields:
            try:
                rec["year"] = int(re.sub(r"\D", "", fields["year"])[:4])
            except (ValueError, IndexError):
                warnings.append(f"{rec['record_id']}: year 无法解析: {fields['year']!r}")
        for src, dst in (("journal", "container"), ("booktitle", "container"),
                         ("volume", "volume"), ("number", "issue"),
                         ("pages", "pages"), ("doi", "doi"), ("url", "url"),
                         ("note", "note"), ("pmid", "pmid")):
            if src in fields and dst not in rec:
                rec[dst] = fields[src]
        if fields.get("archiveprefix", "").lower() == "arxiv" and fields.get("eprint"):
            rec["arxiv"] = fields["eprint"]
        if not key:
            warnings.append(f"{rec['record_id']}: BibTeX 条目缺 cite key")
        records.append(rec)
        i = pos
    return records


# ---------------------------------------------------------------- 信号判定

def _note_corroborates(pre, pub):
    """预印本的 note 字段是否声明了与正式版的关系（含对方 DOI 或容器名）。"""
    note = str(pre.get("note") or "")
    if not note.strip():
        return False
    pub_doi = extract_doi(pub)
    if pub_doi:
        for m in DOI_RE.findall(note.lower()):
            if norm_doi(m) == pub_doi:
                return True
    c = norm_text(pub.get("container"))
    return bool(c) and c in norm_text(note)


def pair_signals(a, b):
    """计算一对记录之间的全部候选信号。"""
    sigs = []
    rid = (a["record_id"], b["record_id"])

    # S1 规范化 DOI 相同
    da, db = extract_doi(a), extract_doi(b)
    if da and da == db:
        sigs.append({"type": "same_doi", "grade": "strong", "members": list(rid),
                     "detail": f"规范化 DOI 相同: {da}"})

    ta, tb = norm_title(a.get("title")), norm_title(b.get("title"))
    fa, fb = first_family(a), first_family(b)
    ya, yb = norm_year(a.get("year")), norm_year(b.get("year"))
    ca, cb = norm_text(a.get("container")), norm_text(b.get("container"))
    corro = (int(bool(fa) and fa == fb)
             + int(bool(ya) and ya == yb)
             + int(bool(ca) and ca == cb))

    # S2 规范化题名相同
    if ta and ta == tb:
        grade = "moderate" if corro >= 2 else "weak"
        sigs.append({"type": "same_title", "grade": grade, "members": list(rid),
                     "detail": f"规范化题名相同（坐标一致数={corro}/3）"})
    else:
        # S5 同第一作者姓 + 同年 + 题名 token Jaccard >= 0.8
        toka, tokb = set(title_tokens(a.get("title"))), set(title_tokens(b.get("title")))
        if toka and tokb and fa and fa == fb and ya and ya == yb:
            j = len(toka & tokb) / len(toka | tokb)
            if j >= JACCARD_THRESHOLD:
                grade = "moderate" if (ca and ca == cb) else "weak"
                sigs.append({"type": "author_year_title_jaccard", "grade": grade,
                             "members": list(rid),
                             "detail": f"同第一作者姓({fa})+同年({ya})+题名 token Jaccard={j:.3f}"})

    # S3 中英题名对：仅凭材料内 translation_of 字段或共享标识符，绝不臆译
    for x, y in ((a, b), (b, a)):
        t = str(x.get("translation_of") or "").strip()
        if t and t in {str(y.get("record_id") or ""), str(y.get("cite_key") or ""),
                       str(y.get("title") or ""), norm_title(y.get("title"))}:
            shared_id = bool(da and da == db)
            sigs.append({"type": "translation_pair", "members": list(rid),
                         "grade": "strong" if shared_id else "moderate",
                         "detail": f"{x['record_id']} 的 translation_of 字段指向 {y['record_id']}"
                                   + ("，且共享规范化 DOI" if shared_id else "")})
            break

    # S4 预印本↔正式版
    if ta and ta == tb and is_preprint(a) != is_preprint(b):
        pre, pub = (a, b) if is_preprint(a) else (b, a)
        noted = _note_corroborates(pre, pub)
        sigs.append({"type": "preprint_published", "members": list(rid),
                     "grade": "strong" if noted else "moderate",
                     "detail": (f"预印本 {pre['record_id']}（arXiv:{pre.get('arxiv','?')}）"
                                f" ↔ 正式版 {pub['record_id']}；"
                                + ("材料内 note 字段声明版本关系" if noted
                                   else "仅凭题名一致+预印本身份，无材料内关系声明"))})
    return sigs


# ---------------------------------------------------------------- 分组与冲突表

class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x, y):
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self.parent[max(rx, ry)] = min(rx, ry)


def field_conflicts(members, recs_by_id):
    """逐字段冲突表：原始值存在 ≥2 种写法即登记，并标注规范化后是否一致。"""
    out = []
    for f in CONFLICT_FIELDS:
        values = {}
        for rid in members:
            rec = recs_by_id[rid]
            if f == "first_author_family":
                v = (rec.get("authors") or [{}])[0].get("family") if rec.get("authors") else None
            elif f == "doi":
                v = rec.get("doi") or (f"[from url] {rec.get('url')}" if extract_doi(rec) and not rec.get("doi") else None)
            else:
                v = rec.get(f)
            if v not in (None, "", []):
                values[rid] = v
        raw_forms = {json.dumps(v, ensure_ascii=False, sort_keys=True) for v in values.values()}
        if len(raw_forms) >= 2:
            if f == "doi":
                normed = {norm_doi(v) if not str(v).startswith("[from url]") else extract_doi(recs_by_id[rid])
                          for rid, v in values.items()}
            elif f == "year":
                normed = {norm_year(v) for v in values.values()}
            else:
                normed = {norm_text(json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                          for v in values.values()}
            out.append({"field": f, "values": values,
                        "normalized_equal": len(normed) <= 1})
    return out


def build_candidates(records):
    recs_by_id = {r["record_id"]: r for r in records}
    ids = sorted(recs_by_id)
    idx = {rid: k for k, rid in enumerate(ids)}
    uf = UnionFind(len(ids))
    pair_sig = {}
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            sigs = pair_signals(recs_by_id[ids[i]], recs_by_id[ids[j]])
            if sigs:
                pair_sig[(ids[i], ids[j])] = sigs
                uf.union(i, j)
    comps = {}
    for rid in ids:
        comps.setdefault(uf.find(idx[rid]), []).append(rid)
    groups = []
    for members in sorted((sorted(m) for m in comps.values() if len(m) > 1), key=lambda m: m[0]):
        sigs = []
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                sigs.extend(pair_sig.get((members[i], members[j]), []))
        grade = "weak"
        for s in sigs:
            if GRADE_RANK[s["grade"]] > GRADE_RANK[grade]:
                grade = s["grade"]
        groups.append({"members": members, "signals": sigs, "evidence_grade": grade,
                       "field_conflicts": field_conflicts(members, recs_by_id)})
    for k, g in enumerate(groups, 1):
        g["group_id"] = f"G{k:03d}"
        g["group_size"] = len(g["members"])
        if len(members := g["members"]) > 2:
            g["note"] = "候选组 >2 条：signals 中已按成员对给出两两证据，裁决时请逐对核对。"
    return groups


def main(argv=None):
    ap = argparse.ArgumentParser(description="去重候选挖掘（只生成候选，不做裁决）")
    ap.add_argument("--records", help="records.jsonl（阶段 1 建档产物）")
    ap.add_argument("--bib", help="可选：简易 BibTeX 导出，解析后与 records 合并")
    ap.add_argument("--out", required=True, help="输出目录（写 candidates.json）")
    args = ap.parse_args(argv)

    if not args.records and not args.bib:
        print("错误：至少需要 --records 或 --bib 之一", file=sys.stderr)
        return 2

    warnings, records = [], []
    if args.records:
        records.extend(load_records_jsonl(args.records, warnings))
    if args.bib:
        records.extend(parse_bib(args.bib, warnings))
    seen = set()
    for r in records:
        if r["record_id"] in seen:
            print(f"错误：record_id 重复: {r['record_id']}", file=sys.stderr)
            return 2
        seen.add(r["record_id"])

    groups = build_candidates(records)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "tool": "dedup_candidates.py",
        "record_count": len(records),
        "group_count": len(groups),
        "evidence_grade_semantics": {
            "strong": "共享规范化标识符（DOI/PMID/arXiv）或材料内明确声明的版本/翻译关系",
            "moderate": "规范化题名相同且有坐标佐证，或同姓同年高 Jaccard 且容器一致，或仅材料内 translation_of 线索",
            "weak": "仅题名相似（Jaccard/裸题名相同而无坐标佐证）——默认不可自动合并",
        },
        "parse_warnings": warnings,
        "groups": groups,
    }
    out_path = out_dir / "candidates.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
                        encoding="utf-8")
    print(f"记录数: {len(records)}  候选组数: {len(groups)}  解析警告: {len(warnings)}")
    for g in groups:
        sig_types = sorted({s["type"] for s in g["signals"]})
        print(f"  {g['group_id']}  members={g['members']}  grade={g['evidence_grade']}  signals={sig_types}")
    print(f"已写出: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
