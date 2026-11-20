#!/usr/bin/env python3
"""evidence_align.py — 命中级证据对齐工具（xlang-hit-evidence-auditor 第一阶段）。

仅使用 Python 3.8+ 标准库；确定性、离线、全程留痕。本脚本不做任何机器翻译，
也不做语义判读：它只做**表面证据对齐**——把 case.json 中的查询概念对齐到每条
候选命中记录的原文实际用词，引用原文片段并给出可回指的定位（文件＋字段/JSON
路径/行号/字符偏移），并显式标注 wording_mismatch（仅通过其他语种词形命中、
命中记录自身语种的原文用词缺位）。

功能
----
1. 读取 /input/case.json：提取 case_id、研究问题、查询概念（query_concepts /
   concepts，支持按语种给出词形表与可选 context_terms），并推断查询语种。
2. 自动发现命中记录：扫描 /input、/app/work、当前目录及 --roots 指定目录下的
   .json/.jsonl/.csv/.txt/.md 文件，异构容错解析（JSON 递归识别含
   title/abstract/body/snippet 等键的记录；JSONL 逐行；CSV 按列名映射；
   TXT/MD 整文件作为一条正文记录，行号定位）。记录自带 text_file/body_file
   指针时加载对应正文文件。
3. 表面匹配：Unicode NFKD 分解 + 去组合符（变音折叠）+ casefold（大小写折叠）
   后做子串匹配；拉丁词形要求词边界（中英混排时 CJK 字符视为天然边界，CJK
   词形不要求边界）；通过归一化索引映射把命中跨度还原为原文偏移，截取原文
   引文片段（含 ±80 字符上下文）。
4. 标注：wording_mismatch、no_surface_match、abbrev_form、short_form、
   title_only、context_terms_absent（概念定义了 context_terms 且命中窗口内
   均未出现）、secondary_source、translation_record、language_uncertain。
   语种识别为确定性字符启发式（CJK→zh；ã/õ/ç 等葡语变音→pt；否则 latin），
   与记录自报语种分列，不互相覆盖。
5. 输出 /app/work/evidence_ledger.json（逐命中台账初稿）与运行日志
   /app/work/evidence_align_log.json。

不伪造：没有表面命中的概念如实记 no_surface_match；正文不可得的记录只对其
现有字段对齐；任何推断（语种启发式、概念回退推断）都写入 uncertainty。

用法
----
    python3 evidence_align.py --case /input/case.json [--workdir /app/work] \
        [--roots dir1,dir2] [--hits file1,file2]

退出码恒为 0；真实情况看输出 JSON 的 stats/uncertainty 与日志。
"""
import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

# ----------------------------------------------------------------------------- 配置

DEFAULT_ROOTS = ["/input", "/app/work", "."]
MAX_FILE_BYTES = 40 * 1024 * 1024
MAX_FILES = 300
MAX_RECORDS_PER_FILE = 5000
MAX_MATCHES_PER_FORM_FIELD = 5
QUOTE_CONTEXT = 80          # 引文片段两端各保留的原文字符数
CONTEXT_WINDOW = 300        # context_terms 检验窗口（命中点两侧字符数）

SKIP_FILE_NAMES = {
    "case.json", "task.md", "result.json", "evidence_ledger.json",
    "backtranslation_queue.json", "audit_ledger.json", "audit_stats.json",
    "evidence_align_log.json", "risk_triage_log.json", "run_log.json",
    "verify_report.json", "readme.md", "skill.md",
}
SKIP_PREFIXES = ("audit_", "verify_", "example_")
DATA_EXTS = (".json", ".jsonl", ".ndjson", ".csv", ".txt", ".md")

TITLE_KEYS = ("title", "display_name", "paper_title", "headline")
ABSTRACT_KEYS = ("abstract", "summary", "resumo", "abstract_text")
BODY_KEYS = ("body", "fulltext", "full_text", "text", "snippet", "segment",
             "paragraph", "content", "excerpt", "pdf_text")
