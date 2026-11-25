#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crosscheck.py — 快照元数据与文档正文的交叉核对（provenance ledger 第二步）。

用法:
    python3 crosscheck.py --workdir /app/work

行为:
    - 读取 workdir/manifest.json（由 fingerprint.py 生成）。
    - 从每个快照 JSON 中防御式提取元数据记录（Crossref message / EuropePMC resultList）。
    - 对每个文本层文件（txt/md 直接读；pdf 尝试 subprocess 调 pdftotext -layout，
      不可用或失败则该文件判 unverifiable）提取正文。
    - 归一化后逐对比较: title_exact / title_fuzzy(token Jaccard ≥ 0.8) /
      year_match / doi_in_text / first_author_surname_in_text。
    - 记录级检测: 重复记录（归一化标题相同）、版本冲突（同 DOI 不同年份或类型）。
    - 每个 源对(source pair) 给出判定: verified / mismatch(列出字段) / unverifiable(原因)。
    - 写出 workdir/verification.json 和 workdir/verification_summary.md。

退出码: 0 正常（包括部分文件无法核对）; 1 manifest 缺失/损坏; 2 参数用法错误。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

FUZZY_THRESHOLD = 0.8
MAX_TEXT_CHARS = 200_000  # 防御: 截断超长文本，避免性能问题


# ---------------------------------------------------------------- 归一化
def normalize(text):
    """NFKC → casefold → 去标点 → 压缩空白。详见 references/veracity_rules.md"""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", str(text))
    t = t.casefold()
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def tokens(text):
    return set(normalize(text).split())


def jaccard(a_tokens, b_tokens):
    if not a_tokens or not b_tokens:
        return 0.0
    inter = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)
    return inter / union if union else 0.0


DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s\"<>]+", re.IGNORECASE)


def strip_doi_url(text):
    """年份检索前剥离 DOI/URL，避免 DOI 内嵌年份造成假命中。"""
    t = DOI_RE.sub(" ", text or "")
    t = URL_RE.sub(" ", t)
    return t


def best_line_jaccard(title_token_set, raw_text):
    """模糊标题匹配: 标题 token 集 与 每一行 token 集 的 Jaccard 最大值。

    与"标题 vs 全文"的 Jaccard 不同，逐行比较对论文标题行（标题独占一行）
    给出有意义的高分，避免被全文海量 token 稀释。
    """
    best = 0.0
    for line in (raw_text or "").splitlines():
        lt = tokens(line)
        if not lt:
            continue
        s = jaccard(title_token_set, lt)
        if s > best:
            best = s
    return best


# ---------------------------------------------------------------- 防御式取值
def first_str(value):
    """从 str / list / None 中取第一个非空字符串。"""
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        for v in value:
            s = first_str(v)
            if s:
                return s
    return ""


def dget(obj, *keys):
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


# ---------------------------------------------------------------- 快照记录提取
def extract_crossref_records(data):
    records = []
    msg = data.get("message")
    if not isinstance(msg, dict):
        return records
    items = msg.get("items")
    if isinstance(items, list):
        works = [w for w in items if isinstance(w, dict)]
    else:  # 单条 work 快照
        works = [msg]
    for w in works:
        authors = w.get("author") if isinstance(w.get("author"), list) else []
        first_family = ""
        if authors and isinstance(authors[0], dict):
            first_family = first_str(authors[0].get("family"))
        year = ""
        dp = dget(w, "issued", "date-parts")
        if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
            year = str(dp[0][0])
        records.append(
            {
                "source_api": "crossref",
                "title": first_str(w.get("title")),
                "doi": first_str(w.get("DOI")),
                "year": year,
                "container": first_str(w.get("container-title")),
                "type": first_str(w.get("type")),
                "first_author_surname": first_family,
            }
        )
    return records


def extract_europepmc_records(data):
    records = []
    rl = data.get("resultList")
    if not isinstance(rl, dict):
        return records
    items = rl.get("result")
    if not isinstance(items, list):
        return records
    for w in items:
        if not isinstance(w, dict):
            continue
        first_surname = ""
        author_string = first_str(w.get("authorString"))
        if author_string:
            first = re.split(r",| and ", author_string)[0].strip()
            first_surname = first.split()[0] if first.split() else ""
        records.append(
            {
                "source_api": "europepmc",
                "title": first_str(w.get("title")),
                "doi": first_str(w.get("doi")),
                "year": str(w.get("pubYear") or ""),
                "container": first_str(dget(w, "journalInfo", "journal", "title")),
                "type": first_str(w.get("pubType")),
                "first_author_surname": first_surname,
            }
        )
    return records


