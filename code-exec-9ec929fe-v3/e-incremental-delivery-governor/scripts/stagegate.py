#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stagegate.py —— 增量交付治理器（incremental delivery governor）。

在 900 秒 / 64 次模型请求的硬预算下，保证任何时刻中断，磁盘上都已存在一个
合法的 result.json：要么是 complete，要么是每个缺失字段都带理由的 partial。
本工具不提高任何单次计算的正确性，只保证交付的合法性与可审计性。

仅使用 Python 3.9+ 标准库：json, hashlib, argparse, pathlib, datetime,
subprocess, time, sys, os, shlex。
"""

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"
TRUNC_AT = 4000
BUDGET_SECONDS = 900
GOVERNOR_FIELDS = {"status", "anomalies", "provenance", "change_records", "missing_fields"}

BUDGET_PLAN_TEMPLATE = """# 预算分配建议（900 秒 / 64 次模型请求）

| 阶段 | 时间预算 | 请求预算 | 说明 |
| --- | --- | --- | --- |
| init 落盘骨架 | ≤ 60 秒 | 第 0 个模型请求内完成 | 先写合法骨架，再开始任何计算 |
| 数据摄入与画像 | ≤ 10%（90 秒） | ≤ 8 次 | 读数据字典、sha256、行数、缺失画像 |
| 核心计算 | ≤ 60%（540 秒） | ≤ 36 次 | 每个子阶段修复重试 ≤ 2 次，超限即记 anomaly 并降级 |
| 校验与复核 | ≤ 20%（180 秒） | ≤ 10 次 | 对账契约字段、证据文件、数值合理性 |
| finalize 预留 | ≥ 90 秒 | ≥ 4 次 | 任何情况下不得挪用；到点立即 finalize |

规则：阶段切换前执行一次 checkpoint；命令一律经 `stagegate.py run` 包裹；
字段填充一律经 `stagegate.py set` 并附 evidence；任何覆盖都会留下 change_records。
"""


# ---------------------------------------------------------------- 基础工具

def utcnow():
    """当前 UTC 时间，ISO 8601 秒级精度（+00:00 形式，Python 3.9 可解析）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_ts(text):
    """解析 ISO 时间戳，容忍 Z 结尾。"""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_obj(obj):
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def truncate(text):
    if text is None:
        return ""
    if len(text) > TRUNC_AT:
        return text[:TRUNC_AT] + "\n...[truncated %d chars]" % (len(text) - TRUNC_AT)
    return text


def eprint(*args):
    print(*args, file=sys.stderr)


# ---------------------------------------------------------------- 状态读写

