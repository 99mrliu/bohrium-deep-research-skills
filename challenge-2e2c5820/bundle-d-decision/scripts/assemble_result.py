#!/usr/bin/env python3
"""assemble_result.py — 汇总 result.json（幂等，非空字段绝不覆盖）。

用法:
  python3 assemble_result.py --case <case.json> --artifacts <dir> --out <result.json> \
      --status <complete|partial|failed> --note "<说明>"

行为:
  1. 从 case.json 提取 case_id 与 output_contract 声明的全部字段（缺失的字段初始化为 null，
     并在 uncertainty 中如实登记，禁止编造内容填充）；
  2. 扫描 artifacts 目录，按已知映射合并产物:
       ranking.json        → 契约字段「版本排序」(或 version_ranking) 及 artifacts 区
       risk_register.md    → 「风险登记表」；ethics_paths.md → 「伦理审批路径」；
       conditions_list.md  → 「条件清单」；overall_verdict.json → 其顶层键值按名合并；
     其余 *.json 产物的顶层键若与契约字段同名且当前为 null，也一并并入；
  3. result.json 已存在时：仅填充仍为 null 的字段（never overwrite non-null），
     change_record 追加而非替换；
  4. status/sources/uncertainty/change_record 总是写入/追加。

退出码: 0 成功; 2 用法错误; 3 case 文件不可读。
"""
import argparse
import datetime
import json
import os
import sys

MD_ALIASES = {
    "risk_register.md": ["风险登记表", "risk_register"],
    "ethics_paths.md": ["伦理审批路径", "ethics_paths"],
    "conditions_list.md": ["条件清单", "condition_list"],
}
MERGE_ALL_JSON = {"overall_verdict.json"}  # 这些文件的顶层键全部参与按名合并


def find_keys(obj, needles, first_scalar=False):
    hits = []

    def rec(o):
        if isinstance(o, dict):
            for k, v in o.items():
                kl = str(k).lower()
                if any(n in kl for n in needles):
                    hits.append(v)
                rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)
    rec(obj)
    return hits


def case_id_of(case):
    ids = find_keys(case, ["case_id", "caseid", "case-id"])
    for v in ids:
        if isinstance(v, (str, int)):
            return v
    return None


def contract_fields_of(case):
    fields = []
    for v in find_keys(case, ["output_contract", "输出契约"]):
        if isinstance(v, dict):
            fields += [str(k) for k in v.keys()]
        elif isinstance(v, list):
            fields += [str(x) for x in v]
        elif isinstance(v, str):
            fields.append(v)
    seen, out = set(), []
    for f in fields:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def load_artifacts(adir, contract):
    """返回 (contract_candidates, free_candidates, manifest)。
    contract_candidates 只用于填充契约字段（含已知别名）；free_candidates 还可补充非契约顶层键。"""
    contract_candidates, free_candidates, manifest = {}, {}, []
    if not os.path.isdir(adir):
        return contract_candidates, free_candidates, manifest
    for name in sorted(os.listdir(adir)):
        path = os.path.join(adir, name)
        if not os.path.isfile(path):
            continue
        manifest.append(name)
        if name.endswith(".json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    doc = json.load(f)
            except ValueError:
                continue
            if not isinstance(doc, dict):
                continue
            if name == "ranking.json":
                rank = doc.get("版本排序", doc)
                contract_candidates.setdefault("版本排序", rank)
                contract_candidates.setdefault("version_ranking", rank)
            elif name in MERGE_ALL_JSON:
                for k, v in doc.items():
                    free_candidates.setdefault(k, v)
            else:
                for k, v in doc.items():
                    if k in contract:
                        contract_candidates.setdefault(k, v)
        elif name.endswith(".md"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                continue
            for key in MD_ALIASES.get(name, []):
                contract_candidates.setdefault(key, text)
    return contract_candidates, free_candidates, manifest


def main(argv):
    ap = argparse.ArgumentParser(description="汇总 result.json")
    ap.add_argument("--case", required=True)
    ap.add_argument("--artifacts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--status", required=True, choices=["complete", "partial", "failed"])
    ap.add_argument("--note", default="")
    args = ap.parse_args(argv[1:])

    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, ValueError) as e:
        sys.stderr.write("错误: 无法读取或解析 %s: %s\n" % (args.case, e))
        return 3

    case_id = case_id_of(case)
    contract = contract_fields_of(case)
    contract_cands, free_cands, manifest = load_artifacts(args.artifacts, contract)
    candidates = dict(contract_cands)
    candidates.update({k: v for k, v in free_cands.items() if k not in candidates})

    result = {}
    if os.path.exists(args.out):
        try:
            with open(args.out, "r", encoding="utf-8") as f:
                result = json.load(f)
        except (OSError, ValueError):
            result = {}

    # case_id 与契约字段：只填空（never overwrite non-null）
    result.setdefault("case_id", case_id)
    if result.get("case_id") is None:
        result["case_id"] = case_id
    for field in contract:
        result.setdefault(field, None)

    filled, still_null = [], []
    for field in contract:
        if result.get(field) is None and field in candidates and candidates[field] is not None:
            result[field] = candidates[field]
            filled.append(field)
        if result.get(field) is None:
            still_null.append(field)

    # 顶层非契约键：仅来自 free_candidates（如 overall_verdict.json 的「总体裁决」），只填空
    for k, v in free_cands.items():
        if k not in contract and k not in result and v is not None:
            result[k] = v
            filled.append(k)

    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    result["status"] = args.status
    result.setdefault("sources", [])
    result["sources"] = sorted(set(result["sources"]) |
                               {os.path.abspath(args.case)} |
                               {os.path.join(os.path.abspath(args.artifacts), m) for m in manifest})
    result.setdefault("uncertainty", [])
    for field in still_null:
        msg = "契约字段「%s」未能从产物合并，保持 null（不编造）。" % field
        if msg not in result["uncertainty"]:
            result["uncertainty"].append(msg)
    if args.note and args.note not in result["uncertainty"]:
        result["uncertainty"].append(args.note)
    result.setdefault("change_record", [])
    result["change_record"].append({
        "time": now, "actor": "assemble_result.py",
        "action": "merge artifacts into result.json",
        "filled_fields": filled, "still_null": still_null,
        "status": args.status, "note": args.note})

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("assemble_result 完成: case_id=%s, 契约字段 %d 个（填充 %d / 仍空 %d）, status=%s -> %s" % (
        result.get("case_id"), len(contract), len([f for f in filled if f in contract]),
        len(still_null), args.status, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
