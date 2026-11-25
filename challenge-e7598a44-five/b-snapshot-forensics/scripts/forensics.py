#!/usr/bin/env python3
"""forensics.py — 上游数据真实性取证：先取证，再谈筛查（本技能的重器）。

对 /input 每个输入文件计算 sha256 指纹，逐文件解析并出具取证报告
（文件指纹、记录数、键分布、异常行）；建立隔离登记册：凡带夹具标记
（synthetic_duplicate / duplicate_of / conflict_opinion / fixture 等）或结构
残缺的记录进入 quarantine，不进入下游筛查，但逐条登记去向；最后对署名文献
清单做元数据法证：DOI / 年份 / 第一作者 / 期刊逐项比对快照记录，判
authentic / mismatch / absent。

用法:
  python3 forensics.py --case /input/case.json --input-dir /input --work /app/work

产物（--work 下）:
  forensics_report.json    逐文件取证报告（指纹/格式/记录数/键分布/异常行/解析失败）
  trusted_records.jsonl    通过信任门的记录（供 gated_screen.py 筛查）
  quarantine.jsonl         隔离登记册（夹具标记 + 结构残缺，登记去向，不筛查）
  metadata_forensics.json  署名清单逐字段法证（authentic/mismatch/absent + 差异明细）

退出码:
  0  取证完成（含零记录的情形，blocked 由 gated_screen.py 判定）；
  2  case.json 缺失/损坏或输入目录不存在——仍尽量落盘报告，指明缺什么。
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys

RECORD_LIST_KEYS = ("records", "results", "items", "entries", "hits", "export", "data")
REFLIST_KEYS = ("attributed_papers", "reference_list", "references", "refs", "paper_list")
FIXTURE_MARKERS = ("synthetic_duplicate", "duplicate_of", "conflict_opinion",
                   "is_fixture", "fixture", "synthetic")
KNOWN_FORMATS = {".json", ".jsonl", ".csv", ".tsv", ".ris"}


# ---------- 文件指纹 ----------
def fingerprint(path):
    h = hashlib.sha256()
    n_bytes = 0
    n_lines = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
            n_bytes += len(chunk)
            n_lines += chunk.count(b"\n")
    return {"sha256": h.hexdigest(), "bytes": n_bytes, "lines": n_lines}


# ---------- 逐格式解析（每种格式单独出异常行） ----------
def scan_json_text(text, rel):
    """返回 (raw_records, anomalies)。raw_records 元素为 (origin_suffix, dict)。"""
    obj = json.loads(text)  # 抛给调用者记 parse_error
    lists = []

    def walk(node, path):
        if isinstance(node, dict):
            for key, val in node.items():
                if key in RECORD_LIST_KEYS and isinstance(val, list):
                    lists.append(("%s.%s" % (path, key), val))
                else:
                    walk(val, "%s.%s" % (path, key))

    anomalies = []
    if isinstance(obj, list):
        lists.append(("$", obj))
    else:
        walk(obj, "$")
    raws = []
    for lpath, rows in lists:
        for i, item in enumerate(rows):
            if isinstance(item, dict):
                raws.append(("%s[%d]" % (lpath, i + 1), item))
            else:
                anomalies.append({"kind": "non_dict_row", "at": "%s[%d]" % (lpath, i + 1),
                                  "detail": "记录不是 JSON 对象，已跳过"})
    return raws, anomalies


def scan_jsonl_text(text, rel):
    raws, anomalies = [], []
    for ln, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception as e:
            anomalies.append({"kind": "unparseable_line", "at": "L%d" % ln,
                              "detail": str(e)[:160]})
            continue
        if isinstance(item, dict):
            raws.append(("L%d" % ln, item))
        else:
            anomalies.append({"kind": "non_dict_row", "at": "L%d" % ln,
                              "detail": "行不是 JSON 对象，已跳过"})
    return raws, anomalies


def scan_table_text(text, rel, delimiter):
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    raws, anomalies = [], []
    for i, row in enumerate(reader, 1):
        if None in row:
            anomalies.append({"kind": "ragged_row", "at": "row%d" % i,
                              "detail": "列数多于表头，多余列已丢弃"})
            row = {k: v for k, v in row.items() if k is not None}
        if not any((v or "").strip() for v in row.values()):
            continue
        raws.append(("row%d" % i, row))
    return raws, anomalies


def scan_ris_text(text, rel):
    tagmap = {"TI": "title", "T1": "title", "AU": "authors", "DO": "doi",
              "PY": "year", "JO": "venue", "JF": "venue", "TY": "type", "AB": "abstract"}
    raws, anomalies, cur, started = [], [], {}, False
    for ln, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^([A-Z][A-Z0-9])  - (.*)$", line)
        if not m:
            if line.strip() and started:
                anomalies.append({"kind": "non_ris_line", "at": "L%d" % ln,
                                  "detail": "记录块内出现非 RIS 标签行"})
            continue
        tag, val = m.group(1), m.group(2).strip()
        if tag == "TY":
            cur, started = {"type": val}, True
        elif tag == "ER":
            if cur:
                raws.append(("ris%d" % (len(raws) + 1), cur))
            cur, started = {}, False
        elif tag in tagmap:
            if tagmap[tag] == "authors":
                cur.setdefault("authors", []).append(val)
            else:
                cur[tagmap[tag]] = val
    if cur:
        raws.append(("ris%d" % (len(raws) + 1), cur))
    return raws, anomalies


def parse_file(path, rel):
    """返回 (file_entry, raws)。任何异常都落成 file_entry['parse_error']。"""
    entry = {"path": rel, "format": os.path.splitext(path)[1].lstrip(".").lower() or "none"}
    entry.update(fingerprint(path))
    raws, anomalies = [], []
    ext = "." + entry["format"]
    if ext not in KNOWN_FORMATS:
        entry["note"] = "非快照数据格式，仅登记指纹，不解析记录"
    else:
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            if ext == ".json":
                raws, anomalies = scan_json_text(text, rel)
            elif ext == ".jsonl":
                raws, anomalies = scan_jsonl_text(text, rel)
            elif ext in (".csv", ".tsv"):
                raws, anomalies = scan_table_text(text, rel, "\t" if ext == ".tsv" else ",")
            elif ext == ".ris":
                raws, anomalies = scan_ris_text(text, rel)
        except Exception as e:
            entry["parse_error"] = str(e)[:200]
    key_hist = {}
    for _suffix, raw in raws:
        for k in raw:
            key_hist[k] = key_hist.get(k, 0) + 1
    entry["record_count"] = len(raws)
    entry["key_histogram"] = dict(sorted(key_hist.items(), key=lambda kv: (-kv[1], kv[0])))
    entry["anomalies"] = anomalies
    return entry, raws


# ---------- 记录规范化与信任门 ----------
def normalize(raw, rid):
    authors = raw.get("authors") or raw.get("author") or []
    if isinstance(authors, str):
        authors = [a.strip() for a in re.split(r";| and ", authors) if a.strip()]
    ym = re.search(r"(19|20)\d{2}", str(raw.get("year") or raw.get("publication_year")
                                        or raw.get("date") or raw.get("py") or ""))
    flags = {m: raw[m] for m in FIXTURE_MARKERS if m in raw}
    return {
        "rid": rid,
        "title": str(raw.get("title") or raw.get("TI") or "").strip(),
        "authors": authors,
        "year": int(ym.group(0)) if ym else None,
        "doi": (str(raw.get("doi") or raw.get("DO") or "").strip().lower() or None),
        "venue": str(raw.get("venue") or raw.get("journal") or raw.get("JO")
                     or raw.get("source") or "").strip(),
        "type": str(raw.get("type") or raw.get("TY") or raw.get("doctype") or "").lower(),
        "abstract": str(raw.get("abstract") or raw.get("AB") or ""),
        "fixture_flags": flags,
    }


def trust_gate(rec):
    """信任门：返回 (是否放行, 隔离类别)。判据见 references/trust-model.md。"""
    if rec["fixture_flags"]:
        if "conflict_opinion" in rec["fixture_flags"]:
            return False, "fixture_conflict_opinion"
        if "synthetic_duplicate" in rec["fixture_flags"] or "duplicate_of" in rec["fixture_flags"]:
            return False, "fixture_synthetic_duplicate"
        return False, "fixture_labelled"
    if not rec["title"]:
        return False, "malformed_no_title"
    return True, ""


def metadata_warnings(rec):
    warns = []
    if rec["year"] is None:
        warns.append("year_missing")
    if not rec["doi"]:
        warns.append("doi_missing")
    if not rec["venue"]:
        warns.append("venue_missing")
    return warns


QUAR_NOTE = {
    "fixture_synthetic_duplicate": "输入夹具标记的合成重复，隔离登记，不参与筛查与计数",
    "fixture_conflict_opinion": "输入夹具标记的冲突意见，登记为争议证据，不做学术裁决，需人工处理",
    "fixture_labelled": "输入夹具标记记录，隔离登记，不参与筛查",
    "malformed_no_title": "结构残缺（缺标题），无法核验身份，隔离待人工",
}


# ---------- 署名清单元数据法证 ----------
def locate_reflist(case, json_texts):
    for key in REFLIST_KEYS:
        if isinstance(case.get(key), list) and case[key]:
            return "case.json!%s" % key, case[key]

    def dig(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in REFLIST_KEYS and isinstance(v, list) and v:
                    return v
                found = dig(v)
                if found:
                    return found
        elif isinstance(node, list):
            for v in node:
                found = dig(v)
                if found:
                    return found
        return None

    for rel, obj in json_texts:
        found = dig(obj)
        if found:
            return "%s!%s" % (rel, "embedded_reflist"), found
    return None, []


def title_tokens(t):
    return set(w for w in re.findall(r"[a-z0-9]+", (t or "").lower()) if len(w) > 2)


def compare_field(name, ref_val, snap_val):
    if ref_val in (None, "", []):
        return None
    if snap_val in (None, "", []):
        return {"field": name, "verdict": "snapshot_missing", "ref": ref_val}
    if name == "first_author":
        ok = str(ref_val).split()[-1].lower() == str(snap_val).split()[-1].lower()
    else:
        ok = str(ref_val).strip().lower() == str(snap_val).strip().lower()
    if ok:
        return {"field": name, "verdict": "match"}
    return {"field": name, "verdict": "diff", "ref": ref_val, "snapshot": snap_val}


def forensicate_metadata(refs, origin, records):
    """records 为全部已解析记录（含隔离中的），法证面向快照事实而非可信子集。"""
    report = {"status": "ok", "origin": origin, "total": len(refs),
              "authentic": 0, "mismatch": 0, "absent": 0, "papers": []}
    for i, ref in enumerate(refs):
        ref = ref if isinstance(ref, dict) else {"title": str(ref)}
        rid = ref.get("ref_id") or ref.get("id") or "ref-%d" % (i + 1)
        entry = {"ref_id": rid, "title": ref.get("title"), "doi": ref.get("doi") or None}
        rdoi = (ref.get("doi") or "").strip().lower()
        rtoks = title_tokens(ref.get("title", ""))
        best, best_score = None, 0.0
        for rec in records:
            if rdoi and rec["doi"] == rdoi:
                best, best_score = rec, 1.0
                break
            stoks = title_tokens(rec["title"])
            if rtoks and stoks:
                score = len(rtoks & stoks) / max(1, min(len(rtoks), len(stoks)))
                if score > best_score:
                    best, best_score = rec, score
        if best is None or best_score < 0.5:
            entry["verdict"] = "absent"
            entry["detail"] = "快照全部记录中无 DOI 匹配且标题重叠 < 0.5"
        else:
            checks = [c for c in (
                compare_field("doi", rdoi or None, best["doi"]),
                compare_field("year", ref.get("year"), best["year"]),
                compare_field("first_author",
                              ref.get("first_author") or (ref.get("authors") or [None])[0],
                              (best["authors"] or [None])[0]),
                compare_field("venue", ref.get("venue") or ref.get("journal"), best["venue"]),
            ) if c]
            diffs = [c for c in checks if c["verdict"] == "diff"]
            entry["verdict"] = "mismatch" if diffs else "authentic"
            entry["matched_record"] = best["rid"]
            entry["match_score"] = round(best_score, 3)
            entry["matched_record_quarantined"] = bool(best["fixture_flags"]) or not best["title"]
            entry["field_checks"] = checks
            if diffs:
                entry["detail"] = "; ".join(
                    "%s: 清单 %r vs 快照 %r" % (d["field"], d["ref"], d["snapshot"])
                    for d in diffs)
        report[entry["verdict"]] += 1
        report["papers"].append(entry)
    return report


# ---------- 主流程 ----------
def main():
    ap = argparse.ArgumentParser(
        description="上游数据真实性取证：文件指纹 + 解析取证 + 隔离登记 + 元数据法证")
    ap.add_argument("--case", required=True, help="/input/case.json")
    ap.add_argument("--input-dir", required=True, help="输入目录（只读）")
    ap.add_argument("--work", required=True, help="取证产物目录，如 /app/work")
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)

    problems, case = [], {}
    if not os.path.isfile(args.case):
        problems.append("case.json 不存在: %s" % args.case)
    else:
        try:
            with open(args.case, encoding="utf-8") as fh:
                case = json.load(fh)
            if not isinstance(case, dict):
                problems.append("case.json 顶层不是对象")
                case = {}
        except Exception as e:
            problems.append("case.json 解析失败: %s" % e)

    files, all_records, json_texts = [], [], []
    if not os.path.isdir(args.input_dir):
        problems.append("输入目录不存在: %s" % args.input_dir)
    else:
        for root, _dirs, names in os.walk(args.input_dir):
            for n in sorted(names):
                p = os.path.join(root, n)
                rel = os.path.relpath(p, args.input_dir)
                entry, raws = parse_file(p, rel)
                files.append(entry)
                for suffix, raw in raws:
                    all_records.append(normalize(raw, "%s::%s" % (rel, suffix)))
                if entry["format"] == "json" and "parse_error" not in entry:
                    try:
                        with open(p, encoding="utf-8") as fh:
                            json_texts.append((rel, json.load(fh)))
                    except Exception:
                        pass

    trusted, quarantine = [], []
    for rec in all_records:
        ok, category = trust_gate(rec)
        if ok:
            rec["metadata_warnings"] = metadata_warnings(rec)
            trusted.append(rec)
        else:
            quarantine.append({
                "qid": "Q-%03d" % (len(quarantine) + 1),
                "rid": rec["rid"],
                "category": category,
                "fixture_flags": rec["fixture_flags"],
                "title": rec["title"] or None,
                "doi": rec["doi"],
                "disposition": "excluded_from_screening__registered_only",
                "note": QUAR_NOTE[category],
            })

    origin, refs = locate_reflist(case, json_texts)
    if refs:
        meta = forensicate_metadata(refs, origin, all_records)
    else:
        meta = {"status": "no_reference_list",
                "note": "输入中未找到署名文献清单（attributed_papers/references/refs 等），"
                        "元数据法证未执行；这不阻塞筛查，但必须如实声明",
                "papers": []}

    by_cat = {}
    for q in quarantine:
        by_cat[q["category"]] = by_cat.get(q["category"], 0) + 1
    report = {
        "case_id": case.get("case_id"),
        "problems": problems,
        "files": files,
        "totals": {
            "files_seen": len(files),
            "files_parsed": sum(1 for f in files if f.get("record_count")),
            "records_parsed": len(all_records),
            "records_trusted": len(trusted),
            "records_quarantined": len(quarantine),
            "quarantine_by_category": by_cat,
            "anomaly_lines": sum(len(f.get("anomalies", [])) for f in files),
            "parse_failures": [f["path"] for f in files if "parse_error" in f],
        },
    }

    def dump(name, obj):
        with open(os.path.join(args.work, name), "w", encoding="utf-8") as fh:
            if name.endswith(".jsonl"):
                for row in obj:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            else:
                json.dump(obj, fh, ensure_ascii=False, indent=2)

    dump("forensics_report.json", report)
    dump("trusted_records.jsonl", trusted)
    dump("quarantine.jsonl", quarantine)
    dump("metadata_forensics.json", meta)

    print(json.dumps({
        "ok": not problems, "problems": problems,
        "files": len(files), "records_parsed": len(all_records),
        "trusted": len(trusted), "quarantined": len(quarantine),
        "metadata_verdicts": {k: meta.get(k) for k in ("authentic", "mismatch", "absent")}
        if meta.get("status") == "ok" else meta.get("status"),
    }, ensure_ascii=False))
    sys.exit(2 if problems else 0)


if __name__ == "__main__":
    main()
