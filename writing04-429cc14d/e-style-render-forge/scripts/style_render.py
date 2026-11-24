#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""style_render.py — style-render-forge 阶段 3：类型化模板确定性渲染器（仅标准库，无网络）。

用法：
    python3 style_render.py --records records.json \
        --style gbt7714-numeric|gbt7714-author-year|apa7|ris|bibtex|csljson \
        --out FILE [--citedate "待补"]

立场：渲染器是草稿而非规范验证器。缺字段一律渲染可见占位符 [缺: X]，
代码中不存在任何"自动编造字段"路径。视觉样式省略的标识符与类型元数据
通过 ris / bibtex / csljson 导出模式完整保留。

样式约定（纯文本）：
    - GB/T 7714—2015 顺序编码制：条目前加 [序号]；著者-出版年制按（首作者, 年, id）排序。
    - 中文条目 >3 作者列前 3 名加"等"，西文条目加"et al."（按记录 language 判定）。
    - APA 7：作者 ≤20 全列；题名句首大写采用保守策略（仅抬升首字母，不回改其余大小写，
      以保护缩写与软件名）；刊名与卷号斜体以 *…* 标记（纯文本约定）。
    - 电子资源 [EB/OL]：url 存在时渲染 (更新年)[引用日期: --citedate 值]，默认"待补"，
      绝不杜撰引用日期。
