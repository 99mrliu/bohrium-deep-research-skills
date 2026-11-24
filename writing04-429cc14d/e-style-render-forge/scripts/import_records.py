#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""import_records.py — style-render-forge 阶段 1：多源文献库导入器（仅标准库，确定性，无网络）。

用法：
    python3 import_records.py --file library.bib [--file more.ris] [--format bibtex|ris|cnki-text] --out DIR

支持来源：
    - BibTeX（.bib）：条目级解析；@string/@preamble/注释逐字保留；字段同时给出
      resolved 值与 raw 源文本；# 连接在读取时解析；重复键与未解析宏登记警告。
    - RIS（.ris）：TY 起始、ER 结束；自动识别 CNKI RefWorks 风味；未知标签
      verbatim 保留进 unmapped_fields，绝不丢弃。
    - CNKI 文本导出（.txt）："题名: ..." 行式，空行分记录；未知键 verbatim 保留。

统一写出 DIR/records.json（schema: style-render-forge/records/v1）。
输出排序按记录 id 字典序，JSON 键序固定，保证逐字节可复现。
"""
import argparse
import json
import os
import re
import sys

SCHEMA = "style-render-forge/records/v1"

# 规范化核心字段（扩展字段在 references/import_export_formats.md 登记）
RECORD_KEYS = [
    "id", "type", "authors", "editors", "title", "title_alt", "year",
    "venue", "volume", "issue", "pages", "article_number", "publisher",
    "address", "doi", "url", "isbn", "language", "type_tag",
    "raw_source", "unmapped_fields", "warnings",
]

BIB_TYPES = {
    "article": ("journal-article", "J"),
    "book": ("book", "M"),
    "booklet": ("book", "M"),
    "inproceedings": ("inproceedings", "C"),
    "conference": ("inproceedings", "C"),
    "incollection": ("incollection", "A"),
    "inbook": ("incollection", "A"),
    "phdthesis": ("thesis", "D"),
    "mastersthesis": ("thesis", "D"),
    "thesis": ("thesis", "D"),
    "online": ("electronic", "EB/OL"),
    "electronic": ("electronic", "EB/OL"),
    "techreport": ("report", "R"),
    "misc": ("misc", None),
    "unpublished": ("misc", None),
    "manual": ("misc", None),
}

BIB_FIELD_MAP = {
    "author": "authors", "editor": "editors", "title": "title",
    "journal": "venue", "journaltitle": "venue", "booktitle": "venue",
    "year": "year", "date": "year", "volume": "volume", "number": "issue",
    "issue": "issue", "pages": "pages", "eid": "article_number",
    "articleno": "article_number", "doi": "doi", "url": "url",
    "publisher": "publisher", "school": "publisher", "institution": "publisher",
    "address": "address", "location": "address", "isbn": "isbn",
}

RIS_TAGS = {
    "TI": "title", "T1": "title", "T2": "venue", "JO": "venue", "JF": "venue",
    "AU": "authors", "A1": "authors", "ED": "editors", "A2": "editors",
    "PY": "year", "Y1": "year", "VL": "volume", "IS": "issue",
    "DO": "doi", "UR": "url", "PB": "publisher", "CY": "address",
    "SN": "isbn", "LA": "language", "M1": "article_number",
    "M3": "type_tag", "T3": "title_alt", "X1": "title_alt",
}

RIS_TYPES = {
    "JOUR": ("journal-article", "J"), "JFULL": ("journal-article", "J"),
    "BOOK": ("book", "M"), "THES": ("thesis", "D"),
    "CONF": ("inproceedings", "C"), "CPAPER": ("inproceedings", "C"),
    "CHAP": ("incollection", "A"), "ELEC": ("electronic", "EB/OL"),
    "RPRT": ("report", "R"), "NEWS": ("newspaper", "N"),
    "GEN": ("misc", None),
}

CNKI_TEXT_MAP = {
    "题名": "title", "标题": "title", "作者": "authors",
    "来源": "venue", "刊名": "venue", "刊名（中）": "venue",
    "年": "year", "发表时间": "year", "年份": "year",
    "卷": "volume", "期": "issue", "页码": "pages", "页数": "pages",
    "DOI": "doi", "doi": "doi", "链接": "url", "URL": "url",
    "出版社": "publisher", "出版地": "address",
}

CJK_RE = re.compile(r"[一-鿿]")
YEAR_RE = re.compile(r"(\d{4})")


def detect_language(*texts):
    """按题名/刊名粗判语言：含 CJK 为 zh，纯拉丁为 en，兼有 mixed，皆空 unknown。"""
    joined = " ".join(t for t in texts if t)
    if not joined:
        return "unknown"
    has_cjk = bool(CJK_RE.search(joined))
    has_lat = bool(re.search(r"[A-Za-z]", joined))
    if has_cjk and has_lat and not re.search(r"[A-Za-z]{4,}", re.sub(r"[一-鿿]", " ", joined)):
        # CJK 为主、零星拉丁缩写 → 仍按 zh
        return "zh"
    if has_cjk and has_lat:
        return "mixed"
    if has_cjk:
        return "zh"
    return "en" if has_lat else "unknown"


def new_record(rid, rtype, raw):
    rec = {k: None for k in RECORD_KEYS}
    rec["id"] = rid
    rec["type"] = rtype
    rec["authors"] = []
    rec["editors"] = []
    rec["unmapped_fields"] = {}
    rec["warnings"] = []
    rec["language"] = "unknown"
    rec["raw_source"] = raw
    return rec


def strip_bib_braces(s):
    """BibTeX 花括号仅用于大小写保护；纯文本渲染目标下去除（文档化行为）。"""
    return s.replace("{", "").replace("}", "")


# ---------------------------------------------------------------- BibTeX ----

def _match_brace(text, start, opench, closech):
    depth = 1
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == opench:
            depth += 1
        elif ch == closech:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _parse_bib_value(s, i, strings, warnings, ctx):
    """解析一个 BibTeX 值表达式（含 # 连接）。返回 (resolved, raw, 新下标)。"""
    n = len(s)
    vstart = i
    parts = []
    while True:
        while i < n and s[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        ch = s[i]
        if ch == "{":
            j = _match_brace(s, i + 1, "{", "}")
            if j < 0:
                warnings.append(f"{ctx}: 值花括号未闭合，按现有内容截断")
                j = n
            parts.append(s[i + 1:j])
            i = j + 1 if j < n else n
        elif ch == '"':
            j = i + 1
            buf = []
            depth = 0
            while j < n:
                cj = s[j]
                if cj == "{":
                    depth += 1
                elif cj == "}":
                    depth -= 1
                elif cj == '"' and depth == 0:
                    break
                buf.append(cj)
                j += 1
            if j >= n:
                warnings.append(f"{ctx}: 值引号未闭合，按现有内容截断")
            parts.append("".join(buf))
            i = j + 1
        else:
            m = re.match(r"[^,\s#{}\"]+", s[i:])
            if not m:
                break
            tok = m.group(0)
            i += len(tok)
            key = tok.lower()
            if key in strings:
                parts.append(strings[key])
            elif re.fullmatch(r"\d+", tok):
                parts.append(tok)
            else:
                warnings.append(
                    f"{ctx}: 宏 `{tok}` 无法解析（未定义 @string），保留原样不手改")
                parts.append(tok)
        while i < n and s[i] in " \t\r\n":
            i += 1
        if i < n and s[i] == "#":
            i += 1
            continue
        break
    raw = s[vstart:i].strip()
    resolved = "".join(parts).strip()
    return resolved, raw, i


def _parse_bib_fields(s, strings, warnings, ctx):
    """解析 'name = value, ...' 字段序列。返回 [(name, resolved, raw)]。"""
    fields = []
    i, n = 0, len(s)
    while i < n:
        while i < n and s[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        m = re.match(r"[A-Za-z][A-Za-z0-9_\-]*", s[i:])
        if not m:
            warnings.append(f"{ctx}: 无法解析的字段起始，已跳过 1 字符")
            i += 1
            continue
        name = m.group(0).lower()
        i += len(name)
        while i < n and s[i] in " \t\r\n":
            i += 1
        if i >= n or s[i] != "=":
            warnings.append(f"{ctx}: 字段 `{name}` 后缺少 '='，该字段按空值登记")
            fields.append((name, "", ""))
            continue
        i += 1
        while i < n and s[i] in " \t\r\n":
            i += 1
        resolved, raw, i = _parse_bib_value(s, i, strings, warnings, ctx)
        fields.append((name, resolved, raw))
        while i < n and s[i] in " \t\r\n":
            i += 1
        if i < n and s[i] == ",":
            i += 1
    return fields


def parse_bibtex(text, global_warnings, meta):
    strings = {}
    records = []
    comments = []
    preambles = []
    seen_keys = {}
    i, n = 0, len(text)

    def skip_ws(k):
        while k < n and text[k] in " \t\r\n":
            k += 1
        return k

    while i < n:
        c = text[i]
        if c == "%":
            j = text.find("\n", i)
            j = n if j < 0 else j
            comments.append(text[i + 1:j].strip())
            i = j
            continue
        if c != "@":
            i += 1
            continue
        m = re.match(r"@\s*([A-Za-z]+)\s*([{(])", text[i:])
        if not m:
            global_warnings.append(f"bibtex: 偏移 {i} 处的 '@' 不构成合法条目头，跳过")
            i += 1
            continue
        etype = m.group(1).lower()
        opench = m.group(2)
        closech = "}" if opench == "{" else ")"
        body_start = i + m.end()
        body_end = _match_brace(text, body_start, opench, closech)
        if body_end < 0:
            global_warnings.append(
                f"bibtex: @{etype} 条目括号未闭合（偏移 {i}），条目按到文件尾截断")
            body_end = n
        raw_entry = text[i:body_end + (1 if body_end < n else 0)]
        body = text[body_start:body_end]
        i = body_end + 1

        if etype == "comment":
            comments.append(body.strip())
            continue
        if etype == "preamble":
            preambles.append(raw_entry)
            continue
        if etype == "string":
            fs = _parse_bib_fields(body, strings, global_warnings, "@string")
            for name, resolved, raw in fs:
                if name in strings:
                    global_warnings.append(
                        f"bibtex: @string `{name}` 重复定义，保留首定义，后定义登记不生效")
                else:
                    strings[name] = strip_bib_braces(resolved)
            meta.setdefault("bibtex_strings_raw", []).append(raw_entry)
            continue

        # 普通条目：key 为首个顶层逗号之前
        depth = 0
        key_end = len(body)
        for k, ch in enumerate(body):
            if ch in "{(":
                depth += 1
            elif ch in "})":
                depth -= 1
            elif ch == "," and depth == 0:
                key_end = k
                break
        key = body[:key_end].strip()
        rest = body[key_end + 1:] if key_end < len(body) else ""
        if not key:
            key = f"unnamed-{len(records) + 1}"
            global_warnings.append(f"bibtex: @{etype} 条目缺 citation key，赋名 {key}")
        rid = key
        if key in seen_keys:
            seen_keys[key] += 1
            rid = f"{key}#dup{seen_keys[key]}"
            global_warnings.append(
                f"bibtex: 重复 citation key `{key}`，第二条登记为 `{rid}`，不覆盖不丢弃")
        else:
            seen_keys[key] = 1

        rtype, tag = BIB_TYPES.get(etype, ("misc", None))
        rec = new_record(rid, rtype, raw_entry)
        if etype not in BIB_TYPES:
            rec["warnings"].append(
                f"未知 BibTeX 条目类型 @{etype}，按 misc 登记并在渲染时按最近类型处理")
        rec["type_tag"] = tag
        raw_fields = {}
        for name, resolved, raw in _parse_bib_fields(
                rest, strings, rec["warnings"], f"@{etype}{{{key}}}"):
            raw_fields[name] = raw
            value = strip_bib_braces(resolved)
            if name in ("year", "date"):
                ym = YEAR_RE.search(value)
                rec["year"] = ym.group(1) if ym else (value or None)
                if not ym and value:
                    rec["warnings"].append(f"year/date `{value}` 中未检出 4 位年份")
                continue
            target = BIB_FIELD_MAP.get(name)
            if target in ("authors", "editors"):
                rec[target] = [a.strip() for a in re.split(r"\s+and\s+", value) if a.strip()]
            elif target:
                rec[target] = value or None
            else:
                rec["unmapped_fields"][name] = value
                rec["warnings"].append(f"未映射 BibTeX 字段 `{name}`，verbatim 保留")
        rec["language"] = detect_language(rec["title"], rec["venue"])
        rec["_raw_fields"] = raw_fields  # 导出用，写盘前剥离
        records.append(rec)

    meta["bibtex_comments"] = comments
    meta["bibtex_preambles"] = preambles
    meta["bibtex_strings"] = strings
    return records


# ------------------------------------------------------------------- RIS ----

CNKI_FLAVOR_HINTS = {"A1", "Y1", "JF", "K1", "LA"}


def parse_ris(text, global_warnings, meta, prefix="ris"):
    records = []
    cur = None
    cur_raw = []
    last_tag = None
    flavor_votes = 0
    total_tags = 0
    counter = 0

    def flush():
        nonlocal cur, cur_raw, counter
        if cur is None:
            return
        counter += 1
        if cur["type"] is None:
            cur["warnings_extra"].append("RIS 记录缺 TY 或 TY 未知，按 misc 登记")
            cur["type"] = "misc"
        rid = cur.get("rid") or f"{prefix}-{counter}"
        rec = new_record(rid, cur["type"], "\n".join(cur_raw))
        for k, v in cur.items():
            if k in ("type", "warnings_extra", "sp", "ep", "rid"):
                continue
            if k in ("authors", "editors", "unmapped_fields"):
                rec[k] = v
            elif k in RECORD_KEYS and v is not None:
                rec[k] = v
        sp, ep = cur.get("sp"), cur.get("ep")
        if sp and ep:
            rec["pages"] = f"{sp}-{ep}"
        elif sp or ep:
            rec["pages"] = sp or ep
        rec["warnings"].extend(cur.get("warnings_extra", []))
        if not rec["language"] or rec["language"] == "unknown":
            rec["language"] = detect_language(rec["title"], rec["venue"])
        records.append(rec)
        cur = None
        cur_raw = []

    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue  # 注释行（本 skill 示例用），跳过
        m = re.match(r"^([A-Z0-9]{2})\s{1,2}-\s?(.*)$", line)
        if not m:
            if cur is not None and last_tag and line.strip():
                # 续行并入上一标签值
                tgt = RIS_TAGS.get(last_tag)
                if tgt in ("authors", "editors"):
                    if cur[tgt]:
                        cur[tgt][-1] += " " + line.strip()
                elif tgt and cur.get(tgt):
                    cur[tgt] += " " + line.strip()
                elif last_tag in cur["unmapped_fields"]:
                    cur["unmapped_fields"][last_tag] += " " + line.strip()
                cur_raw.append(line)
            elif line.strip():
                global_warnings.append(f"ris: 无法识别的行（非标签格式），跳过: {line[:40]}")
            continue
        tag, value = m.group(1), m.group(2).strip()
        last_tag = tag
        total_tags += 1
        if tag in CNKI_FLAVOR_HINTS:
            flavor_votes += 1
        if cur is None and tag != "TY":
            global_warnings.append(f"ris: 记录外出现标签 {tag}，按新记录起始处理")
            cur = {"type": None, "authors": [], "editors": [],
                   "unmapped_fields": {}, "warnings_extra": []}
        if cur is None:
            cur = {"type": None, "authors": [], "editors": [],
                   "unmapped_fields": {}, "warnings_extra": []}
        cur_raw.append(line)
        if tag == "TY":
            rtype, ttag = RIS_TYPES.get(value.upper(), (None, None))
            if rtype is None:
                cur["warnings_extra"].append(f"未知 RIS TY 值 `{value}`，按 misc 登记")
                cur["type"] = "misc"
            else:
                cur["type"] = rtype
                if ttag:
                    cur["type_tag"] = ttag
        elif tag == "ER":
            flush()
            last_tag = None
        elif tag == "SP":
            cur["sp"] = value
        elif tag == "EP":
            cur["ep"] = value
        elif tag == "ID":
            # 标准 RIS 参考号；本 skill 导出时写入原记录 id，往返时恢复 id
            cur["rid"] = value
        elif tag in RIS_TAGS:
            tgt = RIS_TAGS[tag]
            if tgt in ("authors", "editors"):
                cur[tgt].append(value)
            elif tgt == "year":
                ym = YEAR_RE.search(value)
                cur["year"] = ym.group(1) if ym else value
                if not ym:
                    cur["warnings_extra"].append(f"{tag} 值 `{value}` 中未检出 4 位年份")
            else:
                cur[tgt] = value
        else:
            if tag in cur["unmapped_fields"]:
                cur["unmapped_fields"][tag] += " | " + value
            else:
                cur["unmapped_fields"][tag] = value
            cur["warnings_extra"].append(f"未映射 RIS 标签 {tag}，verbatim 保留")

    flush()
    meta["ris_flavor"] = (
        "cnki-refworks" if total_tags and flavor_votes >= 2 else "standard-ris")
    global_warnings.append(f"ris: 风味判定为 {meta['ris_flavor']}"
                           f"（命中提示标签 {flavor_votes}/{total_tags}）")
    return records


# ------------------------------------------------------------- CNKI 文本 ----

def parse_cnki_text(text, global_warnings, meta, prefix="cnki"):
    records = []
    blocks = re.split(r"\n\s*\n", text)
    counter = 0
    for block in blocks:
        lines = [ln for ln in block.splitlines()
                 if ln.strip() and not ln.lstrip().startswith("#")]
        if not lines:
            continue
        counter += 1
        rec = new_record(f"{prefix}-{counter}", "journal-article", "\n".join(lines))
        rec["type_tag"] = "J"
        rec["warnings"].append(
            "CNKI 文本导出不带文献类型，默认按期刊论文登记；如实际为其他类型请人工改 type/type_tag")
        for ln in lines:
            m = re.match(r"^([^:：\s][^:：]*)\s*[:：]\s*(.*)$", ln)
            if not m:
                rec["warnings"].append(f"无法解析的行，跳过: {ln[:40]}")
                continue
            key, value = m.group(1).strip(), m.group(2).strip()
            tgt = CNKI_TEXT_MAP.get(key)
            if tgt == "authors":
                rec["authors"] = [a.strip() for a in re.split(r"[;；,，、]", value) if a.strip()]
            elif tgt == "year":
                ym = YEAR_RE.search(value)
                rec["year"] = ym.group(1) if ym else value
                if not ym:
                    rec["warnings"].append(f"{key} 值 `{value}` 中未检出 4 位年份")
            elif tgt:
                rec[tgt] = value
            else:
                rec["unmapped_fields"][key] = value
                rec["warnings"].append(f"未映射 CNKI 文本键 `{key}`，verbatim 保留")
        rec["language"] = detect_language(rec["title"], rec["venue"])
        records.append(rec)
    meta["cnki_text_blocks"] = counter
    return records


# ----------------------------------------------------------------- 主流程 ----

def detect_format(path):
    ext = os.path.splitext(path)[1].lower()
    return {".bib": "bibtex", ".ris": "ris", ".txt": "cnki-text"}.get(ext)


def main(argv=None):
    ap = argparse.ArgumentParser(description="style-render-forge 文献库导入器")
    ap.add_argument("--file", action="append", required=True,
                    help="输入文献库文件，可重复给出以合并")
    ap.add_argument("--format", choices=["bibtex", "ris", "cnki-text"],
                    help="强制格式；缺省按扩展名自动识别")
    ap.add_argument("--out", required=True, help="输出目录（写 records.json）")
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    all_records = []
    global_warnings = []
    meta = {"sources": []}

    for fidx, path in enumerate(args.file, start=1):
        fmt = args.format or detect_format(path)
        if fmt is None:
            global_warnings.append(f"无法识别 `{path}` 的格式（扩展名），已跳过")
            continue
        with open(path, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
        sub_meta = {}
        if fmt == "bibtex":
            recs = parse_bibtex(text, global_warnings, sub_meta)
        elif fmt == "ris":
            recs = parse_ris(text, global_warnings, sub_meta, prefix=f"ris{fidx}")
        else:
            recs = parse_cnki_text(text, global_warnings, sub_meta, prefix=f"cnki{fidx}")
        meta["sources"].append({"file": os.path.basename(path), "format": fmt,
                                "count": len(recs), "meta": sub_meta})
        all_records.extend(recs)

    # 确定性：按 id 排序；重复 id 加序号后缀
    all_records.sort(key=lambda r: r["id"])
    seen = {}
    for rec in all_records:
        if rec["id"] in seen:
            seen[rec["id"]] += 1
            rec["id"] = f'{rec["id"]}~{seen[rec["id"]]}'
            rec["warnings"].append("合并后 id 冲突，已加序号后缀")
        else:
            seen[rec["id"]] = 1

    out_records = []
    for rec in all_records:
        raw_fields = rec.pop("_raw_fields", None)
        ordered = {k: rec[k] for k in RECORD_KEYS}
        if raw_fields:
            ordered["raw_fields"] = raw_fields
        out_records.append(ordered)

    payload = {
        "schema": SCHEMA,
        "generator": "import_records.py (style-render-forge)",
        "record_count": len(out_records),
        "warnings": global_warnings,
        "meta": meta,
        "records": out_records,
    }
    out_path = os.path.join(args.out, "records.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    summary = {
        "out": out_path,
        "record_count": len(out_records),
        "warning_count": len(global_warnings) + sum(len(r["warnings"]) for r in out_records),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
