#!/usr/bin/env python3
"""extract_text.py — 材料文本抽取：分页 + 章节粗切分

用途：
  把审查材料转成统一的 pages.json，供下游锚定核验（quote_bind.py）机械使用。
  - .txt / .md：直接读取；
  - .pdf：调用外部命令 pdftotext -layout；若 pdftotext 缺失或失败，优雅降级：
    仍输出合法 pages.json（pages 为空），在 warnings 中如实报告，exit 0。
  分页依据换页符 \\f（pdftotext 物理页约定）；无 \\f 的纯文本视为单页。

输出 pages.json 结构：
  {
    "source_file": "...", "page_count": N,
    "pages": [{"page_no": 1, "char_offset": 0, "text": "..."}, ...],
    "sections": [{"name": "Methods", "heading": "2. Methods", "page_no": 2,
                  "char_offset": 1234}, ...],
    "warnings": [...]
  }
char_offset 为该页/标题在原始抽取文本（含 \\f）中的起始偏移。

仅 Python3 标准库；输出确定性（无时间戳、无随机数）；缺键/坏文件不崩溃。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

# 常见章节标题（整行匹配，允许前导编号如 "2." / "3.1"）
SECTION_TERMS = [
    "Abstract", "Introduction", "Background",
    "Materials and Methods", "Methods?", "Methodology",
    "Results?", "Discussion", "Conclusions?", "Acknowledg(?:e)?ments?",
    "References?",
    "材料与方法", "参考文献", "摘要", "引言", "前言", "方法", "结果",
    "讨论", "结论", "致谢",
]
HEADING_RE = re.compile(
    r"^\s*(?:\(?\d+(?:\.\d+)*\)?[.、\)]?\s+)?(" + "|".join(SECTION_TERMS) + r")\s*[:：]?\s*$",
    re.IGNORECASE,
)


def read_material(path, warnings):
    """返回抽取到的全文文本；失败返回 None 并记录 warning（不抛异常）。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        exe = shutil.which("pdftotext")
        if exe is None:
            warnings.append(
                "未找到 pdftotext（poppler），无法解析 PDF：%s；"
                "pages 为空。请安装 poppler 或先将 PDF 人工转为 .txt 后重跑。" % path
            )
            return None
        try:
            proc = subprocess.run(
                [exe, "-layout", path, "-"],
                capture_output=True, timeout=60, check=False,
            )
        except Exception as exc:  # 超时/权限等一律降级
            warnings.append("pdftotext 调用失败：%r；pages 为空。" % exc)
            return None
        if proc.returncode != 0:
            warnings.append(
                "pdftotext 返回非零（rc=%s）：%s；pages 为空。"
                % (proc.returncode, proc.stderr.decode("utf-8", "replace")[:200])
            )
            return None
        return proc.stdout.decode("utf-8", "replace")
    # 其余一律按纯文本读取
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError as exc:
        warnings.append("无法读取输入文件 %s：%s" % (path, exc))
        return None


def split_pages(full_text):
    """按 \\f 切页，返回 [{page_no, char_offset, text}]；空文本返回空列表。"""
    if full_text is None:
        return []
    chunks = full_text.split("\f")
    pages = []
    offset = 0
    for idx, chunk in enumerate(chunks, start=1):
        pages.append({"page_no": idx, "char_offset": offset, "text": chunk})
        offset += len(chunk) + 1  # +1 为被消耗的 \f
    # 去掉末尾纯粹由结尾 \f 产生的空白尾页（pdftotext 常见），保持页数诚实
    while len(pages) > 1 and pages[-1]["text"].strip() == "":
        pages.pop()
    return pages


def detect_sections(pages):
    """逐行扫描整行标题，返回 sections 列表（含全局 char_offset）。"""
    sections = []
    for page in pages:
        cursor = page["char_offset"]
        for line in page["text"].splitlines(keepends=True):
            m = HEADING_RE.match(line.rstrip("\r\n"))
            if m:
                sections.append({
                    "name": m.group(1).strip(),
                    "heading": line.strip(),
                    "page_no": page["page_no"],
                    "char_offset": cursor + (len(line) - len(line.lstrip())),
                })
            cursor += len(line)
    return sections


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="抽取材料文本并按 \\f 分页，输出 pages.json（含 sections 粗切分）。"
    )
    ap.add_argument("input", help="材料文件路径（.txt/.md/.pdf 等）")
    ap.add_argument("--out", required=True, help="输出 pages.json 路径")
    args = ap.parse_args(argv)

    warnings = []
    if not os.path.exists(args.input):
        warnings.append("输入文件不存在：%s" % args.input)
        full_text = None
    else:
        full_text = read_material(args.input, warnings)

    pages = split_pages(full_text)
    sections = detect_sections(pages)
    result = {
        "source_file": os.path.basename(args.input),
        "source_path": os.path.abspath(args.input),
        "extractor": "extract_text.py (stdlib; pdf via pdftotext -layout)",
        "page_count": len(pages),
        "pages": pages,
        "sections": sections,
        "warnings": warnings,
    }
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("extract_text: %s -> %s | pages=%d sections=%d warnings=%d"
          % (args.input, args.out, len(pages), len(sections), len(warnings)))
    for w in warnings:
        print("  WARNING: " + w, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
