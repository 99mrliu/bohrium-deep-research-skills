#!/usr/bin/env python3
"""journal_check.py — 运行日志可复跑校验(仅标准库)。

校验 references/journal_schema.md 定义的强制规则:
  1. 条目按 J-001 起连续编号、字段齐全、step 严格递增、timestamp 非递减;
  2. 声明的输出文件在 --output-dir 下存在且 sha256 一致
     (声明的输入文件在 --input-dir 下同样校验);
  3. 配合 --ledger 时,台账中状态非"未检查"的单元,其 journal_ref 必须指向
     存在的日志条目 id;journal_ref 若给出则必须存在;
  4. 末条必须 final: true 且 outputs 非空(明确声明交付文件)。

用法:
    python3 journal_check.py run_journal.jsonl --output-dir /app/output \
        [--input-dir DIR] [--ledger ledger.json]
存在任何违规时向 stderr 逐条报告并以非零码退出。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime

REQUIRED = ["id", "step", "action", "tool", "inputs", "outputs", "decision", "timestamp"]
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def sha256_file(path: str) -> str | None:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def check_file_list(entries_kind: str, files: object, base_dir: str, eid: str,
                    errors: list[str]) -> int:
    """校验一组 {path, sha256} 声明;返回声明的文件数。"""
    if not isinstance(files, list):
        errors.append(f"{eid}: {entries_kind} 必须是数组")
        return 0
    n = 0
    for j, item in enumerate(files):
        where = f"{eid} {entries_kind}[{j}]"
        if not isinstance(item, dict) or "path" not in item or "sha256" not in item:
            errors.append(f"{where}: 必须是含 path 与 sha256 的对象")
            continue
        n += 1
        digest = item["sha256"]
        if not isinstance(digest, str) or not HEX64.match(digest):
            errors.append(f"{where}: sha256 必须是 64 位小写十六进制")
            continue
        rel = item["path"]
        if not isinstance(rel, str) or rel.strip() == "":
            errors.append(f"{where}: path 必须是非空字符串")
            continue
        full = os.path.normpath(os.path.join(base_dir, rel))
        if not os.path.isfile(full):
            errors.append(f"{where}: 文件不存在: {full}")
            continue
        actual = sha256_file(full)
        if actual != digest:
            errors.append(
                f"{where}: sha256 不匹配(声明 {digest[:12]}…,实算 {str(actual)[:12]}…): {rel}"
            )
    return n


def main() -> int:
    ap = argparse.ArgumentParser(
        description="运行日志(JSONL)可复跑校验:顺序、字段、文件哈希、台账引用与交付声明。"
    )
    ap.add_argument("journal", help="run_journal.jsonl 路径")
    ap.add_argument("--output-dir", default=".",
                    help="日志中 outputs 相对路径的基准目录(默认当前目录)")
    ap.add_argument("--input-dir", default=None,
                    help="日志中 inputs 相对路径的基准目录(默认取 journal 所在目录)")
    ap.add_argument("--ledger", default=None,
                    help="可选:ledger.json 路径,用于交叉校验 journal_ref")
    args = ap.parse_args()

    errors: list[str] = []
    input_dir = args.input_dir or os.path.dirname(os.path.abspath(args.journal)) or "."

    try:
        with open(args.journal, "r", encoding="utf-8") as fh:
            raw_lines = fh.read().splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"FATAL: 无法读取 {args.journal}: {exc}", file=sys.stderr)
        return 2

    entries: list[dict] = []
    for ln, line in enumerate(raw_lines, 1):
        if line.strip() == "":
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"第 {ln} 行: JSON 解析失败: {exc}")
            continue
        if not isinstance(obj, dict):
            errors.append(f"第 {ln} 行: 条目必须是 JSON 对象")
            continue
        entries.append(obj)
    if not entries:
        errors.append("日志为空:没有任何有效条目")

    ids: set[str] = set()
    prev_step = 0
    prev_ts: datetime | None = None
    n_inputs = 0
    n_outputs = 0
    for idx, e in enumerate(entries, 1):
        eid = e.get("id", f"第{idx}条")
        for k in REQUIRED:
            if k not in e:
                errors.append(f"{eid}: 缺少必填字段 {k}")
        expect_id = f"J-{idx:03d}"
        if e.get("id") != expect_id:
            errors.append(f"第{idx}条: id 应为 {expect_id},实为 {e.get('id')!r}")
        if isinstance(e.get("id"), str):
            ids.add(e["id"])
        step = e.get("step")
        if not isinstance(step, int):
            errors.append(f"{eid}: step 必须是整数")
        elif step <= prev_step:
            errors.append(f"{eid}: step 必须严格递增(上一条 {prev_step},本条 {step})")
        else:
            prev_step = step
        ts = e.get("timestamp")
        if not isinstance(ts, str):
            errors.append(f"{eid}: timestamp 必须是 ISO 8601 字符串")
        else:
            try:
                parsed = datetime.fromisoformat(ts)
                if prev_ts is not None and parsed < prev_ts:
                    errors.append(f"{eid}: timestamp 早于上一条,违反非递减规则")
                prev_ts = parsed
            except ValueError:
                errors.append(f"{eid}: timestamp 无法按 ISO 8601 解析: {ts!r}")
        if not isinstance(e.get("decision"), str) or e.get("decision", "").strip() == "":
            errors.append(f"{eid}: decision 必须是非空字符串")
        n_inputs += check_file_list("inputs", e.get("inputs"), input_dir, eid, errors)
        n_outputs += check_file_list("outputs", e.get("outputs"), args.output_dir, eid, errors)

    if entries:
        last = entries[-1]
        lid = last.get("id", "末条")
        if last.get("final") is not True:
            errors.append(f"{lid}: 末条必须声明 final: true")
        if not isinstance(last.get("outputs"), list) or not last.get("outputs"):
            errors.append(f"{lid}: 末条 outputs 必须非空,以声明本轮交付的文件")

    if args.ledger:
        try:
            with open(args.ledger, "r", encoding="utf-8") as fh:
                led = json.load(fh)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"FATAL: 无法读取/解析 ledger {args.ledger}: {exc}", file=sys.stderr)
            return 2
        for i, c in enumerate(led.get("cells", []) or []):
            if not isinstance(c, dict):
                continue
            where = c.get("cell_id", f"cells[{i}]")
            ref = c.get("journal_ref")
            if c.get("status") != "未检查" and (not isinstance(ref, str) or ref.strip() == ""):
                errors.append(f"台账单元 {where}: 状态为{c.get('status')},必须给出 journal_ref")
            if isinstance(ref, str) and ref.strip() != "" and ref not in ids:
                errors.append(f"台账单元 {where}: journal_ref 指向不存在的日志条目 {ref!r}")

    print("== 运行日志校验摘要 ==")
    print(f"有效条目: {len(entries)}  声明输入文件: {n_inputs}  声明输出文件: {n_outputs}")
    print(f"output-dir: {os.path.abspath(args.output_dir)}  input-dir: {os.path.abspath(input_dir)}")
    if errors:
        for e in errors:
            print(f"VIOLATION: {e}", file=sys.stderr)
        print(f"JOURNAL CHECK FAIL ({len(errors)} 处违规)", file=sys.stderr)
        return 1
    print("JOURNAL CHECK PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
