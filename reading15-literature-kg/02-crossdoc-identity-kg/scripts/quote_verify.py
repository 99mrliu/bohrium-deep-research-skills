# -*- coding: utf-8 -*-
"""证据引文核验器（确定性，仅标准库）。

每个实质节点/边的证据必须满足：
1. source_id 在段落库中存在；
2. paragraph_id（组织方 JATS 段落 ID，不是 PDF 页码）在该来源中存在；
3. quote 是该段落原文的逐字短引（空白折叠后仍为子串）；
4. 不得携带 page 字段——本包没有 PDF 页码，自建页码冒充原文页码一律判失败。
任一不满足即判失败，元素由图谱构建阶段剔除并记录，绝不静默放行。
"""
import re

_WS = re.compile(r"\s+")


def _fold(text):
    """空白折叠：核验允许换行/多空格差异，但不允许任何字符差异。"""
    return _WS.sub(" ", str(text)).strip()


def check_quote(store, source_id, paragraph_id, quote):
    """返回 (ok, reason)。store: {source_id: {paragraph_id: text}}。"""
    if not source_id or source_id not in store:
        return False, "source_missing"
    paragraphs = store[source_id]
    if not paragraph_id or str(paragraph_id) not in paragraphs:
        return False, "paragraph_missing"
    if quote is None or not str(quote).strip():
        return False, "quote_empty"
    if _fold(quote) not in _fold(paragraphs[str(paragraph_id)]):
        return False, "quote_not_verbatim"
    return True, "ok"


def check_evidence_dict(store, evidence):
    """核验一条证据字典；携带 page 字段直接判失败（禁止 PDF 页码声称）。"""
    if not isinstance(evidence, dict):
        return False, "evidence_not_dict"
    if "page" in evidence or "pages" in evidence or "pdf_page" in evidence:
        return False, "page_claim_forbidden"
    return check_quote(
        store,
        evidence.get("source_id"),
        evidence.get("paragraph_id"),
        evidence.get("quote"),
    )


def verify_mentions(store, mentions):
    """批量核验提及记录，返回 (valid_map, report)。"""
    valid, report = {}, {"verified": [], "rejected": []}
    for m in mentions:
        mid = m.get("mention_id", "<unknown>")
        ok, reason = check_quote(
            store, m.get("source_id"), m.get("paragraph_id"), m.get("quote"))
        if ok:
            valid[mid] = m
            report["verified"].append({"mention_id": mid})
        else:
            report["rejected"].append({"mention_id": mid, "reason": reason})
    return valid, report
