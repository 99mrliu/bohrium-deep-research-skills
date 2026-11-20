#!/usr/bin/env python3
"""parse_case.py — 步骤①：解析案例与材料清单。

读取 case.json 与 task.md，列出材料文件，搭建工作目录骨架，
产出 materials_index.json 与 case_meta.json。

退出码：0 正常；2 材料不足（诚实降级）；3 校验失败。
仅使用 Python 标准库。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_NAME = "parse_case.py"

# 按扩展名粗分材料类型（仅用于清单登记，不据此推断内容）
TYPE_MAP = {
    ".pdf": "pdf",
    ".bib": "bibtex",
    ".ris": "ris",
    ".csv": "csv",
    ".json": "json",
    ".txt": "text",
    ".md": "markdown",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha1_of(path: str) -> str:
    h = hashlib.sha1()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 16), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def classify_json(path: str) -> str:
    """粗判 JSON 材料用途：API 响应 / 参考图谱 / 检索结果 / 其他。"""
    name = os.path.basename(path).lower()
    for key, tag in (("crossref", "crossref_response"),
                     ("europepmc", "europepmc_response"),
                     ("europe_pmc", "europepmc_response"),
                     ("pubmed", "europepmc_response"),
                     ("publisher", "publisher_response"),
                     ("graph", "reference_graph"),
                     ("refset", "reference_set"),
                     ("search", "search_results"),
                     ("results", "search_results"),
                     ("bib", "bibliography")):
        if key in name:
            return tag
    return "json_other"


def list_materials(indir: str, limit: int = 2000):
    entries = []
    truncated = False
    for root, dirs, files in os.walk(indir):
        dirs.sort()
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            ext = os.path.splitext(fname)[1].lower()
            mtype = TYPE_MAP.get(ext, "other")
            if ext == ".json":
                mtype = classify_json(fpath)
            try:
                size = os.path.getsize(fpath)
            except OSError:
                size = None
            entries.append({
                "path": os.path.relpath(fpath, indir),
                "type": mtype,
                "size_bytes": size,
                "sha1": sha1_of(fpath),
            })
            if len(entries) >= limit:
                truncated = True
                break
        if truncated:
            break
    return entries, truncated


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="解析 case.json / task.md，登记材料清单并搭建工作目录。")
    ap.add_argument("--case", default="/input/case.json", help="case.json 路径")
    ap.add_argument("--task", default="/task.md", help="task.md 路径")
    ap.add_argument("--workdir", default="/app/work", help="工作目录")
    ap.add_argument("--outdir", default="/app/output", help="输出目录")
    ap.add_argument("--materials", default=None,
                    help="材料目录；缺省取 case.json 所在目录")
    args = ap.parse_args(argv)

    os.makedirs(args.workdir, exist_ok=True)
    os.makedirs(args.outdir, exist_ok=True)

    status = "complete"
    limitations = []

    # ---- 读取 case.json ----
    case = {}
    if os.path.isfile(args.case):
        try:
            with open(args.case, "r", encoding="utf-8") as fh:
                case = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            status = "failed"
            limitations.append(f"case.json 读取失败：{exc}")
    else:
        status = "failed"
        limitations.append(f"case.json 不存在：{args.case}")

    case_id = case.get("case_id", "unknown_case")
    output_contract = case.get("output_contract", {})
    if not output_contract:
        limitations.append("case.json 缺少 output_contract 字段；result.json 校验将受限。")
        if status == "complete":
            status = "partial"

    # ---- 读取 task.md ----
    task_excerpt = ""
    if os.path.isfile(args.task):
        try:
            with open(args.task, "r", encoding="utf-8") as fh:
                task_excerpt = fh.read(4096)
        except OSError as exc:
            limitations.append(f"task.md 读取失败：{exc}")
            if status == "complete":
                status = "partial"
    else:
        limitations.append(f"task.md 不存在：{args.task}")
        if status == "complete":
            status = "partial"

    # ---- 扫描材料 ----
    matdir = args.materials or os.path.dirname(os.path.abspath(args.case))
    materials, truncated = list_materials(matdir)
    if truncated:
        limitations.append("材料清单被截断（超过上限），请人工核对是否遗漏。")
    if not materials:
        limitations.append("未发现任何材料文件，无法构建参考集。")
        if status == "complete":
            status = "partial"

    n_biblio = sum(1 for m in materials if m["type"] in
                   ("bibtex", "ris", "csv", "bibliography"))
    n_pdf = sum(1 for m in materials if m["type"] == "pdf")
    n_resp = sum(1 for m in materials if m["type"] in
                 ("crossref_response", "europepmc_response", "publisher_response"))
    if n_biblio + n_pdf == 0:
        limitations.append("未发现任何题录来源（BibTeX/RIS/CSV/PDF），退出码 2。")

    # ---- 写产物 ----
    meta = {
        "case_id": case_id,
        "generated_by": SCRIPT_NAME,
        "generated_at": now_iso(),
        "output_contract": output_contract,
        "task_excerpt": task_excerpt[:2000],
        "status": status,
        "limitations": limitations,
    }
    index = {
        "case_id": case_id,
        "materials_dir": matdir,
        "counts": {
            "total": len(materials),
            "pdf": n_pdf,
            "bibliography_like": n_biblio,
            "api_response_like": n_resp,
        },
        "materials": materials,
        "status": status,
        "limitations": limitations,
    }
    for fname, payload in (("case_meta.json", meta),
                           ("materials_index.json", index)):
        with open(os.path.join(args.workdir, fname), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

    print(f"[{SCRIPT_NAME}] case_id={case_id} status={status} "
          f"materials={len(materials)} (pdf={n_pdf}, bib={n_biblio}, resp={n_resp})")
    for lim in limitations:
        print(f"  limitation: {lim}", file=sys.stderr)

    if status == "failed":
        return 3
    if n_biblio + n_pdf == 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
