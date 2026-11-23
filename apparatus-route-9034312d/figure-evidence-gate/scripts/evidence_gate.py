#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evidence_gate.py — 证据门禁：逐条核验台账 quote 是否真实存在于抽取源文本中。

用法:
    python3 evidence_gate.py <ledger.json> --sources-dir <dir> [--report gate_report.json]

判定:
    verified            quote 经归一化后精确出现于 source.file 指定的抽取文本中
    unverified          源文件存在但找不到匹配（附 difflib 近失提示，便于修正笔误）
    missing-source-file source.file 指向的抽取文本不存在
    invalid             元素缺少必需字段（id/kind/label/source.file/source.quote）
    waived              元素被显式豁免（waived:true 且含 waiver_reason），不计失败

退出码: 0 = 全部 verified/waived；1 = 存在失败项；2 = 参数/IO 错误（仍尽量写报告）。
任何情况下都会尽力写出 gate_report.json，绝不静默崩溃。报告不含时间戳，输出确定。
"""
import argparse
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

CJK = r"\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"

# 常见弯引号/破折号归一为 ASCII，避免 PDF 抽取与手写引号不一致
PUNCT_MAP = {
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "–": "-", "—": "-", "―": "-", "−": "-",
    "…": "...", "　": " ", "­": "",  # 全角空格 / soft hyphen
}


def normalize(s: str) -> str:
    """归一化：NFKC（全角→半角、兼容字符）+ 引号映射 + 空白折叠 +
    去除 CJK 字符之间的空格（pdftotext 常在中文间插入换行/空格）。"""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKC", s)
    for k, v in PUNCT_MAP.items():
        s = s.replace(k, v)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"(?<=[" + CJK + r"]) (?=[" + CJK + r"])", "", s)
    return s.strip()


def split_candidates(raw_text: str):
    """把原始源文本逐行归一化后切成候选片段（行 + 句），用于近失提示。"""
    chunks = []
    for line in raw_text.split("\n"):
        line = normalize(line)
        if not line:
            continue
        chunks.append(line)
        for sent in re.split(r"(?<=[。．.!?！？;；])\s*", line):
            sent = sent.strip()
            if sent and sent != line:
                chunks.append(sent)
    return chunks


def near_miss(norm_quote: str, raw_text: str, topn: int = 3):
    """返回与 quote 最相似的候选片段（含相似度），供人工修正笔误。"""
    candidates = split_candidates(raw_text)
    if not candidates:
        return []
    scored = []
    for c in candidates:
        # 长度相差悬殊的片段直接跳过，节省时间
        if len(c) == 0 or min(len(c), len(norm_quote)) / max(len(c), len(norm_quote)) < 0.3:
            continue
        r = difflib.SequenceMatcher(None, norm_quote, c).ratio()
        if r >= 0.45:
            scored.append((r, c))
    scored.sort(key=lambda x: -x[0])
    return [{"similarity": round(r, 3),
             "candidate": c[:300]} for r, c in scored[:topn]]


def load_ledger(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("elements", [])
    if isinstance(data, list):
        return data
    raise ValueError("ledger.json 必须是对象（含 elements[]）或元素数组")


def verify_element(el, sources_dir: Path, cache: dict):
    """返回 (verdict, detail_dict)。"""
    eid = el.get("id", "<no-id>")
    if el.get("waived") is True:
        reason = el.get("waiver_reason", "")
        if isinstance(reason, str) and reason.strip():
            return "waived", {"waiver_reason": reason.strip()}
        return "invalid", {"error": "waived:true 但缺少 waiver_reason"}

    missing = [k for k in ("id", "kind", "label") if not el.get(k)]
    src = el.get("source")
    if not isinstance(src, dict):
        missing.append("source")
    else:
        if not src.get("file"):
            missing.append("source.file")
        if not src.get("quote"):
            missing.append("source.quote")
    if missing:
        return "invalid", {"error": "缺少必需字段: " + ", ".join(missing)}

    sfile = src["file"]
    # 防路径穿越：只允许指向 sources-dir 内的文件
    cand = (sources_dir / sfile).resolve()
    try:
        cand.relative_to(sources_dir.resolve())
    except ValueError:
        return "missing-source-file", {"error": f"source.file 越出 sources-dir: {sfile}"}
    if not cand.is_file():
        return "missing-source-file", {"error": f"找不到抽取文本: {sfile}"}

    if str(cand) not in cache:
        cache[str(cand)] = cand.read_text(encoding="utf-8", errors="replace")
    raw = cache[str(cand)]
    norm_text = normalize(raw)
    norm_quote = normalize(src["quote"])

    if norm_quote and norm_quote in norm_text:
        return "verified", {"locator": src.get("locator", "")}
    detail = {"locator": src.get("locator", ""),
              "error": "quote 未在源文件中找到（归一化后精确匹配失败）",
              "near_miss": near_miss(norm_quote, raw)}
    return "unverified", detail


def main(argv=None):
    ap = argparse.ArgumentParser(description="证据门禁：核验台账 quote 可溯源性")
    ap.add_argument("ledger", help="ledger.json 路径")
    ap.add_argument("--sources-dir", required=True,
                    help="抽取源文本目录（/app/work/sources）")
    ap.add_argument("--report", default="gate_report.json", help="报告输出路径")
    args = ap.parse_args(argv)

    report = {"tool": "evidence_gate.py",
              "ledger": str(Path(args.ledger).resolve()),
              "sources_dir": str(Path(args.sources_dir).resolve()),
              "summary": {"total": 0, "verified": 0, "unverified": 0,
                          "missing-source-file": 0, "invalid": 0, "waived": 0},
              "elements": [],
              "verdict": "failed"}
    rc = 0
    try:
        elements = load_ledger(Path(args.ledger))
        sources_dir = Path(args.sources_dir)
        cache = {}
        for el in elements:
            if not isinstance(el, dict):
                report["elements"].append({"id": "<non-object>", "verdict": "invalid",
                                           "detail": {"error": "元素必须是 JSON 对象"}})
                report["summary"]["invalid"] += 1
                continue
            verdict, detail = verify_element(el, sources_dir, cache)
            report["summary"]["total"] += 1
            report["summary"][verdict] += 1
            report["elements"].append({"id": el.get("id", "<no-id>"),
                                       "kind": el.get("kind"),
                                       "verdict": verdict,
                                       "detail": detail})
        s = report["summary"]
        failed = s["unverified"] + s["missing-source-file"] + s["invalid"]
        report["verdict"] = "passed" if failed == 0 else "failed"
        rc = 0 if failed == 0 else 1
    except Exception as exc:  # 绝不无报告崩溃
        report["verdict"] = "error"
        report["error"] = f"{type(exc).__name__}: {exc}"
        rc = 2
    try:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"[evidence_gate] 无法写报告 {args.report}: {exc}", file=sys.stderr)
        rc = 2
    s = report["summary"]
    print(f"[evidence_gate] verdict={report['verdict']} total={s['total']} "
          f"verified={s['verified']} waived={s['waived']} "
          f"unverified={s['unverified']} missing_src={s['missing-source-file']} "
          f"invalid={s['invalid']} -> {args.report}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
