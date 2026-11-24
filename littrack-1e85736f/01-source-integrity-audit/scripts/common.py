#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共享工具模块（仅 Python 标准库）。

本模块与 bundle 内所有脚本共同遵守：
  * 完全离线，永不发起网络请求；
  * 所有事实性字段值必须来自案例材料本身；
  * 材料中缺失的字段记为 null 并注明，绝不编造。

提供：JSON 读写、SHA-256、JSON Pointer locator、日期解析、
标识符格式校验（DOI / arXiv / PMID）、材料目录遍历与题录抽取。
"""
import hashlib
import json
import os
import re
from datetime import datetime

# ---- 标识符格式规则 ---------------------------------------------------------
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
ARXIV_NEW_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")
ARXIV_OLD_RE = re.compile(r"^[a-z][a-z\-]*(\.[A-Z]{2})?/\d{7}(v\d+)?$")
PMID_RE = re.compile(r"^\d+$")

# 历史快照文件名约定：xxx_v1.json / xxx_v2.json ... 仅用于结构漂移对比，
# 不参与当前窗口的逐条 Schema / 异常校验。
SNAPSHOT_VERSION_RE = re.compile(r"^(.*)_v(\d+)\.json$")

# 题录中视为"日期"的字段名（按优先级）
DATE_FIELDS = ("published", "date", "issued", "publication_date",
               "published_date", "created")
# 题录中视为"标识符"的字段名
ID_FIELDS = ("doi", "DOI", "arxiv_id", "arxiv", "eprint",
             "pmid", "pmcid", "record_id", "id")
# 材料文件头中视为"固化时间"的字段名
FROZEN_FIELDS = ("snapshot_frozen_at", "frozen_at", "captured_at",
                 "snapshot_time", "taken_at", "generated_at")


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(obj, path):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def json_pointer(*parts):
    """构造 JSON Pointer（# 前缀形式），如 json_pointer('records', 3, 'doi')
    -> '#/records/3/doi'。按 RFC 6901 转义 ~ 与 /。"""
    segs = []
    for part in parts:
        if part is None:
            continue
        seg = str(part).replace("~", "~0").replace("/", "~1")
        segs.append(seg)
    return "#" + ("/" + "/".join(segs) if segs else "")


def parse_date(value):
    """尽力把材料中的日期值解析为 datetime.date；无法解析返回 None。

    支持：'YYYY-MM-DD'、ISO 时间戳（含结尾 Z）、'YYYY/MM/DD'、'YYYY-MM'、
    'YYYY'，以及 Crossref 风格 {"date-parts": [[y, m, d]]} 结构。
    """
    if isinstance(value, dict):
        parts = value.get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list):
            nums = parts[0]
            try:
                if len(nums) >= 3:
                    return datetime(int(nums[0]), int(nums[1]), int(nums[2])).date()
                if len(nums) == 2:
                    return datetime(int(nums[0]), int(nums[1]), 1).date()
                if len(nums) == 1:
                    return datetime(int(nums[0]), 1, 1).date()
            except (ValueError, TypeError):
                return None
        return None
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    s_iso = s[:-1] + "+00:00" if s.endswith(("Z", "z")) else s
    try:
        return datetime.fromisoformat(s_iso).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def extract_records(data):
    """从材料 JSON 中抽取题录列表，返回 (records, base_pointer)；
    找不到返回 (None, None)。兼容 records / message.items / items /
    results / resultList 及顶层 list 多种布局。"""
    if isinstance(data, dict):
        if isinstance(data.get("records"), list):
            return data["records"], "#/records"
        message = data.get("message")
        if isinstance(message, dict) and isinstance(message.get("items"), list):
            return message["items"], "#/message/items"
        for key in ("items", "results", "resultList"):
            if isinstance(data.get(key), list):
                return data[key], "#/" + key
    if isinstance(data, list):
        return data, "#"
    return None, None


def iter_material_files(materials_dir):
    """按路径排序产出材料目录下全部 .json 文件（含历史快照 v1/v2 与
    previous_snapshot 之类的状态文件；是否使用由各脚本自行决定）。"""
    paths = []
    for root, _dirs, names in os.walk(materials_dir):
        for name in names:
            if name.lower().endswith(".json"):
                paths.append(os.path.join(root, name))
    return sorted(paths)


def is_versioned_snapshot(path):
    return SNAPSHOT_VERSION_RE.match(os.path.basename(path)) is not None


def get_date_value(record):
    """返回 (原始日期值, 字段名)；无日期字段返回 (None, None)。"""
    if not isinstance(record, dict):
        return None, None
    for field in DATE_FIELDS:
        if field in record and record[field] not in (None, ""):
            return record[field], field
    return None, None


def get_identifiers(record):
    """抽取题录的标识符字段，键统一小写。"""
    ids = {}
    if not isinstance(record, dict):
        return ids
    for field in ID_FIELDS:
        value = record.get(field)
        if isinstance(value, (str, int)) and str(value).strip():
            ids[field.lower()] = str(value).strip()
    return ids


def normalize_doi(value):
    return str(value).strip().lower() if value else None


def normalize_title(value):
    if not isinstance(value, str):
        return None
    return re.sub(r"\s+", " ", value).strip().lower()


def find_frozen_at(data):
    """从材料文件头取固化时间，返回 (值, pointer)；材料未提供则 (None, None)。"""
    if isinstance(data, dict):
        for field in FROZEN_FIELDS:
            value = data.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip(), json_pointer(field)
    return None, None


def valid_doi(value):
    return isinstance(value, str) and DOI_RE.match(value.strip()) is not None


def valid_arxiv(value):
    if not isinstance(value, str):
        return False
    s = value.strip()
    return ARXIV_NEW_RE.match(s) is not None or ARXIV_OLD_RE.match(s) is not None


def valid_pmid(value):
    return isinstance(value, str) and PMID_RE.match(value.strip()) is not None
