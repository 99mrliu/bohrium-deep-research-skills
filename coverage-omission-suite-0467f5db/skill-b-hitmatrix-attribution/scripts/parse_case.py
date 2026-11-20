#!/usr/bin/env python3
"""parse_case.py — 材料清点与 case.json 校验。

读取 case.json（默认 /input/case.json），校验结构，清点参考集、检索记录与
各来源本地响应文件，冻结参考集并标记不可用记录，输出：
  work/case_normalized.json   归一化案例（供其余脚本读取）
  work/materials_inventory.md 材料清单（含缺失/损坏登记）

case.json 约定结构（宽松解析，缺键即校验失败）:
  case_id: str
  materials_dir: str            材料根目录（相对 case.json 所在目录或绝对路径）
  reference_set: [ {ref_id, title, authors|author, year, doi|pmid|arxiv|ids,
                    usable, unusable_reason, retracted, duplicate_of, keywords} ]
  search_log: [ {query_id, source, executed_at, query_string, fields, date_window,
                 results_file} ]
  output_contract: {required_fields: [...]} 或 [...]

用法:
  python3 parse_case.py --case /input/case.json --work /app/work

退出码: 0 成功; 2 材料不足; 3 校验失败。
仅使用 Python 3 标准库。
"""
import argparse
import json
import os
import sys

REQUIRED_TOP_KEYS = ("case_id", "reference_set", "search_log")
REF_REQUIRED = ("ref_id", "title")
QUERY_REQUIRED = ("query_id", "source", "results_file")


def fail(msg, code):
    print("ERROR: %s" % msg, file=sys.stderr)
    return code


def validate_case(case):
    """结构校验，返回错误信息列表（空列表表示通过）。"""
    errors = []
    if not isinstance(case, dict):
        return ["case.json 根节点必须是对象"]
    for k in REQUIRED_TOP_KEYS:
        if k not in case:
            errors.append("缺少必填键: %s" % k)
    if errors:
        return errors
    if not isinstance(case.get("reference_set"), list):
        errors.append("reference_set 必须是数组")
    else:
        for i, r in enumerate(case["reference_set"]):
            if not isinstance(r, dict):
                errors.append("reference_set[%d] 不是对象" % i)
                continue
            for k in REF_REQUIRED:
                if k not in r:
                    errors.append("reference_set[%d] 缺少键: %s" % (i, k))
    if not isinstance(case.get("search_log"), list):
        errors.append("search_log 必须是数组")
    else:
        for i, q in enumerate(case["search_log"]):
            if not isinstance(q, dict):
                errors.append("search_log[%d] 不是对象" % i)
                continue
            for k in QUERY_REQUIRED:
                if k not in q:
                    errors.append("search_log[%d] 缺少键: %s" % (i, k))
    return errors


def normalize_output_contract(case):
    oc = case.get("output_contract") or {}
    if isinstance(oc, list):
        return {"required_fields": list(oc)}
    if isinstance(oc, dict):
        rf = oc.get("required_fields")
        return {"required_fields": list(rf) if isinstance(rf, list) else []}
    return {"required_fields": []}


def mark_usability(reference_set):
    """冻结参考集：撤稿/重复/题录缺失按规则标记 usable；返回 (usable_list, excluded_list)。"""
    seen_titles = {}
    usable, excluded = [], []
    for r in reference_set:
        r = dict(r)
        title_key = " ".join(str(r.get("title", "")).lower().split())
        if r.get("duplicate_of"):
            r["usable"] = False
            r["unusable_reason"] = "duplicate_of:%s" % r["duplicate_of"]
        elif title_key in seen_titles:
            r["usable"] = False
            r["unusable_reason"] = "duplicate_of:%s" % seen_titles[title_key]
        elif r.get("retracted"):
            r["usable"] = False
            r["unusable_reason"] = "retracted"
        elif not str(r.get("title", "")).strip():
            r["usable"] = False
            r["unusable_reason"] = "missing_bibliography"
        elif r.get("usable") is False:
            r.setdefault("unusable_reason", "flagged_unusable")
        else:
            r["usable"] = True
            seen_titles.setdefault(title_key, r.get("ref_id"))
        if title_key not in seen_titles and r["usable"]:
            seen_titles[title_key] = r.get("ref_id")
        (usable if r["usable"] else excluded).append(r)
    return usable, excluded


