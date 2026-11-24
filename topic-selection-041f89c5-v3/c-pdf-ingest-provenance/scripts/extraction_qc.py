#!/usr/bin/env python3
"""extraction_qc.py — 文本层质检 + 页级引文定位。

子命令：
  qc       对 source_registry.json 中所有来源做质量判定：
           空页、低文字页（<20 字符）、乱码率（>0.02）分级为 ok/suspect/unreadable；
           存在 unreadable 来源时退出码为 1（相关结论必须降级）。
  locate   把一段引文（逐字复制）定位到 来源文件 + 页码 + 字符偏移：
           NFKC + 空白折叠归一化后做子串匹配；找不到时退出码为 1，
           该引文不得进入证据矩阵。

用法：
  python3 extraction_qc.py qc --registry /app/work/source_registry.json \
      --out /app/work/qc
  python3 extraction_qc.py locate --registry /app/work/source_registry.json \
      --quote "逐字引文"
  python3 extraction_qc.py locate --registry ... --quote-file quote.txt
仅依赖 Python 3 标准库。
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

GARBLE_THRESHOLD = 0.02
LOW_TEXT_CHARS = 20


def normalize(text):
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def load_registry(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"registry 读取失败: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_qc(args):
    reg = load_registry(args.registry)
    work = Path(args.registry).parent
    verdicts = []
    for s in reg["sources"]:
        pages = s.get("pages")
        if not pages:
            verdicts.append({"file": s["file"], "verdict": "n/a",
                             "reason": s["status"]})
            continue
        empty = [p["page"] for p in pages if p["chars"] == 0]
        low = [p["page"] for p in pages
               if 0 < p["chars"] < LOW_TEXT_CHARS]
        garbled = [p["page"] for p in pages
                   if p["garble_ratio"] > GARBLE_THRESHOLD]
        total_chars = sum(p["chars"] for p in pages)
        if s["status"] != "ok":
            verdict, reason = "unreadable", s["status"]
        elif total_chars == 0:
            verdict, reason = "unreadable", "全部页面无文字（疑似扫描件）"
        elif garbled or len(empty) == len(pages):
            verdict = "suspect"
            reason = "乱码页:%s 空页:%s" % (garbled or "-", empty or "-")
        elif empty or low:
            verdict = "ok_with_notes"
            reason = "空页:%s 低文字页:%s" % (empty or "-", low or "-")
        else:
            verdict, reason = "ok", "-"
        verdicts.append({"file": s["file"], "verdict": verdict,
                         "reason": reason, "pages": len(pages),
                         "total_chars": total_chars})
    bad = [v for v in verdicts if v["verdict"] == "unreadable"]
    report = {"registry": str(args.registry), "verdicts": verdicts,
              "unreadable_sources": [v["file"] for v in bad],
              "rule": ("unreadable: 相关结论必须降级为 partial 并说明；"
                       "suspect: 引用前人工目检对应页；"
                       "ok_with_notes: 空页/低文字页已记录")}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "qc_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    md = ["# 文本层质检报告（机器生成）", "",
          "| 来源 | 判定 | 页数 | 字符数 | 说明 |", "|-|-|-|-|-|"]
    md += ["| %s | %s | %s | %s | %s |"
           % (v["file"], v["verdict"], v.get("pages", "-"),
              v.get("total_chars", "-"), v["reason"]) for v in verdicts]
    (out / "qc_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(out),
                      "unreadable": report["unreadable_sources"]},
                     ensure_ascii=False))
    if bad:
        sys.exit(1)


def cmd_locate(args):
    reg = load_registry(args.registry)
    work = Path(args.registry).parent
    if args.quote_file:
        quote = Path(args.quote_file).read_text(encoding="utf-8")
    else:
        quote = args.quote or ""
    needle = normalize(quote)
    if len(needle) < 8:
        print("引文太短（归一化后 <8 字符），不足以定位", file=sys.stderr)
        sys.exit(1)
    hits = []
    for s in reg["sources"]:
        layer = s.get("text_layer")
        if not layer:
            continue
        text_path = work / layer
        if not text_path.exists():
            continue
        raw = text_path.read_text(encoding="utf-8", errors="replace")
        for i, page_text in enumerate(raw.split("\f"), 1):
            hay = normalize(page_text)
            pos = hay.find(needle)
            if pos >= 0:
                hits.append({"file": s["file"], "page": i,
                             "char_offset": pos,
                             "locator": f"{s['file']} 第{i}页"})
    print(json.dumps({"quote_head": needle[:60], "hits": hits},
                     ensure_ascii=False, indent=2))
    if not hits:
        print("LOCATE: 未找到——该引文不得作为证据使用", file=sys.stderr)
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("qc")
    p.add_argument("--registry", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_qc)
    p = sub.add_parser("locate")
    p.add_argument("--registry", required=True)
    p.add_argument("--quote", default=None)
    p.add_argument("--quote-file", default=None)
    p.set_defaults(fn=cmd_locate)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
