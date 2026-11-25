#!/usr/bin/env python3
"""init_ledger.py — 从 case.json 递归收割候选文献，归一化、去重，建立筛选台账。

用法:
    python3 init_ledger.py --case /input/case.json [--task /input/task.md] \
        --workdir /app/work [--output-dir /app/output]

产出（workdir 下）:
    candidates.jsonl    去重后的唯一候选，每行 {cand_id, title, authors, year, doi,
                        source, abstract_snippet, source_path}
    duplicates.jsonl    去重合并记录，每行 {survivor, merged_ids, key, reason}
    harvest_report.json 收割报告（identified_raw / unique / lists_found / notes /
                        output_contract 镜像 / case_id）
    <output-dir>/result.json  （可选）骨架但合法的诚实结果，status=in_progress

退出码: 0 正常；2 用法或 IO 错误。空候选集不是错误（退出码 0，notes 说明）。
仅 Python 3 标准库；无网络访问。
"""
import argparse
import json
import os
import re
import sys
import unicodedata

# 候选列表可能出现的键名（小写匹配）
CANDIDATE_KEYS = {"candidates", "documents", "papers", "references",
                  "results", "items", "records"}
# output contract 可能出现的键名
CONTRACT_KEYS = ("output_contract", "contract", "output_fields", "required_fields")
CASE_ID_KEYS = ("case_id", "caseid", "id", "case")

ABSTRACT_SNIPPET_LEN = 600


def norm_text(s):
    """NFKC + casefold + 空白折叠，用于标题去重键与展示归一化。"""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).casefold()
    return re.sub(r"\s+", " ", s).strip()


def title_key(title):
    """标题去重键：归一化后去掉非字母数字字符。"""
    t = norm_text(title)
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", t)


def find_candidate_lists(obj, path="$", hits=None, _in_harvested=False):
    """递归查找候选列表。命中一个列表后不再向其内部递归（避免把候选条目内嵌的
    references 列表二次收割）。"""
    if hits is None:
        hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).strip().lower()
            child = "%s/%s" % (path, k)
            if kl in CANDIDATE_KEYS and isinstance(v, list):
                hits.append({"path": child, "items": v})
            else:
                find_candidate_lists(v, child, hits)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            find_candidate_lists(item, "%s[%d]" % (path, i), hits)
    return hits


def find_contract(obj):
    """递归防御式搜索 output contract；返回找到的第一个 dict 及附加字段列表。"""
    found = {}

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                kl = str(k).strip().lower()
                if kl == "output_contract" and isinstance(v, dict) and "output_contract" not in found:
                    found["output_contract"] = v
                elif kl == "contract" and isinstance(v, dict) and "contract" not in found:
                    found["contract"] = v
                elif kl == "output_fields" and isinstance(v, list) and "output_fields" not in found:
                    found["output_fields"] = v
                elif kl == "required_fields" and isinstance(v, list) and "required_fields" not in found:
                    found["required_fields"] = v
                walk(v)
        elif isinstance(o, list):
            for it in o:
                walk(it)

    walk(obj)
    return found


def find_case_id(obj):
    """递归找 case_id：优先顶层键，找不到再递归。"""
    if isinstance(obj, dict):
        for k in CASE_ID_KEYS:
            for kk, vv in obj.items():
                if str(kk).strip().lower() == k and isinstance(vv, (str, int)):
                    return str(vv)
        for vv in obj.values():
            r = find_case_id(vv)
            if r:
                return r
    elif isinstance(obj, list):
        for it in obj:
            r = find_case_id(it)
            if r:
                return r
    return None


def first_str(d, keys):
    """从 dict 里按候选键名取第一个非空字符串。"""
    low = {str(k).strip().lower(): v for k, v in d.items()}
    for k in keys:
        v = low.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, (int, float)):
            return str(v)
    return ""


