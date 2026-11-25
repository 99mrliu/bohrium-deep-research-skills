"""common.py — 版本链生命周期 Skill 的公共工具（仅 Python3 标准库，完全离线）。

职责：
1. 在材料目录中定位 JSON 快照（不假设固定布局，用 os.walk 兜底）。
2. 兼容多种快照布局抽取题录记录：
   - Crossref:      {"message": {"items": [...]}}
   - Europe PMC:    {"resultList": {"result": [...]}}
   - arXiv / 其他:  顶层 list，或 {"feed": {"entry": [...]}}
3. 把异构记录归一化为统一的 record 字典，并为每个事实性字段
   记录 locator（文件相对路径 + RFC 6901 风格 JSON 指针）。
"""

import json
import os
import re

# ---- JSON 指针工具 ----------------------------------------------------------


def jptr_escape(token):
    """RFC 6901 转义。"""
    return str(token).replace("~", "~0").replace("/", "~1")


def jptr(*tokens):
    """由路径 token 构造 JSON 指针字符串。"""
    return "/" + "/".join(jptr_escape(t) for t in tokens) if tokens else ""


# ---- 快照定位与加载 ---------------------------------------------------------


def find_material_files(materials_dir):
    """递归列出材料目录下全部 .json 文件（相对路径升序）。不假设固定布局。"""
    found = []
    for root, _dirs, files in os.walk(materials_dir):
        for name in files:
            if name.lower().endswith(".json"):
                full = os.path.join(root, name)
                found.append(os.path.relpath(full, materials_dir))
    return sorted(found)


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---- 布局兼容的记录迭代 -----------------------------------------------------


def iter_raw_records(snapshot):
    """从任一受支持的快照布局产出 (raw_obj, pointer)。

    支持：
    - {"message": {"items": [...]}}        (Crossref)
    - {"resultList": {"result": [...]}}    (Europe PMC)
    - {"feed": {"entry": [...]}}           (Atom/arXiv 风格)
    - 顶层 list                            (arXiv 简化导出等)
    """
    if isinstance(snapshot, list):
        for i, obj in enumerate(snapshot):
            if isinstance(obj, dict):
                yield obj, jptr(i)
        return
    if not isinstance(snapshot, dict):
        return
    message = snapshot.get("message")
    if isinstance(message, dict) and isinstance(message.get("items"), list):
        for i, obj in enumerate(snapshot["message"]["items"]):
            if isinstance(obj, dict):
                yield obj, jptr("message", "items", i)
        return
    result_list = snapshot.get("resultList")
    if isinstance(result_list, dict) and isinstance(result_list.get("result"), list):
        for i, obj in enumerate(result_list["result"]):
            if isinstance(obj, dict):
                yield obj, jptr("resultList", "result", i)
        return
    feed = snapshot.get("feed")
    if isinstance(feed, dict) and isinstance(feed.get("entry"), list):
        for i, obj in enumerate(feed["entry"]):
            if isinstance(obj, dict):
                yield obj, jptr("feed", "entry", i)
        return
    if isinstance(snapshot.get("entries"), list):
        for i, obj in enumerate(snapshot["entries"]):
            if isinstance(obj, dict):
                yield obj, jptr("entries", i)
        return
    # 未识别布局：空产出，由调用方诚实记录。


# ---- 文本归一化 -------------------------------------------------------------

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_title(title):
    """标题归一化：小写、去标点、压缩空白。用于近似匹配后备规则。"""
    if not title:
        return ""
    text = _NON_ALNUM.sub(" ", str(title).lower())
    return " ".join(text.split())


def normalize_person(name):
    if not name:
        return ""
    return " ".join(_NON_ALNUM.sub(" ", str(name).lower()).split())


# ---- 各来源记录抽取 ---------------------------------------------------------

_ARXIV_ABS = re.compile(r"arxiv\.org/abs/([0-9]{4}\.[0-9]{4,5})(v(\d+))?", re.I)


