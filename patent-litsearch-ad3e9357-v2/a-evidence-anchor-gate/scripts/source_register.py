#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""source_register.py — 上游数据源登记表生成器（上游数据真实性门控·第一步）。

遍历一个或多个根目录（--roots，可重复），登记每一个文件：
  - 路径（注册时路径 + 绝对路径）
  - sha256（内容指纹，审计阶段以此识别文件）
  - 字节数
  - 字节→文本解码说明（utf-8 / utf-8-with-replacement / binary-pdf 等）

PDF 特殊处理：记录哈希；若系统存在 pdftotext，则用 `pdftotext -layout`
抽取文本到 --workdir（默认 <out目录>/pdftext），并登记抽取文本路径；
若 pdftotext 缺失，标记 text_extraction="unavailable" 并继续，绝不崩溃。

OCR 容差声明：--tolerance-ocr <path>（可重复）为指定文件打上
`tolerance: "ocr"` 预声明标记；只有带此标记的源文件，审计时才允许
锚点使用声明过的容差匹配（anchor.tolerance_used == true）。

退出码：0 成功；2 用法/输入错误。
仅使用 Python 标准库。
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

EMBED_TEXT_CAP = 1_000_000  # 文本 <=1MB 时内嵌进登记表，审计可不依赖原文件


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def decode_bytes(raw):
    """返回 (decoding_note, text_or_None)。"""
    try:
        return "utf-8", raw.decode("utf-8")
    except UnicodeDecodeError:
        return "utf-8-with-replacement", raw.decode("utf-8", errors="replace")


def iter_files(root):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            yield os.path.join(dirpath, name)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="登记输入源文件（路径/sha256/大小/解码说明），生成登记表 JSON。")
    p.add_argument("--roots", action="append", required=True, metavar="DIR_OR_FILE",
                   help="要登记的根目录（或单文件），可重复多次。")
    p.add_argument("--out", required=True, metavar="REGISTRY_JSON",
                   help="登记表 JSON 输出路径。")
    p.add_argument("--workdir", default=None, metavar="DIR",
                   help="PDF 抽取文本等工作文件目录（默认：<out所在目录>/pdftext）。")
    p.add_argument("--tolerance-ocr", action="append", default=[], metavar="PATH",
                   help="为指定文件预声明 OCR 容差（tolerance=ocr），可重复。")
    args = p.parse_args(argv)

    for r in args.roots:
        if not os.path.exists(r):
            print("错误：root 不存在: %s" % r, file=sys.stderr)
            return 2
    out_dir = os.path.dirname(os.path.abspath(args.out)) or "."
    os.makedirs(out_dir, exist_ok=True)
    workdir = args.workdir or os.path.join(out_dir, "pdftext")

    ocr_paths = set()
    for pth in args.tolerance_ocr:
        if not os.path.exists(pth):
            print("错误：--tolerance-ocr 文件不存在: %s" % pth, file=sys.stderr)
            return 2
        ocr_paths.add(os.path.abspath(pth))

    pdftotext = shutil.which("pdftotext")
    entries = []
    seen = set()
    for root in args.roots:
        for path in iter_files(root):
            abspath = os.path.abspath(path)
            if abspath in seen:
                continue
            seen.add(abspath)
            if os.path.islink(abspath):
                print("警告：跳过符号链接: %s" % path, file=sys.stderr)
                continue
            try:
                size = os.path.getsize(abspath)
                digest = sha256_of(abspath)
            except OSError as e:
                print("警告：无法读取 %s: %s（跳过）" % (path, e), file=sys.stderr)
                continue
            entry = {
                "path": path,
                "abspath": abspath,
                "sha256": digest,
                "size": size,
                "decoding": None,
                "text_extraction": "not-applicable",
                "text_path": None,
                "text": None,
            }
            if abspath in ocr_paths:
                entry["tolerance"] = "ocr"

            if abspath.lower().endswith(".pdf"):
                entry["decoding"] = "binary-pdf"
                if pdftotext:
                    os.makedirs(workdir, exist_ok=True)
                    txt_path = os.path.join(workdir, digest[:16] + ".txt")
                    try:
                        subprocess.run(
                            [pdftotext, "-layout", abspath, txt_path],
                            check=True, capture_output=True, timeout=120)
                        with open(txt_path, "rb") as f:
                            raw = f.read()
                        note, text = decode_bytes(raw)
                        entry["decoding"] = "binary-pdf;" + note
                        entry["text_extraction"] = "pdftotext-layout"
                        entry["text_path"] = os.path.abspath(txt_path)
                        if len(raw) <= EMBED_TEXT_CAP:
                            entry["text"] = text
                    except Exception as e:  # 绝不因单个 PDF 崩溃
                        print("警告：pdftotext 抽取失败 %s: %s（标记 unavailable 继续）"
                              % (path, e), file=sys.stderr)
                        entry["text_extraction"] = "unavailable"
                else:
                    entry["text_extraction"] = "unavailable"
                    print("警告：未找到 pdftotext，%s 的文本抽取标记为 unavailable"
                          % path, file=sys.stderr)
            else:
                try:
                    with open(abspath, "rb") as f:
                        raw = f.read()
                    note, text = decode_bytes(raw)
                    entry["decoding"] = note
                    entry["text_extraction"] = "self"
                    entry["text_path"] = abspath
                    if len(raw) <= EMBED_TEXT_CAP:
                        entry["text"] = text
                except OSError as e:
                    entry["decoding"] = "unreadable: %s" % e
                    entry["text_extraction"] = "unavailable"

            entries.append(entry)

    registry = {
        "version": 1,
        "tool": "source_register.py",
        "roots": [os.path.abspath(r) for r in args.roots],
        "pdftotext_available": bool(pdftotext),
        "entries": entries,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
        f.write("\n")
    n_ocr = sum(1 for e in entries if e.get("tolerance") == "ocr")
    print("登记完成：%d 个文件 → %s（其中 OCR 容差预声明 %d 个，pdftotext=%s）"
          % (len(entries), args.out, n_ocr,
             "可用" if pdftotext else "不可用"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
