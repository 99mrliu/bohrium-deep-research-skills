#!/usr/bin/env python3
"""fill_result.py — 把 agent 的工作文件按 output_contract 填入 result.json。

约定：
  * 工作目录（默认 /app/work）下依次查找 answers.json、items.json、evidence_map.json。
  * 工作文件为 JSON 对象时，顶层键名与契约字段名匹配即作为该字段的值来源；
    evidence_map.json 若无显式 "evidence_map" 键，则整个对象充作 evidence_map 字段；
    answers.json / items.json 为 JSON 数组时分别充作 "answers" / "item_bank"。
  * 逐字段校验：类型不符置 null 并记 uncertainty；字符串超过 8000 字符截断并加
    [TRUNCATED] 标记与告警；缺字段填 null 并记 uncertainty；绝不编造内容。
  * 生成 field_provenance：字段 -> 工作文件键 -> 证据锚点列表。
  * --init 模式：立即写合法的部分 result.json 骨架（所有契约字段为 null）。

确定性：无时间戳，change_records 用序号；原子写；绝不因畸形输入崩溃。
仅使用标准库（python3 >= 3.8）。
"""
import argparse
import json
import os
import sys
import tempfile

MAX_STR = 8000
WORK_FILES = ("answers.json", "items.json", "evidence_map.json")


