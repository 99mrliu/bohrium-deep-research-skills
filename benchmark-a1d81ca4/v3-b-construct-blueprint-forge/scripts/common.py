#!/usr/bin/env python3
"""Shared stdlib helpers for construct blueprint and item-bank tools."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

OPERATIONS = {
    "locate_extract",
    "table_relation_calculation",
    "comparison_boundary",
    "synthesis_conflict",
}

PLACEHOLDER_RE = re.compile(
    r"(?:\{\{[^}]+\}\}|<[^<>]+>|__[^_]+__|\bTBD\b|\bTODO\b|"
    r"\bPLACEHOLDER\b|\bFILL[_ -]?ME\b|待填写|待补充|占位符|科学内容待定)",
    re.IGNORECASE,
)

VAGUE_PHRASES = (
    "all sources",
    "any source",
    "various aspects",
    "understand the material",
    "analyze the information",
    "answer appropriately",
    "cover everything",
    "全部材料",
    "所有材料",
    "任意来源",
    "各种方面",
    "相关内容",
    "考查理解",
    "综合分析即可",
    "酌情给分",
    "答案合理即可",
)

ENGLISH_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "both",
    "by", "can", "could", "did", "do", "does", "each", "either", "for",
    "from", "had", "has", "have", "how", "in", "into", "is", "it", "its",
    "may", "might", "more", "most", "neither", "not", "of", "on", "only",
    "or", "other", "our", "per", "should", "than", "that", "the", "their",
    "then", "there", "these", "they", "this", "those", "to", "under", "use",
    "using", "was", "were", "what", "when", "where", "which", "while", "who",
    "why", "will", "with", "would", "according", "actual", "answer", "based",
    "case", "cite", "correct", "data", "describe", "determine", "evidence",
    "example", "field", "following", "given", "include", "item", "material",
    "materials", "name", "paragraph", "provide", "question", "reference",
    "report", "result", "results", "show", "source", "sources", "state",
    "synthetic", "table", "task", "text", "unit", "units", "value", "values",
    "percent", "percentage", "point", "points", "true", "false", "yes", "no",
}

CJK_STOP_NGRAMS = {
    "根据", "材料", "来源", "段落", "表格", "问题", "回答", "答案", "正确",
    "内容", "数据", "数值", "结果", "说明", "判断", "指出", "是否", "什么",
    "综合", "分析", "一个", "两个", "所有", "相关", "如下", "以及", "并且",
    "单位", "题目", "示例", "合成", "必须", "可以", "不能", "没有", "进行",
}

HEDGE_MARKERS = (
    "uncertain", "uncertainty", "unknown", "unclear", "not reported",
    "not_reported", "undetermined", "unresolved", "may", "might", "could",
    "possible", "approximately", "suggests", "cannot determine",
    "未报告", "未知", "不确定", "可能", "大约", "约", "尚未", "有待",
    "无法确定", "不能确定", "未解决", "提示", "估计",
)


def load_json(path: str) -> Any:
    file_path = Path(path)
    if not file_path.is_file():
        raise ValueError("not a regular file: %s" % path)
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read JSON %s: %s" % (path, exc)) from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def content_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def write_json(path: str, value: Any) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    temporary.replace(output)


def fail_message(exc: BaseException) -> None:
    sys.stderr.write("ERROR: %s\n" % exc)


def normalized_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(ch for ch in text if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def text_is_blank(value: Any) -> bool:
    return not isinstance(value, str) or not value.strip()


def contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return bool(PLACEHOLDER_RE.search(value))
    if isinstance(value, dict):
        return any(contains_placeholder(key) or contains_placeholder(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(contains_placeholder(item) for item in value)
    return False


def vague_phrase(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    folded = unicodedata.normalize("NFKC", value).casefold()
    for phrase in VAGUE_PHRASES:
        if phrase in folded:
            return phrase
    return None


def iter_strings(value: Any, include_keys: bool = False) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if include_keys:
                yield str(key)
            yield from iter_strings(item, include_keys=include_keys)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from iter_strings(item, include_keys=include_keys)


def answer_tokens(value: Any) -> set:
    """Meaningful answer-value tokens; numbers, keys and trivial words are excluded."""
    tokens = set()
    for text in iter_strings(value, include_keys=False):
        normalized = unicodedata.normalize("NFKC", text).casefold()
        for token in re.findall(r"[a-z]+(?:[-'][a-z]+)?", normalized):
            bare = token.replace("-", "").replace("'", "")
            if len(bare) >= 4 and bare not in ENGLISH_STOPWORDS and not bare.isdigit():
                tokens.add(bare)
        for sequence in re.findall(r"[\u4e00-\u9fff]+", normalized):
            if len(sequence) < 2:
                continue
            for size in range(2, min(6, len(sequence)) + 1):
                for start in range(0, len(sequence) - size + 1):
                    gram = sequence[start:start + size]
                    if gram not in CJK_STOP_NGRAMS and not gram.isdigit():
                        tokens.add(gram)
    return tokens


def task_tokens(value: Any) -> set:
    return answer_tokens(value)


def normalized_question(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(ch for ch in text if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def question_similarity(left: str, right: str) -> float:
    def shingles(text: str) -> set:
        if len(text) < 6:
            return {text} if text else set()
        return {text[index:index + 5] for index in range(len(text) - 4)}

    left_set, right_set = shingles(left), shingles(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


class Report:
    def __init__(self, tool: str, input_value: Any = None) -> None:
        self.tool = tool
        self.input_sha256 = content_sha256(input_value) if input_value is not None else None
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []

    def error(self, code: str, path: str, message: str, item_id: Optional[str] = None) -> None:
        entry: Dict[str, Any] = {"code": code, "path": path, "message": message}
        if item_id:
            entry["item_id"] = item_id
        self.errors.append(entry)

    def warning(self, code: str, path: str, message: str, item_id: Optional[str] = None) -> None:
        entry: Dict[str, Any] = {"code": code, "path": path, "message": message}
        if item_id:
            entry["item_id"] = item_id
        self.warnings.append(entry)

    def as_dict(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "tool": self.tool,
            "status": "fail" if self.errors else "pass",
            "input_sha256": self.input_sha256,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
        }
        if extra:
            result.update(extra)
        return result


def source_ids_from_case(case: Dict[str, Any]) -> set:
    materials = case.get("materials", case.get("sources", []))
    identifiers = set()
    if isinstance(materials, list):
        for entry in materials:
            if isinstance(entry, str):
                identifiers.add(entry)
            elif isinstance(entry, dict):
                source_id = entry.get("source_id", entry.get("id"))
                if isinstance(source_id, str) and source_id:
                    identifiers.add(source_id)
    elif isinstance(materials, dict):
        identifiers.update(str(key) for key in materials)
    return identifiers


def scope_pairs(value: Any) -> set:
    pairs = set()
    if not isinstance(value, list):
        return pairs
    for entry in value:
        if isinstance(entry, dict):
            pairs.add((str(entry.get("source_id", "")), str(entry.get("locator", ""))))
    return pairs


def scope_source_ids(value: Any) -> set:
    return {source_id for source_id, _ in scope_pairs(value) if source_id}


def validate_scope(report: Report, value: Any, path: str, item_id: Optional[str] = None) -> None:
    if not isinstance(value, list) or not value:
        report.error("SOURCE_SCOPE_REQUIRED", path, "source_scope must be a non-empty list of {source_id, locator}.", item_id)
        return
    seen = set()
    for index, entry in enumerate(value):
        entry_path = "%s[%d]" % (path, index)
        if not isinstance(entry, dict):
            report.error("SOURCE_SCOPE_ENTRY", entry_path, "Each scope entry must be an object.", item_id)
            continue
        source_id, locator = entry.get("source_id"), entry.get("locator")
        if text_is_blank(source_id) or text_is_blank(locator):
            report.error("SOURCE_SCOPE_ENTRY", entry_path, "Both source_id and a specific locator are required.", item_id)
            continue
        combined = vague_phrase(locator)
        if combined or str(locator).strip() in {"*", "all", "ALL", "全文", "全部"}:
            report.error("SOURCE_SCOPE_CATCH_ALL", entry_path, "Use explicit paragraph, row, cell, section or table locators, not a catch-all.", item_id)
        pair = (source_id, locator)
        if pair in seen:
            report.error("SOURCE_SCOPE_DUPLICATE", entry_path, "Duplicate source scope entry.", item_id)
        seen.add(pair)


def _descriptor(name: str, spec: Any = None) -> Dict[str, Any]:
    if isinstance(spec, str):
        return {"name": name, "type": spec}
    if isinstance(spec, dict):
        result = copy.deepcopy(spec)
        result["name"] = name
        return result
    if spec is None:
        return {"name": name}
    return {"name": name, "default": copy.deepcopy(spec)}


def parse_output_contract(contract: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Return field descriptors for list, fields-list, JSON-schema-like or direct-map contracts."""
    problems: List[str] = []
    raw_fields: Any
    if contract is None:
        return [], []
    if isinstance(contract, list):
        raw_fields = contract
    elif isinstance(contract, dict):
        if "fields" in contract:
            raw_fields = contract["fields"]
        elif "properties" in contract and isinstance(contract["properties"], dict):
            raw_fields = contract["properties"]
        else:
            raw_fields = contract
    else:
        return [], ["output_contract must be a list or object."]

    fields: List[Dict[str, Any]] = []
    seen = set()
    if isinstance(raw_fields, list):
        entries = raw_fields
        for index, entry in enumerate(entries):
            descriptor: Optional[Dict[str, Any]] = None
            if isinstance(entry, str) and entry:
                descriptor = _descriptor(entry)
            elif isinstance(entry, dict):
                name = entry.get("name", entry.get("key", entry.get("field", entry.get("id"))))
                if isinstance(name, str) and name:
                    descriptor = copy.deepcopy(entry)
                    descriptor["name"] = name
                elif len(entry) == 1:
                    only_name, spec = next(iter(entry.items()))
                    descriptor = _descriptor(str(only_name), spec)
            if descriptor is None:
                problems.append("output_contract field %d lacks a valid name." % index)
                continue
            name = descriptor["name"]
            if name in seen:
                problems.append("output_contract repeats field %s." % name)
                continue
            seen.add(name)
            fields.append(descriptor)
    elif isinstance(raw_fields, dict):
        for name, spec in raw_fields.items():
            if not isinstance(name, str) or not name:
                problems.append("output_contract contains a non-string or empty field name.")
                continue
            descriptor = _descriptor(name, spec)
            fields.append(descriptor)
            seen.add(name)
    else:
        problems.append("output_contract.fields must be a list or object.")
    return fields, problems


def empty_for_descriptor(descriptor: Dict[str, Any]) -> Any:
    if "default" in descriptor:
        return copy.deepcopy(descriptor["default"])
    declared_type = descriptor.get("type", descriptor.get("value_type"))
    if isinstance(declared_type, list):
        declared_type = next((item for item in declared_type if item != "null"), declared_type[0] if declared_type else None)
    mapping = {
        "array": [], "list": [], "object": {}, "map": {}, "string": "",
        "str": "", "integer": 0, "number": 0, "float": 0, "boolean": False,
        "bool": False, "null": None,
    }
    if isinstance(declared_type, str):
        return copy.deepcopy(mapping.get(declared_type.casefold(), ""))
    return ""
