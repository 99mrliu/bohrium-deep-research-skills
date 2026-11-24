#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_lib.py — tracking-qa-harness 共享工具库（仅依赖 Python3 标准库）。

提供：
- JSON 读取与 JSON Pointer（RFC 6901 子集）解析
- locator（形如 "materials/x.json#/message/items/3"）解析，限制在案例目录内
- Crossref / Europe PMC 风格题录适配器（DOI / 标题 / 日期 / 作者提取）
- 字段归一化与日期比较
- 通用 QA 报告结构构造

本模块与全部 QA 脚本永不发起网络请求；所有字段值只可能来自案例材料文件。
"""
from __future__ import annotations

import json
import re
from pathlib import Path


class QaError(Exception):
    """可预期的 QA 工具错误（文件缺失、指针不可解析等）。"""


# ---------------------------------------------------------------- JSON / pointer

def load_json(path):
    p = Path(path)
    if not p.is_file():
        raise QaError(f"文件不存在: {p}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QaError(f"JSON 解析失败 {p}: {exc}")


def dump_json(obj, path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _unescape(token):
    return token.replace("~1", "/").replace("~0", "~")


def resolve_pointer(doc, pointer):
    """解析 "/message/items/3" 形式的 JSON Pointer；失败抛 QaError。"""
    if pointer in ("", "/"):
        return doc
    if not pointer.startswith("/"):
        raise QaError(f"非法 JSON Pointer: {pointer!r}（须以 '/' 开头）")
    node = doc
    for raw in pointer.lstrip("/").split("/"):
        tok = _unescape(raw)
        if isinstance(node, dict):
            if tok not in node:
                raise QaError(f"指针路径中不存在键 {tok!r}（pointer={pointer}）")
            node = node[tok]
        elif isinstance(node, list):
            if not tok.isdigit():
                raise QaError(f"数组下标不是非负整数: {tok!r}（pointer={pointer}）")
            idx = int(tok)
            if idx >= len(node):
                raise QaError(f"数组下标越界: {idx}（数组长度 {len(node)}，pointer={pointer}）")
            node = node[idx]
        else:
            raise QaError(f"指针穿过标量节点（pointer={pointer}，剩余键 {tok!r}）")
    return node


def resolve_locator(locator, base_dir):
    """locator: "相对路径#/json/pointer"。返回 (record_node, absolute_path)。

    base_dir 为案例根目录；locator 不允许越出 base_dir。
    """
    if not isinstance(locator, str) or "#" not in locator:
        raise QaError(f"locator 格式非法（缺少 '#' 分隔符）: {locator!r}")
    rel, _, pointer = locator.partition("#")
    rel = rel.strip()
    if not rel:
        raise QaError(f"locator 缺少文件部分: {locator!r}")
    path = (Path(base_dir) / rel).resolve()
    root = Path(base_dir).resolve()
    if path != root and root not in path.parents:
        raise QaError(f"locator 越出案例目录: {locator!r}")
    doc = load_json(path)
    node = resolve_pointer(doc, pointer or "")
    return node, str(path)


# ---------------------------------------------------------------- 归一化

_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "doi:")


def norm_doi(doi):
    if doi is None:
        return None
    s = re.sub(r"\s+", "", str(doi)).lower()
    for pre in _DOI_PREFIXES:
        if s.startswith(pre):
            s = s[len(pre):]
    return s or None


def norm_title(title):
    if title is None:
        return None
    s = re.sub(r"\s+", " ", str(title)).strip().lower()
    return s.rstrip(".")


# ---------------------------------------------------------------- 题录适配器

def detect_format(doc):
    """识别题录响应格式：crossref / europepmc / unknown。"""
    if isinstance(doc, dict):
        msg = doc.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("items"), list):
            return "crossref"
        rl = doc.get("resultList")
        if isinstance(rl, dict) and isinstance(rl.get("result"), list):
            return "europepmc"
    if isinstance(doc, list):
        return "record-list"
    return "unknown"


def iter_records(doc):
    """返回题录记录列表（不展开指针，仅结构适配）。"""
    fmt = detect_format(doc)
    if fmt == "crossref":
        return doc["message"]["items"]
    if fmt == "europepmc":
        return doc["resultList"]["result"]
    if fmt == "record-list":
        return doc
    return []


def _date_parts_to_iso(dp):
    parts = (dp.get("date-parts") or [[]])[0]
    if not parts:
        return None
    if len(parts) == 1:
        return f"{parts[0]:04d}"
    if len(parts) == 2:
        return f"{parts[0]:04d}-{parts[1]:02d}"
    return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"


def record_doi(rec):
    if not isinstance(rec, dict):
        return None
    return norm_doi(rec.get("DOI") or rec.get("doi"))


def record_title(rec):
    if not isinstance(rec, dict):
        return None
    t = rec.get("title")
    if isinstance(t, list):
        t = t[0] if t else None
    return t


_CROSSREF_DATE_KEYS = (
    "published", "published-online", "published-print", "issued", "created",
)
_EUROPEPMC_DATE_KEYS = (
    "firstPublicationDate", "electronicPublicationDate", "printPublicationDate",
)


def record_dates(rec):
    """返回记录的全部日期（ISO 字符串，精度可为 YYYY / YYYY-MM / YYYY-MM-DD）。"""
    if not isinstance(rec, dict):
        return []
    dates = []
    for key in _CROSSREF_DATE_KEYS:
        v = rec.get(key)
        if isinstance(v, dict) and "date-parts" in v:
            iso = _date_parts_to_iso(v)
            if iso:
                dates.append(iso)
    for key in _EUROPEPMC_DATE_KEYS:
        v = rec.get(key)
        if isinstance(v, str) and re.match(r"^\d{4}(-\d{2}){0,2}$", v.strip()):
            dates.append(v.strip())
    ji = rec.get("journalInfo")
    if isinstance(ji, dict):
        v = ji.get("printPublicationDate")
        if isinstance(v, str) and re.match(r"^\d{4}(-\d{2}){0,2}$", v.strip()):
            dates.append(v.strip())
    y = rec.get("pubYear")
    if isinstance(y, str) and re.match(r"^\d{4}$", y.strip()):
        dates.append(y.strip())
    # 去重保序
    seen, out = set(), []
    for d in dates:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def record_authors(rec):
    """返回作者 family name 列表（尽量覆盖 crossref / europepmc 两种形态）。"""
    fams = []
    if not isinstance(rec, dict):
        return fams
    for a in rec.get("author") or []:
        if isinstance(a, dict) and a.get("family"):
            fams.append(str(a["family"]))
    s = rec.get("authorString")
    if isinstance(s, str):
        for part in s.rstrip(".").split(","):
            tokens = part.strip().split()
            if tokens:
                fams.append(tokens[0])
    return fams


# ---------------------------------------------------------------- 日期比较

def parse_iso_date(s):
    """把 YYYY / YYYY-MM / YYYY-MM-DD 规整为可比较字符串；非法返回 None。"""
    if not isinstance(s, str):
        return None
    s = s.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s) or re.match(r"^\d{4}-\d{2}$", s) \
            or re.match(r"^\d{4}$", s):
        return s
    return None


def date_in_window(date_str, start, end):
    """date_str（任意 ISO 精度）是否落在 [start, end]（均为 YYYY-MM-DD）窗口内。

    精度不足时按"该日期区间与窗口有交集即视为在窗口内"的宽松口径处理。
    """
    d = parse_iso_date(date_str)
    if d is None or not start or not end:
        return None
    if len(d) == 10:
        return start <= d <= end
    if len(d) == 7:  # YYYY-MM：整个月与窗口有交集
        return (d >= start[:7]) and (d <= end[:7])
    # YYYY：整年与窗口有交集
    return (d >= start[:4]) and (d <= end[:4])


def compare_date(item_date, source_dates):
    """比对 result 条目日期与源记录日期。

    返回 (level, detail)：level ∈ {"match", "partial", "year-only", "mismatch", "missing"}。
    """
    item = parse_iso_date(item_date)
    if item is None:
        return ("missing", f"result 条目日期缺失或非法: {item_date!r}")
    src = [d for d in (parse_iso_date(x) for x in source_dates) if d]
    if item in src:
        return ("match", "日期与源记录完全一致")
    for sd in src:
        if len(sd) >= 7 and len(item) >= 7 and item[:7] == sd[:7]:
            return ("partial", f"同年同月但日/精度不一致: result={item}, source={src}")
    for sd in src:
        if item[:4] == sd[:4]:
            return ("year-only", f"仅年份一致: result={item}, source={src}")
    return ("mismatch", f"日期不一致: result={item}, source={src}")


def compare_title(item_title, source_title):
    """返回 (level, detail)：level ∈ {"match", "near", "mismatch", "missing"}。"""
    a, b = norm_title(item_title), norm_title(source_title)
    if not a or not b:
        return ("missing", f"标题缺失: result={item_title!r}, source={source_title!r}")
    if a == b:
        return ("match", "标题一致")
    if len(a) >= 12 and (a in b or b in a):
        return ("near", f"标题近似（一方为另一方子串）: result={a!r}, source={b!r}")
    return ("mismatch", f"标题不一致: result={a!r}, source={b!r}")


# ---------------------------------------------------------------- snapshot / 报告

def load_snapshot_dois(path):
    """读取 previous_snapshot，返回归一化 DOI 集合。支持多种快照形态。"""
    doc = load_json(path)
    dois = []
    if isinstance(doc, list):
        entries = doc
    elif isinstance(doc, dict):
        entries = doc.get("known_dois") or doc.get("items") or doc.get("records") or []
    else:
        entries = []
    for e in entries:
        if isinstance(e, str):
            d = norm_doi(e)
        elif isinstance(e, dict):
            d = record_doi(e)
        else:
            d = None
        if d:
            dois.append(d)
    return set(dois)


def make_report(tool, checks):
    errors = sum(1 for c in checks if c["status"] == "fail")
    warnings = sum(1 for c in checks if c["status"] == "warn")
    status = "fail" if errors else ("warn" if warnings else "pass")
    return {
        "tool": tool,
        "status": status,
        "summary": {"checks": len(checks), "errors": errors, "warnings": warnings},
        "checks": checks,
    }


def check(check_id, status, message, severity=None, **extra):
    c = {"id": check_id, "status": status, "message": message}
    if severity:
        c["severity"] = severity
    elif status == "fail":
        c["severity"] = "error"
    elif status == "warn":
        c["severity"] = "warning"
    else:
        c["severity"] = "info"
    c.update(extra)
    return c