def normalize_authors(v):
    """作者字段容忍：字符串 / 字符串列表 / 对象列表（取 name）。"""
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    if isinstance(v, list):
        out = []
        for a in v:
            if isinstance(a, str) and a.strip():
                out.append(a.strip())
            elif isinstance(a, dict):
                n = first_str(a, ["name", "full_name", "author", "family"])
                if n:
                    out.append(n)
        return out
    return []


def normalize_year(v):
    """从 year/date/published 等字段提取 4 位年份；取不到返回 None。"""
    if v is None:
        return None
    m = re.search(r"(1[5-9]\d{2}|20\d{2}|21\d{2})", str(v))
    return int(m.group(1)) if m else None


def normalize_entry(entry, cand_id, source_path, notes):
    """把任意形态的条目归一化为标准候选记录。"""
    if isinstance(entry, str):
        return {"cand_id": cand_id, "title": entry.strip(), "authors": [],
                "year": None, "doi": "", "source": "", "abstract_snippet": "",
                "source_path": source_path}
    if not isinstance(entry, dict):
        notes.append("条目类型 %s 无法解析，已跳过（%s）" % (type(entry).__name__, cand_id))
        return None
    title = first_str(entry, ["title", "name", "headline", "label"])
    if not title:
        # 没有标题的元数据对象：退化为 JSON 摘要，保证不丢失、不崩溃
        title = "(untitled record)"
        notes.append("%s 缺少 title 字段，已按无标题记录处理" % cand_id)
    authors = normalize_authors(entry.get("authors") or entry.get("author")
                                or entry.get("creators"))
    year = normalize_year(entry.get("year") or entry.get("date")
                          or entry.get("published") or entry.get("published_year")
                          or entry.get("issued"))
    doi = first_str(entry, ["doi", "DOI", "doi_url"]).strip()
    source = first_str(entry, ["source", "journal", "container-title",
                               "container_title", "venue", "database"])
    abstract = first_str(entry, ["abstract", "description", "summary",
                                 "abstract_snippet", "snippet"])
    return {"cand_id": cand_id, "title": title, "authors": authors,
            "year": year, "doi": doi, "source": source,
            "abstract_snippet": abstract[:ABSTRACT_SNIPPET_LEN],
            "source_path": source_path}


def dedup_key(rec):
    """去重键：有 doi 用 doi（小写去空白去前缀），否则用归一化标题。"""
    if rec["doi"]:
        d = re.sub(r"\s+", "", rec["doi"]).lower()
        d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
        return "doi:" + d
    tk = title_key(rec["title"])
    if tk:
        return "title:" + tk
    return "raw:" + norm_text(json.dumps(rec, ensure_ascii=False, sort_keys=True))[:200]


