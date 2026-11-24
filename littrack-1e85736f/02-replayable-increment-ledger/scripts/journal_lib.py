#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""journal_lib.py — 增量证据链共享库（仅 Python3 标准库，完全离线）。

提供：
- 规范化与稳定 dedup_key 计算（DOI -> arXiv -> 标题指纹 优先级链）
- append-only increment_journal.jsonl 的读写
- 已知条目注册表（Registry）：由 previous_snapshot + journal 历史重建
- 增量判定（new / duplicate / version_update / skipped_*）的纯函数 process_run
  record_run.py 与 replayer.py 共用同一实现，保证“记录”与“回放”逐字节可比。

判定规则编号（详见 references/dedup-key-rules.md）：
  R0-new                       无任何已知标识命中 -> 新增
  R1-exact-doi                 DOI 规范化后精确命中 -> 重复
  R1-exact-arxiv               arXiv 基础号命中且版本不更新 -> 重复
  R2-arxiv-version             同 arXiv 基础号、版本号更高 -> 版本更新
  R3-preprint-published-link   关系字段（如 Crossref relation）链接到已知 arXiv/DOI -> 版本更新（预印本->正式版）
  R4-title-fingerprint         标题指纹命中 -> 重复
  RX-out-of-window             题录日期落在窗口之外 -> 跳过
  RX-no-date                   无法解析日期 -> 跳过
"""

import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime, timezone

SCHEMA_VERSION = "increment-journal/1.0"

# ---------------------------------------------------------------------------
# 规范化与哈希
# ---------------------------------------------------------------------------

def canonical_json(obj):
    """确定性 JSON 序列化：键排序、无空白、UTF-8 不转义。所有逐字节比较均基于此。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)


def normalize_doi(raw):
    """DOI 规范化：小写、去 URL/方案前缀、去首尾空白与结尾句点。"""
    if not raw:
        return None
    s = str(raw).strip().lower()
    for p in _DOI_PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
    s = s.strip().rstrip(".")
    return s or None


_ARXIV_RE = re.compile(
    r"(?P<base>(?:\d{4}\.\d{4,5})|(?:[a-z][a-z\-]*(?:\.[a-z]{2})?/\d{7}))"
    r"(?:v(?P<ver>\d+))?",
    re.IGNORECASE,
)


def parse_arxiv_id(raw):
    """解析 arXiv 标识 -> (base, version)。接受 'arXiv:2506.01234v2'、
    'http://arxiv.org/abs/2506.01234v2'、'2506.01234'、'hep-th/9901001v1' 等形态。"""
    if not raw:
        return (None, None)
    s = str(raw).strip()
    s = re.sub(r"^arxiv:\s*", "", s, flags=re.IGNORECASE)
    m = re.search(r"abs/(.+)$", s)
    if m:
        s = m.group(1)
    m = _ARXIV_RE.search(s)
    if not m:
        return (None, None)
    base = m.group("base").lower()
    ver = int(m.group("ver")) if m.group("ver") else None
    return (base, ver)


def title_fingerprint(title):
    """标题指纹：NFKD -> 去变音符号(Mn) -> 小写 -> 非字母数字折叠为空白 -> 压缩空白。"""
    if not title:
        return None
    s = unicodedata.normalize("NFKD", str(title))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.lower()
    s = "".join(ch if ch.isalnum() else " " for ch in s)
    fp = " ".join(s.split())
    return fp or None


def compute_dedup_key(ident):
    """稳定 dedup_key 优先级链：doi: -> arxiv: -> title: 。"""
    if ident.get("doi"):
        return "doi:" + ident["doi"], "K1-doi"
    if ident.get("arxiv_base"):
        return "arxiv:" + ident["arxiv_base"], "K2-arxiv"
    if ident.get("title_fp"):
        return "title:" + ident["title_fp"], "K3-title"
    return None, "K0-none"


# ---------------------------------------------------------------------------
# 日期处理（统一规范化为 UTC 秒级 ISO 字符串）
# ---------------------------------------------------------------------------