def _first_author_from_crossref(item):
    authors = item.get("author")
    if isinstance(authors, list) and authors:
        a0 = authors[0]
        if isinstance(a0, dict):
            return normalize_person(" ".join(
                p for p in [a0.get("given", ""), a0.get("family", "")] if p))
    return ""


def _date_from_crossref(item):
    pub = item.get("published") or item.get("issued") or {}
    parts = pub.get("date-parts") if isinstance(pub, dict) else None
    if isinstance(parts, list) and parts and isinstance(parts[0], list):
        return "-".join(str(x).zfill(2) if i else str(x)
                        for i, x in enumerate(parts[0]))
    return None


def extract_crossref(item, ptr, relpath):
    doi = item.get("DOI")
    title = None
    if isinstance(item.get("title"), list) and item["title"]:
        title = item["title"][0]
    ctype = str(item.get("type", "") or "").lower()
    subtype = str(item.get("subtype", "") or "").lower()
    relations = []
    for j, rel in enumerate(item.get("relation") or []):
        if isinstance(rel, dict) and rel.get("id"):
            relations.append({
                "type": str(rel.get("relation-type", "")).lower(),
                "id": str(rel["id"]).lower(),
                "id_type": rel.get("id-type"),
                "pointer": jptr("relation", j),
            })
    update_to = []
    for j, upd in enumerate(item.get("update-to") or []):
        if isinstance(upd, dict) and upd.get("DOI"):
            update_to.append({
                "type": str(upd.get("type", "")).lower(),
                "doi": str(upd["DOI"]).lower(),
                "pointer": jptr("update-to", j),
            })
    if subtype == "retraction-notice" or any(
            r["type"] == "is-retraction-of" for r in relations):
        kind = "retraction-notice"
    elif any(r["type"] == "is-correction-of" for r in relations):
        kind = "correction-notice"
    elif ctype in ("posted-content", "preprint"):
        kind = "preprint"
    elif ctype == "journal-article":
        kind = "journal-article"
    else:
        kind = "other"
    return {
        "source": "crossref",
        "doi": str(doi).lower() if doi else None,
        "arxiv_id": None,
        "arxiv_version": None,
        "title": title,
        "title_norm": normalize_title(title),
        "first_author": _first_author_from_crossref(item),
        "kind": kind,
        "relations": relations,
        "update_to": update_to,
        "date": _date_from_crossref(item),
        "comment": None,
        "locator": {"file": relpath, "pointer": ptr},
    }


def extract_arxiv(entry, ptr, relpath):
    raw_id = str(entry.get("id", "") or "")
    m = _ARXIV_ABS.search(raw_id)
    arxiv_id = m.group(1) if m else None
    version = int(m.group(3)) if m and m.group(3) else 1
    title = entry.get("title")
    authors = entry.get("author") or entry.get("authors") or []
    first_author = ""
    if isinstance(authors, list) and authors:
        a0 = authors[0]
        if isinstance(a0, dict):
            first_author = normalize_person(a0.get("name", ""))
        elif isinstance(a0, str):
            first_author = normalize_person(a0)
    relations = []
    for j, rel in enumerate(entry.get("relation") or []):
        if isinstance(rel, dict) and rel.get("id"):
            relations.append({
                "type": str(rel.get("relation-type", "")).lower(),
                "id": str(rel["id"]).lower(),
                "id_type": rel.get("id-type"),
                "pointer": jptr("relation", j),
            })
    comment = entry.get("arxiv:comment") or entry.get("comment")
    doi = entry.get("arxiv:doi") or entry.get("doi")
    if not doi and arxiv_id:
        # arXiv 记录的数据 DOI（DataCite），用于与 Crossref 关系字段对齐。
        doi = "10.48550/arxiv." + arxiv_id.lower()
    return {
        "source": "arxiv",
        "doi": str(doi).lower() if doi else None,
        "arxiv_id": arxiv_id,
        "arxiv_version": version,
        "title": title,
        "title_norm": normalize_title(title),
        "first_author": first_author,
        "kind": "preprint",
        "relations": relations,
        "update_to": [],
        "date": entry.get("updated") or entry.get("published"),
        "comment": comment,
        "locator": {"file": relpath, "pointer": ptr},
    }