LANG_KEYS = ("language", "lang", "text_language", "body_language",
             "original_language", "doc_language")
VERSION_KEYS = ("version", "edition", "version_label", "version_tag",
                "translation_status", "record_version")
TYPE_KEYS = ("record_type", "type", "kind", "mention_type", "source_type")
BODY_FILE_KEYS = ("text_file", "body_file", "fulltext_file", "pdf_text_file")
ID_KEYS = ("hit_id", "record_id", "id", "uid")

CJK_RE = re.compile(r"[一-鿿㐀-䶿]")
PT_DIACRITICS = "ãõçÃÕÇáâàéêíóôúÁÂÀÉÊÍÓÔÚ"
SECONDARY_TYPES = {"secondary", "review", "citation", "citation_mention",
                   "mention", "news", "blog", "press", "commentary", "转述"}
TRANSLATION_HINTS = ("translation", "translated", "译本", "official_translation")

LANG_CODES = {"en", "pt", "zh", "es", "de", "fr", "ja", "ko", "ru", "it", "und"}

# ----------------------------------------------------------------------------- 基础工具


def is_cjk(ch):
    return bool(CJK_RE.match(ch))


def has_cjk(text):
    return bool(CJK_RE.search(text))


def normalize_with_map(text):
    """NFKD 分解 + 去组合符 + casefold；返回 (归一化串, 归一化索引->原文索引)。"""
    norm_chars, nmap = [], []
    for i, ch in enumerate(text):
        for d in unicodedata.normalize("NFKD", ch):
            if unicodedata.combining(d):
                continue
            for c in d.casefold():
                norm_chars.append(c)
                nmap.append(i)
    return "".join(norm_chars), nmap


def detect_language(text):
    """确定性字符启发式语种识别；en 实际含义为“非 CJK、无葡语变音的拉丁文本”。"""
    if not text:
        return None
    sample = text[:2000]
    if has_cjk(sample):
        return "zh"
    pt_marks = sum(1 for c in sample if c in PT_DIACRITICS)
    if pt_marks >= 2 or any(c in sample for c in "ãõÃÕçÇ"):
        return "pt"
    return "en"


def infer_form_lang(form):
    if has_cjk(form):
        return "zh"
    if any(c in form for c in PT_DIACRITICS):
        return "pt"
    if re.search(r"[A-Za-z]", form):
        return "en"
    return "und"


def is_abbrev(form):
    return (form.isascii() and re.search(r"[A-Z]", form) is not None
            and form.upper() == form and 2 <= len(form) <= 6)


def line_of(text, offset):
    return text.count("\n", 0, max(0, offset)) + 1


def find_matches(form, field_text):
    """在 field_text 中归一化匹配 form，返回原文跨度列表 [(start, end), ...]。

    拉丁词形要求词边界；中英混排时 CJK 字符视为天然边界；CJK 词形不要求边界。
    """
    ntext, nmap = normalize_with_map(field_text)
    nform = normalize_with_map(form)[0].strip()
    if not nform or not ntext:
        return []
    need_boundary = not has_cjk(form)
    out, start = [], 0
    while len(out) < MAX_MATCHES_PER_FORM_FIELD:
        idx = ntext.find(nform, start)
        if idx < 0:
            break
        start = idx + 1
        end = idx + len(nform)
        if need_boundary:
            before = ntext[idx - 1] if idx > 0 else " "
            after = ntext[end] if end < len(ntext) else " "
            before_ok = (not before.isalnum()) or is_cjk(before)
            after_ok = (not after.isalnum()) or is_cjk(after)
            if not (before_ok and after_ok):
                continue  # 子串误命中（如 method 命中 methodology），丢弃
        o_start = nmap[idx]
        o_end = nmap[min(end - 1, len(nmap) - 1)] + 1
        out.append((o_start, o_end))
    return out


