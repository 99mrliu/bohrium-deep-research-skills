#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_sources.py — 输入材料盘点与纯文本层抽取（证据锚定第一步）。

对输入目录（默认 /input）中的每个文件登记：相对路径、字节数、md5、
角色猜测（role_guess）与来源类别猜测（source_class_guess）；
并尽力获得纯文本层，写入 <out>/src_text/：

  - .pdf          调 pdftotext -layout 抽取为 src_text/<name>.txt，按换页符计页数；
                  pdftotext 缺失或执行失败时标记 unreadable 并记录原因。
  - .md/.txt/.json 直接复制到 src_text/（保持原名）。
  - .docx         尝试 soffice --headless --convert-to txt；soffice 缺失或失败时
                  标记 unreadable 并记录原因。
  - 其他扩展名     登记并标记 skipped（不抽文本）。

产出 <out>/materials_inventory.json。输出确定性：文件按相对路径排序，
不写时间戳，同一输入同一命令二次运行字节一致。

退出码：0 正常完成（个别文件 unreadable/skipped 不算失败，已如实登记）；
        2 参数错误或输入目录不存在；3 输出写入失败。

角色猜测规则（确定性启发式，仅供 anchor_audit 兜底与人工参考，最终以来源内容为准）：
  case.json / task.md        -> case-definition
  文件名含 workorder          -> organizer-workorder
  .pdf                       -> external-pdf        （PDF 多为外部论文/资料，默认外部）
  .docx                      -> office-doc
  文件名含 记录/前期/record/notebook/logbook -> applicant-record（申请人证据类）
  其他 .md/.txt              -> notes-or-draft
  其他 .json                 -> structured-data
source_class_guess：applicant-record -> applicant；external-pdf -> external；
其余 -> unknown。规则全文见 references/status_taxonomy.md。
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

TEXT_COPY_EXTS = {".md", ".txt", ".json"}

CLASS_BY_ROLE = {
    "applicant-record": "applicant",
    "external-pdf": "external",
}


def guess_role(rel_path, ext):
    base = os.path.basename(rel_path).lower()
    if base in ("case.json", "task.md"):
        return "case-definition"
    if "workorder" in base:
        return "organizer-workorder"
    if ext == ".pdf":
        return "external-pdf"
    if ext == ".docx":
        return "office-doc"
    if any(k in base for k in ("记录", "前期", "record", "notebook", "logbook")):
        return "applicant-record"
    if ext in (".md", ".txt"):
        return "notes-or-draft"
    if ext == ".json":
        return "structured-data"
    return "unknown"


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def unique_name(used, name):
    if name not in used:
        used.add(name)
        return name
    stem, ext = os.path.splitext(name)
    i = 2
    while True:
        cand = "%s__%d%s" % (stem, i, ext)
        if cand not in used:
            used.add(cand)
            return cand
        i += 1