def main(argv=None):
    ap = argparse.ArgumentParser(description="材料清点与 case.json 校验，输出归一化案例。")
    ap.add_argument("--case", default="/input/case.json", help="case.json 路径（默认 /input/case.json）")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.case):
        return fail("case.json 不存在: %s" % args.case, 2)
    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, ValueError) as e:
        return fail("case.json 不可解析: %s" % e, 3)

    errors = validate_case(case)
    if errors:
        for e in errors:
            print("ERROR: %s" % e, file=sys.stderr)
        return 3

    os.makedirs(args.work, exist_ok=True)
    base = os.path.dirname(os.path.abspath(args.case))
    mdir = case.get("materials_dir") or "."
    materials_dir = mdir if os.path.isabs(mdir) else os.path.normpath(os.path.join(base, mdir))

    usable, excluded = mark_usability(case["reference_set"])
    if not usable:
        return fail("冻结后可用参考集为空，无法计算覆盖率", 2)
    if not case["search_log"]:
        return fail("检索记录为空，无查询单元可判定", 2)

    # 相对路径解析：优先相对 materials_dir，回退相对 case.json 所在目录
    def resolve_rel(rel):
        if rel is None or os.path.isabs(rel):
            return rel
        p1 = os.path.join(materials_dir, rel)
        if os.path.isfile(p1):
            return p1
        p2 = os.path.join(base, rel)
        return p2 if os.path.isfile(p2) else p1

    # 清点响应文件
    inventory = []
    missing = []
    for q in case["search_log"]:
        rf = q.get("results_file")
        path = resolve_rel(rf)
        ok = bool(path) and os.path.isfile(path)
        size = os.path.getsize(path) if ok else 0
        inventory.append({"results_file": rf, "resolved_path": path,
                          "exists": ok, "bytes": size})
        if not ok:
            missing.append(rf)
    if missing and len(missing) == len(case["search_log"]):
        return fail("全部响应文件缺失: %s" % ", ".join(missing), 2)

    # 检索记录中登记绝对路径，保证后续脚本与材料目录解耦
    norm_queries = []
    for q in case["search_log"]:
        q = dict(q)
        q["results_file"] = resolve_rel(q.get("results_file"))
        norm_queries.append(q)

    # extra.sources 中的索引文件同样解析为绝对路径
    extra = dict(case.get("extra") or {})
    if isinstance(extra.get("sources"), list):
        for s in extra["sources"]:
            if isinstance(s, dict) and s.get("index_file"):
                s["index_file"] = resolve_rel(s["index_file"])

    normalized = {
        "case_id": case["case_id"],
        "materials_dir": materials_dir,
        "reference_set": usable + excluded,
        "usable_reference_count": len(usable),
        "excluded_references": [
            {"ref_id": r.get("ref_id"), "reason": r.get("unusable_reason")} for r in excluded],
        "search_log": norm_queries,
        "output_contract": normalize_output_contract(case),
        "extra": extra,
    }
    out_path = os.path.join(args.work, "case_normalized.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    inv_path = os.path.join(args.work, "materials_inventory.md")
    with open(inv_path, "w", encoding="utf-8") as f:
        f.write("# 材料清单\n\n")
        f.write("- case_id: %s\n" % case["case_id"])
        f.write("- 材料目录: %s\n" % materials_dir)
        f.write("- 参考集: %d 条（可用 %d，剔除 %d）\n"
                % (len(case["reference_set"]), len(usable), len(excluded)))
        f.write("- 检索记录: %d 条查询\n\n" % len(case["search_log"]))
        f.write("## 响应文件\n\n| results_file | 存在 | 字节数 |\n| --- | --- | --- |\n")
        for it in inventory:
            f.write("| %s | %s | %d |\n" % (it["results_file"],
                                            "是" if it["exists"] else "否", it["bytes"]))
        if excluded:
            f.write("\n## 分母剔除清单\n\n| ref_id | 原因 |\n| --- | --- |\n")
            for r in excluded:
                f.write("| %s | %s |\n" % (r.get("ref_id"), r.get("unusable_reason")))

    print("parse_case: 参考集 %d 条（可用 %d，剔除 %d），查询 %d 条，缺失响应文件 %d 个"
          % (len(case["reference_set"]), len(usable), len(excluded),
             len(norm_queries), len(missing)))
    print("输出: %s ; %s" % (out_path, inv_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
