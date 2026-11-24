#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_probe.py — 解析 /input 下的 case.json 与 task.md，提取交付契约。

纯标准库、无网络、确定性输出。

用法：
    python3 contract_probe.py --input-dir /input --work-dir /app/work

输出 <work-dir>/contract.json：
{
  "case_id": "...",                      # 缺失时为 null 并在 unrecognized 说明
  "contract_source": "output_contract",  # 实际命中位置/键名；未命中为 null
  "contract_fields": [
    {"name": "...", "type_guess": "...", "required": true/false,
     "semantic_guess": "...", "declared": <契约中的原始声明>}
  ],
  "task_constraints": {                  # 从 task.md 提取的要点（提取不到则为空串）
    "genre": "...", "audience": "...", "format": "...",
    "length": "...", "raw_headings": [...]
  },
  "materials": [...],                    # /input 下除 case.json/task.md 外的材料文件
  "unrecognized": [...]                  # 诚实清单：未能解析/未能识别的内容
}
"""
import argparse
import json
import os
import re
import sys

CONTRACT_KEY_VARIANTS = ("output_contract", "outputContract", "output-contract",
                         "output contract", "deliverables", "deliverable_contract")

# 语义猜测用的关键词表（命中则给出猜测，否则标 unknown，绝不编造）
SEMANTIC_HINTS = [
    (("artifact", "essay", "chapter", "paper", "document", "report", "manuscript"),
     "主要产物（章节正文或其文件路径）"),
    (("source", "citation", "reference", "provenance"),
     "来源定位（引用材料的文件与位置）"),
    (("uncertain", "ambigu", "caveat"),
     "不确定性声明"),
    (("change", "edit", "revision", "modification", "diff"),
     "修改记录"),
    (("status", "state"),
     "任务完成状态"),
    (("review", "human", "confirm", "approval"),
     "需人工确认项"),
    (("preview", "render", "image", "figure", "svg", "pdf", "png"),
     "渲染预览产物"),
    (("dataset", "data", "split"),
     "数据集与划分说明"),
    (("param", "config", "hyper"),
     "参数与来源"),
    (("metric", "result", "score", "evaluation", "benchmark"),
     "结果或评测指标"),
    (("baseline", "control", "ablation", "comparison"),
     "对照设置"),
    (("reproduc", "seed", "environment"),
     "复现信息"),
    (("limit", "threat", "valid"),
     "局限性说明"),
]

GENRE_RE = re.compile(r"(体裁|genre|文体|写作类型|章节类型)\s*[:：]\s*(.+)", re.I)
AUDIENCE_RE = re.compile(r"(受众|读者|audience|readers?)\s*[:：]\s*(.+)", re.I)
FORMAT_RE = re.compile(r"(格式|format|格式要求|输出格式|模板)\s*[:：]\s*(.+)", re.I)
LENGTH_RE = re.compile(r"(篇幅|长度|字数|length|words?)\s*[:：]\s*(.+)", re.I)


def _type_guess(declared):
    """由契约声明猜测字段类型。"""
    if isinstance(declared, dict):
        t = declared.get("type") or declared.get("kind")
        if isinstance(t, str):
            return t.lower()
        return "object"
    if isinstance(declared, list):
        return "array"
    if isinstance(declared, str):
        s = declared.strip().lower()
        for t in ("string", "number", "integer", "boolean", "array", "object", "file", "path"):
            if t in s:
                return t
        return "string"
    if declared is None:
        return "unknown"
    return type(declared).__name__


def _required_guess(name, declared):
    if isinstance(declared, dict):
        for k in ("required", "mandatory", "optional"):
            if k in declared:
                v = declared[k]
                if isinstance(v, bool):
                    return v if k != "optional" else not v
        return True  # 契约中显式声明的字段默认按必填处理（保守）
    return True


def _semantic_guess(name, declared):
    low = name.lower()
    for keys, desc in SEMANTIC_HINTS:
        if any(k in low for k in keys):
            return desc
    if isinstance(declared, dict):
        d = declared.get("description") or declared.get("desc") or ""
        if isinstance(d, str) and d.strip():
            return "契约自述：" + d.strip()[:120]
    return "unknown（语义不明，交付时须保守填充并记录 assumption）"


def _find_contract(obj, path="$"):
    """深度优先搜索契约键，返回 (命中路径, 契约对象)。确定性：按键序遍历。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            norm = k.strip().lower().replace("_", "").replace("-", "").replace(" ", "")
            if norm in ("outputcontract", "deliverables", "deliverablecontract"):
                return path + "." + k, v
        for k, v in obj.items():
            hit = _find_contract(v, path + "." + str(k))
            if hit[0] is not None:
                return hit
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hit = _find_contract(v, "%s[%d]" % (path, i))
            if hit[0] is not None:
                return hit
    return None, None


