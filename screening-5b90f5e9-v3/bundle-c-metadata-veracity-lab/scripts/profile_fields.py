#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""profile_fields.py — 字段画像（field profiling）

对已解析的结构化题录逐字段做可信度画像：
  * 完整率 / 空值 / 占位符（"N/A"、"."、空字符串等）识别
  * 取值域 sanity：年份范围、页码形态、DOI 形态（仅形态，不联网）
  * 语种鉴定：字符脚本 + 停用词启发式，与 case.json 的 eligible_languages 比对

本脚本只做"画像与标记"，不改写任何记录内容。

退出码：0 成功；2 运行/IO 错误；3 输入合同不满足（records 为空或非法）。
输入默认值可用参数覆盖；重复运行产出一致（幂等，输出整体重写）。
"""
import argparse
import datetime
import json
import re
import sys

PLACEHOLDERS = {"", "n/a", "na", "n.a.", ".", "-", "--", "none", "null",
                "unknown", "missing", "?", "tbd", "not available"}

YEAR_FIELDS = {"year", "publication_year", "pub_year", "pubyear"}
PAGES_FIELDS = {"pages", "page", "pagination"}
DOI_FIELDS = {"doi"}

YEAR_MIN = 1800
PAGES_RE = re.compile(r"^[A-Za-z]?\d+([-–][A-Za-z]?\d+)?$")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)

# 停用词表（小样本启发式，见 references/field_trust_model.md 的局限说明）
STOPWORDS = {
    "en": {"the", "and", "of", "in", "with", "for", "study", "analysis",
           "between", "effects", "patients"},
    "pt": {"de", "da", "do", "em", "no", "na", "uma", "com", "para", "dos"},
    "es": {"el", "la", "los", "las", "de", "en", "con", "una", "para", "del"},
    "fr": {"le", "la", "les", "des", "une", "avec", "pour", "etude", "dans"},
    "de": {"der", "die", "das", "und", "mit", "eine", "einer", "von"},
}

CJK_RE = re.compile(r"[一-鿿]")
KANA_RE = re.compile(r"[぀-ヿ]")
HANGUL_RE = re.compile(r"[가-힯]")
CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")
ARABIC_RE = re.compile(r"[؀-ۿ]")
LATIN_RE = re.compile(r"[A-Za-zÀ-ɏ]")


def is_placeholder(value):
    """空值或占位符判定。"""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in PLACEHOLDERS
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def load_records(path):
    """读取记录：JSONL / JSON 数组 / 含 records|citations|references 键的对象。"""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    stripped = text.strip()
    if not stripped:
        return []
    data = None
    if stripped[0] in "[{":
        try:
            data = json.loads(stripped)
        except ValueError:
            data = None  # 首字符像 JSON 但实为 JSONL，落回逐行解析
    if data is not None:
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = None
            for key in ("records", "citations", "references"):
                if isinstance(data.get(key), list):
                    records = data[key]
                    break
            if records is None:
                records = [data]
        else:
            raise ValueError("records 文件顶层类型非法")
    else:
        records = [json.loads(line) for line in stripped.splitlines() if line.strip()]
    out = []
    for i, rec in enumerate(records, 1):
        if not isinstance(rec, dict):
            raise ValueError("第 %d 条记录不是对象" % i)
        rec = dict(rec)
        rec.setdefault("record_id", rec.get("id") or "rec-%03d" % i)
        out.append(rec)
    return out


def load_eligible_languages(case_path):
    if not case_path:
        return []
    try:
        with open(case_path, "r", encoding="utf-8") as fh:
            case = json.load(fh)
    except (OSError, ValueError):
        return []
    langs = case.get("eligible_languages") or case.get("eligible_language") or []
    if isinstance(langs, str):
        langs = [langs]
    return [str(x).strip().lower() for x in langs]


def guess_language(text):
    """返回 (语种代码, 置信度 high|medium|low)。纯启发式，不联网。"""
    if not text:
        return ("unknown", "low")
    n_cjk = len(CJK_RE.findall(text))
    n_kana = len(KANA_RE.findall(text))
    n_hangul = len(HANGUL_RE.findall(text))
    n_cyr = len(CYRILLIC_RE.findall(text))
    n_arab = len(ARABIC_RE.findall(text))
    n_latin = len(LATIN_RE.findall(text))
    if n_kana >= 3 and n_kana >= n_latin // 4:
        return ("ja", "high")
    if n_hangul >= 3:
        return ("ko", "high")
    if n_cjk >= 3 and n_cjk > n_latin:
        return ("zh", "high")
    if n_cyr > n_latin and n_cyr >= 5:
        return ("ru", "medium")
    if n_arab > n_latin and n_arab >= 5:
        return ("ar", "medium")
    tokens = re.findall(r"[a-zà-ɏ]+", text.lower())
    if not tokens:
        return ("unknown", "low")
    best, best_hits = "en", 0
    for lang, words in STOPWORDS.items():
        hits = sum(1 for t in tokens if t in words)
        if hits > best_hits:
            best, best_hits = lang, hits
    conf = "high" if best_hits >= 3 else ("medium" if best_hits >= 1 else "low")
    return (best, conf)


def check_domain(field, value):
    """取值域 sanity；返回 issue 描述或 None。"""
    fname = field.lower()
    if fname in YEAR_FIELDS:
        if isinstance(value, int):
            year = value
        elif isinstance(value, str) and re.fullmatch(r"\d{4}", value.strip()):
            year = int(value.strip())
        else:
            return "year_not_4digit_int"
        year_max = datetime.date.today().year + 1
        if not (YEAR_MIN <= year <= year_max):
            return "year_out_of_range_%d_%d" % (YEAR_MIN, year_max)
    elif fname in PAGES_FIELDS:
        if isinstance(value, str) and not PAGES_RE.match(value.strip()):
            return "pages_odd_shape"
        if isinstance(value, (int, float)):
            return "pages_not_string"
    elif fname in DOI_FIELDS:
        if isinstance(value, str):
            v = value.strip()
            v = re.sub(r"^https?://(dx\.)?doi\.org/", "", v, flags=re.IGNORECASE)
            v = re.sub(r"^doi:\s*", "", v, flags=re.IGNORECASE)
            if not DOI_RE.match(v):
                return "doi_malformed"
        else:
            return "doi_not_string"
    return None


def profile(records, eligible):
    fields = {}
    domain_flags = {}
    languages = {}
    all_fields = sorted({f for rec in records for f in rec if f != "record_id"})
    for field in all_fields:
        stats = fields.setdefault(field, {"present": 0, "placeholder": 0,
                                          "missing": 0})
        for rec in records:
            value = rec.get(field)
            if field not in rec:
                stats["missing"] += 1
            elif is_placeholder(value):
                stats["placeholder"] += 1
            else:
                stats["present"] += 1
        total = len(records)
        stats["completeness"] = round(stats["present"] / total, 4) if total else 0.0
    for rec in records:
        rid = rec["record_id"]
        flags = []
        for field in all_fields:
            value = rec.get(field)
            if is_placeholder(value):
                continue
            issue = check_domain(field, value)
            if issue:
                flags.append({"field": field, "value": value, "issue": issue})
        if flags:
            domain_flags[rid] = flags
        text = " ".join(str(rec.get(k) or "") for k in ("title", "abstract"))
        guess, conf = guess_language(text)
        declared = rec.get("language")
        entry = {"guess": guess, "confidence": conf,
                 "declared": declared if not is_placeholder(declared) else None,
                 "eligible_languages": eligible,
                 "language_flag": False}
        if eligible and guess != "unknown" and guess not in eligible:
            entry["language_flag"] = True
        languages[rid] = entry
    return {
        "generated_by": "profile_fields.py",
        "records_total": len(records),
        "fields": {f: fields[f] for f in all_fields},
        "domain_flags": domain_flags,
        "language": languages,
        "records_with_language_flag": sorted(
            rid for rid, e in languages.items() if e["language_flag"]),
        "notes": ["画像仅做标记，不改写记录；",
                   "语种为字符脚本+停用词启发式，低置信度结果仅供人工参考。"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="字段画像：完整率/占位符/取值域/语种")
    parser.add_argument("--records", required=True, help="题录文件（JSONL 或 JSON）")
    parser.add_argument("--case", default="/input/case.json",
                        help="case.json 路径（取 eligible_languages），默认 /input/case.json")
    parser.add_argument("--work", default="/app/work", help="中间产物目录，默认 /app/work")
    args = parser.parse_args(argv)
    try:
        records = load_records(args.records)
        if not records:
            print("ERROR: 记录为空，无法画像", file=sys.stderr)
            return 3
        eligible = load_eligible_languages(args.case)
        report = profile(records, eligible)
        out_path = args.work.rstrip("/") + "/field_profile.json"
        import os
        os.makedirs(args.work, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
        print("OK: %d 条记录，%d 个字段；domain_flags=%d，language_flag=%d -> %s"
              % (report["records_total"], len(report["fields"]),
                 len(report["domain_flags"]),
                 len(report["records_with_language_flag"]), out_path))
        return 0
    except FileNotFoundError as exc:
        print("ERROR: 输入文件不存在: %s" % exc, file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # 顶层兜底：绝不以 traceback 崩溃退出
        print("ERROR: 未预期异常: %r" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
