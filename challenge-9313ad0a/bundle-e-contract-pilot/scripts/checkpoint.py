#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""checkpoint.py — 预算感知的中间检查点脚本（仅标准库，无网络，确定性输出）。

加载既有 result.json，应用一组更新，并向 change_record.md 追加一条
单调递增序号的对账记录。不使用时钟、不使用随机数。

关键规则：
  * --artifact 登记 {"name","path","exists","bytes"} 到 artifacts 列表（同名替换）；
    若 name 与某个仍为 "__pending__" 的契约字段同名，则以该路径填充该字段。
  * --set 仅允许写入契约字段；未知字段警告并跳过。
  * --status success 仅当无任何契约字段仍为 "__pending__" 时允许；
    否则强制回退为 partial 并追加说明。
  * --resolve-uncertainty 按 1 起始序号删除不确定性条目。
退出码：0 正常；2 result.json 缺失或不可解析。
"""

import argparse
import json
import os
import sys

PLACEHOLDER = "__pending__"
VALID_STATUS = ("success", "partial", "unable_to_determine", "refused")


def eprint(*args):
    print(*args, file=sys.stderr)


def split_kv(text, optname):
    if "=" not in text:
        raise argparse.ArgumentTypeError("%s 需要 NAME=VALUE 形式: %s" % (optname, text))
    name, value = text.split("=", 1)
    name = name.strip()
    if not name:
        raise argparse.ArgumentTypeError("%s 名称不能为空: %s" % (optname, text))
    return name, value


def parse_scalar(value):
    """尽量把 --set 的值解析为 JSON 标量，失败则按字符串处理。"""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value
    if isinstance(parsed, (str, int, float, bool)) or parsed is None:
        return parsed
    return value


def load_result(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, "result.json 顶层不是对象"
    return data, None


def pending_fields(result, contract_fields):
    return [f for f in contract_fields if result.get(f) == PLACEHOLDER]


def main(argv=None):
    parser = argparse.ArgumentParser(description="检查点：更新 result.json 并追加 change_record")
    parser.add_argument("--out", required=True, help="输出目录，如 /app/output")
    parser.add_argument("--status", choices=VALID_STATUS, default=None)
    parser.add_argument("--set", dest="sets", action="append", default=[],
                        type=lambda s: split_kv(s, "--set"), metavar="FIELD=VALUE")
    parser.add_argument("--artifact", dest="artifacts", action="append", default=[],
                        type=lambda s: split_kv(s, "--artifact"), metavar="NAME=PATH")
    parser.add_argument("--uncertainty", dest="uncertainties", action="append",
                        default=[], metavar="TEXT")
    parser.add_argument("--resolve-uncertainty", dest="resolutions", action="append",
                        default=[], type=int, metavar="INDEX")
    parser.add_argument("--source", dest="sources", action="append", default=[],
                        metavar="PATH")
    parser.add_argument("--note", default=None, metavar="TEXT")
    args = parser.parse_args(argv)

    result_path = os.path.join(args.out, "result.json")
    result, err = load_result(result_path)
    if result is None:
        eprint("[checkpoint] ERROR: 无法加载 %s: %s（请先运行 contract_boot.py）" % (result_path, err))
        return 2

    contract_fields = result.get("contract_fields")
    if not isinstance(contract_fields, list):
        contract_fields = []
    contract_set = set(contract_fields)

    added_artifacts = []
    replaced_artifacts = []
    added_unc = 0
    resolved_unc = 0
    notes = []

    # ---- sources ----
    sources = result.get("sources")
    if not isinstance(sources, list):
        sources = []
    for src in args.sources:
        if src not in sources:
            sources.append(src)
    result["sources"] = sources

    # ---- --set：仅契约字段 ----
    for field, raw_value in args.sets:
        if field not in contract_set:
            eprint("[checkpoint] WARNING: --set 拒绝未知字段（不在 contract_fields 内）: %s" % field)
            notes.append("拒绝写入未知字段 %s" % field)
            continue
        result[field] = parse_scalar(raw_value)

    # ---- artifacts ----
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list):
        artifacts = []
    for name, path in args.artifacts:
        exists = os.path.isfile(path)
        nbytes = os.path.getsize(path) if exists else 0
        if not exists:
            eprint("[checkpoint] WARNING: artifact 路径不存在: %s (%s)" % (path, name))
            notes.append("artifact %s 路径不存在" % name)
        entry = {"name": name, "path": path, "exists": exists, "bytes": nbytes}
        for i, old in enumerate(artifacts):
            if isinstance(old, dict) and old.get("name") == name:
                artifacts[i] = entry
                replaced_artifacts.append(name)
                break
        else:
            artifacts.append(entry)
            added_artifacts.append(name)
        # 同名契约字段仍处于占位状态则以路径填充
        if name in contract_set and result.get(name) == PLACEHOLDER:
            result[name] = path
    result["artifacts"] = artifacts

    # ---- uncertainty ----
    uncertainty = result.get("uncertainty")
    if not isinstance(uncertainty, list):
        uncertainty = []
    for text in args.uncertainties:
        uncertainty.append(text)
        added_unc += 1
    for index in args.resolutions:
        if 1 <= index <= len(uncertainty):
            uncertainty.pop(index - 1)
            resolved_unc += 1
        else:
            eprint("[checkpoint] WARNING: --resolve-uncertainty 序号越界: %d（当前 %d 条）" % (
                index, len(uncertainty)))
            notes.append("uncertainty 序号 %d 越界，未删除" % index)
    result["uncertainty"] = uncertainty

    # ---- status 转移校验 ----
    if args.status is not None:
        pending = pending_fields(result, contract_fields)
        if args.status == "success" and pending:
            result["status"] = "partial"
            refusal = ("checkpoint: 请求 success 被拒绝——契约字段仍为占位: %s；状态保持 partial"
                       % ", ".join(pending))
            prev = result.get("partial_reason")
            result["partial_reason"] = ("%s；%s" % (prev, refusal)) if isinstance(prev, str) and prev else refusal
            notes.append(refusal)
            eprint("[checkpoint] WARNING: %s" % refusal)
        else:
            result["status"] = args.status
            if args.status == "success":
                result.pop("partial_reason", None)

    if args.note:
        notes.append(args.note)

    with open(result_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    # ---- change_record.md：单调序号，无时间戳 ----
    record_path = os.path.join(args.out, "change_record.md")
    seq = 1
    existing_lines = []
    if os.path.isfile(record_path):
        with open(record_path, "r", encoding="utf-8") as fh:
            existing_lines = [ln for ln in fh.read().splitlines() if ln.strip().startswith("- seq ")]
        seq = len(existing_lines) + 1

    art_parts = ["+%s" % n for n in added_artifacts] + ["~%s" % n for n in replaced_artifacts]
    art_text = " ".join(art_parts) if art_parts else "-"
    unc_text = "+%d/-%d" % (added_unc, resolved_unc)
    note_text = " | ".join(notes) if notes else "-"
    line = "- seq %d | status: %s | artifacts: %s | uncertainty: %s | note: %s" % (
        seq, result.get("status", "?"), art_text, unc_text, note_text)

    if not existing_lines and not os.path.isfile(record_path):
        with open(record_path, "w", encoding="utf-8") as fh:
            fh.write("# change record（变更对账记录，序号为单调序号，不含时间戳）\n\n")
            fh.write(line + "\n")
    else:
        with open(record_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    print("[checkpoint] seq=%d status=%s artifacts=%s uncertainty=%s" % (
        seq, result.get("status", "?"), art_text, unc_text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
