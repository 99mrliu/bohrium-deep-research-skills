#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
forensic_intake.py — 上游材料取证建库（source intake forensics）

功能：
  1. 扫描输入目录内全部常规文件，计算 SHA-256 与字节数；
  2. 依据 magic bytes 嗅探真实文件类型（不依赖扩展名）；
  3. 文本类材料抽取全文并记录行数；PDF 在系统存在 pdftotext 时逐页抽取
     （pdftotext -layout），记录页数与每页字符数；缺失时如实记
     "extractor_unavailable"，绝不臆造页内容；
  4. 图片/二进制材料记为 "non_text_material"（缺口，需人工读图）；
  5. 产出 manifest.json、receipts/*.json、anchor_index.json 与抽取文本副本。

只使用 Python3 标准库；pdftotext 为可选外部工具（shutil.which 检测）。

退出码：0 成功；1 参数/目录错误；2 输入目录无可用文件。
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


# ---------- 类型嗅探：只看 magic bytes，不信任扩展名 ----------

def sniff_type(path: Path) -> str:
    """按文件头 magic bytes 判定真实类型；均判不出时尝试 UTF-8 解码判文本。"""
    raw = path.read_bytes()
    head = raw[:16]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        return "zip"  # docx/xlsx/pptx 等 OOXML 容器
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    try:
        raw.decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        return "binary"


def sha256_of(path: Path) -> str:
    """流式计算 SHA-256，避免大文件占内存。"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------- 抽取 ----------

def extract_text(path: Path):
    """文本类材料：全文解码，返回 (文本, 行数)。"""
    text = path.read_bytes().decode("utf-8")
    lines = text.split("\n")
    return text, len(lines)


def extract_pdf(path: Path, pdftotext: str):
    """
    PDF 材料：调用 pdftotext -layout 逐页抽取。
    返回 (页文本列表, 状态)。失败时状态如实记录，不臆造页内容。
    """
    try:
        proc = subprocess.run(
            [pdftotext, "-layout", str(path), "-"],
            capture_output=True, timeout=120,
        )
    except Exception as exc:  # 超时、权限等一律如实记录
        return None, f"extractor_error:{type(exc).__name__}"
    if proc.returncode != 0:
        # 加密 PDF / 损坏 PDF 通常在这里失败
        err = proc.stderr.decode("utf-8", errors="replace").strip().split("\n")
        return None, "extractor_error:" + (err[0][:80] if err and err[0] else "pdftotext_failed")
    out = proc.stdout.decode("utf-8", errors="replace")
    pages = out.split("\f")  # pdftotext 用换页符分页
    if pages and pages[-1].strip() == "":
        pages.pop()
    if not pages:
        # 扫描件：能运行但无文字层
        return [], "no_text_layer"
    return pages, "extracted"


# ---------- 主流程 ----------

def main() -> int:
    ap = argparse.ArgumentParser(description="上游材料取证建库：manifest + receipts + anchor_index")
    ap.add_argument("--input", required=True, help="输入目录（评测时为 /input）")
    ap.add_argument("--work", required=True, help="工作目录（评测时为 /app/work）")
    args = ap.parse_args()

    in_dir = Path(args.input)
    work_dir = Path(args.work)
    if not in_dir.is_dir():
        print(f"[intake] 错误：输入目录不存在 {in_dir}", file=sys.stderr)
        return 1
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "receipts").mkdir(exist_ok=True)
    (work_dir / "extracted").mkdir(exist_ok=True)

    # 收集全部常规文件（跳过目录与符号链接），按相对路径排序保证编号确定
    files = sorted(
        (p for p in in_dir.rglob("*") if p.is_file() and not p.is_symlink()),
        key=lambda p: p.relative_to(in_dir).as_posix(),
    )
    if not files:
        print(f"[intake] 错误：输入目录无可用文件 {in_dir}", file=sys.stderr)
        return 2

    pdftotext = shutil.which("pdftotext")
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    materials = []       # manifest 条目
    anchor_index = {}    # 锚点索引
    for i, f in enumerate(files, start=1):
        mid = f"M{i}"
        rel = f.relative_to(in_dir).as_posix()
        ftype = sniff_type(f)
        digest = sha256_of(f)
        size = f.stat().st_size

        receipt = {
            "material_id": mid,
            "path": rel,
            "type_sniffed": ftype,
            "sha256": digest,
            "bytes": size,
            "extractor": None,
            "extracted_at": now,
            "status": None,
            "lines": None,
            "pages": None,
            "page_chars": None,
            "note": None,
        }

        if ftype == "text":
            text, nlines = extract_text(f)
            (work_dir / "extracted" / f"{mid}.txt").write_text(text, encoding="utf-8")
            receipt.update(extractor="python_utf8", status="extracted", lines=nlines)
            anchor_index[mid] = {
                "kind": "line", "count": nlines,
                "extracted": f"extracted/{mid}.txt",
                "path": rel, "type": ftype,
            }
        elif ftype == "pdf":
            if pdftotext is None:
                # 无 pdftotext：如实记缺口，不臆造页内容
                receipt.update(extractor=None, status="extractor_unavailable",
                               note="系统无 pdftotext，未抽取；需人工阅读或安装 poppler")
            else:
                pages, status = extract_pdf(f, pdftotext)
                receipt["extractor"] = "pdftotext -layout"
                receipt["status"] = status
                if pages:
                    receipt["pages"] = len(pages)
                    receipt["page_chars"] = [len(p) for p in pages]
                    (work_dir / "extracted" / f"{mid}.pages.json").write_text(
                        json.dumps(pages, ensure_ascii=False, indent=1), encoding="utf-8")
                    anchor_index[mid] = {
                        "kind": "page", "count": len(pages),
                        "extracted": f"extracted/{mid}.pages.json",
                        "path": rel, "type": ftype,
                    }
                elif status == "no_text_layer":
                    receipt["note"] = "PDF 无文字层（疑为扫描件），需 OCR 或人工阅读"
        else:
            # 图片/zip/其他二进制：非文本材料缺口
            receipt.update(extractor=None, status="non_text_material",
                           note="非文本材料，无法自动锚定；正文引用其内容需人工核对原文件")

        materials.append({
            "id": mid, "path": rel, "type": ftype,
            "sha256": digest, "bytes": size, "status": receipt["status"],
        })
        (work_dir / "receipts" / f"{mid}.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "generated_at": now,
        "input_dir": str(in_dir),
        "material_count": len(materials),
        "materials": materials,
        "integrity": "baseline_recorded",
    }
    (work_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (work_dir / "anchor_index.json").write_text(
        json.dumps(anchor_index, ensure_ascii=False, indent=2), encoding="utf-8")

    n_text = sum(1 for m in materials if m["status"] == "extracted")
    n_gap = len(materials) - n_text
    print(f"[intake] 材料 {len(materials)} 份：可锚定 {n_text} 份，缺口 {n_gap} 份"
          f"（pdftotext={'可用' if pdftotext else '缺失'}）")
    print(f"[intake] 产物：{work_dir}/manifest.json, anchor_index.json, receipts/, extracted/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