def extract_europepmc(item, ptr, relpath):
    doi = item.get("doi")
    title = item.get("title")
    author_string = item.get("authorString") or item.get("author_string") or ""
    first_author = normalize_person(author_string.split(",")[0]) if author_string else ""
    pub_type = str(item.get("pubType", "") or "").lower()
    if "retract" in pub_type:
        kind = "retraction-notice"
    elif "preprint" in pub_type or item.get("source") == "PPR":
        kind = "preprint"
    elif pub_type:
        kind = "journal-article"
    else:
        kind = "other"
    relations = []
    for j, rel in enumerate(item.get("relation") or []):
        if isinstance(rel, dict) and rel.get("id"):
            relations.append({
                "type": str(rel.get("relation-type", "")).lower(),
                "id": str(rel["id"]).lower(),
                "id_type": rel.get("id-type"),
                "pointer": jptr("relation", j),
            })
    return {
        "source": "europepmc",
        "doi": str(doi).lower() if doi else None,
        "arxiv_id": None,
        "arxiv_version": None,
        "title": title,
        "title_norm": normalize_title(title),
        "first_author": first_author,
        "kind": kind,
        "relations": relations,
        "update_to": [],
        "date": item.get("firstPublicationDate") or item.get("pubYear"),
        "comment": item.get("pubType"),
        "locator": {"file": relpath, "pointer": ptr},
    }


_EXTRACTORS = {
    "crossref": extract_crossref,
    "arxiv": extract_arxiv,
    "europepmc": extract_europepmc,
}


def sniff_source(relpath, snapshot):
    """来源识别：先看文件名提示，再看结构。返回 crossref/arxiv/europepmc/None。"""
    name = os.path.basename(relpath).lower()
    for hint in ("crossref", "arxiv", "europepmc", "pmc"):
        if hint in name:
            return "europepmc" if hint == "pmc" else hint
    if isinstance(snapshot, dict):
        if isinstance(snapshot.get("message"), dict):
            return "crossref"
        if isinstance(snapshot.get("resultList"), dict):
            return "europepmc"
        feed = snapshot.get("feed")
        if isinstance(feed, dict):
            return "arxiv"
    if isinstance(snapshot, list) and snapshot:
        first = snapshot[0]
        if isinstance(first, dict) and "arxiv.org/abs/" in str(first.get("id", "")):
            return "arxiv"
    return None


def extract_records(materials_dir):
    """遍历材料目录，产出统一记录列表与布局异常清单。

    返回 (records, anomalies)。anomalies 记录无法识别布局/来源的文件，
    保证空材料或陌生布局时诚实降级而不是静默丢弃。
    """
    records, anomalies = [], []
    for relpath in find_material_files(materials_dir):
        full = os.path.join(materials_dir, relpath)
        try:
            snapshot = load_json(full)
        except (OSError, json.JSONDecodeError) as exc:
            anomalies.append({"file": relpath, "reason": "unreadable: %s" % exc})
            continue
        source = sniff_source(relpath, snapshot)
        raw = list(iter_raw_records(snapshot))
        if source is None or not raw:
            anomalies.append({
                "file": relpath,
                "reason": "unrecognized layout or source" if source is None
                          else "no records found in recognized layout",
            })
            continue
        extractor = _EXTRACTORS[source]
        for i, (obj, ptr) in enumerate(raw):
            rec = extractor(obj, ptr, relpath)
            if source == "arxiv" and rec["arxiv_id"]:
                # arXiv 记录按 base id + 版本号区分，v1/v2 是不同实体。
                local_id = "%sv%s" % (rec["arxiv_id"], rec["arxiv_version"])
            else:
                local_id = rec["doi"] or (
                    "arxiv:%sv%s" % (rec["arxiv_id"], rec["arxiv_version"])
                    if rec["arxiv_id"] else "%s#%d" % (relpath, i))
            rec["uid"] = "%s:%s" % (rec["source"], local_id)
            records.append(rec)
    return records, anomalies