"""
import argparse
import json
import os
import re
import sys

CJK_RE = re.compile(r"[一-鿿]")
LATIN_TOKEN = re.compile(r"[A-Za-z][A-Za-z\-']*")

STYLES = ["gbt7714-numeric", "gbt7714-author-year", "apa7", "ris", "bibtex", "csljson"]

GB_TAG_FALLBACK = {
    "journal-article": "J", "book": "M", "inproceedings": "C",
    "incollection": "A", "thesis": "D", "report": "R",
    "electronic": "EB/OL", "newspaper": "N", "misc": "Z",
}

RIS_TYPE_REV = {
    "journal-article": "JOUR", "book": "BOOK", "thesis": "THES",
    "inproceedings": "CONF", "incollection": "CHAP", "electronic": "ELEC",
    "report": "RPRT", "newspaper": "NEWS", "misc": "GEN",
}

BIB_TYPE_REV = {
    "journal-article": "article", "book": "book", "inproceedings": "inproceedings",
    "incollection": "incollection", "thesis": "thesis", "electronic": "online",
    "report": "techreport", "newspaper": "misc", "misc": "misc",
}

CSL_TYPE_REV = {
    "journal-article": "article-journal", "book": "book",
    "inproceedings": "paper-conference", "incollection": "chapter",
    "thesis": "thesis", "electronic": "webpage", "report": "report",
    "newspaper": "article-newspaper", "misc": "document",
}


def has_cjk(s):
    return bool(CJK_RE.search(s or ""))


def _initials(given):
    return " ".join(w[0].upper() for w in re.split(r"[\s\-]+", given.strip())
                    if w and w[0].isalpha())


def _initials_dot(given):
    return " ".join(w[0].upper() + "." for w in re.split(r"[\s\-]+", given.strip())
                    if w and w[0].isalpha())


# ------------------------------------------------------------- 作者格式化 ----

def gbt_name(name, notes):
    """GB/T：姓全称大写 + 名缩写；CJK 姓名原样。逗号为显式 姓,名 分隔。"""
    name = (name or "").strip()
    if not name:
        return None
    if has_cjk(name):
        return name
    if "," in name:
        family, given = name.split(",", 1)
        inits = _initials(given)
        return family.strip().upper() + (" " + inits if inits else "")
    toks = name.split()
    if len(toks) >= 2 and all(LATIN_TOKEN.fullmatch(t) for t in toks):
        notes.append(f"作者 `{name}` 无逗号分隔，按“首词为姓”解析（保守约定，见 references）")
        inits = _initials(" ".join(toks[1:]))
        return toks[0].upper() + (" " + inits if inits else "")
    return name


def gbt_authors(authors, language, notes):
    names = [gbt_name(a, notes) for a in (authors or [])]
    names = [x for x in names if x]
    if not names:
        return None
    if len(names) > 3:
        suffix = "等" if language in ("zh", "mixed") else "et al."
        return ", ".join(names[:3]) + ", " + suffix
    return ", ".join(names)


def apa_name(name, notes):
    name = (name or "").strip()
    if not name:
        return None
    if has_cjk(name):
        return name
    if "," in name:
        family, given = name.split(",", 1)
        inits = _initials_dot(given)
        return family.strip() + (", " + inits if inits else "")
    toks = name.split()
    if len(toks) >= 2 and all(LATIN_TOKEN.fullmatch(t) for t in toks):
        notes.append(f"作者 `{name}` 无逗号分隔，按“末词为姓”解析（APA 保守约定）")
        inits = _initials_dot(" ".join(toks[:-1]))
        return toks[-1] + ", " + inits
    return name


def apa_authors(authors, notes):
    names = [apa_name(a, notes) for a in (authors or [])]
    names = [x for x in names if x]
    if not names:
        return None
    if len(names) > 20:
        notes.append(f"作者 {len(names)} 名 > 20，APA 7 规则：列前 19 + … + 末位")
        return ", ".join(names[:19]) + ", ... " + names[-1]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + ", & " + names[-1]


def apa_title(title, notes):
    """APA 句首大写保守策略：仅抬升首字母，不回改其余大小写（保护缩写/软件名）。"""
    if title and title[0].isalpha() and title[0].islower():
        notes.append("APA 题名句首大写：仅抬升首字母，其余字符原样（保守策略）")
        return title[0].upper() + title[1:]
    return title


# ------------------------------------------------------------ GB/T 7714 ----


def _adot(auth):
    """作者段后接句点；若已以西文句点结尾（如 et al. / 缩写）则不重复加。"""
    return auth if auth.endswith(".") else auth + "."


def _need(rec, field, label, ph):
    v = rec.get(field)
    if v is None or v == "" or v == []:
        ph.append(field)
        return f"[缺: {label}]"
    return v


def _gb_tag(rec, notes):
    tag = rec.get("type_tag") or GB_TAG_FALLBACK.get(rec.get("type") or "misc", "Z")
    if (rec.get("type") or "misc") == "misc" and tag == "Z":
        notes.append("类型未定型，按 [Z]（其他）渲染并标注，未伪造成期刊条目")
    return tag


def _vol_issue(rec):
    vol, iss = rec.get("volume"), rec.get("issue")
    if vol and iss:
        return f", {vol}({iss})"
    if vol:
        return f", {vol}"
    if iss:
        return f"({iss})"
    return ""


def _pages_or_artno(rec, ph, notes):
    if rec.get("pages"):
        return rec["pages"]
    if rec.get("article_number"):
        notes.append("无页码，按文章号渲染（GB/T 允许）")
        return rec["article_number"]
    ph.append("pages")
    return "[缺: 页码]"


def render_gbt(rec, citedate, author_year=False):
    ph, notes = [], []
    rtype = rec.get("type") or "misc"
    tag = _gb_tag(rec, notes)
    auth = gbt_authors(rec.get("authors"), rec.get("language"), notes)
    if auth is None:
        ph.append("authors")
        auth = "[缺: 作者]"
    auth = _adot(auth)
    title = _need(rec, "title", "题名", ph)
    year = rec.get("year")
    yseg = year if year else "[缺: 年份]"
    if not year:
        ph.append("year")

    def loc_pub(addr_label="出版地", pub_label="出版者", optional=False):
        addr, pub = rec.get("address"), rec.get("publisher")
        if optional and not addr and not pub:
            return ""
        a = addr if addr else f"[缺: {addr_label}]"
        p = pub if pub else f"[缺: {pub_label}]"
        if not addr:
            ph.append("address")
        if not pub:
            ph.append("publisher")
        return f"{a}: {p}, "

    if rtype == "journal-article":
        venue = _need(rec, "venue", "刊名", ph)
        pp = _pages_or_artno(rec, ph, notes)
        vi = _vol_issue(rec)
        if author_year:
            line = f"{auth} {yseg}. {title}[{tag}]. {venue}{vi}: {pp}."
        else:
            line = f"{auth} {title}[{tag}]. {venue}, {yseg}{vi}: {pp}."
    elif rtype == "book":
        lp = loc_pub()
        if author_year:
            line = f"{auth} {yseg}. {title}[{tag}]. {lp.rstrip(', ')}."
        else:
            line = f"{auth} {title}[{tag}]. {lp}{yseg}."
    elif rtype in ("incollection", "inproceedings"):
        venue = _need(rec, "venue", "论文集题名", ph)
        pp = _pages_or_artno(rec, ph, notes)
        eds = gbt_authors(rec.get("editors"), rec.get("language"), notes)
        host = f"{eds}. {venue}" if eds else venue
        lp = loc_pub(optional=(rtype == "inproceedings"))
        if author_year:
            if lp:
                line = f"{auth} {yseg}. {title}[{tag}]//{host}. {lp.rstrip(', ')}: {pp}."
            else:
                line = f"{auth} {yseg}. {title}[{tag}]//{host}: {pp}."
        else:
            line = f"{auth} {title}[{tag}]//{host}. {lp}{yseg}: {pp}."
    elif rtype == "thesis":
        lp = loc_pub(addr_label="地点", pub_label="培养单位")
        if author_year:
            line = f"{auth} {yseg}. {title}[{tag}]. {lp.rstrip(', ')}."
        else:
            line = f"{auth} {title}[{tag}]. {lp}{yseg}."
    elif rtype == "report":
        lp = loc_pub()
        line = (f"{auth} {yseg}. {title}[{tag}]. {lp.rstrip(', ')}." if author_year
                else f"{auth} {title}[{tag}]. {lp}{yseg}.")
    elif rtype == "electronic":
        url = rec.get("url")
        if url:
            if author_year:
                line = f"{auth} {yseg}. {title}[{tag}]. [引用日期: {citedate}]. {url}."
            else:
                line = f"{auth} {title}[{tag}]. ({yseg})[引用日期: {citedate}]. {url}."
        else:
            ph.append("url")
            line = f"{auth} {title}[{tag}]. ({yseg}). [缺: 网址]"
            notes.append("电子资源缺 URL，[EB/OL] 与引用日期段无法完整渲染")
    elif rtype == "newspaper":
        venue = _need(rec, "venue", "报纸名", ph)
        notes.append("报纸条目按简化模板渲染（缺月日/版次字段时不杜撰）")
        line = (f"{auth} {yseg}. {title}[{tag}]. {venue}." if author_year
                else f"{auth} {title}[{tag}]. {venue}, {yseg}.")
    else:  # misc
        bits = [b for b in (rec.get("venue"), None if author_year else rec.get("year")) if b]
        tail = (", ".join(bits) + ".") if bits else ""
        line = f"{auth} " + (f"{yseg}. " if author_year else "") + f"{title}[{tag}]. {tail}".rstrip()
    if rec.get("doi") and rtype in ("journal-article", "inproceedings", "incollection",
                                    "book", "thesis", "report"):
        line += f" DOI: {rec['doi']}."
    return line, ph, notes


# ---------------------------------------------------------------- APA 7 ----

def render_apa(rec):
    ph, notes = [], []
    rtype = rec.get("type") or "misc"
    auth = apa_authors(rec.get("authors"), notes)
    if auth is None:
        ph.append("authors")
        auth = "[缺: 作者]"
    auth = _adot(auth)
    year = rec.get("year")
    if year:
        yseg = f"({year})"
    else:
        ph.append("year")
        yseg = "([缺: 年份])"
    title = rec.get("title")
    if title:
        title = apa_title(title, notes)
    else:
        ph.append("title")
        title = "[缺: 题名]"
    doi = rec.get("doi")
    doipart = f" https://doi.org/{doi}" if doi else ""

    if rtype == "journal-article":
        venue = rec.get("venue")
        vseg = f"*{venue}*" if venue else "[缺: 刊名]"
        if not venue:
            ph.append("venue")
        vol, iss = rec.get("volume"), rec.get("issue")
        if vol:
            vseg += f", *{vol}*" + (f"({iss})" if iss else "")
        elif iss:
            vseg += f", ({iss})"
            notes.append("有期无卷，APA 卷号斜体段省略，仅保留期号")
        if rec.get("pages"):
            pseg = f", {rec['pages']}"
        elif rec.get("article_number"):
            pseg = f", Article {rec['article_number']}"
        else:
            ph.append("pages")
            pseg = ", [缺: 页码]"
        line = f"{auth} {yseg}. {title}. {vseg}{pseg}.{doipart}"
    elif rtype == "book":
        pub = rec.get("publisher")
        if not pub:
            ph.append("publisher")
            pub = "[缺: 出版者]"
        line = f"{auth} {yseg}. *{title}*. {pub}.{doipart}"
    elif rtype in ("incollection", "inproceedings"):
        venue = rec.get("venue") or "[缺: 论文集题名]"
        if not rec.get("venue"):
            ph.append("venue")
        pp = rec.get("pages") or "[缺: 页码]"
        if not rec.get("pages"):
            ph.append("pages")
        pub = rec.get("publisher") or "[缺: 出版者]"
        if not rec.get("publisher"):
            ph.append("publisher")
        notes.append("APA 论文集析出按简化模板渲染（省略文集编者段，不杜撰）")
        line = f"{auth} {yseg}. {title}. In *{venue}* (pp. {pp}). {pub}.{doipart}"
    elif rtype == "thesis":
        pub = rec.get("publisher") or "[缺: 培养单位]"
        if not rec.get("publisher"):
            ph.append("publisher")
        line = f"{auth} {yseg}. *{title}* [学位论文, {pub}].{doipart}"
    elif rtype == "electronic":
        url = rec.get("url") or "[缺: 网址]"
        if not rec.get("url"):
            ph.append("url")
        line = f"{auth} {yseg}. {title}. {url}"
    else:
        notes.append(f"APA 模板未覆盖类型 {rtype}，按最近结构（题名+来源）渲染并标注")
        venue = rec.get("venue") or ""
        line = f"{auth} {yseg}. {title}." + (f" {venue}." if venue else "")
    return line, ph, notes


# ------------------------------------------------------------------ 导出 ----

def export_ris(records):
    out = []
    for rec in records:
        rtype = rec.get("type") or "misc"
        lines = [f"TY  - {RIS_TYPE_REV.get(rtype, 'GEN')}"]
        if rec.get("id"):
            lines.append(f"ID  - {rec['id']}")
        if rec.get("title"):
            lines.append(f"TI  - {rec['title']}")
        if rec.get("title_alt"):
            lines.append(f"T3  - {rec['title_alt']}")
        for a in rec.get("authors") or []:
            lines.append(f"AU  - {a}")
        for e in rec.get("editors") or []:
            lines.append(f"ED  - {e}")
        if rec.get("year"):
            lines.append(f"PY  - {rec['year']}")
        if rec.get("venue"):
            lines.append(f"{'JO' if rtype == 'journal-article' else 'T2'}  - {rec['venue']}")
        if rec.get("volume"):
            lines.append(f"VL  - {rec['volume']}")
        if rec.get("issue"):
            lines.append(f"IS  - {rec['issue']}")
        if rec.get("pages"):
            m = re.match(r"^(\d+)[-–](\d+)$", rec["pages"].strip())
            if m:
                lines.append(f"SP  - {m.group(1)}")
                lines.append(f"EP  - {m.group(2)}")
            else:
                lines.append(f"SP  - {rec['pages'].strip()}")
        if rec.get("article_number"):
            lines.append(f"M1  - {rec['article_number']}")
        if rec.get("doi"):
            lines.append(f"DO  - {rec['doi']}")
        if rec.get("url"):
            lines.append(f"UR  - {rec['url']}")
        if rec.get("publisher"):
            lines.append(f"PB  - {rec['publisher']}")
        if rec.get("address"):
            lines.append(f"CY  - {rec['address']}")
        if rec.get("isbn"):
            lines.append(f"SN  - {rec['isbn']}")
        if rec.get("language") and rec["language"] != "unknown":
            lines.append(f"LA  - {rec['language']}")
        if rec.get("type_tag"):
            lines.append(f"M3  - {rec['type_tag']}")
        for tag, val in sorted((rec.get("unmapped_fields") or {}).items()):
            if re.fullmatch(r"[A-Z0-9]{2}", tag):
                for piece in str(val).split(" | "):
                    lines.append(f"{tag}  - {piece}")
        lines.append("ER  - ")
        out.append("\n".join(lines))
    return "\n\n".join(out) + ("\n" if out else "")


def export_bibtex(records):
    out = []
    for rec in records:
        rtype = rec.get("type") or "misc"
        etype = BIB_TYPE_REV.get(rtype, "misc")
        key = re.sub(r"[^A-Za-z0-9_\-]", "_", rec.get("id") or "unnamed")
        lines = [f"@{etype}{{{key},"]
        if rec.get("authors"):
            lines.append(f"  author = {{{' and '.join(rec['authors'])}}},")
        if rec.get("editors"):
            lines.append(f"  editor = {{{' and '.join(rec['editors'])}}},")
        if rec.get("title"):
            lines.append(f"  title = {{{rec['title']}}},")
        if rec.get("venue"):
            fname = "journal" if rtype == "journal-article" else "booktitle"
            lines.append(f"  {fname} = {{{rec['venue']}}},")
        if rec.get("year"):
            lines.append(f"  year = {{{rec['year']}}},")
        if rec.get("volume"):
            lines.append(f"  volume = {{{rec['volume']}}},")
        if rec.get("issue"):
            lines.append(f"  number = {{{rec['issue']}}},")
        if rec.get("pages"):
            lines.append(f"  pages = {{{rec['pages'].replace('–', '-')}}},")
        if rec.get("doi"):
            lines.append(f"  doi = {{{rec['doi']}}},")
        if rec.get("url"):
            lines.append(f"  url = {{{rec['url']}}},")
        if rec.get("publisher"):
            fname = "school" if rtype == "thesis" else "publisher"
            lines.append(f"  {fname} = {{{rec['publisher']}}},")
        if rec.get("address"):
            lines.append(f"  address = {{{rec['address']}}},")
        if rec.get("isbn"):
            lines.append(f"  isbn = {{{rec['isbn']}}},")
        for name, val in sorted((rec.get("unmapped_fields") or {}).items()):
            if re.fullmatch(r"[a-z][a-z0-9_\-]*", str(name)):
                lines.append(f"  {name} = {{{val}}},")
        lines.append("}")
        out.append("\n".join(lines))
    return "\n\n".join(out) + ("\n" if out else "")


def export_csljson(records):
    items = []
    for rec in records:
        rtype = rec.get("type") or "misc"
        item = {
            "id": rec.get("id"),
            "type": CSL_TYPE_REV.get(rtype, "document"),
        }
        if rec.get("authors"):
            item["author"] = [{"literal": a} for a in rec["authors"]]
        if rec.get("editors"):
            item["editor"] = [{"literal": e} for e in rec["editors"]]
        if rec.get("title"):
            item["title"] = rec["title"]
        if rec.get("title_alt"):
            item["title-short"] = rec["title_alt"]
        if rec.get("year"):
            item["issued"] = {"date-parts": [[int(rec["year"])]]}
        if rec.get("venue"):
            item["container-title"] = rec["venue"]
        for src, dst in (("volume", "volume"), ("issue", "issue"),
                         ("pages", "page"), ("article_number", "article-number"),
                         ("doi", "DOI"), ("url", "URL"),
                         ("publisher", "publisher"), ("address", "publisher-place"),
                         ("isbn", "ISBN"), ("language", "language")):
            if rec.get(src):
                item[dst] = rec[src]
        if rec.get("type_tag"):
            item["note"] = f"GB/T 7714 类型标识: [{rec['type_tag']}]"
        items.append(item)
    return json.dumps(items, ensure_ascii=False, indent=2) + "\n"


# ---------------------------------------------------------------- 主流程 ----

def main(argv=None):
    ap = argparse.ArgumentParser(description="style-render-forge 确定性渲染器")
    ap.add_argument("--records", required=True, help="records.json 路径")
    ap.add_argument("--style", required=True, choices=STYLES)
    ap.add_argument("--out", required=True, help="输出文件路径")
    ap.add_argument("--citedate", default="待补",
                    help="[EB/OL] 引用日期占位内容（默认“待补”，绝不杜撰日期）")
    args = ap.parse_args(argv)

    with open(args.records, "r", encoding="utf-8") as fh:
        records = json.load(fh).get("records", [])

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    notes_path = os.path.splitext(os.path.abspath(args.out))[0] + ".render_notes.json"

    if args.style in ("ris", "bibtex", "csljson"):
        text = {"ris": export_ris, "bibtex": export_bibtex,
                "csljson": export_csljson}[args.style](records)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        notes = {
            "schema": "style-render-forge/render-notes/v1",
            "style": args.style, "mode": "export",
            "note": "导出模式：完整保留标识符与类型元数据（DOI/URL/卷期页/类型标识），"
                    "即使视觉样式省略它们",
            "entries": [{"id": r.get("id"), "placeholders": [], "notes": []}
                        for r in records],
            "summary": {"entries": len(records), "entries_with_placeholders": 0,
                        "placeholder_total": 0},
        }
        with open(notes_path, "w", encoding="utf-8") as fh:
            json.dump(notes, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(json.dumps({"out": args.out, "style": args.style, "mode": "export",
                          "entries": len(records)}, ensure_ascii=False))
        return 0

    entries_notes = []
    lines = []
    if args.style == "gbt7714-numeric":
        ordered = list(records)
        for i, rec in enumerate(ordered, 1):
            line, ph, notes = render_gbt(rec, args.citedate, author_year=False)
            lines.append(f"[{i}] {line}")
            entries_notes.append({"id": rec.get("id"), "index": i,
                                  "placeholders": ph, "notes": notes})
    elif args.style == "gbt7714-author-year":
        ordered = sorted(records, key=lambda r: (
            ((r.get("authors") or [""])[0] or "").lower(),
            r.get("year") or "9999", r.get("id") or ""))
        for i, rec in enumerate(ordered, 1):
            line, ph, notes = render_gbt(rec, args.citedate, author_year=True)
            lines.append(line)
            entries_notes.append({"id": rec.get("id"), "index": i,
                                  "placeholders": ph, "notes": notes})
    else:  # apa7
        ordered = sorted(records, key=lambda r: (
            ((r.get("authors") or [""])[0] or "").lower(),
            r.get("year") or "9999", r.get("id") or ""))
        for i, rec in enumerate(ordered, 1):
            line, ph, notes = render_apa(rec)
            lines.append(line)
            entries_notes.append({"id": rec.get("id"), "index": i,
                                  "placeholders": ph, "notes": notes})

    text = "\n".join(lines) + "\n"
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)

    n_ph = sum(len(e["placeholders"]) for e in entries_notes)
    notes = {
        "schema": "style-render-forge/render-notes/v1",
        "style": args.style, "mode": "render", "citedate": args.citedate,
        "entries": entries_notes,
        "summary": {
            "entries": len(entries_notes),
            "entries_with_placeholders": sum(1 for e in entries_notes if e["placeholders"]),
            "placeholder_total": n_ph,
        },
    }
    with open(notes_path, "w", encoding="utf-8") as fh:
        json.dump(notes, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(json.dumps({"out": args.out, "style": args.style, "mode": "render",
                      "entries": len(entries_notes), "placeholder_total": n_ph},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