def _fields_from_contract(contract, unrecognized):
    """把契约对象规整为字段清单。"""
    fields = []
    if isinstance(contract, dict):
        # 形态A：{"fields": {...}} 或 {"required": [...]}
        inner = None
        for key in ("fields", "properties", "schema"):
            if isinstance(contract.get(key), dict):
                inner = contract[key]
                break
        if inner is None and isinstance(contract.get("required"), list):
            inner = {n: {} for n in contract["required"]}
        if inner is None:
            inner = contract  # 形态B：字段名直接作为键
        for name, declared in inner.items():
            if not isinstance(name, str) or name in ("fields", "properties", "schema"):
                continue
            fields.append({
                "name": name,
                "type_guess": _type_guess(declared),
                "required": _required_guess(name, declared),
                "semantic_guess": _semantic_guess(name, declared),
                "declared": declared,
            })
    elif isinstance(contract, list):
        for item in contract:
            if isinstance(item, str):
                fields.append({"name": item, "type_guess": "unknown", "required": True,
                               "semantic_guess": _semantic_guess(item, item), "declared": item})
            elif isinstance(item, dict) and isinstance(item.get("name"), str):
                fields.append({"name": item["name"], "type_guess": _type_guess(item),
                               "required": _required_guess(item["name"], item),
                               "semantic_guess": _semantic_guess(item["name"], item),
                               "declared": item})
            else:
                unrecognized.append("契约列表项无法识别为字段：%r" % (item,))
    else:
        unrecognized.append("output_contract 不是对象或列表（实际类型 %s），无法提取字段"
                            % type(contract).__name__)
    return fields


def _parse_case(input_dir, unrecognized):
    path = os.path.join(input_dir, "case.json")
    if not os.path.isfile(path):
        unrecognized.append("case.json 不存在于 %s" % input_dir)
        return None, None, None
    try:
        with open(path, "r", encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        unrecognized.append("case.json 读取/解析失败：%s" % e)
        return None, None, None
    case_id = case.get("case_id") if isinstance(case, dict) else None
    if case_id is None and isinstance(case, dict):
        for k in ("caseId", "case-id", "id"):
            if k in case:
                case_id = case[k]
                unrecognized.append("case_id 使用变体键 %r" % k)
                break
    if case_id is None:
        unrecognized.append("case.json 中未找到 case_id")
    src, contract = _find_contract(case)
    if src is None:
        unrecognized.append("未找到 output_contract（含命名变体与嵌套搜索）")
    return case_id, src, contract


def _parse_task(input_dir, unrecognized):
    path = os.path.join(input_dir, "task.md")
    info = {"genre": "", "audience": "", "format": "", "length": "", "raw_headings": []}
    if not os.path.isfile(path):
        unrecognized.append("task.md 不存在于 %s" % input_dir)
        return info
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        unrecognized.append("task.md 读取失败：%s" % e)
        return info
    for line in text.splitlines():
        m = re.match(r"^#{1,4}\s+(.*)$", line)
        if m:
            info["raw_headings"].append(m.group(1).strip())
            continue
        for regex, key in ((GENRE_RE, "genre"), (AUDIENCE_RE, "audience"),
                           (FORMAT_RE, "format"), (LENGTH_RE, "length")):
            m = regex.search(line)
            if m and not info[key]:
                info[key] = m.group(2).strip()
    if not text.strip():
        unrecognized.append("task.md 为空")
    return info


def _list_materials(input_dir):
    materials = []
    for root, dirs, files in os.walk(input_dir):
        dirs.sort()
        for fn in sorted(files):
            rel = os.path.relpath(os.path.join(root, fn), input_dir)
            if rel in ("case.json", "task.md"):
                continue
            materials.append(rel)
    return materials


def main(argv=None):
    ap = argparse.ArgumentParser(description="解析 case.json/task.md，输出 contract.json")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--work-dir", required=True)
    args = ap.parse_args(argv)

    unrecognized = []
    if not os.path.isdir(args.input_dir):
        print("ERROR: 输入目录不存在：%s" % args.input_dir, file=sys.stderr)
        return 2

    case_id, src, contract_obj = _parse_case(args.input_dir, unrecognized)
    fields = _fields_from_contract(contract_obj, unrecognized) if contract_obj is not None else []
    task = _parse_task(args.input_dir, unrecognized)
    materials = _list_materials(args.input_dir)

    out = {
        "case_id": case_id,
        "contract_source": src,
        "contract_fields": fields,
        "task_constraints": task,
        "materials": materials,
        "unrecognized": unrecognized,
    }
    os.makedirs(args.work_dir, exist_ok=True)
    out_path = os.path.join(args.work_dir, "contract.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")
    print("OK: contract.json -> %s（case_id=%r，契约字段 %d 个，材料 %d 个，未识别 %d 项）"
          % (out_path, case_id, len(fields), len(materials), len(unrecognized)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
