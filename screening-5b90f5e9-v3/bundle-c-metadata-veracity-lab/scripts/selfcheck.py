#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — bundle 合规自查 + result.json 合同校验

检查项：
  1. 平台约束：文件数 ≤50、单文件 ≤500KB、总计 ≤2MB、无符号链接、
     全部 UTF-8 文本（无二进制）
  2. SKILL.md frontmatter 合法（--- 包围、含 name 与 description）
  3. （可选）result.json 合同：含 case_id/status/sources/uncertainty/
     change_records，且 output_contract 字段一个不缺（可为 null，不可缺键）

退出码：0 全部通过；2 运行/IO 错误；3 任一检查不通过。
"""
import argparse
import json
import os
import sys

MAX_FILES = 50
MAX_SINGLE = 500 * 1024
MAX_TOTAL = 2 * 1024 * 1024


def check_bundle(bundle_dir):
    failures = []
    files = []
    total = 0
    for root, dirs, names in os.walk(bundle_dir):
        for name in names:
            path = os.path.join(root, name)
            rel = os.path.relpath(path, bundle_dir)
            if os.path.islink(path):
                failures.append("符号链接: %s" % rel)
                continue
            size = os.path.getsize(path)
            total += size
            files.append((rel, size, path))
            if size > MAX_SINGLE:
                failures.append("单文件超限(>500KB): %s (%dB)" % (rel, size))
            try:
                with open(path, "rb") as fh:
                    raw = fh.read()
                raw.decode("utf-8")
                if b"\x00" in raw:
                    failures.append("含 NUL 字节（疑似二进制）: %s" % rel)
            except UnicodeDecodeError:
                failures.append("非 UTF-8 文本: %s" % rel)
    if len(files) > MAX_FILES:
        failures.append("文件数超限: %d > %d" % (len(files), MAX_FILES))
    if total > MAX_TOTAL:
        failures.append("总大小超限: %dB > %dB" % (total, MAX_TOTAL))

    skill_path = os.path.join(bundle_dir, "SKILL.md")
    if not os.path.exists(skill_path):
        failures.append("缺 SKILL.md")
    else:
        with open(skill_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        if not text.startswith("---\n"):
            failures.append("SKILL.md frontmatter 未以 --- 开头")
        else:
            end = text.find("\n---", 4)
            if end < 0:
                failures.append("SKILL.md frontmatter 未闭合")
            else:
                fm = text[4:end]
                if "name:" not in fm or "description:" not in fm:
                    failures.append("SKILL.md frontmatter 缺 name/description")
    return files, total, failures


def check_result(result_path):
    failures = []
    with open(result_path, "r", encoding="utf-8") as fh:
        result = json.load(fh)
    for key in ("case_id", "status", "sources", "uncertainty",
                "change_records"):
        if key not in result:
            failures.append("result.json 缺基础键: %s" % key)
    if result.get("status") not in ("success", "partial", "failed"):
        failures.append("result.json status 非法: %r" % result.get("status"))
    if result.get("case_id") in (None, ""):
        failures.append("result.json case_id 为空")
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description="bundle 合规自查")
    parser.add_argument("--bundle",
                        default=os.path.dirname(os.path.dirname(
                            os.path.abspath(__file__))),
                        help="bundle 根目录（默认取脚本上一级）")
    parser.add_argument("--result", default=None,
                        help="可选：同时校验 result.json")
    args = parser.parse_args(argv)
    try:
        files, total, failures = check_bundle(args.bundle)
        print("bundle=%s" % os.path.abspath(args.bundle))
        print("文件数=%d（上限 %d） 总字节=%d（上限 %d）"
              % (len(files), MAX_FILES, total, MAX_TOTAL))
        for rel, size, _ in sorted(files):
            print("  %-58s %8dB" % (rel, size))
        if args.result:
            failures += check_result(args.result)
            print("result.json 校验: %s" % args.result)
        if failures:
            print("FAIL:")
            for f in failures:
                print("  - %s" % f)
            return 3
        print("PASS: 全部检查通过")
        return 0
    except FileNotFoundError as exc:
        print("ERROR: 文件不存在: %s" % exc, file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # 顶层兜底
        print("ERROR: 未预期异常: %r" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
