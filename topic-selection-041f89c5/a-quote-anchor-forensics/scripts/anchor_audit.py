#!/usr/bin/env python3
"""anchor_audit.py — 证据锚点取证核验器（quote-anchor-forensics 技能的核心脚本）。

用途：对一份证据台账（JSONL）逐条做可机检的真实性核验：
  1. 来源登记：扫描来源目录，为每个文件登记字节数与 SHA-256；
  2. 逐字引用核验：台账记录中的 quote 经 Unicode NFKC + 空白折叠归一化后，
     必须是指定来源文件归一化全文的子串；找不到即判 FAIL，绝不放行；
  3. 元数据抽查：记录可选带 check_fields（如 title/year），其值也必须能在
     来源原文中找到；
  4. 可选字符偏移核验：记录给出 char_offset（基于归一化全文）时必须吻合。

输出：--out 目录下
  source_registry.json   来源登记册（文件名、字节数、SHA-256）
  audit_report.json      逐条判定与汇总
  audit_report.md        人读版核验报告
退出码：全部通过 0；存在 FAIL/ERROR 为 1；参数或 IO 错误为 2。
仅依赖 Python 3.8+ 标准库。

台账格式（每行一个 JSON 对象）：
  {"id": "E1", "claim": "综述中要使用的陈述",
   "source_file": "paper1.txt",          # 相对 --sources 的文件名
   "quote": "逐字摘自来源的原文片段",
   "locator": "page 3, column 2",        # 人读定位，信息性字段
   "char_offset": 1234,                   # 可选；归一化全文中的偏移
   "check_fields": {"title": "..."}      # 可选；元数据抽查
  }
"""
import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path


def normalize(text):
    """NFKC 归一化 + 全角空白处理 + 空白折叠，用于逐字比对的公平基准。"""
    text = unicodedata.normalize("NFKC", text)
    return " ".join(text.split())


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_registry(sources_dir):
    registry = []
    for p in sorted(sources_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(sources_dir))
        entry = {"file": rel, "bytes": p.stat().st_size,
                 "sha256": sha256_of(p)}
        try:
            entry["text"] = p.read_text(encoding="utf-8")
            entry["readable"] = True
        except (UnicodeDecodeError, OSError) as exc:
            entry["readable"] = False
            entry["error"] = str(exc)
        registry.append(entry)
    return registry


def audit_record(rec, registry_by_file):
    rid = rec.get("id", "<no-id>")
    problems = []
    src_name = rec.get("source_file", "")
    entry = registry_by_file.get(src_name)
    if entry is None:
        return {"id": rid, "verdict": "ERROR",
                "problems": ["source_file 不在来源目录: %s" % src_name]}
    if not entry.get("readable"):
        return {"id": rid, "verdict": "ERROR",
                "problems": ["来源文件不可解析: %s" % entry.get("error", "?")]}
    norm_text = normalize(entry["text"])
    quote = rec.get("quote", "")
    if not quote.strip():
        problems.append("quote 为空")
        offset = -1
    else:
        nq = normalize(quote)
        offset = norm_text.find(nq)
        if offset < 0:
            problems.append("quote 在来源全文中找不到逐字匹配（归一化后）")
        elif norm_text.find(nq, offset + 1) >= 0:
            problems.append("quote 在来源中出现多次，锚点不唯一，需加长引文")
    if "char_offset" in rec and offset >= 0:
        if rec["char_offset"] != offset:
            problems.append("char_offset=%s 与实际偏移 %d 不符"
                            % (rec["char_offset"], offset))
    for key, val in (rec.get("check_fields") or {}).items():
        if normalize(str(val)) not in norm_text:
            problems.append("check_fields.%s 的值在来源中找不到: %r" % (key, val))
    if not rec.get("locator"):
        problems.append("缺少人读定位 locator（页码/小节）")
    verdict = "PASS" if not problems else "FAIL"
    return {"id": rid, "verdict": verdict, "source_file": src_name,
            "char_offset": offset if offset >= 0 else None,
            "problems": problems}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sources", required=True, help="来源文件目录")
    ap.add_argument("--ledger", required=True, help="证据台账 JSONL")
    ap.add_argument("--out", required=True, help="输出目录")
    args = ap.parse_args()

    sources_dir = Path(args.sources)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not sources_dir.is_dir():
        print("sources 目录不存在: %s" % sources_dir, file=sys.stderr)
        return 2

    registry = build_registry(sources_dir)
    registry_by_file = {e["file"]: e for e in registry}
    public_registry = [{k: v for k, v in e.items() if k != "text"}
                       for e in registry]
    (out_dir / "source_registry.json").write_text(
        json.dumps(public_registry, ensure_ascii=False, indent=2),
        encoding="utf-8")

    records = []
    with open(args.ledger, encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                records.append({"id": "line-%d" % ln, "_parse_error": str(exc)})

    results = []
    for rec in records:
        if "_parse_error" in rec:
            results.append({"id": rec["id"], "verdict": "ERROR",
                            "problems": ["JSONL 解析失败: " + rec["_parse_error"]]})
        else:
            results.append(audit_record(rec, registry_by_file))

    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0}
    for r in results:
        counts[r["verdict"]] += 1
    summary = {"total": len(results), **counts,
               "all_passed": counts["FAIL"] == 0 and counts["ERROR"] == 0}
    report = {"summary": summary, "results": results}
    (out_dir / "audit_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 证据锚点核验报告", "",
             "来源文件 %d 个；台账记录 %d 条：PASS %d / FAIL %d / ERROR %d。"
             % (len(registry), summary["total"], counts["PASS"],
                counts["FAIL"], counts["ERROR"]), "",
             "| 记录 | 来源文件 | 判定 | 问题 |", "|---|---|---|---|"]
    for r in results:
        lines.append("| %s | %s | %s | %s |" % (
            r["id"], r.get("source_file", "-"), r["verdict"],
            "<br>".join(r["problems"]) if r["problems"] else "-"))
    lines.append("")
    lines.append("来源登记册（SHA-256 见 source_registry.json）：")
    for e in public_registry:
        lines.append("- `%s`（%d 字节，%s）" % (
            e["file"], e["bytes"],
            "可解析" if e["readable"] else "不可解析: " + e.get("error", "?")))
    (out_dir / "audit_report.md").write_text("\n".join(lines) + "\n",
                                             encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
