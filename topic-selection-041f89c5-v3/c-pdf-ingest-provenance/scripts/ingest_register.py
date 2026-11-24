#!/usr/bin/env python3
"""ingest_register.py — 摄入登记器：把 /input 材料变成带页级溯源的可信文本层。

对输入目录逐个文件登记（SHA-256、字节数、类型）；PDF 用系统可用的
pdftotext 真实解析（不假设存在预提取文本层），按 \\f 拆页并记录每页字符数；
TXT/MD 作为单页文本源登记。产物：
  WORK/source_registry.json   来源登记册（含每页字符统计与提取状态）
  WORK/ingest_report.md       人读摄入报告
  WORK/sources/<name>.txt     提取出的文本层（页间以 \\f 分隔）

用法：
  python3 ingest_register.py --input /input --work /app/work
退出码：0 正常（个别来源失败会登记在 registry 而不中断）；1 输入目录不存在。
仅依赖 Python 3 标准库；PDF 解析依赖系统 pdftotext，缺失时如实登记 tool_missing。
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

TEXT_KINDS = {".txt", ".md"}
RECORD_KINDS = {".json", ".jsonl", ".csv"}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def garble_ratio(text):
    if not text:
        return 0.0
    bad = 0
    for ch in text:
        if ch in "\n\t\f\r":
            continue
        cat = unicodedata.category(ch)
        if ch == "�" or cat in ("Cc", "Cf"):
            bad += 1
    return round(bad / len(text), 4)


def extract_pdf(pdf_path, out_txt):
    tool = shutil.which("pdftotext")
    if not tool:
        return {"status": "tool_missing",
                "detail": "系统无 pdftotext；需改用运行环境提供的 "
                          "pdf-text-tool 后重跑本脚本"}
    proc = subprocess.run([tool, "-layout", str(pdf_path), str(out_txt)],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        return {"status": "extract_failed",
                "detail": (proc.stderr or "").strip()[:300]}
    raw = Path(out_txt).read_text(encoding="utf-8", errors="replace")
    pages = raw.split("\f")
    # pdftotext 在末页后也会输出一个 \f，产生且仅产生一个尾部空块；
    # 只弹掉这一个——真实的空白末页必须保留，否则 QC 无法检出
    if pages and not pages[-1].strip():
        pages.pop()
    return {"status": "ok" if any(p.strip() for p in pages)
            else "empty_extraction",
            "pages": [{"page": i + 1, "chars": len(p.strip()),
                       "garble_ratio": garble_ratio(p)}
                      for i, p in enumerate(pages)]}


def register_text(path, out_txt):
    raw = path.read_text(encoding="utf-8", errors="replace")
    Path(out_txt).write_text(raw, encoding="utf-8")
    return {"status": "ok" if raw.strip() else "empty_extraction",
            "pages": [{"page": 1, "chars": len(raw.strip()),
                       "garble_ratio": garble_ratio(raw)}]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    args = ap.parse_args()
    in_dir = Path(args.input)
    if not in_dir.is_dir():
        print(f"输入目录不存在: {in_dir}", file=sys.stderr)
        sys.exit(1)
    work = Path(args.work)
    src_dir = work / "sources"
    src_dir.mkdir(parents=True, exist_ok=True)

    registry = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "input_dir": str(in_dir.resolve()), "sources": []}
    for path in sorted(p for p in in_dir.rglob("*") if p.is_file()):
        rel = str(path.relative_to(in_dir))
        suffix = path.suffix.lower()
        entry = {"file": rel, "bytes": path.stat().st_size,
                 "sha256": sha256_of(path),
                 "kind": suffix.lstrip(".") or "unknown"}
        safe_name = rel.replace("/", "__") + ".txt"
        if suffix == ".pdf":
            entry.update(extract_pdf(path, src_dir / safe_name))
            entry["text_layer"] = "sources/" + safe_name
        elif suffix in TEXT_KINDS:
            entry.update(register_text(path, src_dir / safe_name))
            entry["text_layer"] = "sources/" + safe_name
        elif suffix in RECORD_KINDS:
            entry["status"] = "registered"
            entry["detail"] = "记录型材料（非引文来源）；按结构读取，不建文本层"
        else:
            entry["status"] = "skipped"
            entry["detail"] = "未支持的类型；如任务需要请人工确认处理方式"
        registry["sources"].append(entry)

    reg_path = work / "source_registry.json"
    reg_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2)
                        + "\n", encoding="utf-8")

    lines = ["# 摄入报告（机器生成）", "",
             f"输入目录：`{registry['input_dir']}`",
             f"来源数：{len(registry['sources'])}", "",
             "| 文件 | 类型 | 字节 | 状态 | 页数 | 空页/乱码 |",
             "|-|-|-|-|-|-|"]
    for s in registry["sources"]:
        pages = s.get("pages") or []
        n_pages = len(pages)
        empties = [p["page"] for p in pages if p["chars"] == 0]
        garbled = [p["page"] for p in pages if p["garble_ratio"] > 0.02]
        notes = []
        if empties:
            notes.append("空页:" + ",".join(map(str, empties)))
        if garbled:
            notes.append("疑似乱码页:" + ",".join(map(str, garbled)))
        lines.append("| %s | %s | %d | %s | %s | %s |"
                     % (s["file"], s["kind"], s["bytes"], s["status"],
                        n_pages or "-", "; ".join(notes) or "-"))
    lines += ["", "状态释义：ok=已建文本层；empty_extraction=解析成功但无文字"
              "（可能为扫描件，需 OCR）；tool_missing/extract_failed=需换工具"
              "重试；registered=记录型材料；skipped=未支持类型。"]
    (work / "ingest_report.md").write_text("\n".join(lines) + "\n",
                                           encoding="utf-8")
    print(json.dumps({"ok": True, "registry": str(reg_path),
                      "sources": len(registry["sources"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