def main(argv=None):
    ap = argparse.ArgumentParser(description="收割候选文献并建立筛选台账")
    ap.add_argument("--case", required=True, help="case.json 路径")
    ap.add_argument("--task", default=None, help="task.md 路径（可选，仅记录）")
    ap.add_argument("--workdir", required=True, help="工作目录")
    ap.add_argument("--output-dir", default=None, help="交付目录（可选，写骨架 result.json）")
    args = ap.parse_args(argv)

    notes = []
    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    except Exception as e:  # 防御式：连 JSON 都不是也要诚实报错，不崩栈
        print("ERROR: 无法解析 case.json: %s" % e, file=sys.stderr)
        return 2

    os.makedirs(args.workdir, exist_ok=True)
    case_id = find_case_id(case) or "unknown"
    contract = find_contract(case)
    task_note = ""
    if args.task:
        try:
            with open(args.task, "r", encoding="utf-8") as f:
                task_note = f.read(2000)
        except Exception as e:
            notes.append("task.md 读取失败: %s" % e)

    lists_found = find_candidate_lists(case)
    if not lists_found:
        notes.append("未在 case.json 中发现候选列表（已递归搜索键: %s）。"
                     "按空候选集处理。" % ", ".join(sorted(CANDIDATE_KEYS)))

    # 收割 + 归一化
    raw_records = []
    seq = 0
    for hit in lists_found:
        for entry in hit["items"]:
            seq += 1
            cid = "C%03d" % seq
            rec = normalize_entry(entry, cid, hit["path"], notes)
            if rec is not None:
                raw_records.append(rec)
    identified_raw = len(raw_records)

    # 去重（保留首见者，其余合并）。双索引：DOI 相同判重；归一化标题相同也判重
    # （覆盖一方缺 DOI 的快照对）。主键规则：有 doi 用 doi，否则用标题。
    doi_index = {}
    title_index = {}
    unique_records = []
    dup_rows = []
    for rec in raw_records:
        k = dedup_key(rec)
        tk = "title:" + title_key(rec["title"]) if title_key(rec["title"]) else None
        survivor = None
        matched_key = None
        if k.startswith("doi:") and k in doi_index:
            survivor, matched_key = doi_index[k], k
        elif tk and tk in title_index:
            survivor, matched_key = title_index[tk], tk
        if survivor is not None:
            dup_rows.append({
                "survivor": survivor["cand_id"],
                "merged_ids": [rec["cand_id"]],
                "key": matched_key,
                "reason": "与 %s 重复（%s；来源 %s 并入 %s）" % (
                    survivor["cand_id"],
                    "DOI 相同" if matched_key.startswith("doi:") else "归一化标题相同",
                    rec["source_path"], survivor["source_path"]),
            })
        else:
            if k.startswith("doi:"):
                doi_index[k] = rec
            if tk:
                title_index[tk] = rec
            unique_records.append(rec)

    # 写盘
    cand_path = os.path.join(args.workdir, "candidates.jsonl")
    with open(cand_path, "w", encoding="utf-8") as f:
        for rec in unique_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    dup_path = os.path.join(args.workdir, "duplicates.jsonl")
    with open(dup_path, "w", encoding="utf-8") as f:
        for row in dup_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = {
        "case_id": case_id,
        "identified_raw": identified_raw,
        "unique": len(unique_records),
        "duplicates_removed": len(dup_rows),
        "lists_found": [{"path": h["path"], "count": len(h["items"])} for h in lists_found],
        "output_contract": contract,
        "task_excerpt": task_note[:500] if task_note else "",
        "notes": notes,
    }
    with open(os.path.join(args.workdir, "harvest_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 变更日志
    with open(os.path.join(args.workdir, "change_records.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "action": "init_ledger",
            "identified_raw": identified_raw,
            "unique": len(unique_records),
            "duplicates_removed": len(dup_rows),
        }, ensure_ascii=False) + "\n")

    # 骨架 result.json（诚实 partial/in_progress）
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        skeleton = {
            "case_id": case_id,
            "status": "in_progress",
            "output_contract": contract,
            "screening": [],
            "evidence_records": [],
            "flow": None,
            "omissions": ["筛选尚未执行；本文件为 init_ledger.py 生成的骨架结果。"],
            "uncertainties": notes,
            "change_records": ["init_ledger: identified=%d unique=%d duplicates=%d"
                               % (identified_raw, len(unique_records), len(dup_rows))],
        }
        # 镜像 contract 声明的 required 字段
        req = contract.get("required_fields") or contract.get("output_fields") or []
        if isinstance(contract.get("output_contract"), dict):
            req = req or contract["output_contract"].get("required_fields") or []
        for field in req:
            if isinstance(field, str) and field not in skeleton:
                skeleton[field] = None
        with open(os.path.join(args.output_dir, "result.json"), "w", encoding="utf-8") as f:
            json.dump(skeleton, f, ensure_ascii=False, indent=2)

    print("identified=%d unique=%d duplicates_removed=%d lists=%d"
          % (identified_raw, len(unique_records), len(dup_rows), len(lists_found)))
    if identified_raw == 0:
        print("NOTE: 空候选集——按诚实零结果流程继续，不要发明候选。")
    for n in notes:
        print("note:", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
