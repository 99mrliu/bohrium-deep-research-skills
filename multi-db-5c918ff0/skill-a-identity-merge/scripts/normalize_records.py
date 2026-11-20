#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""normalize_records.py — 把各来源原始响应解析为统一中间格式 normalized.jsonl。

输入：parse_case.py 的 case_summary.json（--summary），或显式 --files 列表
（此时做轻量内容嗅探）。仅处理记录型材料（crossref/europepmc/publisher/
recordlist/jsonl/csv）；reference_graph / import_state / unknown 跳过并留痕。

每行输出（JSONL）：
  source            嗅探来源类型
  record_uid        来源+文件+item 索引，如 "crossref:raw_crossref.json:0"
  identifiers       {doi, pmid, pmcid}：归一值 + 各自 status
  title_raw / title_norm   原标题 / 归一题名（小写、去 HTML、去标点、去停用词、折空白）
  year              4 位年份（issued/published/date 多字段回退）或 null
  authors_raw       原始作者载荷（list 或 string 原样留痕）
  authors_norm      [{family, given}]，兼容 "Family, Given" 与 "Surname I." 两种串格式
  container_raw / container_norm
  volume / issue / pages / type / abstract / pub_date_iso
  field_status      {field: present|unknown|not_provided}
  raw_excerpt       原始响应中该 item 的路径定位 + 截断片段
  parse_warnings    解析降级留痕

字段缺失三级语义（与 references/merge_policy.md 一致）：
  present       字段键存在且值非空可用
  unknown       来源给出了字段键但为空或无法解析
  not_provided  该来源该条记录根本没有此字段键
（聚合级 missing = 所有来源均 not_provided，由 merge_records.py 计算。）

退出码：0=成功；2=输入缺失或未提取到任何记录（材料不足）；3=输入 JSON 非法。
顶层兜底：未预期异常 → exit 2，绝不 crash。

用法：
  python3 normalize_records.py --summary /app/work/case_summary.json \
      --out /app/work/normalized.jsonl