def extract_records_from_file(entry):
    flavor = entry.get("snapshot_flavor")
    path = entry["abspath"]
    if flavor not in ("crossref", "europepmc"):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001
        return []
    if flavor == "crossref":
        recs = extract_crossref_records(data)
    else:
        recs = extract_europepmc_records(data)
    for r in recs:
        r["snapshot_file"] = entry["relpath"]
        r["snapshot_sha256"] = entry.get("sha256", "")
    return recs


# ---------------------------------------------------------------- 文本层提取
def read_text_layer(entry):
    """返回 (text_or_None, note)。None 表示无法获得文本层。"""
    path = entry["abspath"]
    kind = entry.get("kind")
    if kind in ("txt", "md"):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read(MAX_TEXT_CHARS), ""
        except Exception as e:  # noqa: BLE001
            return None, "read failed: %s" % e.__class__.__name__
    if kind == "pdf":
        exe = shutil.which("pdftotext")
        if not exe:
            return None, "pdftotext not available; PDF 文本层未提取"
        try:
            proc = subprocess.run(
                [exe, "-layout", path, "-"],
                capture_output=True,
                timeout=60,
                check=False,
            )
            if proc.returncode != 0:
                return None, "pdftotext exited %d" % proc.returncode
            text = proc.stdout.decode("utf-8", errors="replace")
            if not text.strip():
                return None, "pdftotext 输出为空（可能是无文本层的扫描件）"
            return text[:MAX_TEXT_CHARS], ""
        except Exception as e:  # noqa: BLE001
            return None, "pdftotext failed: %s" % e.__class__.__name__
    return None, "kind=%s 不是可比对文本层" % kind


# ---------------------------------------------------------------- 比对
def compare_record_to_text(rec, norm_text, raw_text):
    """返回 (checks_dict, matched_fields, mismatched_fields)"""
    checks = {}
    matched, mismatched = [], []

    title_norm = normalize(rec.get("title"))
    if title_norm:
        exact = title_norm in norm_text
        score = best_line_jaccard(tokens(rec.get("title")), raw_text)
        fuzzy = score >= FUZZY_THRESHOLD
        checks["title_exact"] = exact
        checks["title_fuzzy"] = fuzzy
        checks["title_fuzzy_score"] = round(score, 4)
        if exact or fuzzy:
            matched.append("title")
        else:
            mismatched.append("title")

    year = (rec.get("year") or "").strip()
    if year:
        # 剥离 DOI/URL 后按数字边界检索，避免 DOI 内嵌年份假命中
        hay = strip_doi_url(raw_text)
        hit = re.search(r"(?<!\d)%s(?!\d)" % re.escape(year), hay) is not None
        checks["year_match"] = hit
        (matched if hit else mismatched).append("year")

    doi = (rec.get("doi") or "").strip().casefold()
    if doi:
        hit = doi in (raw_text or "").casefold() or doi in norm_text
        checks["doi_in_text"] = hit
        (matched if hit else mismatched).append("doi")

    surname = normalize(rec.get("first_author_surname"))
    if surname:
        hit = surname in norm_text
        checks["first_author_surname_in_text"] = hit
        (matched if hit else mismatched).append("first_author")

    return checks, matched, mismatched


def verdict_for(checks, matched, mismatched, had_any_field):
    if not had_any_field:
        return "unverifiable", "快照记录缺少可比字段（无标题/年份/DOI/作者）"
    title_ok = checks.get("title_exact") or checks.get("title_fuzzy")
    if title_ok and not mismatched:
        return "verified", ""
    if title_ok and mismatched:
        return "mismatch", "字段不一致: %s" % ", ".join(sorted(mismatched))
    if not title_ok:
        return "mismatch", "标题在正文中未命中(exact/fuzzy 均失败)"
    return "unverifiable", "无法判定"