def make_quote(field_text, start, end):
    lo = max(0, start - QUOTE_CONTEXT)
    hi = min(len(field_text), end + QUOTE_CONTEXT)
    snippet = field_text[lo:hi]
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(field_text) else ""
    return prefix + " ".join(snippet.split()) + suffix

# ----------------------------------------------------------------------------- 概念装载


def _forms_from_spec(spec):
    """把词形规格统一为 {lang: [form, ...]}。接受 {lang: [...]}、扁平列表、单串。"""
    forms = {}
    if isinstance(spec, str):
        forms.setdefault(infer_form_lang(spec), []).append(spec)
    elif isinstance(spec, list):
        for f in spec:
            if isinstance(f, str) and f.strip():
                forms.setdefault(infer_form_lang(f.strip()), []).append(f.strip())
    elif isinstance(spec, dict):
        for k, v in spec.items():
            lang = k.lower() if k.lower() in LANG_CODES else "und"
            vals = v if isinstance(v, list) else [v]
            for f in vals:
                if isinstance(f, str) and f.strip():
                    forms.setdefault(lang, []).append(f.strip())
    return forms


def load_concepts(case, log, uncertainty):
    raw = (case.get("query_concepts") or case.get("concepts")
           or case.get("query_concept_list") or case.get("concept_list"))
    concepts = []
    if isinstance(raw, dict):
        for label, spec in raw.items():
            concepts.append({"id": str(label), "label": str(label),
                             "forms": _forms_from_spec(spec),
                             "context_terms": []})
    elif isinstance(raw, list):
        for i, item in enumerate(raw):
            if isinstance(item, str):
                concepts.append({"id": "c%d" % (i + 1), "label": item,
                                 "forms": _forms_from_spec(item),
                                 "context_terms": []})
            elif isinstance(item, dict):
                cid = str(item.get("id") or item.get("concept_id")
                          or item.get("label") or "c%d" % (i + 1))
                spec = (item.get("forms") or item.get("surface_forms")
                        or item.get("terms")
                        or {k: v for k, v in item.items()
                            if k.lower() in LANG_CODES})
                ctx = item.get("context_terms") or item.get("context") or []
                if isinstance(ctx, str):
                    ctx = [ctx]
                concepts.append({"id": cid,
                                 "label": str(item.get("label") or cid),
                                 "forms": _forms_from_spec(spec),
                                 "context_terms": [str(t) for t in ctx]})
    concepts = [c for c in concepts if c["forms"]]
    if not concepts:
        # 回退：从研究问题文本中提取引号包裹短语作为概念词形，并如实标记
        q = (case.get("research_question") or case.get("question")
             or case.get("task") or "")
        if isinstance(q, dict):
            q = json.dumps(q, ensure_ascii=False)
        quoted = re.findall(r"[\"“「『]([^\"”」』]{2,60})[\"”」』]", str(q))
        for i, term in enumerate(quoted[:12]):
            concepts.append({"id": "q%d" % (i + 1), "label": term,
                             "forms": _forms_from_spec(term),
                             "context_terms": []})
        if concepts:
            uncertainty.append("case.json 未提供结构化 query_concepts；概念由研究问题中"
                               "的引号短语回退推断（concepts_inferred=true），覆盖可能不全")
            log.append("concepts inferred from quoted phrases in research question: %d"
                       % len(concepts))
    else:
        log.append("loaded %d query concepts from case.json" % len(concepts))
    return concepts


def query_language(case):
    q = (case.get("query_language") or case.get("question_language") or "")
    if isinstance(q, str) and q.lower() in LANG_CODES:
        return q.lower()
    text = json.dumps({k: v for k, v in case.items()
                       if k in ("research_question", "question", "task")},
                      ensure_ascii=False)
    return detect_language(text) or "und"

# ----------------------------------------------------------------------------- 命中记录发现与解析