"""
import argparse
import csv
import json
import os
import re
import sys

STOPWORDS = set(("a an the of for and or in on to with by from at as is are was "
                 "were via using based its it be been into over under between "
                 "among through per et al").split())

RECORD_KINDS = ("crossref", "europepmc", "publisher", "recordlist", "jsonl", "csv")

# 通用别名表（publisher/recordlist/jsonl/csv 等未知 schema 的浅层键匹配）
ALIASES = {
    "doi": ["doi", "DOI", "Doi"],
    "pmid": ["pmid", "PMID", "pubmed_id", "pubmedId"],
    "pmcid": ["pmcid", "PMCID", "pmc_id"],
    "title": ["title", "headline", "name", "article_title"],
    "authors": ["author", "authors", "authorString", "author_string",
                "creators", "contributors"],
    "container": ["container-title", "container_title", "journal",
                  "journal_title", "journalTitle", "source", "venue"],
    "volume": ["volume", "vol"],
    "issue": ["issue", "number"],
    "pages": ["page", "pages", "pageInfo", "pagination"],
    "type": ["type", "pubtype", "pub_type", "publication_type"],
    "abstract": ["abstract", "abstractText", "abstract_text",
                 "description", "summary"],
    "date": ["issued", "published", "published-print", "published-online",
             "created", "date", "pubDate", "pub_date", "publication_date",
             "firstPublicationDate", "electronicPublicationDate",
             "printPublicationDate", "dateOfCompletion"],
    "year": ["year", "pubYear", "pub_year", "yearOfPublication"],
}
FIELDS = ["title", "year", "authors", "container", "volume", "issue",
          "pages", "type", "abstract", "pub_date_iso"]
ID_FIELDS = ["doi", "pmid", "pmcid"]


# ---------------- 文本与标识符归一 ----------------

def strip_html(s):
    return re.sub(r"<[^>]+>", " ", s)


def clean_text(s):
    return re.sub(r"\s+", " ", strip_html(str(s))).strip()


def norm_title(s):
    t = strip_html(str(s)).lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    toks = [w for w in t.split() if w and w not in STOPWORDS]
    return " ".join(toks)


def norm_doi(v):
    if v is None:
        return None
    d = str(v).strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    d = re.sub(r"^doi:\s*", "", d)
    d = re.sub(r"\s+", "", d)
    return d or None


def norm_pmid(v):
    if v is None:
        return None
    m = re.sub(r"\D", "", str(v))
    return m or None


def norm_pmcid(v):
    if v is None:
        return None
    s = re.sub(r"\s+", "", str(v).strip().upper())
    if re.fullmatch(r"PMC\d+", s):
        return s
    digits = re.sub(r"\D", "", s)
    return ("PMC" + digits) if digits else None


def extract_year(*vals):
    for v in vals:
        if v is None:
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            if 1500 <= v <= 2100:
                return v
            continue
        m = re.search(r"(1[5-9]\d{2}|20\d{2})", str(v))
        if m:
            return int(m.group(1))
    return None


def extract_date_iso(*vals):
    """Crossref date-parts 或 ISO-ish 字符串 → YYYY[-MM[-DD]]；不可得返回 None。"""
    for v in vals:
        if v is None:
            continue
        if isinstance(v, dict):
            dp = v.get("date-parts")
            if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
                parts = [p for p in dp[0] if isinstance(p, int) and not isinstance(p, bool)]
                if parts:
                    out = "%04d" % parts[0]
                    if len(parts) > 1:
                        out += "-%02d" % parts[1]
                    if len(parts) > 2:
                        out += "-%02d" % parts[2]
                    return out
            continue
        s = str(v).strip()
        m = re.match(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", s)
        if m:
            out = m.group(1)
            if m.group(2):
                out += "-%02d" % int(m.group(2))
            if m.group(3):
                out += "-%02d" % int(m.group(3))
            return out
        m = re.search(r"(1[5-9]\d{2}|20\d{2})", s)
        if m:
            return m.group(1)
    return None


# ---------------- 作者解析 ----------------

def _looks_initials(tok):
    return bool(re.fullmatch(r"[A-Z]{1,3}\.?|[A-Z](\.[A-Z]\.?)+", tok))


def _parse_single_name(chunk):
    """单个作者块：'Family, Given' 或 'Surname FM' 或 'van der Berg J'。"""
    chunk = chunk.strip().rstrip(".")
    if not chunk:
        return None
    if "," in chunk:
        fam, _, giv = chunk.partition(",")
        fam, giv = fam.strip(), giv.strip()
        if fam:
            return {"family": fam, "given": giv}
    toks = chunk.split()
    if len(toks) == 1:
        return {"family": toks[0], "given": ""}
    split_at = None
    for i in range(1, len(toks)):
        if _looks_initials(toks[i]):
            split_at = i
            break
    if split_at is None:
        # 无首字母缩写模式：末词视为名不足为据，整体首词为姓（保守）
        return {"family": toks[0], "given": " ".join(toks[1:])}
    return {"family": " ".join(toks[:split_at]),
            "given": " ".join(toks[split_at:])}


def parse_author_string(s):
    """作者串 → [{family, given}]。兼容：
    'Zhang W, Li N'（EuropePMC 'Surname Initials, ...'）、
    'Chen, Jing; Wang, Lin'（'Family, Given' 分号分隔）、
    'Garcia, Maria'（单人 'Family, Given'）。
    """
    s = clean_text(s)
    if not s:
        return []
    out = []
    if ";" in s:
        chunks = [c for c in s.split(";") if c.strip()]
        for c in chunks:
            a = _parse_single_name(c)
            if a:
                out.append(a)
        return out
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) == 2 and not _looks_initials(parts[-1].split()[-1]) \
            and len(parts[0].split()) >= 1 and len(parts[1].split()) == 1 \
            and not _looks_initials(parts[1]):
        # 单人 "Family, Given"
        return [{"family": parts[0], "given": parts[1]}]
    # EuropePMC 风格："Zhang W, Li N" 或混合：逐段按 'Surname Initials' 解析
    for p in parts:
        a = _parse_single_name(p)
        if a:
            out.append(a)
    return out


def parse_authors_loose(raw, warns):
    """作者载荷可为 dict/list/str 变体，统一为 [{family, given}]。"""
    out = []
    if raw is None:
        return out
    if isinstance(raw, dict):
        raw = [raw]
    if isinstance(raw, str):
        return parse_author_string(raw)
    if not isinstance(raw, list):
        warns.append("authors_unexpected_type: %s" % type(raw).__name__)
        return out
    for a in raw:
        if isinstance(a, dict):
            fam = a.get("family") or a.get("last") or a.get("surname") \
                or a.get("lastName") or a.get("lastname")
            giv = a.get("given") or a.get("first") or a.get("fore") \
                or a.get("firstName") or a.get("firstname") or a.get("initials")
            if fam:
                out.append({"family": clean_text(fam),
                            "given": clean_text(giv) if giv else ""})
            elif a.get("name"):
                out.extend(parse_author_string(str(a["name"])))
            else:
                warns.append("author_dict_no_name_keys: %s"
                             % sorted(a.keys())[:6])
        elif isinstance(a, str):
            out.extend(parse_author_string(a))
    return out


# ---------------- 记录提取 ----------------

def _candidate_dicts(item):
    """浅层候选 dict：自身 + journalInfo + journalInfo.journal（EuropePMC）。"""
    cands = [item]
    ji = item.get("journalInfo") if isinstance(item, dict) else None
    if isinstance(ji, dict):
        cands.append(ji)
        if isinstance(ji.get("journal"), dict):
            cands.append(ji["journal"])
    return cands


def grab(item, field):
    """按别名表在候选 dict 中找 (key_present, value)。"""
    for cand in _candidate_dicts(item):
        if not isinstance(cand, dict):
            continue
        for k in ALIASES.get(field, []):
            if k in cand:
                return True, cand[k]
    return False, None


def fstatus(key_present, value):
    if not key_present:
        return "not_provided"
    if value in (None, "", [], {}):
        return "unknown"
    return "present"


def first_str(v):
    """list/dict 变体取第一个非空字符串。"""
    if isinstance(v, list):
        for x in v:
            if isinstance(x, str) and x.strip():
                return x
        return None
    if isinstance(v, str):
        return v
    return None


def build_record(source, fname, idx, item):
    warns = []
    rec = {"source": source,
           "record_uid": "%s:%s:%d" % (source, fname, idx),
           "identifiers": {}, "title_raw": None, "title_norm": "",
           "year": None, "authors_raw": None, "authors_norm": [],
           "container_raw": None, "container_norm": "",
           "volume": None, "issue": None, "pages": None, "type": None,
           "abstract": None, "pub_date_iso": None,
           "field_status": {}, "raw_excerpt": "", "parse_warnings": warns}

    # 标识符
    for fid in ID_FIELDS:
        kp, v = grab(item, fid)
        norm = {"doi": norm_doi, "pmid": norm_pmid,
                "pmcid": norm_pmcid}[fid](v)
        st = fstatus(kp, v)
        if kp and v not in (None, "") and not norm:
            st = "unknown"
            warns.append("%s_unparseable: %r" % (fid, str(v)[:60]))
        rec["identifiers"][fid] = {"value": norm, "status": st}

    # 题名
    kp, v = grab(item, "title")
    title = first_str(v)
    if title and strip_html(title) != title:
        warns.append("html_stripped_in_title")
    rec["title_raw"] = clean_text(title) if title else None
    rec["title_norm"] = norm_title(title) if title else ""
    rec["field_status"]["title"] = fstatus(kp, title)

    # 作者
    kp, v = grab(item, "authors")
    rec["authors_raw"] = v if isinstance(v, (list, str)) else (
        json.dumps(v, ensure_ascii=False)[:200] if v is not None else None)
    rec["authors_norm"] = parse_authors_loose(v, warns)
    st = fstatus(kp, v)
    if st == "present" and not rec["authors_norm"]:
        st = "unknown"
        warns.append("authors_present_but_unparsed")
    rec["field_status"]["authors"] = st

    # 容器（刊名）
    kp, v = grab(item, "container")
    cont = first_str(v)
    if cont is None and isinstance(v, dict):
        cont = first_str(v.get("title"))
    rec["container_raw"] = clean_text(cont) if cont else None
    rec["container_norm"] = re.sub(r"\s+", " ",
                                   re.sub(r"[^a-z0-9]+", " ",
                                          (cont or "").lower())).strip()
    rec["field_status"]["container"] = fstatus(kp, cont)

    # 卷期页/类型/摘要
    for f in ("volume", "issue", "pages", "type"):
        kp, v = grab(item, f)
        val = first_str(v)
        if val is None and isinstance(v, (int,)) and not isinstance(v, bool):
            val = str(v)
        if f == "pages" and val:
            val = val.replace("–", "-").replace("—", "-")  # 破折号归一
        rec[f] = clean_text(val) if val else None
        rec["field_status"][f] = fstatus(kp, v if v not in (None, "") else val)

    kp, v = grab(item, "abstract")
    abst = first_str(v)
    if abst:
        abst = clean_text(abst)
    rec["abstract"] = abst or None
    rec["field_status"]["abstract"] = fstatus(kp, v)

    # 日期与年份（多字段回退）
    date_kp, date_v = grab(item, "date")
    _, year_v = grab(item, "year")
    iso = extract_date_iso(date_v, year_v)
    rec["pub_date_iso"] = iso
    rec["field_status"]["pub_date_iso"] = "present" if iso else (
        "unknown" if (date_kp and date_v not in (None, "")) else "not_provided")
    rec["year"] = extract_year(iso, year_v, date_v)
    rec["field_status"]["year"] = "present" if rec["year"] else (
        "unknown" if (date_kp or year_v not in (None, "")) else "not_provided")
    if rec["year"] is None and (date_kp or year_v not in (None, "")):
        warns.append("year_unparseable: date=%r year=%r"
                     % (str(date_v)[:40], str(year_v)[:40]))

    snippet = ""
    try:
        snippet = json.dumps(item, ensure_ascii=False)[:160]
    except (TypeError, ValueError):
        snippet = str(item)[:160]
    rec["raw_excerpt"] = "%s#item[%d] | %s" % (fname, idx, snippet)
    return rec


# ---------------- item 枚举 ----------------

def enumerate_items(source, obj, raw_text, warns):
    """按嗅探类型从已解析对象枚举 item dict 列表。"""
    if source == "crossref":
        msg = obj.get("message") if isinstance(obj, dict) else None
        if isinstance(msg, dict) and isinstance(msg.get("items"), list):
            return [it for it in msg["items"] if isinstance(it, dict)]
        if isinstance(msg, dict) and (msg.get("DOI") or msg.get("title")):
            return [msg]
        warns.append("crossref_shape_unrecognized")
        return []
    if source == "europepmc":
        rl = obj.get("resultList") if isinstance(obj, dict) else None
        if isinstance(rl, dict) and isinstance(rl.get("result"), list):
            return [it for it in rl["result"] if isinstance(it, dict)]
        if isinstance(obj, dict) and (obj.get("title") or obj.get("pmid")):
            return [obj]
        warns.append("europepmc_shape_unrecognized")
        return []
    if source == "csv":
        rows = []
        try:
            reader = csv.DictReader(raw_text.splitlines())
            for row in reader:
                rows.append({k: v for k, v in row.items() if k})
        except csv.Error as e:
            warns.append("csv_parse_error: %s" % e)
        return rows
    if source == "jsonl":
        rows = []
        for ln, line in enumerate(raw_text.splitlines()):
            if not line.strip():
                continue
            try:
                it = json.loads(line)
                if isinstance(it, dict):
                    rows.append(it)
            except json.JSONDecodeError:
                warns.append("jsonl_line_%d_decode_error" % ln)
        return rows
    # publisher / recordlist：宽容枚举
    if isinstance(obj, list):
        return [it for it in obj if isinstance(it, dict)]
    if isinstance(obj, dict):
        for lk in ("records", "items", "results", "data", "entries", "result"):
            if isinstance(obj.get(lk), list):
                return [it for it in obj[lk] if isinstance(it, dict)]
        if obj.get("title") or obj.get("doi") or obj.get("DOI"):
            return [obj]
    warns.append("%s_shape_unrecognized" % source)
    return []


def sniff_light(path):
    """--files 模式下的轻量嗅探（与 parse_case 规则子集一致）。"""
    base = os.path.basename(path).lower()
    ext = os.path.splitext(base)[1]
    if ext in (".csv", ".tsv"):
        return "csv"
    if ext in (".jsonl", ".ndjson"):
        return "jsonl"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            obj = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return "unknown"
    if isinstance(obj, dict):
        msg = obj.get("message")
        if isinstance(msg, dict) and ("items" in msg or "DOI" in msg):
            return "crossref"
        if isinstance(obj.get("resultList"), dict):
            return "europepmc"
    if isinstance(obj, (dict, list)):
        if "publisher" in base or "press" in base:
            return "publisher"
        return "recordlist"
    return "unknown"


def run(args):
    jobs = []  # (source, path)
    if args.files:
        for p in args.files:
            if not os.path.isfile(p):
                print("WARN: 材料文件不存在，跳过: %s" % p, file=sys.stderr)
                continue
            st = sniff_light(p)
            if st in RECORD_KINDS:
                jobs.append((st, p))
            else:
                print("WARN: %s 轻量嗅探为 %s，跳过（不解析非记录型材料）"
                      % (p, st), file=sys.stderr)
    else:
        if not os.path.isfile(args.summary):
            print("ERROR: case_summary 不存在（材料不足）: %s" % args.summary,
                  file=sys.stderr)
            return 2
        try:
            with open(args.summary, "r", encoding="utf-8") as f:
                summary = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print("ERROR: case_summary 非法（校验失败）: %s" % e, file=sys.stderr)
            return 3
        for m in summary.get("materials") or []:
            st = m.get("sniff_type")
            p = m.get("path")
            if st in RECORD_KINDS and p:
                jobs.append((st, p))
            elif st in ("reference_graph", "import_state"):
                print("INFO: 跳过非记录型材料 %s (%s)"
                      % (os.path.basename(p or "?"), st), file=sys.stderr)
    if not jobs:
        print("ERROR: 没有可处理的记录型材料（材料不足，诚实降级）。",
              file=sys.stderr)
        return 2

    records, skipped = [], []
    for source, path in jobs:
        fname = os.path.basename(path)
        fw = []
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                raw_text = f.read()
        except OSError as e:
            skipped.append({"path": path, "reason": "read_error: %s" % e})
            continue
        obj = None
        if source not in ("csv", "jsonl"):
            try:
                obj = json.loads(raw_text)
            except json.JSONDecodeError as e:
                skipped.append({"path": path,
                                "reason": "json_decode_error: %s" % e})
                continue
        items = enumerate_items(source, obj, raw_text, fw)
        if not items:
            skipped.append({"path": path,
                            "reason": "no_items_extracted; warnings=%s" % fw})
        for idx, it in enumerate(items):
            try:
                records.append(build_record(source, fname, idx, it))
            except Exception as e:  # 单条失败不拖垮整文件
                skipped.append({"path": path, "reason":
                                "item_%d_build_error: %r" % (idx, e)})
    if not records:
        print("ERROR: 全部材料均未提取到记录（材料不足，诚实降级）。",
              file=sys.stderr)
        return 2

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("OK: normalized.jsonl 已写出 -> %s (记录=%d, 材料=%d, 降级跳过=%d)"
          % (args.out, len(records), len(jobs), len(skipped)))
    for s in skipped:
        print("WARN: skip %s: %s" % (s["path"], s["reason"]), file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="各来源原始响应 -> 统一中间格式 normalized.jsonl（exit 0/2/3）。")
    ap.add_argument("--summary", default="/app/work/case_summary.json",
                    help="case_summary.json 路径（默认）；与 --files 二选一")
    ap.add_argument("--files", nargs="*", default=None,
                    help="显式材料文件列表（轻量嗅探，绕过 case_summary）")
    ap.add_argument("--out", default="/app/work/normalized.jsonl", help="输出路径")
    args = ap.parse_args()
    try:
        return run(args)
    except Exception as e:
        print("ERROR: normalize_records 未预期异常（降级 exit 2）: %r" % e,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
