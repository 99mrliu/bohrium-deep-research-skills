#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""source_registry.py — 来源文件登记册（SHA-256 registry）生成器。

仅依赖 Python 3.10+ 标准库；无网络访问；确定性输出（同一输入产生同一输出）。

功能：
  遍历 --sources 目录中的全部文件（含子目录），对每个文件计算 SHA-256 摘要与
  字节数，并按扩展名/内容嗅探类型（txt/md/json/bib/ris/csv/pdf 等；pdf 标记为
  不可解析的二进制）。输出 registry JSON，包含生成时间（UTC）、文件列表与警告。

时间戳：从环境变量 SOURCE_DATE_EPOCH 读取（整数秒或 ISO 字符串），
缺省固定为 "1970-01-01T00:00:00Z"，以保证可复现。

用法：
  python3 source_registry.py --sources DIR --out FILE.json

退出码：
  0  正常完成（警告不导致失败，但会写入 warnings 字段）；
  1  设计缺陷：--sources 不存在/不是目录、--out 不可写、参数缺失。
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

TOOL_NAME = "source_registry"
TOOL_VERSION = "1.0.0"
DEFAULT_TIMESTAMP = "1970-01-01T00:00:00Z"

EXT_TYPE = {
    ".txt": "txt",
    ".md": "md",
    ".json": "json",
    ".bib": "bib",
    ".ris": "ris",
    ".csv": "csv",
    ".pdf": "pdf",
}


def resolve_timestamp() -> str:
    """确定性时间戳：优先 SOURCE_DATE_EPOCH，缺省固定常量。"""
    raw = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if not raw:
        return DEFAULT_TIMESTAMP
    if raw.isdigit():
        return datetime.fromtimestamp(int(raw), tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    return raw  # 视为已格式化的 ISO 字符串，原样使用


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sniff_type(path: str, ext: str):
    """返回 (type, note)。note 为 None 表示无附加说明。"""
    note = None
    if ext in EXT_TYPE:
        ftype = EXT_TYPE[ext]
    else:
        try:
            with open(path, "rb") as f:
                head = f.read(8192)
        except OSError:
            return "unreadable", "file_cannot_be_read"
        if head.startswith(b"%PDF"):
            ftype = "pdf"
        else:
            try:
                text = head.decode("utf-8")
            except UnicodeDecodeError:
                return "unknown_binary", "unknown_extension_and_non_utf8_content"
            stripped = text.lstrip()
            if stripped.startswith("{") or stripped.startswith("["):
                ftype = "json"
            elif stripped.startswith("TY  -"):
                ftype = "ris"
            elif stripped.startswith("@") and "{" in stripped[:200]:
                ftype = "bib"
            else:
                ftype = "txt"
            note = "type_inferred_from_content"
    if ftype == "pdf":
        # PDF 为二进制容器，本工具不解析其正文，仅登记摘要。
        note = "binary_not_parsed"
    elif ftype == "json":
        try:
            with open(path, "r", encoding="utf-8") as f:
                json.load(f)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            note = "json_parse_failed"
    return ftype, note


def build_registry(sources_dir: str):
    files = []
    warnings = []
    for root, dirs, names in os.walk(sources_dir):
        dirs.sort()
        for name in sorted(names):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, sources_dir).replace(os.sep, "/")
            ext = os.path.splitext(name)[1].lower()
            entry = {"path": rel, "bytes": None, "sha256": None, "type": None}
            try:
                entry["bytes"] = os.path.getsize(full)
            except OSError:
                warnings.append(f"stat_failed: {rel}")
            try:
                entry["sha256"] = sha256_of(full)
            except OSError:
                warnings.append(f"hash_failed: {rel}")
            ftype, note = sniff_type(full, ext)
            entry["type"] = ftype
            if note:
                entry["note"] = note
                warnings.append(f"{note}: {rel}")
            files.append(entry)
    files.sort(key=lambda e: e["path"])
    total = sum(e["bytes"] for e in files if isinstance(e["bytes"], int))
    return {
        "tool": TOOL_NAME,
        "version": TOOL_VERSION,
        "generated_utc": resolve_timestamp(),
        "sources_dir": sources_dir,
        "file_count": len(files),
        "total_bytes": total,
        "files": files,
        "warnings": warnings,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="生成来源目录的 SHA-256 登记册（确定性、仅标准库）。"
    )
    parser.add_argument("--sources", required=True, help="来源文件目录")
    parser.add_argument("--out", required=True, help="输出 registry JSON 路径")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.sources):
        print(
            f"[source_registry] ERROR: --sources 不是有效目录: {args.sources}",
            file=sys.stderr,
        )
        return 1

    registry = build_registry(args.sources)
    out_dir = os.path.dirname(os.path.abspath(args.out))
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2, sort_keys=False)
            f.write("\n")
    except OSError as exc:
        print(f"[source_registry] ERROR: 无法写出 {args.out}: {exc}", file=sys.stderr)
        return 1

    print(
        f"[source_registry] 登记 {registry['file_count']} 个文件，"
        f"共 {registry['total_bytes']} 字节，警告 {len(registry['warnings'])} 条 -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
