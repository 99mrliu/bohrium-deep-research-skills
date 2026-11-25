#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fingerprint.py — 对输入目录内的所有材料做来源指纹登记（provenance ledger 第一步）。

用法:
    python3 fingerprint.py --input-dir /input --workdir /app/work \
        [--output-dir /app/output] [--case CASE_JSON_PATH]

行为:
    - 递归遍历 --input-dir，对每个文件记录: 相对路径、字节数、sha256、类型猜测。
    - 对 JSON 文件尝试识别快照风格:
        * crossref    : 顶层有 "message"，且 message 含 "items" 或 "title"/"DOI"
        * europepmc   : 顶层有 "resultList"
        * generic     : 其余可解析 JSON
    - 写出 workdir/manifest.json。
    - 若提供 --output-dir，同时写一个诚实的不完整 result.json 骨架
      （status=in_progress，不确定项注明 verification pending），
      保证即使后续步骤失败也有可交付物。
    - 所有异常就地降级，绝不崩溃。

退出码: 0 正常; 1 输入目录不存在等校验失败; 2 参数用法错误。
"""
import argparse
import hashlib
import json
import os
import sys

KIND_BY_EXT = {
    ".pdf": "pdf",
    ".txt": "txt",
    ".md": "md",
    ".markdown": "md",
    ".json": "json",
}


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                b = f.read(chunk)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except Exception as e:  # noqa: BLE001 - 防御式：读不了的文件也要登记
        return "UNREADABLE:%s" % e.__class__.__name__


def guess_kind(relpath):
    ext = os.path.splitext(relpath)[1].lower()
    return KIND_BY_EXT.get(ext, "other")


def detect_snapshot_flavor(path):
    """返回 (flavor, error_or_None)。flavor ∈ crossref|europepmc|generic|unparsed"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        return "unparsed", "%s: %s" % (e.__class__.__name__, e)
    if not isinstance(data, dict):
        return "generic", None
    msg = data.get("message")
    if isinstance(msg, dict) and (
        "items" in msg or "title" in msg or "DOI" in msg or "container-title" in msg
    ):
        return "crossref", None
    if isinstance(data.get("resultList"), dict):
        return "europepmc", None
    return "generic", None


def main(argv=None):
    ap = argparse.ArgumentParser(description="指纹登记输入材料并生成 manifest.json")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--case", default=None, help="case.json 路径（可选，用于提取 case_id）")
    args = ap.parse_args(argv)

    input_dir = os.path.abspath(args.input_dir)
    workdir = os.path.abspath(args.workdir)
    if not os.path.isdir(input_dir):
        sys.stderr.write("ERROR: input dir not found: %s\n" % input_dir)
        return 1
    os.makedirs(workdir, exist_ok=True)

    files = []
    for root, _dirs, names in os.walk(input_dir):
        for name in sorted(names):
            full = os.path.join(root, name)
            if not os.path.isfile(full) or os.path.islink(full):
                continue
            rel = os.path.relpath(full, input_dir)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = -1
            entry = {
                "relpath": rel,
                "abspath": full,
                "size_bytes": size,
                "sha256": sha256_of(full),
                "kind": guess_kind(rel),
            }
            if entry["kind"] == "json":
                flavor, err = detect_snapshot_flavor(full)
                entry["snapshot_flavor"] = flavor
                if err:
                    entry["snapshot_error"] = err
            files.append(entry)

    case_id = "unknown_case"
    if args.case and os.path.isfile(args.case):
        try:
            with open(args.case, "r", encoding="utf-8", errors="replace") as f:
                cj = json.load(f)
            if isinstance(cj, dict):
                case_id = (
                    cj.get("case_id") or cj.get("id") or cj.get("caseId") or case_id
                )
        except Exception:  # noqa: BLE001
            pass

    manifest = {
        "case_id": case_id,
        "input_dir": input_dir,
        "file_count": len(files),
        "files": files,
    }
    manifest_path = os.path.join(workdir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    sys.stdout.write("manifest written: %s (%d files)\n" % (manifest_path, len(files)))

    if args.output_dir:
        outdir = os.path.abspath(args.output_dir)
        os.makedirs(outdir, exist_ok=True)
        skeleton = {
            "case_id": case_id,
            "status": "in_progress",
            "main_results": {},
            "evidence": {"manifest": manifest_path, "file_count": len(files)},
            "uncertainties": [
                "verification pending: 仅完成文件指纹登记，"
                "快照-正文交叉核对（crosscheck.py）尚未运行"
            ],
            "change_records": [
                {"step": "fingerprint", "action": "created manifest + skeleton result"}
            ],
        }
        skeleton_path = os.path.join(outdir, "result.json")
        with open(skeleton_path, "w", encoding="utf-8") as f:
            json.dump(skeleton, f, ensure_ascii=False, indent=2)
        sys.stdout.write("skeleton result written: %s\n" % skeleton_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