def norm_doi(value):
    if not value:
        return None
    v = str(value).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if v.startswith(prefix):
            v = v[len(prefix):]
    return v or None


def _first_str(obj, keys):
    for k in keys:
        v = obj.get(k)
        if isinstance(v, list):
            v = v[0] if v else None
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def hit_from_record(obj, locator, base_dir, log):
    """把一个 JSON 对象/CSV 行解释为候选命中记录；不是命中则返回 None。"""
    if not isinstance(obj, dict):
        return None
    title = _first_str(obj, TITLE_KEYS)
    abstract = _first_str(obj, ABSTRACT_KEYS)
    body = _first_str(obj, BODY_KEYS)
    if not (title or abstract or body):
        return None
    body_locator = None
    body_file = _first_str(obj, BODY_FILE_KEYS)
    if body_file and not body:
        p = Path(body_file)
        if not p.is_absolute():
            p = Path(base_dir) / body_file
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
            body_locator = {"file": str(p), "pointer": "lines/1-%d" % (body.count("\n") + 1)}
        except OSError as exc:
            log.append("WARNING: body file %s unreadable for %s: %s" % (p, locator, exc))
    rec_type = (_first_str(obj, TYPE_KEYS) or "").lower()
    version = _first_str(obj, VERSION_KEYS)
    hit_id = _first_str(obj, ID_KEYS) or norm_doi(obj.get("doi") or obj.get("DOI"))
    return {
        "hit_id": hit_id,   # 稍后统一补缺
        "title": title or "",
        "fields": {k: v for k, v in (("title", title), ("abstract", abstract),
                                     ("body", body)) if v},
        "field_locators": ({"body": body_locator} if body_locator else {}),
        "language_declared": (_first_str(obj, LANG_KEYS) or "").lower() or None,
        "version": version,
        "doi": norm_doi(obj.get("doi") or obj.get("DOI")),
        "source": _first_str(obj, ("source", "database", "provenance",
                                   "retrieved_from", "provider")),
        "record_type": rec_type or None,
        "locator": locator,
    }


def is_hit_record(obj):
    return isinstance(obj, dict) and any(
        isinstance(obj.get(k), (str, list)) and obj.get(k)
        for k in TITLE_KEYS + ABSTRACT_KEYS + BODY_KEYS)


def walk_json(obj, path, file_path, hits, log, depth=0):
    if depth > 12 or len(hits) >= MAX_RECORDS_PER_FILE:
        return
    if isinstance(obj, dict):
        if is_hit_record(obj):
            rec = hit_from_record(obj, {"file": file_path, "pointer": path or "$"},
                                  str(Path(file_path).parent), log)
            if rec:
                hits.append(rec)
            return
        for k, v in obj.items():
            walk_json(v, "%s/%s" % (path, k), file_path, hits, log, depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:20000]):
            walk_json(v, "%s/%d" % (path, i), file_path, hits, log, depth + 1)


def parse_csv(path, hits, log):
    file_path = str(path)
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;") \
                if sample.strip() else csv.excel
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        if not reader.fieldnames:
            return
        for i, row in enumerate(reader):
            if i >= MAX_RECORDS_PER_FILE:
                break
            rec = hit_from_record({k: v for k, v in row.items() if v},
                                  {"file": file_path, "pointer": "row/%d" % (i + 2)},
                                  str(path.parent), log)
            if rec:
                hits.append(rec)