def parse_date(s):
    """解析 'YYYY-MM-DD'、'YYYY-MM-DDTHH:MM:SSZ'、带时区偏移的 ISO 字符串 -> aware datetime(UTC)。
    无法解析返回 None。"""
    if not s:
        return None
    s = str(s).strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def iso_z(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# 题录条目规范化（Crossref 形态 / arXiv 形态 / Europe PMC 形态的宽容解析）
# ---------------------------------------------------------------------------

def normalize_item(source_name, item):
    """把一条原始题录映射为统一标识结构。任何字段缺失都保留为 None，绝不臆造。"""
    norm = {
        "doi": None,
        "arxiv_base": None,
        "arxiv_version": None,
        "title": None,
        "title_fp": None,
        "date": None,
        "related_arxiv_bases": [],
        "related_dois": [],
        "display_id": None,
    }
    if not isinstance(item, dict):
        return norm

    if "DOI" in item or item.get("message-type") or source_name == "crossref":
        # ---- Crossref 形态 ----
        norm["doi"] = normalize_doi(item.get("DOI"))
        t = item.get("title")
        if isinstance(t, list) and t:
            norm["title"] = t[0]
        elif isinstance(t, str):
            norm["title"] = t
        issued = item.get("issued") or item.get("published") or {}
        dp = issued.get("date-parts") if isinstance(issued, dict) else None
        if dp and dp[0]:
            parts = list(dp[0]) + [1, 1, 1]
            norm["date"] = "%04d-%02d-%02dT00:00:00Z" % (parts[0], parts[1], parts[2])
        rel = item.get("relation") or {}
        if isinstance(rel, dict):
            for _rel_type, entries in rel.items():
                for e in entries or []:
                    rid = (e or {}).get("id", "")
                    b, _v = parse_arxiv_id(rid)
                    if b:
                        norm["related_arxiv_bases"].append(b)
                    else:
                        d = normalize_doi(rid)
                        if d:
                            norm["related_dois"].append(d)
        norm["display_id"] = norm["doi"]
    else:
        # ---- arXiv / Europe PMC 形态 ----
        raw_id = item.get("id") or item.get("arxiv_id") or item.get("arxivId")
        base, ver = parse_arxiv_id(raw_id)
        norm["arxiv_base"] = base
        norm["arxiv_version"] = ver
        t = item.get("title")
        if isinstance(t, list) and t:
            t = t[0]
        norm["title"] = re.sub(r"\s+", " ", t).strip() if isinstance(t, str) else None
        norm["date"] = item.get("updated") or item.get("published") or item.get("firstPublicationDate")
        norm["doi"] = normalize_doi(item.get("doi") or item.get("DOI"))
        norm["display_id"] = (base + ("v%d" % ver if ver else "")) if base else norm["doi"]

    norm["title_fp"] = title_fingerprint(norm["title"])
    return norm


_DEFAULT_ITEMS_PATHS = {
    "crossref": ["message", "items"],
    "arxiv": ["entries"],
    "europepmc": ["resultList", "result"],
}


def extract_items(source_name, doc):
    """从源响应 JSON 中定位题录数组 -> (items, keys_path)。宽容兜底多种形态。"""
    if isinstance(doc, list):
        return doc, []
    if source_name in _DEFAULT_ITEMS_PATHS:
        keys = _DEFAULT_ITEMS_PATHS[source_name]
        node = doc
        ok = True
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                ok = False
                break
        if ok and isinstance(node, list):
            return node, keys
    for keys in (["message", "items"], ["entries"], ["resultList", "result"], ["items"], ["results"]):
        node = doc
        ok = True
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                ok = False
                break
        if ok and isinstance(node, list):
            return node, keys
    return [], []


def json_path_str(keys, index):
    return "$" + "".join("." + k for k in keys) + "[%d]" % index


# ---------------------------------------------------------------------------
# 已知条目注册表
# ---------------------------------------------------------------------------

class Registry:
    """已知文献注册表。dedup_key 以首次见到时的优先级链结果为准并保持稳定；
    后续合并只补充标识（DOI / arXiv / 标题指纹），不回溯改写 dedup_key。"""

    def __init__(self):
        self.entries = []
        self.by_doi = {}
        self.by_arxiv = {}
        self.by_title = {}

    def _index(self, e):
        if e.get("doi"):
            self.by_doi[e["doi"]] = e
        if e.get("arxiv_base"):
            self.by_arxiv[e["arxiv_base"]] = e
        if e.get("title_fp"):
            self.by_title[e["title_fp"]] = e

    def lookup(self, norm):
        for key, idx in (("doi", self.by_doi), ("arxiv_base", self.by_arxiv), ("title_fp", self.by_title)):
            v = norm.get(key)
            if v and v in idx:
                return idx[v]
        return None

    def add_item(self, ident, first_seen_run, locator):
        e = self.lookup(ident)
        if e is None:
            e = {
                "dedup_key": None,
                "doi": None,
                "arxiv_base": None,
                "arxiv_version_max": None,
                "title_fp": None,
                "title": None,
                "first_seen_run": first_seen_run,
                "locator": locator,
            }
            self.entries.append(e)
        for k in ("doi", "arxiv_base", "title_fp"):
            if ident.get(k) and not e.get(k):
                e[k] = ident[k]
        ver = ident.get("arxiv_version", ident.get("arxiv_version_max"))
        if ver is not None and (e["arxiv_version_max"] is None or ver > e["arxiv_version_max"]):
            e["arxiv_version_max"] = ver
        if ident.get("title") and not e.get("title"):
            e["title"] = ident["title"]
        if not e.get("dedup_key"):
            e["dedup_key"], _ = compute_dedup_key(e)
        self._index(e)
        return e


# 判定规则常量
R_NEW = "R0-new"
R_DUP_DOI = "R1-exact-doi"
R_DUP_ARXIV = "R1-exact-arxiv"
R_VER_ARXIV = "R2-arxiv-version"
R_VER_P2P = "R3-preprint-published-link"
R_DUP_TITLE = "R4-title-fingerprint"
R_SKIP_WIN = "RX-out-of-window"
R_SKIP_NODATE = "RX-no-date"


def decide(reg, norm):
    """增量判定 -> (decision, rule, matched_entry_or_None)。规则优先级见模块docstring。"""
    if norm["doi"] and norm["doi"] in reg.by_doi:
        return "duplicate", R_DUP_DOI, reg.by_doi[norm["doi"]]
    if norm["arxiv_base"] and norm["arxiv_base"] in reg.by_arxiv:
        e = reg.by_arxiv[norm["arxiv_base"]]
        ev = e.get("arxiv_version_max")
        nv = norm.get("arxiv_version")
        if ev is not None and nv is not None and nv > ev:
            return "version_update", R_VER_ARXIV, e
        return "duplicate", R_DUP_ARXIV, e
    for b in norm.get("related_arxiv_bases", []):
        if b in reg.by_arxiv:
            return "version_update", R_VER_P2P, reg.by_arxiv[b]
    for d in norm.get("related_dois", []):
        if d in reg.by_doi:
            return "version_update", R_VER_P2P, reg.by_doi[d]
    if norm["title_fp"] and norm["title_fp"] in reg.by_title:
        return "duplicate", R_DUP_TITLE, reg.by_title[norm["title_fp"]]
    return "new", R_NEW, None


# ---------------------------------------------------------------------------
# journal 读写（append-only JSONL）
# ---------------------------------------------------------------------------

def read_journal(path):
    runs = []
    if not path or not os.path.exists(path):
        return runs
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("record_type") == "run":
                runs.append(obj)
    return runs


def append_run(path, record):
    with open(path, "a", encoding="utf-8") as f:
        f.write(canonical_json(record) + "\n")


def registry_from(snapshot, runs):
    """由 previous_snapshot.seen_items + journal 历史 run 的 events 重建注册表。"""
    reg = Registry()
    if snapshot:
        for it in snapshot.get("seen_items", []) or []:
            reg.add_item(it, it.get("first_seen_run"), it.get("locator"))
    for run in runs:
        for ev in run.get("events", []) or []:
            ident = ev.get("identifiers") or {}
            if ident:
                reg.add_item(ident, run.get("run_id"), ev.get("locator"))
    return reg


def registry_to_seen_items(reg):
    def sort_key(e):
        return (e.get("dedup_key") is None, e.get("dedup_key") or "")
    return sorted(reg.entries, key=sort_key)


# ---------------------------------------------------------------------------
# 水位
# ---------------------------------------------------------------------------

def update_watermark(wm, date_str, ident_str):
    wm = dict(wm or {"last_seen_date": None, "last_seen_id": None})
    d = parse_date(date_str)
    if d is None:
        return wm
    cur = parse_date(wm.get("last_seen_date")) if wm.get("last_seen_date") else None
    if cur is None or d > cur:
        wm["last_seen_date"] = iso_z(d)
        wm["last_seen_id"] = ident_str
    return wm


# ---------------------------------------------------------------------------
# 一轮增量处理（record_run 与 replayer 共用的纯函数核心）
# ---------------------------------------------------------------------------

def compute_input_digest(source_specs):
    listing = [
        {"source": s["name"], "sha256": s["file_sha256"]}
        for s in sorted(source_specs, key=lambda x: x["name"])
    ]
    return sha256_text(canonical_json(listing))


def compute_run_id(window_start, window_end, input_digest):
    seed = {"end": window_end, "input_digest": input_digest, "start": window_start}
    return "run-" + sha256_text(canonical_json(seed))[:16]


def process_run(window_start, window_end, source_specs, snapshot, prior_runs, alert_channel):
    """对一轮窗口执行增量判定。纯函数：相同输入必然产生逐字节相同的输出。

    source_specs: [{"name","path","items","items_keys","file_sha256"}, ...]
    返回 dict: run_id/input_digest/events/deliveries/counts/watermarks_before/after/registry
    """
    input_digest = compute_input_digest(source_specs)
    run_id = compute_run_id(window_start, window_end, input_digest)
    reg = registry_from(snapshot, prior_runs)
    watermarks_before = (snapshot or {}).get("sources") or {}
    watermarks_after = {k: dict(v) for k, v in watermarks_before.items()}

    w_start = parse_date(window_start)
    w_end = parse_date(window_end)

    events = []
    deliveries = []
    counts = {
        "candidates": 0,
        "in_window": 0,
        "new": 0,
        "version_updates": 0,
        "duplicates": 0,
        "skipped_out_of_window": 0,
        "skipped_no_date": 0,
    }

    for spec in sorted(source_specs, key=lambda x: x["name"]):
        name = spec["name"]
        if name not in watermarks_after:
            watermarks_after[name] = {"last_seen_date": None, "last_seen_id": None}
        for i, item in enumerate(spec["items"]):
            counts["candidates"] += 1
            norm = normalize_item(name, item)
            locator = {
                "file": spec["path"],
                "json_path": json_path_str(spec["items_keys"], i),
                "file_sha256": spec["file_sha256"],
            }
            identifiers = {
                "doi": norm["doi"],
                "arxiv_base": norm["arxiv_base"],
                "arxiv_version": norm["arxiv_version"],
                "title_fp": norm["title_fp"],
            }
            dedup_key, key_rule = compute_dedup_key(identifiers)

            item_dt = parse_date(norm["date"])
            if item_dt is None:
                decision, rule, matched = "skipped", R_SKIP_NODATE, None
            elif w_start is not None and w_end is not None and not (w_start <= item_dt < w_end):
                decision, rule, matched = "skipped", R_SKIP_WIN, None
            else:
                counts["in_window"] += 1
                decision, rule, matched = decide(reg, norm)

            if decision == "new":
                counts["new"] += 1
            elif decision == "version_update":
                counts["version_updates"] += 1
            elif decision == "duplicate":
                counts["duplicates"] += 1
            elif rule == R_SKIP_WIN:
                counts["skipped_out_of_window"] += 1
            elif rule == R_SKIP_NODATE:
                counts["skipped_no_date"] += 1

            matched_info = None
            if matched is not None:
                matched_info = {
                    "dedup_key": matched.get("dedup_key"),
                    "first_seen_run": matched.get("first_seen_run"),
                    "locator": matched.get("locator"),
                }

            event = {
                "source": name,
                "item_index": i,
                "locator": locator,
                "title": norm["title"],
                "item_date": iso_z(item_dt) if item_dt else norm["date"],
                "identifiers": identifiers,
                "dedup_key": dedup_key,
                "key_rule": key_rule,
                "decision": decision,
                "rule": rule,
                "matched": matched_info,
            }
            events.append(event)

            # 所有判定过的条目都合并进注册表（含 skipped：它们客观存在，利于后续判重）
            reg.add_item(
                {
                    "doi": norm["doi"],
                    "arxiv_base": norm["arxiv_base"],
                    "arxiv_version": norm["arxiv_version"],
                    "title_fp": norm["title_fp"],
                    "title": norm["title"],
                },
                run_id,
                locator,
            )

            # 水位推进：窗口内所有判定条目（new/version_update/duplicate）都算
            # “已见”；skipped（窗口外/无日期）不推进。
            if decision in ("new", "version_update", "duplicate"):
                watermarks_after[name] = update_watermark(
                    watermarks_after.get(name), norm["date"], norm["display_id"]
                )
            if decision in ("new", "version_update"):
                payload = {
                    "run_id": run_id,
                    "channel": alert_channel,
                    "window": {"start_utc": window_start, "end_utc": window_end},
                    "dedup_key": dedup_key,
                    "decision": decision,
                    "title": norm["title"],
                }
                deliveries.append(
                    {
                        "channel": alert_channel,
                        "delivered_to": "journal-log",
                        "dedup_key": dedup_key,
                        "decision": decision,
                        "delivery_hash": sha256_text(canonical_json(payload)),
                    }
                )

    return {
        "run_id": run_id,
        "input_digest": input_digest,
        "window": {"start_utc": window_start, "end_utc": window_end},
        "alert_channel": alert_channel,
        "events": events,
        "deliveries": deliveries,
        "counts": counts,
        "watermarks_before": watermarks_before,
        "watermarks_after": watermarks_after,
        "registry": reg,
    }


def build_run_record(result, source_specs):
    """把 process_run 结果封装为 journal run 记录（含自校验哈希）。"""
    record = {
        "record_type": "run",
        "schema_version": SCHEMA_VERSION,
        "run_id": result["run_id"],
        "window": result["window"],
        "input_digest": result["input_digest"],
        "alert_channel": result["alert_channel"],
        "sources": [
            {
                "name": s["name"],
                "locator_file": s["path"],
                "file_sha256": s["file_sha256"],
                "items_path": json_path_str(s["items_keys"], 0).rsplit("[", 1)[0],
                "item_count": len(s["items"]),
            }
            for s in sorted(source_specs, key=lambda x: x["name"])
        ],
        "watermarks_before": result["watermarks_before"],
        "watermarks_after": result["watermarks_after"],
        "counts": result["counts"],
        "events": result["events"],
        "deliveries": result["deliveries"],
        "events_sha256": sha256_text(canonical_json(result["events"])),
        "deliveries_sha256": sha256_text(canonical_json(result["deliveries"])),
    }
    record["record_sha256"] = sha256_text(canonical_json(record))
    return record


def load_source_spec(name, path):
    """读取一个源响应文件 -> source_spec（含宽容的 items 定位）。"""
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    items, keys = extract_items(name, doc)
    return {
        "name": name,
        "path": path,
        "items": items,
        "items_keys": keys,
        "file_sha256": sha256_file(path),
    }
