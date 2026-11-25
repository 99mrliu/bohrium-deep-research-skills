#!/usr/bin/env python3
"""concept_parse.py — 研究问题 -> 概念块（PICO 式：object / method / scenario）。

输入 case.json：
  - 若 case.json 直接给出 "concepts"（list[{id,label,terms}]），校验结构后直接使用（推荐路径，
    确定性最高）；
  - 否则从 "research_question"（必要时拼接 task 文本）用确定性规则抽取概念块，
    此时 degraded=true、needs_model_review=true，提示模型必须人工复核；
  - 两者皆无时诚实降级：输出空 concepts + warnings，退出码仍为 0，由下游/模型决定如何处理。

仅用 Python3 标准库，完全离线，同样输入必然产生同样输出。

用法:
  python3 concept_parse.py --case /input/case.json [--task /input/task.md] --out concepts.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BLOCK_IDS = ("object", "method", "scenario")

EDGE_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "and", "or", "to", "for", "with",
    "via", "using", "use", "based", "by", "at", "as", "from", "into", "that",
    "which", "what", "which", "recent", "latest", "new", "novel", "studies",
    "study", "papers", "literature", "research", "apply", "applied",
    "applications", "application", "settings", "setting",
}


def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def validate_concepts(raw) -> tuple[list[dict], list[str]]:
    """校验 case.json 给出的 concepts 结构，返回 (concepts, problems)。"""
    problems: list[str] = []
    concepts: list[dict] = []
    if not isinstance(raw, list):
        return [], ["concepts 字段不是 list"]
    seen_ids: set[str] = set()
    for i, blk in enumerate(raw):
        if not isinstance(blk, dict):
            problems.append(f"concepts[{i}] 不是 object")
            continue
        bid = str(blk.get("id") or f"block{i}")
        terms = blk.get("terms")
        if not isinstance(terms, list) or not all(isinstance(t, str) for t in terms):
            problems.append(f"concepts[{i}].terms 不是 string list")
            continue
        terms = [norm_space(t) for t in terms if norm_space(t)]
        if not terms:
            problems.append(f"concept block '{bid}' 无任何 term")
        if bid in seen_ids:
            problems.append(f"concept block id 重复: '{bid}'")
        seen_ids.add(bid)
        concepts.append({
            "id": bid,
            "label": str(blk.get("label") or bid),
            "terms": terms,
        })
    return concepts, problems


def _clean_phrase(phrase: str, max_tokens: int = 5) -> str:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-]*", phrase.lower())
    while tokens and tokens[0] in EDGE_STOPWORDS:
        tokens.pop(0)
    while tokens and tokens[-1] in EDGE_STOPWORDS:
        tokens.pop()
    tokens = tokens[:max_tokens]
    if not tokens or all(t in EDGE_STOPWORDS for t in tokens):
        return ""
    return " ".join(tokens)


def heuristic_parse(text: str) -> tuple[list[dict], list[str]]:
    """从自由文本按确定性规则抽取概念块。这是兜底降级路径，结果必须人工复核。

    规则（按序执行，先到先得）:
      R1  method   <- "using|via|with|based on X" 之后、在 for/in/to/标点之前的名词短语
      R2  object   <- "for|of X" 之后、在 in/using/via/标点之前的名词短语
      R3  scenario <- "in|under|during X" 之后、到标点或句尾的名词短语
      R4  文本中显式引号包裹的短语 -> 作为所在块的补充同义词（找不到归属则进 object）
      R5  文本中的全大写缩写（2-6 字母）-> 若其小写形式出现在某块的任一 term 中，则作为该块同义词
    """
    warnings: list[str] = []
    text = norm_space(text)
    blocks: dict[str, list[str]] = {b: [] for b in BLOCK_IDS}

    def add(block: str, phrase: str) -> None:
        cleaned = _clean_phrase(phrase)
        if cleaned and cleaned not in blocks[block]:
            blocks[block].append(cleaned)

    m = re.search(r"(?:using|via|with|based on)\s+([^,.;?]+?)(?:\s+(?:for|in|to|of)\b|[,.;?]|$)",
                  text, flags=re.I)
    if m:
        add("method", m.group(1))
    m = re.search(r"(?:\bfor|\bof)\s+([^,.;?]+?)(?:\s+(?:in|using|via|under|during)\b|[,.;?]|$)",
                  text, flags=re.I)
    if m:
        add("object", m.group(1))
    m = re.search(r"(?:\bin|\bunder|\bduring)\s+([^,.;?]+?)(?:[,.;?]|$)", text, flags=re.I)
    if m:
        add("scenario", m.group(1))

    for q in re.findall(r"[\"“]([^\"”]+)[\"”]", text):
        target = "object"
        low = q.lower()
        if any(k in low for k in ("network", "model", "learning", "algorithm", "method")):
            target = "method"
        add(target, q)

    for acro in set(re.findall(r"\b[A-Z]{2,6}\b", text)):
        low = acro.lower()
        for bid, terms in blocks.items():
            if any(re.search(r"\b" + re.escape(low), t) for t in terms):
                if acro not in terms:
                    terms.append(acro)

    concepts = [
        {"id": bid, "label": {"object": "研究对象", "method": "方法", "scenario": "应用场景"}[bid],
         "terms": blocks[bid]}
        for bid in BLOCK_IDS if blocks[bid]
    ]
    if not concepts:
        warnings.append("规则抽取未得到任何概念块；需人工/模型补全")
    else:
        missing = [b for b in BLOCK_IDS if b not in {c["id"] for c in concepts}]
        if missing:
            warnings.append(f"规则抽取缺少概念块: {missing}")
    return concepts, warnings


def parse_case(case_path: str | Path, task_path: str | Path | None = None) -> dict:
    """主入口：返回 concepts 文档（可直接写盘）。"""
    case_path = Path(case_path)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    result: dict = {
        "case_id": case.get("case_id"),
        "source": None,
        "degraded": False,
        "needs_model_review": False,
        "concepts": [],
        "warnings": [],
        "locator": {"path": str(case_path), "pointer": "/concepts"},
    }

    if "concepts" in case and case["concepts"]:
        concepts, problems = validate_concepts(case["concepts"])
        result["concepts"] = concepts
        result["source"] = "case.json:concepts"
        result["warnings"].extend(problems)
        if problems:
            result["needs_model_review"] = True
        return result

    text_parts = []
    if case.get("research_question"):
        text_parts.append(str(case["research_question"]))
        result["locator"] = {"path": str(case_path), "pointer": "/research_question"}
    if case.get("task"):
        text_parts.append(str(case["task"]))
    if task_path and Path(task_path).is_file():
        text_parts.append(Path(task_path).read_text(encoding="utf-8"))
    text = " ".join(text_parts).strip()

    if not text:
        result["degraded"] = True
        result["needs_model_review"] = True
        result["warnings"].append(
            "case.json 既无 concepts 也无 research_question/task 文本，无法解析概念块；"
            "下游应产出 status=partial 并诚实说明")
        return result

    concepts, warnings = heuristic_parse(text)
    result["concepts"] = concepts
    result["source"] = "heuristic:research_question"
    result["degraded"] = True          # 规则抽取一律视为降级路径
    result["needs_model_review"] = True
    result["warnings"].extend(warnings)
    result["warnings"].append("概念块来自确定性规则抽取，模型必须逐块复核后再进入检索式构建")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="研究问题 -> 概念块（PICO 式）")
    ap.add_argument("--case", required=True, help="case.json 路径")
    ap.add_argument("--task", default=None, help="task.md 路径（可选，用于兜底抽取）")
    ap.add_argument("--out", required=True, help="输出 concepts.json 路径")
    args = ap.parse_args(argv)

    doc = parse_case(args.case, args.task)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[concept_parse] source={doc['source']} degraded={doc['degraded']} "
          f"blocks={len(doc['concepts'])} warnings={len(doc['warnings'])} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
