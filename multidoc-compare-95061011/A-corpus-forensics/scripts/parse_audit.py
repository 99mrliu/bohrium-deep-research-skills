#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_audit.py — 解析保真审计（parse fidelity audit），可独立运行的自包含脚本。

用途：
  对语料文档（.md/.txt/.jsonl 直接读取；.pdf 调用 pdftotext 子进程）做解析保真审计，
  输出 parse-audit.json。build_registry.py 会复用本脚本的 audit_pdf / audit_text 函数，
  但本脚本不依赖 bundle 内任何其他文件，可单独拷贝使用。

审计信号（判据详见 references/forensics-rules.md）：
  - replacement_char_ratio : U+FFFD(�) 替换字符占比
  - empty_page_ratio       : PDF 空页比例（pdftotext 以 \f 分页；非 PDF 恒为 0）
  - short_line_ratio       : 异常短行（<20 字符）占非空行比例（参考信号）
  - layout_diff_rate       : pdftotext 默认模式 vs -layout 模式的文本差异率（1 - difflib ratio）
  - total_chars            : 提取到的总字符数（<100 判 failed）

退出码：0 = 审计完成（即使个别文档 failed；这是报告而非门禁）；1 = 用法/IO 错误。
"""
import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time

TEXT_EXTS = {".md", ".txt", ".jsonl"}
PDF_EXTS = {".pdf"}

MIN_EXTRACTED_CHARS = 100          # 提取字符数低于此值 -> failed
REPL_RATIO_DEGRADED = 0.005        # � 占比超过 0.5% -> degraded
DIFF_RATE_DEGRADED = 0.30          # 默认 vs -layout 差异率超过 30% -> degraded
EMPTY_PAGE_RATIO_DEGRADED = 0.30   # 空页比例超过 30% -> degraded
SHORT_LINE_LEN = 20
PDFTOTEXT_TIMEOUT = 120


def _collapse_ws(text):
    return re.sub(r"\s+", " ", text or "").strip()


def text_stats(text):
    """统计纯文本层面的保真信号（不含 layout 差异率）。"""
    total_chars = len(text)
    repl = text.count("�")
    repl_ratio = (repl / total_chars) if total_chars else 0.0
    lines = text.splitlines()
    nonempty = [l for l in lines if l.strip()]
    short_lines = [l for l in nonempty if len(l.strip()) < SHORT_LINE_LEN]
    short_line_ratio = (len(short_lines) / len(nonempty)) if nonempty else 0.0
    # pdftotext 用 \f 分页；单页文本（普通 txt/md）无分页概念，空页率记 0
    if "\f" in text:
        pages = text.split("\f")
        empty_pages = [p for p in pages if len(p.strip()) < SHORT_LINE_LEN]
        empty_page_ratio = len(empty_pages) / len(pages) if pages else 0.0
        n_pages = len(pages)
    else:
        empty_page_ratio = 0.0
        n_pages = 1 if text.strip() else 0
    return {
        "total_chars": total_chars,
        "replacement_chars": repl,
        "replacement_char_ratio": round(repl_ratio, 6),
        "n_lines": len(lines),
        "short_line_ratio": round(short_line_ratio, 4),
        "n_pages": n_pages,
        "empty_page_ratio": round(empty_page_ratio, 4),
    }


def verdict_from_stats(stats, layout_diff_rate=None):
    if stats["total_chars"] < MIN_EXTRACTED_CHARS:
        return "failed"
    if stats["replacement_char_ratio"] > REPL_RATIO_DEGRADED:
        return "degraded"
    if layout_diff_rate is not None and layout_diff_rate > DIFF_RATE_DEGRADED:
        return "degraded"
    if stats["empty_page_ratio"] > EMPTY_PAGE_RATIO_DEGRADED:
        return "degraded"
    return "good"


def audit_text(text):
    """审计非 PDF 文本。返回含 verdict 与统计信号的字典（不含原文）。"""
    stats = text_stats(text)
    out = {"mode": "text", "verdict": verdict_from_stats(stats), "layout_diff_rate": None}
    out.update(stats)
    return out


def _run_pdftotext(args, timeout=PDFTOTEXT_TIMEOUT):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def audit_pdf(path, keep_text=False):
    """审计 PDF：pdftotext 默认模式 + -layout 交叉比对。
    keep_text=True 时返回值中带 "text"（供 build_registry 复用），否则剔除。"""
    if shutil.which("pdftotext") is None:
        return {"mode": "pdf", "verdict": "tool_missing",
                "error": "pdftotext not found in PATH (install poppler)"}
    try:
        r1 = _run_pdftotext(["pdftotext", path, "-"])
    except Exception as e:  # 超时、权限等
        return {"mode": "pdf", "verdict": "failed", "error": "pdftotext exception: %s" % e}
    if r1.returncode != 0:
        return {"mode": "pdf", "verdict": "failed",
                "error": "pdftotext exit %d: %s" % (r1.returncode, (r1.stderr or "").strip()[:500])}
    text = r1.stdout or ""
    layout_text = ""
    try:
        r2 = _run_pdftotext(["pdftotext", "-layout", path, "-"])
        if r2.returncode == 0:
            layout_text = r2.stdout or ""
    except Exception:
        layout_text = ""
    layout_diff_rate = None
    if text.strip() and layout_text.strip():
        ratio = difflib.SequenceMatcher(None, _collapse_ws(text), _collapse_ws(layout_text)).ratio()
        layout_diff_rate = round(1.0 - ratio, 4)
    stats = text_stats(text)
    out = {"mode": "pdf", "verdict": verdict_from_stats(stats, layout_diff_rate),
           "layout_diff_rate": layout_diff_rate}
    out.update(stats)
    if keep_text:
        out["text"] = text
    return out


def audit_path(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in PDF_EXTS:
        return audit_pdf(path)
    if ext in TEXT_EXTS:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            return {"mode": "text", "verdict": "failed", "error": "read error: %s" % e}
        return audit_text(text)
    return {"mode": "unknown", "verdict": "skipped", "error": "unsupported extension %s" % ext}


def iter_documents(root):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            if os.path.splitext(name)[1].lower() in (TEXT_EXTS | PDF_EXTS):
                yield os.path.join(dirpath, name)


def main(argv=None):
    ap = argparse.ArgumentParser(description="解析保真审计：输出 parse-audit.json")
    ap.add_argument("inputs", nargs="+", help="语料文件或目录（目录递归扫描）")
    ap.add_argument("-o", "--out", default=None, help="输出 JSON 路径（默认打印到 stdout）")
    args = ap.parse_args(argv)

    documents = []
    seen = set()
    for root in args.inputs:
        for path in iter_documents(root):
            apath = os.path.abspath(path)
            if apath in seen:
                continue
            seen.add(apath)
            rec = audit_path(apath)
            rec.pop("text", None)
            documents.append({"path": apath, **rec})

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool_status": {"pdftotext": "available" if shutil.which("pdftotext") else "missing"},
        "thresholds": {
            "min_extracted_chars": MIN_EXTRACTED_CHARS,
            "replacement_char_ratio_degraded": REPL_RATIO_DEGRADED,
            "layout_diff_rate_degraded": DIFF_RATE_DEGRADED,
            "empty_page_ratio_degraded": EMPTY_PAGE_RATIO_DEGRADED,
        },
        "documents": documents,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
        print("parse-audit written to %s (%d documents)" % (args.out, len(documents)))
    else:
        print(payload)
    # 汇总到 stderr 便于管道使用
    counts = {}
    for d in documents:
        counts[d["verdict"]] = counts.get(d["verdict"], 0) + 1
    print("verdict summary: %s" % counts, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
