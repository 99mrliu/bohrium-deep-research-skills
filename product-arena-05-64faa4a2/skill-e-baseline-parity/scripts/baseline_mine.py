#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""baseline_mine.py — 从材料文本中挖掘基线台账。

纯标准库、确定性、无网络。

功能：
  扫描给定目录（或文件）中的 .txt/.md/.log/.yaml/.yml/.json/.csv 文本，
  识别基线提及（baseline/基线/对比方法/SOTA 关键字行、方法名+年份、
  方法名+[n] 引用标记、配置中的 model/name 字段）、版本号、引用标记、
  指标名与数值，判定来源类型（自复现/原报/未知），并给出证据 file:line。

用法：
  python3 baseline_mine.py --input <目录或文件> [--input ...] --out <输出目录>

输出：
  <out>/baselines.json  结构化台账
  <out>/baselines.md    人读表格
退出码：恒为 0（挖掘工具，不做判定）。
"""
import argparse
import json
import os
import re
import sys

SCAN_EXTS = {".txt", ".md", ".log", ".yaml", ".yml", ".json", ".csv"}

BASELINE_KEYWORDS = re.compile(
    r"baseline|基线|对比方法|对照方法|对照组|sota|state-of-the-art", re.IGNORECASE)

# 方法名：首字母大写，允许字母数字与 - _ 连接的分段（如 ResNet-50, VGG-16, BERT-large）
NAME = r"[A-Z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*"
RE_NAME_CITNUM = re.compile(r"\b(%s)\s*\[\s*(\d{1,3})\s*\]" % NAME)          # Name [1]
RE_NAME_YEAR = re.compile(r"\b(%s)\s*[\(\[]\s*((?:19|20)\d{2})\s*[\)\]]" % NAME)  # Name (2016)
RE_NAME_AUTHYEAR = re.compile(
    r"\b(%s)\s*\(\s*[A-Z][A-Za-z\-]+(?:\s+et\s+al\.?)?\s*,?\s*(?:19|20)\d{2}\s*\)" % NAME)  # Name (Author, 2016)
RE_CONFIG_MODEL = re.compile(
    r"^\s*(?:model|baseline|method|backbone|name)\s*[:=]\s*[\"']?(%s)[\"']?\s*$" % NAME)

REPORT_WORDS = re.compile(
    r"原论文|原报|原文报告|报告中|报告|引用自|引自|非同等条件|"
    r"reported|reports|as reported|original paper|from the paper", re.IGNORECASE)
REPRO_WORDS = re.compile(
    r"复现|reproduc|our implementation|re-implement|自训|重训", re.IGNORECASE)
NEG_REPRO = re.compile(
    r"(未|不|无|尚未|并未)[^。；;，,]{0,10}复现|not\s+reproduc|no\s+reproduction",
    re.IGNORECASE)

METRIC_WORDS = [
    "top-1 accuracy", "top-5 accuracy", "accuracy", "acc", "f1-score", "f1",
    "auc", "auroc", "rmse", "mse", "mae", "bleu", "rouge-l", "rouge",
    "precision", "recall", "map", "perplexity", "ppl", "wer", "cer", "psnr", "ssim",
]
RE_METRIC = re.compile(
    r"(top-?[15]\s*accuracy|accuracy|acc|f1(?:-score)?|auroc|auc|rmse|mse|mae|"
    r"bleu|rouge(?:-l)?|precision|recall|map|perplexity|ppl|wer|cer|psnr|ssim)"
    r"\s*(?:of|is|=|:|为|达到|达|：)?\s*(\d{1,3}(?:\.\d+)?)\s*%?",
    re.IGNORECASE)
# 反向：数值在前，如 "71.3% accuracy"；数值前不得紧跟字母/数字/./-/%（避免把 top-1 的 1 当数值）
RE_METRIC_REV = re.compile(
    r"(?<![\w.\-%/])(\d{1,3}(?:\.\d+)?)\s*%?\s*"
    r"(top-?[15]\s*accuracy|accuracy|f1(?:-score)?|"
    r"auroc|auc|rmse|mse|mae|bleu|rouge(?:-l)?|precision|recall|map|perplexity|ppl)",
    re.IGNORECASE)

RE_VERSION = re.compile(r"\b[vV]\d+(?:\.\d+)*\b")
RE_RUN_LINE = re.compile(r"\brun\s*[=:]\s*([A-Za-z0-9_\-]+)")

STOPWORDS = {
    "SOTA", "Baseline", "Baselines", "The", "We", "Our", "Ours", "OurNet",
    "Table", "Figure", "Section", "Eq", "Eq.", "Note", "Abstract", "References",
    "ImageNet", "CIFAR", "CIFAR-10", "CIFAR-100", "MNIST", "ICLR", "CVPR",
    "NeurIPS", "ICML", "ACL", "IEEE", "ACM",
}
SELF_WORDS = re.compile(r"^(ours?|our[-_ ]?method|proposed|本文|我们)$", re.IGNORECASE)
DATASET_WORDS = re.compile(
    r"^(imagenet|cifar|mnist|squad|glue|coco|voc|ade20k|wmt|librispeech)", re.IGNORECASE)


def norm_name(name):
    """归一化方法名用于跨文件匹配（resnet50 == ResNet-50）。"""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def collect_files(inputs):
    files = []
    for item in inputs:
        if os.path.isfile(item):
            files.append(item)
        elif os.path.isdir(item):
            for root, dirs, names in os.walk(item):
                dirs.sort()
                for n in sorted(names):
                    if os.path.splitext(n)[1].lower() in SCAN_EXTS:
                        files.append(os.path.join(root, n))
        else:
            print("警告：输入不存在，已跳过：%s" % item, file=sys.stderr)
    return sorted(dict.fromkeys(files))


def read_lines(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError as e:
        print("警告：无法读取 %s：%s" % (path, e), file=sys.stderr)
        return []


def is_plausible_name(token):
    if token in STOPWORDS or SELF_WORDS.match(token) or DATASET_WORDS.match(token):
        return False
    if token.isupper() and len(token) <= 3 and not any(c.isdigit() for c in token):
        return False  # 纯缩写如 CNN/RNN，缺少年份或引用时不作候选
    return len(token) >= 3


def extract_candidates(files_lines):
    """返回 {norm_name: {"name": 显示名, "citations": set, "config": bool,
    "run_names": set, "keyword_hit": bool}}"""
    cands = {}

    def add(name, citation=None, config=False, run_name=None, keyword=False):
        if not is_plausible_name(name):
            return
        key = norm_name(name)
        if not key:
            return
        rec = cands.setdefault(key, {
            "name": name, "citations": set(), "config": False,
            "run_names": set(), "keyword_hit": False,
        })
        if citation:
            rec["citations"].add(citation)
        if config:
            rec["config"] = True
        if run_name:
            rec["run_names"].add(run_name)
        if keyword:
            rec["keyword_hit"] = True

    for path, lines in files_lines:
        for text in lines:
            for m in RE_NAME_CITNUM.finditer(text):
                add(m.group(1), citation="[%s]" % m.group(2))
            for m in RE_NAME_YEAR.finditer(text):
                add(m.group(1), citation="(%s)" % m.group(2))
            for m in RE_NAME_AUTHYEAR.finditer(text):
                add(m.group(1), citation="(Author, year)")
            m = RE_CONFIG_MODEL.match(text)
            if m:
                add(m.group(1), config=True)
            m = RE_RUN_LINE.search(text)
            if m:
                add(m.group(1), run_name=m.group(1))
            if BASELINE_KEYWORDS.search(text):
                for m in re.finditer(r"\b(%s)\b" % NAME, text):
                    add(m.group(1), keyword=True)
    return cands


def find_metrics(text):
    out = []
    for m in RE_METRIC.finditer(text):
        out.append((m.group(1), m.group(2)))
    for m in RE_METRIC_REV.finditer(text):
        out.append((m.group(2), m.group(1)))
    return out


def classify_source(rec, evidence_texts):
    """自复现 / 原报 / 未知。自复现优先（有 run 或 config 证据且非纯引用）。"""
    has_repro_text = any(
        REPRO_WORDS.search(t) and not NEG_REPRO.search(t)
        for t in evidence_texts)
    has_repro = bool(rec["run_names"]) or rec["config"] or has_repro_text
    has_report = bool(rec["citations"]) and \
        any(REPORT_WORDS.search(t) for t in evidence_texts)
    if has_repro:
        return "自复现", "材料中存在该基线的运行配置或日志证据"
    if has_report:
        return "原报", "数值引自原论文/原报值，未在本工作中复现，非同等条件"
    if rec["citations"]:
        return "原报", "带引用标记但未见复现证据，按原报处理（非同等条件）"
    return "未知", "仅见名称提及，无法判定来源，需人工确认"


def main():
    ap = argparse.ArgumentParser(description="挖掘基线台账")
    ap.add_argument("--input", action="append", required=True,
                    help="输入目录或文件，可重复")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--max-evidence", type=int, default=8,
                    help="每个基线最多保留的证据条数（默认 8）")
    args = ap.parse_args()

    files = collect_files(args.input)
    files_lines = [(p, read_lines(p)) for p in files]
    cands = extract_candidates(files_lines)

    # 汇总证据 / 版本 / 指标
    baselines = []
    for key in sorted(cands.keys()):
        rec = cands[key]
        name = rec["name"]
        evidence, versions, metrics = [], set(), []
        for path, lines in files_lines:
            for i, text in enumerate(lines, 1):
                hit = False
                # 名字命中（含 run=xxx 的归一化匹配）
                if re.search(r"\b%s\b" % re.escape(name), text):
                    hit = True
                else:
                    m = RE_RUN_LINE.search(text)
                    if m and norm_name(m.group(1)) == key:
                        hit = True
                if not hit:
                    continue
                if len(evidence) < args.max_evidence:
                    evidence.append({"file": path, "line": i,
                                     "text": text.strip()[:200]})
                for vm in RE_VERSION.finditer(text):
                    versions.add(vm.group(0))
                for mname, mval in find_metrics(text):
                    metrics.append({"metric": mname, "value": mval,
                                    "file": path, "line": i})
        source_type, source_detail = classify_source(
            rec, [e["text"] for e in evidence])
        baselines.append({
            "name": name,
            "normalized": key,
            "version": sorted(versions)[0] if versions else None,
            "versions_seen": sorted(versions),
            "source_type": source_type,
            "source_detail": source_detail,
            "citations": sorted(rec["citations"]),
            "metrics": metrics,
            "evidence": evidence,
        })

    result = {
        "tool": "baseline_mine",
        "inputs": args.input,
        "files_scanned": files,
        "baseline_count": len(baselines),
        "baselines": baselines,
    }

    os.makedirs(args.out, exist_ok=True)
    jpath = os.path.join(args.out, "baselines.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    mpath = os.path.join(args.out, "baselines.md")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("# 基线台账（baseline_mine 自动产出，需人工复核）\n\n")
        f.write("| 基线 | 版本 | 来源类型 | 引用标记 | 关联指标 | 证据(file:line) |\n")
        f.write("|---|---|---|---|---|---|\n")
        for b in baselines:
            mets = "; ".join(sorted({"%s=%s" % (m["metric"], m["value"])
                                     for m in b["metrics"]})) or "—"
            evs = "; ".join("%s:%d" % (os.path.basename(e["file"]), e["line"])
                            for e in b["evidence"][:4]) or "—"
            f.write("| %s | %s | %s | %s | %s | %s |\n" % (
                b["name"], b["version"] or "—", b["source_type"],
                ", ".join(b["citations"]) or "—", mets, evs))
        f.write("\n> 来源类型为启发式判定：自复现=配置/日志有运行证据；"
                "原报=数值引自原文（非同等条件）；未知=需人工确认。\n")

    print("baseline_mine：扫描 %d 个文件，识别基线 %d 个 -> %s, %s"
          % (len(files), len(baselines), jpath, mpath))
    for b in baselines:
        print("  - %s [%s] 版本=%s 引用=%s 指标=%d条"
              % (b["name"], b["source_type"], b["version"] or "—",
                 ",".join(b["citations"]) or "—", len(b["metrics"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