# ---------------------------------------------------------------- 主流程
def main(argv=None):
    ap = argparse.ArgumentParser(description="快照元数据与正文交叉核对")
    ap.add_argument("--workdir", required=True)
    args = ap.parse_args(argv)
    workdir = os.path.abspath(args.workdir)
    manifest_path = os.path.join(workdir, "manifest.json")
    if not os.path.isfile(manifest_path):
        sys.stderr.write("ERROR: manifest.json not found in %s\n" % workdir)
        return 1
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("ERROR: manifest.json unreadable: %s\n" % e)
        return 1

    files = manifest.get("files") or []

    # 1. 提取全部快照记录
    records = []
    for entry in files:
        if entry.get("kind") == "json":
            records.extend(extract_records_from_file(entry))

    # 2. 记录级检测: 重复 + 版本冲突
    duplicates = []
    by_title = {}
    for i, r in enumerate(records):
        key = normalize(r.get("title"))
        if not key:
            continue
        if key in by_title:
            duplicates.append(
                {
                    "normalized_title": key,
                    "record_indices": [by_title[key], i],
                    "files": sorted(
                        {records[by_title[key]]["snapshot_file"], r["snapshot_file"]}
                    ),
                }
            )
        else:
            by_title[key] = i

    version_conflicts = []
    by_doi = {}
    for i, r in enumerate(records):
        doi = (r.get("doi") or "").casefold()
        if not doi:
            continue
        if doi in by_doi:
            j = by_doi[doi]
            other = records[j]
            if (r.get("year") and other.get("year") and r["year"] != other["year"]) or (
                r.get("type") and other.get("type") and r["type"] != other["type"]
            ):
                version_conflicts.append(
                    {
                        "doi": doi,
                        "record_indices": [j, i],
                        "years": sorted({other.get("year", ""), r.get("year", "")}),
                        "types": sorted({other.get("type", ""), r.get("type", "")}),
                    }
                )
        else:
            by_doi[doi] = i

    # 3. 文本层文件 vs 记录 逐对核对
    text_layers = {}
    for entry in files:
        if entry.get("kind") in ("txt", "md", "pdf"):
            text, note = read_text_layer(entry)
            text_layers[entry["relpath"]] = {
                "text": text,
                "note": note,
                "sha256": entry.get("sha256", ""),
                "kind": entry.get("kind"),
            }

    pair_verdicts = []
    for relpath, tl in text_layers.items():
        if tl["text"] is None:
            pair_verdicts.append(
                {
                    "text_file": relpath,
                    "verdict": "unverifiable",
                    "reason": tl["note"],
                    "pairs": [],
                }
            )
            continue
        norm_text = normalize(tl["text"])
        pairs = []
        for r in records:
            checks, matched, mismatched = compare_record_to_text(
                r, norm_text, tl["text"]
            )
            had_any = bool(checks)
            verdict, reason = verdict_for(checks, matched, mismatched, had_any)
            pairs.append(
                {
                    "snapshot_file": r.get("snapshot_file"),
                    "snapshot_title": r.get("title"),
                    "snapshot_doi": r.get("doi"),
                    "snapshot_year": r.get("year"),
                    "source_api": r.get("source_api"),
                    "checks": checks,
                    "matched_fields": matched,
                    "mismatched_fields": mismatched,
                    "verdict": verdict,
                    "reason": reason,
                }
            )
        # 该文本文件的整体判定: 有任何 verified 即 verified；否则若全部 unverifiable 则 unverifiable；
        # 其余为 mismatch。
        pvs = [p["verdict"] for p in pairs]
        if "verified" in pvs:
            overall = "verified"
        elif pvs and all(v == "unverifiable" for v in pvs):
            overall = "unverifiable"
        elif not pvs:
            overall = "unverifiable"
        else:
            overall = "mismatch"
        pair_verdicts.append(
            {
                "text_file": relpath,
                "verdict": overall,
                "reason": "" if overall == "verified" else "见 pairs 明细",
                "pairs": pairs,
            }
        )

    for r in records:
        r.pop("_raw_text", None)

    result = {
        "case_id": manifest.get("case_id", "unknown_case"),
        "record_count": len(records),
        "records": records,
        "duplicates": duplicates,
        "version_conflicts": version_conflicts,
        "text_layer_verdicts": pair_verdicts,
    }
    vpath = os.path.join(workdir, "verification.json")
    with open(vpath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 人类可读摘要
    lines = [
        "# 交叉核对摘要 (verification_summary)",
        "",
        "- case_id: `%s`" % result["case_id"],
        "- 快照记录数: %d" % len(records),
        "- 文本层文件数: %d" % len(text_layers),
        "- 重复记录: %d 组" % len(duplicates),
        "- 版本冲突: %d 组" % len(version_conflicts),
        "",
        "## 逐文件判定",
        "",
        "| 文本文件 | 判定 | 说明 |",
        "|---|---|---|",
    ]
    for pv in pair_verdicts:
        lines.append(
            "| %s | %s | %s |"
            % (pv["text_file"], pv["verdict"], pv.get("reason", "") or "-")
        )
    lines += ["", "## 明细（文本文件 × 快照记录）", ""]
    for pv in pair_verdicts:
        lines.append("### %s → %s" % (pv["text_file"], pv["verdict"]))
        for p in pv.get("pairs", []):
            lines.append(
                "- [%s] `%s` (doi=%s, year=%s) mismatched=%s %s"
                % (
                    p["verdict"],
                    (p.get("snapshot_title") or "")[:80],
                    p.get("snapshot_doi") or "-",
                    p.get("snapshot_year") or "-",
                    p.get("mismatched_fields"),
                    p.get("reason") or "",
                )
            )
        lines.append("")
    spath = os.path.join(workdir, "verification_summary.md")
    with open(spath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    sys.stdout.write("verification written: %s\n" % vpath)
    sys.stdout.write("summary written: %s\n" % spath)
    return 0


if __name__ == "__main__":
    sys.exit(main())