def parse_contract(raw):
    """容忍 output_contract 为名字列表或字典两种形态，返回字段名列表。"""
    if raw is None:
        return []
    if isinstance(raw, dict):
        for key in ("fields", "required", "required_fields"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
        else:
            return [str(k) for k in raw.keys()]
    names = []
    for item in raw:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            for key in ("name", "field", "key"):
                if key in item:
                    names.append(str(item[key]))
                    break
    return names


def result_path(output_dir):
    return Path(output_dir) / "result.json"


def load_result(output_dir):
    path = result_path(output_dir)
    if not path.exists():
        eprint("error: %s 不存在；请先执行 init" % path)
        sys.exit(2)
    return json.loads(path.read_text(encoding="utf-8"))


def save_result(output_dir, result):
    path = result_path(output_dir)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def contract_of(result):
    prov = result.get("provenance") or {}
    return list(prov.get("output_contract_fields") or [])


def missing_fields_of(result):
    return result.setdefault("missing_fields", [])


# ---------------------------------------------------------------- init

def cmd_init(args):
    case_path = Path(args.case)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    rpath = result_path(out)
    if rpath.exists() and not args.force:
        eprint(
            "refuse: %s 已存在（保护既有进度）；如确需重来，使用 --force" % rpath
        )
        return 2

    case = json.loads(case_path.read_text(encoding="utf-8"))
    contract = parse_contract(case.get("output_contract"))
    started = utcnow()

    provenance = {
        "tool": "stagegate %s" % VERSION,
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "started_utc": started,
        "case_json_sha256": sha256_file(case_path),
        "output_contract_fields": contract,
        "budget_seconds": BUDGET_SECONDS,
    }

    result = {"case_id": case.get("case_id")}
    missing = []
    for field in contract:
        if field == "case_id":
            if result["case_id"] is None:
                missing.append({"field": field, "reason": "case.json 未提供 case_id"})
            continue
        if field in GOVERNOR_FIELDS:
            continue  # 治理字段由本工具自动维护，恒为非 null
        result[field] = None
        missing.append({"field": field, "reason": "not yet computed"})

    result["status"] = "in_progress"
    result["anomalies"] = []
    result["provenance"] = provenance
    result["change_records"] = [
        {
            "ts": started,
            "field": None,
            "action": "init",
            "evidence": None,
            "note": "skeleton created from output_contract (%d fields)" % len(contract),
        }
    ]
    result["missing_fields"] = missing

    save_result(out, result)
    (out / "budget_plan.md").write_text(BUDGET_PLAN_TEMPLATE, encoding="utf-8")
    print(
        "init ok: %s（契约字段 %d 个，待填 %d 个）"
        % (rpath, len(contract), len(missing))
    )
    return 0


# ---------------------------------------------------------------- set / reason / anomaly

def cmd_set(args):
    result = load_result(args.output)
    contract = contract_of(result)

    if args.field in GOVERNOR_FIELDS:
        eprint(
            "warning: 字段 '%s' 由治理器自动维护，不接受 set；跳过" % args.field
        )
        return 2

    if args.value_file is not None:
        try:
            value = json.loads(Path(args.value_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            eprint("error: --value-file 读取或解析失败：%s" % exc)
            return 2
    else:
        try:
            value = json.loads(args.value_json)
        except json.JSONDecodeError as exc:
            eprint("error: --value-json 不是合法 JSON：%s" % exc)
            return 2

    ts = utcnow()
    if contract and args.field not in contract:
        warning = "字段 '%s' 不在 output_contract 中，已转存 extras" % args.field
        eprint("warning: " + warning)
        extras = result.setdefault("extras", {})
        previous = extras.get(args.field)
        extras[args.field] = value
        record = {
            "ts": ts,
            "field": args.field,
            "action": "set_extra",
            "evidence": args.evidence,
            "note": warning,
        }
        if previous is not None:
            record["previous_sha256"] = sha256_obj(previous)
        result["change_records"].append(record)
    else:
        previous = result.get(args.field)
        action = "set" if previous is None else "overwrite"
        result[args.field] = value
        result["missing_fields"] = [
            m for m in missing_fields_of(result) if m.get("field") != args.field
        ]
        record = {"ts": ts, "field": args.field, "action": action, "evidence": args.evidence}
        if action == "overwrite":
            record["previous_sha256"] = sha256_obj(previous)
            record["note"] = "覆盖旧值（留痕，不删除历史）"
        result["change_records"].append(record)

    save_result(args.output, result)
    print("set ok: %s（evidence=%s）" % (args.field, args.evidence))
    return 0


def cmd_reason(args):
    result = load_result(args.output)
    for entry in missing_fields_of(result):
        if entry.get("field") == args.field:
            entry["reason"] = args.text
            result["change_records"].append(
                {
                    "ts": utcnow(),
                    "field": args.field,
                    "action": "reason",
                    "evidence": None,
                    "note": args.text,
                }
            )
            save_result(args.output, result)
            print("reason ok: %s" % args.field)
            return 0
    eprint("error: 字段 '%s' 不在 missing_fields 中（可能已填充或不存在）" % args.field)
    return 2


def cmd_anomaly(args):
    result = load_result(args.output)
    result.setdefault("anomalies", []).append(
        {"ts": utcnow(), "kind": args.kind, "detail": args.detail}
    )
    save_result(args.output, result)
    print("anomaly recorded: %s" % args.kind)
    return 0


# ---------------------------------------------------------------- run

def cmd_run(args):
    cmd = list(args.cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        eprint("error: run 需要在 -- 之后给出真实命令")
        return 2

    journal_path = Path(args.journal)
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    start = utcnow()
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        exit_code = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
    except FileNotFoundError as exc:
        exit_code = 127
        stdout, stderr = "", "command not found: %s" % exc
    duration = time.monotonic() - t0

    entry = {
        "ts_start": start,
        "ts_end": utcnow(),
        "duration_s": round(duration, 3),
        "cmd": cmd,
        "cmd_str": shlex.join(cmd),
        "exit_code": exit_code,
        "stdout": truncate(stdout),
        "stderr": truncate(stderr),
    }
    with open(journal_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    if exit_code != 0:
        try:
            result = load_result(args.output)
        except SystemExit:
            result = None
        if result is not None:
            result.setdefault("anomalies", []).append(
                {
                    "ts": utcnow(),
                    "kind": "stage_command_failed",
                    "detail": "%s exited %d" % (shlex.join(cmd), exit_code),
                }
            )
            save_result(args.output, result)

    print(
        "run done: exit=%d duration=%.3fs cmd=%s"
        % (exit_code, duration, shlex.join(cmd))
    )
    return exit_code  # 透明传递子进程退出码


# ---------------------------------------------------------------- checkpoint / status

def cmd_checkpoint(args):
    rpath = result_path(args.output)
    if not rpath.exists():
        eprint("error: %s 不存在；请先执行 init" % rpath)
        return 2
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    chain_path = work / "checkpoints.jsonl"

    prev = None
    if chain_path.exists():
        lines = chain_path.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            prev = json.loads(lines[-1]).get("result_sha256")

    digest = sha256_file(rpath)
    entry = {
        "ts": utcnow(),
        "note": args.note,
        "result_sha256": digest,
        "prev_sha256": prev,
    }
    with open(chain_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print("checkpoint ok: %s（prev=%s）" % (digest[:12], (prev or "genesis")[:12]))
    return 0


def cmd_status(args):
    result = load_result(args.output)
    contract = contract_of(result)
    filled, unfilled = [], []
    for field in contract:
        if field in GOVERNOR_FIELDS:
            continue
        if result.get(field) is None:
            unfilled.append(field)
        else:
            filled.append(field)

    anomalies = result.get("anomalies") or []
    prov = result.get("provenance") or {}
    started = prov.get("started_utc")
    elapsed = (datetime.now(timezone.utc) - parse_ts(started)).total_seconds() if started else None

    last_ck = "（无）"
    chain_path = Path(args.work) / "checkpoints.jsonl"
    if chain_path.exists():
        lines = chain_path.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            entry = json.loads(lines[-1])
            last_ck = "%s note=%s" % (entry["result_sha256"][:12], entry.get("note"))

    total = len(filled) + len(unfilled)
    print("case_id: %s" % result.get("case_id"))
    print("status: %s" % result.get("status"))
    print("字段填充: %d/%d；未填: %s" % (len(filled), total, ", ".join(unfilled) or "（无）"))
    print("anomalies: %d 条" % len(anomalies))
    print("最近 checkpoint: %s" % last_ck)
    if elapsed is not None:
        print("已用时: %.0f 秒 / 预算 %d 秒" % (elapsed, BUDGET_SECONDS))
        remaining = BUDGET_SECONDS - elapsed
        if remaining <= 90:
            hint = "立即 finalize：预留时间已到，不得再启动新计算"
        elif remaining <= 240:
            hint = "停止开新子阶段；为未填字段写 reason，做一次 checkpoint，准备 finalize"
        elif unfilled:
            hint = "按预算表推进；下一个子阶段开始前先 checkpoint"
        else:
            hint = "字段已填满，进入校验与 finalize"
        print("建议: %s" % hint)
    return 0


# ---------------------------------------------------------------- finalize

def cmd_finalize(args):
    result = load_result(args.output)
    contract = contract_of(result)
    out = Path(args.output)

    # 1) 静默 null 校验：每个契约字段要么非 null，要么 missing_fields 里有非空理由
    reasons = {
        m.get("field"): (m.get("reason") or "").strip() for m in missing_fields_of(result)
    }
    invalid, still_missing = [], []
    for field in contract:
        if field in GOVERNOR_FIELDS:
            continue
        if result.get(field) is None:
            if reasons.get(field):
                still_missing.append(field)
            else:
                invalid.append(field)

    # 2) case_id 与 case.json 一致性（如提供 --case）
    if args.case:
        case = json.loads(Path(args.case).read_text(encoding="utf-8"))
        if result.get("case_id") != case.get("case_id"):
            result.setdefault("anomalies", []).append(
                {
                    "ts": utcnow(),
                    "kind": "case_id_mismatch",
                    "detail": "result.case_id=%r != case.json case_id=%r"
                    % (result.get("case_id"), case.get("case_id")),
                }
            )
            invalid.append("case_id")

    # 3) 证据文件存在性（尽力而为，只警告不判负）
    for record in result.get("change_records") or []:
        ev = record.get("evidence")
        if ev and isinstance(ev, str) and not (out / ev).exists():
            eprint("warning: 证据文件不存在（不判负）：%s（字段 %s）" % (ev, record.get("field")))

    if invalid:
        save_result(args.output, result)
        eprint(
            "finalize INVALID: 以下字段为 null 且缺少理由（静默 null 不被接受）：%s"
            % ", ".join(invalid)
        )
        eprint("修复方法：stagegate.py set 填值，或 stagegate.py reason 写明原因后重试")
        return 1

    status = "complete" if not still_missing else "partial"
    result["status"] = status
    result["change_records"].append(
        {
            "ts": utcnow(),
            "field": None,
            "action": "finalize",
            "evidence": None,
            "note": "status=%s；未填字段=%s" % (status, ", ".join(still_missing) or "（无）"),
        }
    )
    save_result(args.output, result)
    write_delivery_summary(args, result, contract, still_missing)
    print("finalize ok: status=%s（exit %d）" % (status, 0 if status == "complete" else 4))
    return 0 if status == "complete" else 4


def write_delivery_summary(args, result, contract, still_missing):
    out = Path(args.output)
    reasons = {
        m.get("field"): m.get("reason") for m in result.get("missing_fields") or []
    }
    last_evidence = {}
    for record in result.get("change_records") or []:
        if record.get("field") and record.get("evidence"):
            last_evidence[record["field"]] = record["evidence"]

    lines = []
    lines.append("# 交付摘要（delivery summary）")
    lines.append("")
    lines.append("- case_id: %s" % result.get("case_id"))
    lines.append("- 状态: **%s**" % result.get("status"))
    lines.append("- finalize 时间(UTC): %s" % utcnow())
    prov = result.get("provenance") or {}
    lines.append("- 输入 case.json sha256: `%s`" % prov.get("case_json_sha256"))
    lines.append("- 工具: %s；Python %s；平台 %s" % (prov.get("tool"), prov.get("python_version"), prov.get("platform")))
    lines.append("")

    lines.append("## 字段明细")
    lines.append("")
    lines.append("| 字段 | 状态 | 证据 | 缺失原因 |")
    lines.append("| --- | --- | --- | --- |")
    for field in contract:
        if field in GOVERNOR_FIELDS:
            state = "治理器维护"
            lines.append("| %s | %s | — | — |" % (field, state))
            continue
        if result.get(field) is None:
            lines.append("| %s | 缺失 | — | %s |" % (field, reasons.get(field, "")))
        else:
            lines.append("| %s | 已填充 | %s | — |" % (field, last_evidence.get(field, "（无）")))
    lines.append("")

    lines.append("## 异常（anomalies，%d 条）" % len(result.get("anomalies") or []))
    lines.append("")
    for a in result.get("anomalies") or []:
        lines.append("- [%s] %s：%s" % (a.get("ts"), a.get("kind"), a.get("detail")))
    if not result.get("anomalies"):
        lines.append("- （无）")
    lines.append("")

    lines.append("## 命令日志摘要（journal digest）")
    lines.append("")
    journal_path = Path(args.journal)
    entries = []
    if journal_path.exists():
        for line in journal_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    failures = [e for e in entries if e.get("exit_code") != 0]
    total_s = sum(e.get("duration_s", 0.0) for e in entries)
    lines.append("- 命令总数: %d；失败: %d；总耗时: %.3f 秒" % (len(entries), len(failures), total_s))
    lines.append("")
    if entries:
        lines.append("| # | exit | duration_s | cmd |")
        lines.append("| --- | --- | --- | --- |")
        for i, e in enumerate(entries, 1):
            lines.append("| %d | %d | %.3f | `%s` |" % (i, e.get("exit_code"), e.get("duration_s", 0.0), e.get("cmd_str", "")))
        lines.append("")

    if still_missing:
        lines.append("## 本次 partial 的边界")
        lines.append("")
        for field in still_missing:
            lines.append("- `%s`：%s" % (field, reasons.get(field, "")))
        lines.append("")

    (out / "delivery_summary.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- argparse

def build_parser():
    parser = argparse.ArgumentParser(
        prog="stagegate.py",
        description="增量交付治理器：骨架先行、证据填充、命令日志、链式校验、诚实 finalize",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="从 case.json 生成 result.json 骨架与 budget_plan.md")
    p.add_argument("--case", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--force", action="store_true", help="覆盖已存在的 result.json")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("set", help="填充一个契约字段（带证据，覆盖留痕）")
    p.add_argument("--output", required=True)
    p.add_argument("--field", required=True)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--value-json", help="JSON 字面值")
    group.add_argument("--value-file", help="从文件读取 JSON 值（适合大对象）")
    p.add_argument("--evidence", default=None, help="证据文件相对路径（相对 output 目录）")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("reason", help="为未填字段写明缺失理由（诚实 partial 的依据）")
    p.add_argument("--output", required=True)
    p.add_argument("--field", required=True)
    p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_reason)

    p = sub.add_parser("anomaly", help="记录一条异常")
    p.add_argument("--output", required=True)
    p.add_argument("--kind", required=True)
    p.add_argument("--detail", required=True)
    p.set_defaults(func=cmd_anomaly)

    p = sub.add_parser("run", help="包裹执行真实命令并写日志（透明传递退出码）")
    p.add_argument("--output", required=True)
    p.add_argument("--journal", required=True, help="journal.jsonl 路径（建议置于 /app/work）")
    p.add_argument("cmd", nargs=argparse.REMAINDER, help="-- 之后的真实命令")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("checkpoint", help="对当前 result.json 做链式 sha256 校验")
    p.add_argument("--output", required=True)
    p.add_argument("--note", required=True)
    p.add_argument("--work", default="/app/work", help="checkpoints.jsonl 所在目录")
    p.set_defaults(func=cmd_checkpoint)

    p = sub.add_parser("status", help="打印填充进度与剩余预算建议")
    p.add_argument("--output", required=True)
    p.add_argument("--work", default="/app/work")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("finalize", help="校验并定稿（exit 0 complete / 4 partial / 1 invalid）")
    p.add_argument("--output", required=True)
    p.add_argument("--case", default=None, help="提供则校验 case_id 一致性")
    p.add_argument("--journal", default="/app/work/journal.jsonl")
    p.set_defaults(func=cmd_finalize)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