def parse_text_doc(path, hits, log):
    """TXT/MD（例如 pdf-text-tool 的解析产物）整文件作为一条正文命中记录。"""
    file_path = str(path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.append("WARNING: cannot read %s: %s" % (file_path, exc))
        return
    if len(text.strip()) < 20:
        return
    first_line = next((l.strip().lstrip("#").strip()
                       for l in text.splitlines() if l.strip()), path.stem)
    n_lines = text.count("\n") + 1
    hits.append({
        "hit_id": None,
        "title": first_line[:120],
        "fields": {"title": first_line[:300], "body": text},
        "field_locators": {"body": {"file": file_path,
                                    "pointer": "lines/1-%d" % n_lines}},
        "language_declared": None,
        "version": None,
        "doi": norm_doi((re.search(r"10\.\d{4,9}/[^\s\"',}\]]+", text) or [None])[0]
                        if re.search(r"10\.\d{4,9}/[^\s\"',}\]]+", text) else None),
        "source": file_path,
        "record_type": "fulltext_document",
        "locator": {"file": file_path, "pointer": "lines/1-%d" % n_lines},
    })


def discover_files(roots, explicit_hits, log):
    seen, out = set(), []
    candidates = [Path(h) for h in explicit_hits if h]
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        stack = [(root, 0)]
        while stack and len(out) + len(candidates) < MAX_FILES:
            node, depth = stack.pop()
            try:
                if node.is_dir():
                    if node.name.startswith(".") or node.name in (
                            "node_modules", "__pycache__", "venv", ".venv"):
                        continue
                    if depth <= 5:
                        for child in sorted(node.iterdir()):
                            stack.append((child, depth + 1))
                elif node.suffix.lower() in DATA_EXTS:
                    candidates.append(node)
            except (OSError, PermissionError):
                continue
    files = []
    for node in candidates:
        try:
            name = node.name.lower()
            rp = str(node.resolve())
            if (rp in seen or name in SKIP_FILE_NAMES
                    or any(name.startswith(p) for p in SKIP_PREFIXES)
                    or node.stat().st_size > MAX_FILE_BYTES):
                continue
            seen.add(rp)
            files.append(node)
        except OSError:
            continue
    log.append("discovered %d candidate data files under roots %s"
               % (len(files), [str(r) for r in roots]))
    return files


def load_hits(files, log, uncertainty):
    hits = []
    for path in files:
        suffix = path.suffix.lower()
        file_path = str(path)
        try:
            if suffix == ".json":
                walk_json(json.loads(path.read_text(encoding="utf-8",
                                                    errors="replace")),
                          "$", file_path, hits, log)
            elif suffix in (".jsonl", ".ndjson"):
                with open(path, encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            walk_json(json.loads(line), "$/%d" % i,
                                      file_path, hits, log)
                        except json.JSONDecodeError:
                            log.append("bad JSONL line %s:%d" % (file_path, i + 1))
            elif suffix == ".csv":
                parse_csv(path, hits, log)
            elif suffix in (".txt", ".md"):
                parse_text_doc(path, hits, log)
        except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
            log.append("skipped %s: %s" % (file_path, exc))
            uncertainty.append("文件解析失败被跳过: %s (%s)" % (file_path, exc))
    # 统一补缺 hit_id 并去重（按 文件+指针）
    seen_loc, unique = set(), []
    for rec in hits:
        sig = (rec["locator"]["file"], rec["locator"]["pointer"])
        if sig in seen_loc:
            continue
        seen_loc.add(sig)
        unique.append(rec)
    for i, rec in enumerate(unique):
        if not rec["hit_id"]:
            rec["hit_id"] = "hit-%04d" % (i + 1)
    log.append("parsed %d hit records from %d files" % (len(unique), len(files)))
    return unique

# ----------------------------------------------------------------------------- 证据对齐


def align_hit(rec, concepts, query_lang):
    """对一条命中记录执行概念对齐，返回台账条目。"""
    field_texts = rec["fields"]
    probe = field_texts.get("abstract") or field_texts.get("body") \
        or field_texts.get("title") or ""
    lang_detected = detect_language(probe)
    hit_lang = rec["language_declared"] or lang_detected

    hit_flags = []
    if rec["record_type"] and any(t in rec["record_type"] for t in SECONDARY_TYPES):
        hit_flags.append("secondary_source")
    version_l = (rec["version"] or "").lower()
    if any(h in version_l for h in TRANSLATION_HINTS) \
            or (rec["record_type"] and any(h in rec["record_type"]
                                           for h in TRANSLATION_HINTS)):
        hit_flags.append("translation_record")
    if not rec["language_declared"]:
        hit_flags.append("language_uncertain")

    concept_evidence = []
    for concept in concepts:
        ev = {"concept_id": concept["id"], "label": concept["label"],
              "matched": False, "matched_forms": [],
              "matched_langs": [], "expected_langs": sorted(concept["forms"]),
              "wording_mismatch": False, "no_surface_match": True, "flags": []}
        ctx_terms = concept.get("context_terms") or []
        ctx_hit_any = False
        for lang, forms in sorted(concept["forms"].items()):
            for form in forms:
                for field, text in field_texts.items():
                    for (s, e) in find_matches(form, text):
                        # context_terms 窗口检验
                        if ctx_terms:
                            lo = max(0, s - CONTEXT_WINDOW)
                            hi = min(len(text), e + CONTEXT_WINDOW)
                            nwin = normalize_with_map(text[lo:hi])[0]
                            if any(normalize_with_map(t)[0].strip()
                                   and normalize_with_map(t)[0].strip() in nwin
                                   for t in ctx_terms):
                                ctx_hit_any = True
                        entry = {
                            "form": form, "form_lang": lang, "field": field,
                            "quote": field_texts[field][s:e],
                            "quote_context": make_quote(field_texts[field], s, e),
                            "span": [s, e], "line": line_of(text, s),
                        }
                        floc = rec["field_locators"].get(field)
                        entry["locator"] = floc or rec["locator"]
                        if is_abbrev(form):
                            entry["abbrev_form"] = True
                        nform_len = len(normalize_with_map(form)[0].strip())
                        if nform_len <= 3 and not has_cjk(form):
                            entry["short_form"] = True
                        ev["matched_forms"].append(entry)
        if ev["matched_forms"]:
            ev["matched"] = True
            ev["no_surface_match"] = False
            ev["matched_langs"] = sorted({m["form_lang"]
                                          for m in ev["matched_forms"]})
            if all(m.get("abbrev_form") for m in ev["matched_forms"]):
                ev["flags"].append("abbrev_form")
            if any(m.get("short_form") for m in ev["matched_forms"]):
                ev["flags"].append("short_form")
            if {m["field"] for m in ev["matched_forms"]} == {"title"}:
                ev["flags"].append("title_only")
            if ctx_terms and not ctx_hit_any:
                ev["flags"].append("context_terms_absent")
            # wording_mismatch：命中记录语种在概念词形表中有对应词形，
            # 但没有任何该语种词形命中，仅靠其他语种（译文）词形命中
            if (hit_lang and hit_lang in concept["forms"]
                    and hit_lang not in ev["matched_langs"]):
                ev["wording_mismatch"] = True
                ev["flags"].append("wording_mismatch")
                ev["wording_mismatch_detail"] = (
                    "命中记录语种为 %s，概念词形表提供了 %s 语词形 %s，但原文未命中；"
                    "仅通过 %s 语词形 %s 命中（疑似译文词面命中）"
                    % (hit_lang, hit_lang, concept["forms"][hit_lang],
                       "/".join(ev["matched_langs"]),
                       [m["form"] for m in ev["matched_forms"][:3]]))
        concept_evidence.append(ev)

    return {
        "hit_id": rec["hit_id"],
        "title": rec["title"],
        "doi": rec["doi"],
        "source": rec["source"],
        "version": rec["version"],
        "record_type": rec["record_type"],
        "language": rec["language_declared"],
        "language_detected": lang_detected,
        "language_effective": hit_lang,
        "locator": rec["locator"],
        "fields_present": sorted(field_texts),
        "flags": hit_flags,
        "concept_evidence": concept_evidence,
    }

# ----------------------------------------------------------------------------- 主流程


def main():
    ap = argparse.ArgumentParser(
        description="命中级证据对齐：把查询概念对齐到每条命中记录的原文实际用词，"
                    "引用原文片段并标注 wording_mismatch。仅标准库、离线。")
    ap.add_argument("--case", default="/input/case.json", help="case.json 路径")
    ap.add_argument("--workdir", default="/app/work", help="工作目录（输出台账与日志）")
    ap.add_argument("--roots", default=None,
                    help="逗号分隔的额外命中记录搜索根目录")
    ap.add_argument("--hits", default=None,
                    help="逗号分隔的显式命中记录文件（跳过自动发现时可用）")
    args = ap.parse_args()

    started = time.time()
    work_dir = Path(args.workdir)
    work_dir.mkdir(parents=True, exist_ok=True)
    log = ["evidence_align started " + time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                     time.gmtime())]
    uncertainty = []

    # 1. case.json
    case_path = Path(args.case)
    case, case_id = {}, "unknown_case"
    try:
        case = json.loads(case_path.read_text(encoding="utf-8"))
        case_id = case.get("case_id") or case.get("id") or "unknown_case"
    except (OSError, json.JSONDecodeError) as exc:
        log.append("FATAL: cannot read case file %s: %s" % (args.case, exc))
        uncertainty.append("case.json 不可读：%s；概念为空，仅做记录扫描" % exc)
    q_lang = query_language(case) if case else "und"
    concepts = load_concepts(case, log, uncertainty) if case else []
    if case and not concepts:
        uncertainty.append("未能从 case.json 获得任何查询概念；所有命中将记为无概念可对齐")

    # 2. 命中记录发现与解析
    roots = [Path(r) for r in DEFAULT_ROOTS]
    if case_path.exists():
        roots.insert(0, case_path.resolve().parent)
    if args.roots:
        roots += [Path(r.strip()) for r in args.roots.split(",") if r.strip()]
    explicit = [h.strip() for h in (args.hits or "").split(",") if h.strip()]
    files = discover_files(roots, explicit, log)
    hits = load_hits(files, log, uncertainty)
    if not hits:
        uncertainty.append("未发现任何候选命中记录文件（.json/.jsonl/.csv/.txt/.md）")

    # 3. 逐命中对齐
    entries = [align_hit(rec, concepts, q_lang) for rec in hits]

    # 4. 汇总与输出
    n_matched = sum(1 for e in entries
                    if any(c["matched"] for c in e["concept_evidence"]))
    n_wm = sum(1 for e in entries
               if any(c["wording_mismatch"] for c in e["concept_evidence"]))
    n_nsm = sum(1 for e in entries
                if e["concept_evidence"]
                and all(c["no_surface_match"] for c in e["concept_evidence"]))
    ledger = {
        "skill": "xlang-hit-evidence-auditor",
        "stage": "evidence_align",
        "case_id": case_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "query_language": q_lang,
        "concepts": [{"id": c["id"], "label": c["label"], "forms": c["forms"],
                      "context_terms": c.get("context_terms") or []}
                     for c in concepts],
        "hits": entries,
        "stats": {
            "n_hits": len(entries),
            "n_concepts": len(concepts),
            "n_hits_with_any_match": n_matched,
            "n_hits_wording_mismatch": n_wm,
            "n_hits_no_surface_match_all": n_nsm,
            "n_files_scanned": len(files),
        },
        "sources": [{"file": str(f)} for f in files],
        "uncertainty": uncertainty,
    }
    (work_dir / "evidence_ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    log.append("finished in %.1fs: %d hits, %d concepts, %d wording_mismatch, %d no_match"
               % (time.time() - started, len(entries), len(concepts), n_wm, n_nsm))
    (work_dir / "evidence_align_log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "ledger": str(work_dir / "evidence_ledger.json"),
                      "hits": len(entries), "concepts": len(concepts),
                      "wording_mismatch_hits": n_wm,
                      "no_match_hits": n_nsm}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