def atomic_write_json(path, obj):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_json_safe(path):
    """读取 JSON，失败返回 (None, 错误说明)。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, "not_found"
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)


def type_ok(t, v):
    if v is None or t == "any":
        return True
    if t == "string":
        return isinstance(v, str)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "boolean":
        return isinstance(v, bool)
    if t == "array":
        return isinstance(v, list)
    if t == "object":
        return isinstance(v, dict)
    return True


def list_sources(input_dir):
    srcs = []
    try:
        for n in sorted(os.listdir(input_dir)):
            if n in ("case.json", "task.md"):
                continue
            p = os.path.join(input_dir, n)
            if os.path.isfile(p):
                srcs.append(p)
    except OSError:
        pass
    return srcs


def collect_candidates(work_dir):
    """扫描工作文件，返回 (candidates, evidence_index, notes)。

    candidates: {字段名: (value, work_file, work_key)}，按 answers > items >
    evidence_map 优先级（先到先得）。
    evidence_index: 证据锚点索引（dict: 键 -> 锚点列表），用于 provenance。
    """
    candidates = {}
    notes = []
    evidence_index = {}
    for fname in WORK_FILES:
        obj, err = load_json_safe(os.path.join(work_dir, fname))
        if obj is None:
            if err != "not_found":
                notes.append("工作文件 %s 解析失败(%s)，已跳过" % (fname, err))
            continue
        if isinstance(obj, dict):
            for k, v in obj.items():
                candidates.setdefault(str(k), (v, fname, str(k)))
            if fname == "evidence_map.json":
                inner = obj.get("evidence_map", obj)
                if isinstance(inner, dict):
                    evidence_index = inner
                candidates.setdefault("evidence_map",
                                      (inner, fname, "evidence_map"))
        elif isinstance(obj, list):
            if fname == "answers.json":
                candidates.setdefault("answers", (obj, fname, "<root>"))
            if fname == "items.json":
                candidates.setdefault("item_bank", (obj, fname, "<root>"))
    return candidates, evidence_index, notes


def anchors_for(field_name, evidence_index):
    """字段级证据锚点：item_bank 聚合全部 item_* 锚点，其余按键名取。"""
    if not isinstance(evidence_index, dict):
        return []
    if field_name == "item_bank":
        out = []
        for k in sorted(evidence_index):
            v = evidence_index[k]
            if isinstance(v, list):
                for a in v:
                    if isinstance(a, str) and a not in out:
                        out.append(a)
        return out
    v = evidence_index.get(field_name)
    if isinstance(v, list):
        return [a for a in v if isinstance(a, str)]
    return []


def truncate_check(value, field_name, warnings):
    """超长字符串截断（>8000 字符），返回处理后的值。"""
    if isinstance(value, str) and len(value) > MAX_STR:
        warnings.append("字段 %s 超长(%d 字符)，已截断至 %d 并加 [TRUNCATED] 标记"
                        % (field_name, len(value), MAX_STR))
        return value[:MAX_STR] + "…[TRUNCATED original_len=%d]" % len(value)
    return value


def build_skeleton(contract, sources):
    fields = contract.get("fields", []) if isinstance(contract, dict) else []
    result = {"case_id": contract.get("case_id", "UNKNOWN_CASE_ID")}
    for f in fields:
        result[f["name"]] = None
    result.update({
        "status": "无法判断",
        "status_reason": "初始化骨架：契约字段尚未填充，等待 agent 工作文件；"
                         "此为合法的部分结果，后续由 fill_result 增量完善。",
        "sources": sources,
        "uncertainty": [{"field": f["name"], "reason": "尚未填充（init 骨架）"}
                        for f in fields],
        "change_records": [{"seq": 1, "action": "init",
                            "detail": "写入合法部分 result.json 骨架，"
                                      "全部契约字段置 null"}],
        "field_provenance": {},
    })
    if contract.get("degraded"):
        result["uncertainty"].append(
            {"field": "<contract>", "reason": "contract degraded："
             "；".join(contract.get("notes", [])) or "未知原因"})
    return result


def fill(contract, work_dir, result_path, sources):
    fields = contract.get("fields", []) if isinstance(contract, dict) else []
    candidates, evidence_index, notes = collect_candidates(work_dir)

    old, _ = load_json_safe(result_path)
    if isinstance(old, dict) and isinstance(old.get("change_records"), list):
        change_records = old["change_records"]
    else:
        change_records = [{"seq": 1, "action": "init",
                           "detail": "（无既有骨架）由 fill 直接创建"}]

    result = {"case_id": contract.get("case_id", "UNKNOWN_CASE_ID")}
    uncertainty = []
    warnings = []
    provenance = {}
    null_fields = []
    filled = 0

    for f in fields:
        name, tguess = f["name"], f.get("type_guess", "any")
        required = bool(f.get("required", True))
        cand = candidates.get(name)
        if cand is None:
            result[name] = None
            if required:
                null_fields.append(name)
                uncertainty.append({"field": name,
                                    "reason": "工作文件中未提供该必填字段，"
                                              "按契约置 null，未编造内容"})
            continue
        value, work_file, work_key = cand
        if not type_ok(tguess, value):
            result[name] = None
            if required:
                null_fields.append(name)
            uncertainty.append({"field": name,
                                "reason": "类型不匹配（期望 %s，实际 %s），已置 null"
                                % (tguess, type(value).__name__)})
            continue
        value = truncate_check(value, name, warnings)
        result[name] = value
        filled += 1
        provenance[name] = {
            "work_file": os.path.join(work_dir, work_file),
            "work_key": work_key,
            "evidence_anchors": anchors_for(name, evidence_index),
        }

    for w in warnings:
        uncertainty.append({"field": "<truncation>", "reason": w})
    for n in notes:
        uncertainty.append({"field": "<work_files>", "reason": n})
    if contract.get("degraded"):
        uncertainty.append({"field": "<contract>",
                            "reason": "contract degraded："
                            + ("；".join(contract.get("notes", [])) or "未知")})

    if not fields:
        status, reason = "无法判断", "契约字段为空（degraded），仅保证 case_id"
    elif null_fields:
        status = "部分完成"
        reason = ("以下必填字段缺失，已置 null：%s；其余 %d 个字段已填充，"
                  "局限：缺失字段代表对应产出未完成，需 agent 补齐后重跑。"
                  % ("、".join(null_fields), filled))
    else:
        status, reason = "成功", "契约内全部 %d 个字段已填充并通过类型校验" % filled

    result.update({
        "status": status,
        "status_reason": reason,
        "sources": sources,
        "uncertainty": uncertainty,
        "change_records": change_records + [{
            "seq": len(change_records) + 1, "action": "fill",
            "detail": "填充 %d/%d 个契约字段；null 字段：%s"
                      % (filled, len(fields),
                         "、".join(null_fields) if null_fields else "无")}],
        "field_provenance": provenance,
    })
    atomic_write_json(result_path, result)
    print("fill_result: status=%s filled=%d/%d null=%s -> %s"
          % (status, filled, len(fields),
             "、".join(null_fields) if null_fields else "无", result_path))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="按 contract.json 把 agent 工作文件填入 result.json")
    ap.add_argument("--contract", default="/app/work/contract.json")
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--input-dir", default="/input")
    ap.add_argument("--init", action="store_true",
                    help="立即写合法的部分 result.json 骨架（字段全 null）")
    args = ap.parse_args(argv)

    contract, err = load_json_safe(args.contract)
    if not isinstance(contract, dict):
        contract = {"case_id": "UNKNOWN_CASE_ID", "degraded": True,
                    "fields": [],
                    "notes": ["contract.json 缺失或畸形(%s)" % (err or "?")]}
    sources = list_sources(args.input_dir)

    if args.init:
        atomic_write_json(args.result, build_skeleton(contract, sources))
        print("fill_result --init: 骨架已写入 %s（status=无法判断，字段全 null）"
              % args.result)
        return 0
    return fill(contract, args.work_dir, args.result, sources)


if __name__ == "__main__":
    sys.exit(main())
