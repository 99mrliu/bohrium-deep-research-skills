#!/usr/bin/env python3
"""query_lint.py — 检索式静态审计（lint）。

对"概念块定义"与"已序列化的各源查询串"两个层面执行确定性 lint 规则，
每条 finding 给出修改建议。规则表见 references/lint-rules.md：

  QL001 (info)  crossref 方言中多词 term 短语语义丢失
  QL002 (error) 序列化查询串中出现裸 OR（未加括号的分组）
  QL003 (warn)  过宽单词 term（噪声源）；若为块内唯一 term 则升为 error
  QL004 (error) 在不支持通配符的源（crossref/arxiv）中使用 * 或 ?
  QL005 (warn)  同块内存在仅大小写不同的重复 term
  QL006 (error) 空概念块
  QL007 (warn)  term 自带引号，存在双重引用风险

仅用 Python3 标准库，完全离线，确定性输出。

用法:
  python3 query_lint.py --concepts concepts.json --queries queries.json --out lint_report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BROAD_TERMS = {
    "model", "models", "data", "study", "studies", "analysis", "method",
    "methods", "system", "systems", "approach", "property", "properties",
    "learning", "prediction", "network", "networks", "review", "results",
}

RULE_DOC = {
    "QL001": "crossref 无短语语义：多词 term 词序约束丢失",
    "QL002": "裸 OR 无括号：布尔优先级可能与意图不符",
    "QL003": "过宽单词 term：引入大量噪声",
    "QL004": "该源不支持通配符",
    "QL005": "大小写变体重复 term",
    "QL006": "空概念块",
    "QL007": "term 自带引号：双重引用风险",
}


def _finding(rule, severity, message, suggestion, concept=None, term=None, source=None):
    return {
        "rule_id": rule,
        "severity": severity,
        "concept": concept,
        "term": term,
        "source": source,
        "message": message,
        "suggestion": suggestion,
    }


def lint_concepts(concepts: list[dict]) -> list[dict]:
    findings: list[dict] = []
    for blk in concepts:
        bid = blk.get("id")
        terms = blk.get("terms", [])
        if not terms:
            findings.append(_finding(
                "QL006", "error",
                f"概念块 '{bid}' 没有任何 term，AND 语义下会使整体召回为 0",
                "删除该块或补充至少一个 term", concept=bid))
            continue
        lowered: dict[str, str] = {}
        for t in terms:
            key = t.strip().lower()
            if key in lowered and lowered[key] != t:
                findings.append(_finding(
                    "QL005", "warn",
                    f"块 '{bid}' 中 '{lowered[key]}' 与 '{t}' 仅大小写不同",
                    "保留一种写法；各源检索均大小写不敏感，重复徒增审计成本",
                    concept=bid, term=t))
            lowered.setdefault(key, t)
            stripped = t.strip()
            if stripped.startswith('"') or stripped.endswith('"'):
                findings.append(_finding(
                    "QL007", "warn",
                    f"块 '{bid}' 的 term '{t}' 自带引号，序列化时可能产生双重引用",
                    "在概念块中存裸 term，引号由 query_build 按方言添加",
                    concept=bid, term=t))
            if "*" in t or "?" in t:
                for src in ("crossref", "arxiv"):
                    findings.append(_finding(
                        "QL004", "error",
                        f"term '{t}' 含通配符，{src} 不支持通配符扩展",
                        "改用枚举同义词（OR 组）替代截断符；Europe PMC 才支持词尾 *",
                        concept=bid, term=t, source=src))
            if " " not in stripped and stripped.lower() in BROAD_TERMS:
                sev = "error" if len(terms) == 1 else "warn"
                findings.append(_finding(
                    "QL003", sev,
                    f"块 '{bid}' 的单词 term '{t}' 过于宽泛，会引入大量噪声",
                    "替换为更具体的多词短语，或与块内其他 term 合并为短语；"
                    "若为唯一 term 则该块实际上起不到限定作用",
                    concept=bid, term=t))
    return findings


def lint_queries(queries: dict, concepts: list[dict]) -> list[dict]:
    findings: list[dict] = []
    # QL001: crossref 序列化中多词 term 短语语义丢失
    for blk in concepts:
        for t in blk.get("terms", []):
            if " " in t.strip():
                findings.append(_finding(
                    "QL001", "info",
                    f"多词 term '{t}' 在 crossref query.bibliographic 中退化为无序词集合",
                    "Crossref 结果需在客户端做短语级后置过滤，或以 Europe PMC/arXiv 的"
                    "短语查询为准、Crossref 仅作补充召回",
                    concept=blk.get("id"), term=t, source="crossref"))
    # QL002: 裸 OR（顶层 AND 分段内含 OR 且无括号）
    for src, q in queries.items():
        qs = (q or {}).get("query") or ""
        for seg in qs.split(" AND "):
            seg = seg.strip()
            if " OR " in seg and not seg.startswith("("):
                findings.append(_finding(
                    "QL002", "error",
                    f"{src} 查询串分段 '{seg[:60]}...' 含裸 OR 且未加括号",
                    "给每个 OR 组显式加括号，避免 AND/OR 优先级歧义",
                    source=src))
    return findings


def lint(concepts: list[dict], queries: dict) -> dict:
    findings = lint_concepts(concepts) + lint_queries(queries, concepts)
    summary = {"error": 0, "warn": 0, "info": 0}
    for f in findings:
        summary[f["severity"]] = summary.get(f["severity"], 0) + 1
    return {
        "findings": findings,
        "summary": summary,
        "rule_table": RULE_DOC,
        "note": "lint 只做静态审计与建议，不自动改写检索式；召回类问题交给 coverage_check 诊断",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="检索式静态审计")
    ap.add_argument("--concepts", required=True)
    ap.add_argument("--queries", required=True, help="query_build 的输出（含 concepts/window/queries）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    qdoc = json.loads(Path(args.queries).read_text(encoding="utf-8"))
    cdoc = json.loads(Path(args.concepts).read_text(encoding="utf-8"))
    concepts = cdoc["concepts"] if isinstance(cdoc, dict) and "concepts" in cdoc else cdoc
    report = lint(concepts, qdoc["queries"])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[query_lint] findings={len(report['findings'])} summary={report['summary']} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