def run_pdf(src, dst):
    """返回 (status, pages, reason)。"""
    exe = shutil.which("pdftotext")
    if exe is None:
        return "unreadable", None, "pdftotext 不可用：无法抽取 PDF 文本层"
    try:
        proc = subprocess.run(
            [exe, "-layout", src, dst],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
        )
    except Exception as exc:  # 超时等
        return "unreadable", None, "pdftotext 执行异常：%s" % exc
    if proc.returncode != 0 or not os.path.isfile(dst):
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        tail = err[-1] if err else "未知错误"
        return "unreadable", None, "pdftotext 失败（退出码 %s）：%s" % (proc.returncode, tail)
    with open(dst, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    pages = max(text.count("\f"), 1) if text.strip() else 0
    if not text.strip():
        return "unreadable", 0, "pdftotext 输出为空：PDF 可能无文本层（扫描件/加密），需渲染+OCR 或声明不可读"
    return "extracted", pages, None


def run_docx(src, dst_dir, stem):
    """返回 (status, text_name, reason)。"""
    exe = shutil.which("soffice")
    if exe is None:
        return "unreadable", None, "soffice 不可用：无法转换 docx"
    try:
        proc = subprocess.run(
            [exe, "--headless", "--convert-to", "txt", "--outdir", dst_dir, src],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
        )
    except Exception as exc:
        return "unreadable", None, "soffice 执行异常：%s" % exc
    out = os.path.join(dst_dir, stem + ".txt")
    if proc.returncode != 0 or not os.path.isfile(out):
        return "unreadable", None, "soffice 转换失败（退出码 %s）" % proc.returncode
    return "extracted", os.path.basename(out), None


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="盘点输入材料并抽取纯文本层，产出 materials_inventory.json。",
        epilog="退出码：0 正常；2 参数/输入错误；3 输出写入失败。",
    )
    ap.add_argument("--input", default="/input", help="输入材料目录（默认 /input）")
    ap.add_argument("--out", default=".", help="输出目录（默认当前目录）；src_text/ 与 materials_inventory.json 写于此")
    args = ap.parse_args(argv)

    in_dir = os.path.abspath(args.input)
    out_dir = os.path.abspath(args.out)
    if not os.path.isdir(in_dir):
        print("错误：输入目录不存在：%s" % in_dir, file=sys.stderr)
        return 2
    src_text_dir = os.path.join(out_dir, "src_text")
    try:
        os.makedirs(src_text_dir, exist_ok=True)
    except OSError as exc:
        print("错误：无法创建输出目录：%s" % exc, file=sys.stderr)
        return 3

    used_names = set()
    files = []
    for root, dirs, names in os.walk(in_dir):
        dirs.sort()
        for name in sorted(names):
            full = os.path.join(root, name)
            if not os.path.isfile(full) or os.path.islink(full):
                continue
            rel = os.path.relpath(full, in_dir)
            ext = os.path.splitext(name)[1].lower()
            role = guess_role(rel, ext)
            rec = {
                "path": rel,
                "size_bytes": os.path.getsize(full),
                "md5": md5_of(full),
                "ext": ext,
                "role_guess": role,
                "source_class_guess": CLASS_BY_ROLE.get(role, "unknown"),
                "extract": {"status": "skipped", "text_path": None, "pages": None, "reason": None},
            }
            if ext in TEXT_COPY_EXTS:
                dst_name = unique_name(used_names, name)
                dst = os.path.join(src_text_dir, dst_name)
                try:
                    shutil.copyfile(full, dst)
                    rec["extract"].update(status="copied", text_path="src_text/" + dst_name)
                except OSError as exc:
                    rec["extract"].update(status="unreadable", reason="复制失败：%s" % exc)
            elif ext == ".pdf":
                dst_name = unique_name(used_names, os.path.splitext(name)[0] + ".txt")
                dst = os.path.join(src_text_dir, dst_name)
                status, pages, reason = run_pdf(full, dst)
                rec["extract"]["status"] = status
                rec["extract"]["pages"] = pages
                rec["extract"]["reason"] = reason
                if status == "extracted":
                    rec["extract"]["text_path"] = "src_text/" + dst_name
            elif ext == ".docx":
                stem = unique_name(used_names, os.path.splitext(name)[0]) 
                status, out_name, reason = run_docx(full, src_text_dir, stem)
                rec["extract"]["status"] = status
                rec["extract"]["reason"] = reason
                if status == "extracted" and out_name:
                    rec["extract"]["text_path"] = "src_text/" + out_name
            files.append(rec)

    files.sort(key=lambda r: r["path"])
    inventory = {
        "input_dir": in_dir,
        "file_count": len(files),
        "tools": {
            "pdftotext": "available" if shutil.which("pdftotext") else "missing",
            "soffice": "available" if shutil.which("soffice") else "missing",
        },
        "files": files,
    }
    out_path = os.path.join(out_dir, "materials_inventory.json")
    try:
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(inventory, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
    except OSError as exc:
        print("错误：写入 inventory 失败：%s" % exc, file=sys.stderr)
        return 3

    n_unread = sum(1 for r in files if r["extract"]["status"] == "unreadable")
    print("盘点完成：%d 个文件（%d 个 unreadable），inventory -> %s" % (len(files), n_unread, out_path))
    for r in files:
        ex = r["extract"]
        line = "  [%s] %s (%s, %d bytes, md5=%s)" % (ex["status"], r["path"], r["role_guess"], r["size_bytes"], r["md5"][:8])
        if ex["pages"] is not None:
            line += " pages=%s" % ex["pages"]
        if ex["reason"]:
            line += " 原因：" + ex["reason"]
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
