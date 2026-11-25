#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""repair_fields.py — 标识符规范化 + 快照内保守补全（conservative cross-fill）

两件事，都逐条留痕：
  1. DOI 规范化（安全修复）：去 https://doi.org/ 前缀、去 "doi:"、小写化、
     去尾部标点；规范化后仍不符合 10.\\d{4,9}/ 形态的登记为 doi_malformed，
     不臆造、不联网验证。
  2. 保守补全：仅当同一快照内存在强键（规范化 DOI 精确一致，或长度足够的
     规范化题名精确一致）的另一记录持有缺失字段、且该字段在键组内取值唯一时，
     才补全缺失字段。冲突（键组内取值不唯一）则不补并记录 conflict。

红线：只补字段，绝不合并/删除记录（记录合并是别的方向的职责）；
      无强键宁可不补；绝不覆盖已有非占位符值。

退出码：0 成功；2 运行/IO 错误；3 输入合同不满足。幂等（输出整体重写；
对已规范化/已补全的记录再跑不会产生新改动）。
"""
import argparse
import json
import os
import re
import sys

DOI_STRIP_RE = re.compile(r"^https?://(dx\.)?doi\.org/", re.IGNORECASE)
DOI_PREFIX_RE = re.compile(r"^doi:\s*", re.IGNORECASE)
DOI_SHAPE_RE = re.compile(r"^10\.\d{4,9}/\S+$")
TRAILING_PUNCT = ".,;)]}>\"'”’"

# 允许跨源补全的字段白名单（标识符/书目事实类；不补结论性字段）
FILLABLE_FIELDS = ["doi", "year", "publication_year", "journal", "volume",
                   "issue", "pages", "authors", "abstract", "language",
                   "keywords", "publication_type", "issn", "pmid"]

TITLE_MIN_LEN = 12  # 规范化题名低于此长度不做强键，避免"Intro"类碰撞

PLACEHOLDERS = {"", "n/a", "na", "n.a.", ".", "-", "--", "none", "null",
                "unknown", "missing", "?", "tbd", "not available"}


def is_missing(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in PLACEHOLDERS
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def normalize_doi(raw):
    """返回 (规范化值或 None, 是否做了改写)。"""
    if not isinstance(raw, str):
        return (None, False)
    v = raw.strip()
    v = DOI_STRIP_RE.sub("", v)
    v = DOI_PREFIX_RE.sub("", v)
    v = v.strip().rstrip(TRAILING_PUNCT).strip()
    v = v.lower()
    return (v, v != raw)


def normalize_title(raw):
    if not isinstance(raw, str):
        return None
    t = raw.lower()
    t = re.sub(r"[^0-9a-z一-鿿]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) >= TITLE_MIN_LEN else None


def norm_value(value):
    """键组内取值唯一性比较用的归一化。"""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value.strip().lower())
    if isinstance(value, list):
        return tuple(norm_value(str(v)) for v in value)
    return value


def repair(records):
    records = [dict(r) for r in records]
    changes = []
    conflicts = []
    doi_flags = []

    # ---- 1) DOI 规范化与形态登记 ----
    for rec in records:
        rid = rec["record_id"]
        raw = rec.get("doi")
        if is_missing(raw):
            continue
        norm, rewritten = normalize_doi(raw)
        if norm and DOI_SHAPE_RE.match(norm):
            if rewritten:
                changes.append({"record_id": rid, "field": "doi",
                                "old": raw, "new": norm,
                                "source_record_id": None,
                                "rule": "doi_normalize"})
                rec["doi"] = norm
        else:
            doi_flags.append({"record_id": rid, "value": raw,
                              "issue": "doi_malformed",
                              "action": "kept_original_flagged_untrusted"})

    # ---- 2) 建强键索引：doi:<norm> 与 title:<norm> ----
    key_index = {}  # key -> [record 下标]
    for idx, rec in enumerate(records):
        doi = rec.get("doi")
        if isinstance(doi, str) and DOI_SHAPE_RE.match(doi):
            key_index.setdefault("doi:" + doi, []).append(idx)
        ntitle = normalize_title(rec.get("title"))
        if ntitle:
            key_index.setdefault("title:" + ntitle, []).append(idx)

    # ---- 3) 保守补全 ----
    filled_pairs = set()  # (record_id, field) 防止多键重复补
    for key, idxs in sorted(key_index.items()):
        if len(idxs) < 2:
            continue
        rule = "cross_fill_by_doi" if key.startswith("doi:") else \
               "cross_fill_by_title"
        for field in FILLABLE_FIELDS:
            holders = {}  # norm_value -> [idx]
            for idx in idxs:
                value = records[idx].get(field)
                if not is_missing(value):
                    holders.setdefault(norm_value(value), []).append(idx)
            if not holders:
                continue
            if len(holders) > 1:
                # 键组内取值冲突：谁也不信，记录冲突，不补
                conflicts.append({
                    "key": key, "field": field,
                    "candidates": [
                        {"record_id": records[i]["record_id"],
                         "value": records[i].get(field)}
                        for i in idxs if not is_missing(records[i].get(field))],
                    "action": "not_filled_conflict",
                })
                continue
            donor_idx = next(iter(holders.values()))[0]
            donor = records[donor_idx]
            for idx in idxs:
                target = records[idx]
                pair = (target["record_id"], field)
                if idx == donor_idx or pair in filled_pairs:
                    continue
                if not is_missing(target.get(field)):
                    continue
                old = target.get(field)
                target[field] = donor[field]
                filled_pairs.add(pair)
                changes.append({
                    "record_id": target["record_id"], "field": field,
                    "old": old if old is not None else None,
                    "new": donor[field],
                    "source_record_id": donor["record_id"],
                    "rule": rule,
                })

    ledger = {
        "generated_by": "repair_fields.py",
        "records_total": len(records),
        "changes": changes,
        "conflicts": conflicts,
        "doi_flags": doi_flags,
        "stats": {
            "doi_normalized": sum(1 for c in changes
                                  if c["rule"] == "doi_normalize"),
            "cross_filled": sum(1 for c in changes
                                if c["rule"].startswith("cross_fill")),
            "conflicts_not_filled": len(conflicts),
            "doi_malformed": len(doi_flags),
        },
        "notes": ["只补字段、不合并记录；无强键不补；冲突不补；",
                   "DOI 仅做形态规范化，未联网验证。"],
    }
    return records, ledger


def main(argv=None):
    parser = argparse.ArgumentParser(description="DOI 规范化 + 快照内保守补全")
    parser.add_argument("--records",
                        default="/app/work/records_text_fixed.jsonl",
                        help="输入记录（默认用上一步 text_health 的产物）")
    parser.add_argument("--work", default="/app/work", help="中间产物目录")
    args = parser.parse_args(argv)
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from profile_fields import load_records
        records = load_records(args.records)
        if not records:
            print("ERROR: 记录为空", file=sys.stderr)
            return 3
        fixed, ledger = repair(records)
        os.makedirs(args.work, exist_ok=True)
        rec_path = args.work.rstrip("/") + "/records_final.jsonl"
        ledger_path = args.work.rstrip("/") + "/repair_ledger.json"
        with open(rec_path, "w", encoding="utf-8") as fh:
            for rec in fixed:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        with open(ledger_path, "w", encoding="utf-8") as fh:
            json.dump(ledger, fh, ensure_ascii=False, indent=2, sort_keys=True)
        s = ledger["stats"]
        print("OK: %d 条记录；doi 规范化=%d，补全=%d，冲突未补=%d，畸形 DOI=%d -> %s, %s"
              % (len(fixed), s["doi_normalized"], s["cross_filled"],
                 s["conflicts_not_filled"], s["doi_malformed"],
                 rec_path, ledger_path))
        return 0
    except FileNotFoundError as exc:
        print("ERROR: 输入文件不存在: %s" % exc, file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # 顶层兜底
        print("ERROR: 未预期异常: %r" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
