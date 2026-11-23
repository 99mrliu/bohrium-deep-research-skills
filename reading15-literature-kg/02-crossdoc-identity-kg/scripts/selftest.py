# -*- coding: utf-8 -*-
"""自检（仅标准库）：正向端到端 + 负向守门测试。

覆盖：
P1 合成示例端到端：>=8 节点、>=8 边、MERGE/KEEP_DISTINCT/UNDECIDED 各至少 1、>=3 条实际执行查询；
N1 精确别名相同但无属性证据 -> 不得合并（UNDECIDED）；
N2 数值冲突（同名同单位不同值）-> KEEP_DISTINCT 且记录 blocking_evidence；
N3 证据不足 -> UNDECIDED；
N4 伪造引文（非逐字）-> 核验失败并被图谱剔除；
N5 不同 DOI/来源本身不是阻断项（定义性属性一致即 MERGE）；
N6 携带 page 字段的证据被判失败（禁止 PDF 页码声称）；
N7 通用术语缺强身份键 -> 至多 UNDECIDED。
运行：python3 scripts/selftest.py；全部通过退出码 0。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import load_json
from identity_gate import adjudicate
from build_graph import build_graph
from quote_verify import check_evidence_dict, check_quote
from query_graph import run_queries

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "examples", "minimal", "input")

_FAILURES = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print("[%s] %s%s" % (status, name, (" — " + detail) if detail else ""))
    if not cond:
        _FAILURES.append(name)


def _m(mid, src, surface, aliases=None, props=None, numbers=None,
       pid="p-0001", quote=None):
    return {"mention_id": mid, "source_id": src, "paragraph_id": pid,
            "surface": surface, "entity_type": "material",
            "aliases": aliases or [], "quote": quote or "quote-" + mid,
            "properties": props or {}, "numbers": numbers or []}


def test_negative_alias_only():
    ms = [_m("N1-a", "P1", "perovskite"), _m("N1-b", "P2", "Perovskite")]
    dec, clusters = adjudicate(ms)
    check("N1 精确别名相同不合并",
          len(dec) == 1 and dec[0]["decision"] == "UNDECIDED"
          and dec[0]["merge_basis"] == [],
          str(dec[0]["decision"]) if dec else "无裁决")
    check("N1 簇保持分离", len([c for c in clusters if c["merged"]]) == 0)


def test_negative_numeric_conflict():
    ms = [_m("N2-a", "P1", "random forest model",
             props={"architecture": "random forest"},
             numbers=[{"name": "R2", "value": 0.81, "unit": "1"}]),
          _m("N2-b", "P2", "random forest model",
             props={"architecture": "random forest"},
             numbers=[{"name": "R2", "value": 0.74, "unit": "1"}])]
    dec, _ = adjudicate(ms)
    kinds = [b["kind"] for d in dec for b in d["blocking_evidence"]]
    check("N2 数值冲突阻断合并",
          dec[0]["decision"] == "KEEP_DISTINCT" and "numeric_conflict" in kinds,
          str(kinds))


def test_negative_insufficient():
    ms = [_m("N3-a", "P1", "XRD", aliases=["X-ray diffraction"]),
          _m("N3-b", "P2", "x-ray diffraction", aliases=["XRD"])]
    dec, _ = adjudicate(ms)
    check("N3 证据不足 UNDECIDED", dec[0]["decision"] == "UNDECIDED")


def test_negative_fabricated_quote():
    store = {"P1": {"p-0001": "We measured the sample at room temperature."}}
    ok, reason = check_quote(store, "P1", "p-0001", "measured the sample at room")
    check("N4a 真实逐字引文通过", ok, reason)
    ok2, reason2 = check_quote(store, "P1", "p-0001",
                               "we annealed at 900 C overnight")
    check("N4b 伪造引文被拒", (not ok2) and reason2 == "quote_not_verbatim",
          reason2)
    ms = [_m("N4-a", "P1", "sample A", quote="we annealed at 900 C overnight")]
    dec, clusters = adjudicate(ms)
    graph, report, _ = build_graph(ms, [], dec, clusters, store)
    check("N4c 伪造引文节点被剔除",
          len(graph["nodes"]) == 0 and len(report["rejected"]) == 1)


def test_doi_not_blocker():
    ms = [_m("N5-a", "DOI:10.1/A", "LLZO",
             props={"chemical_formula": "Li7La3Zr2O12"}),
          _m("N5-b", "DOI:10.2/B", "llzo",
             props={"chemical_formula": "li7la3zr2o12"})]
    dec, clusters = adjudicate(ms)
    check("N5 不同 DOI 不是阻断项（定义性属性一致即合并）",
          dec[0]["decision"] == "MERGE"
          and any(c["merged"] for c in clusters))


def test_page_claim_forbidden():
    store = {"P1": {"p-0001": "some text here"}}
    ok, reason = check_evidence_dict(store, {
        "source_id": "P1", "paragraph_id": "p-0001",
        "quote": "some text", "page": 3})
    check("N6 page 字段判失败", (not ok) and reason == "page_claim_forbidden",
          reason)


def test_generic_term_cap():
    ms = [_m("N7-a", "P1", "sintering",
             props={"principle": "thermal densification"}),
          _m("N7-b", "P2", "sintering",
             props={"principle": "thermal densification"})]
    dec, _ = adjudicate(ms, generic_terms={"sintering"})
    check("N7 通用术语缺强身份键至多 UNDECIDED",
          dec[0]["decision"] == "UNDECIDED", dec[0]["decision"])


def test_example_end_to_end():
    papers = load_json(os.path.join(BASE, "papers.json"), {})
    mdoc = load_json(os.path.join(BASE, "mentions.json"), {})
    rdoc = load_json(os.path.join(BASE, "relations.json"), {})
    qdoc = load_json(os.path.join(BASE, "queries.json"), {})
    store = {sid: {str(k): v for k, v in (p.get("paragraphs") or {}).items()}
             for sid, p in (papers.get("papers") or {}).items()}
    mentions = mdoc.get("mentions") or []
    check("P1a 示例提及 >=10 条", len(mentions) >= 10, str(len(mentions)))
    generic = set(mdoc.get("meta", {}).get("generic_terms") or [])
    dec, clusters = adjudicate(mentions, generic_terms=generic)
    graph, report, conflicts = build_graph(
        mentions, rdoc.get("relations") or [], dec, clusters, store)
    check("P1b 终图 >=8 节点", len(graph["nodes"]) >= 8,
          str(len(graph["nodes"])))
    check("P1c 终图 >=8 边", len(graph["edges"]) >= 8,
          str(len(graph["edges"])))
    kinds = {d["decision"] for d in dec}
    check("P1d 三种裁决齐备",
          {"MERGE", "KEEP_DISTINCT", "UNDECIDED"} <= kinds, str(kinds))
    check("P1e 全部引文核验通过",
          not report["rejected"] and not report["rejected_edges"],
          str(report["rejected"]))
    results = run_queries(graph, qdoc.get("queries") or [])
    check("P1f >=3 条实际执行查询且成功",
          len(results) >= 3
          and sum(1 for q in results if q.get("status") == "ok") >= 3,
          str([q.get("status") for q in results]))
    check("P1g 跨篇测量冲突被记录且分别保留", len(conflicts) >= 1,
          str(len(conflicts)))
    q3 = next((q for q in results if q["spec"].get("type") == "path"), None)
    check("P1h 跨篇路径存在（合并带来连通，数据集仍分离）",
          q3 is not None and q3.get("status") == "ok"
          and q3["result"]["length"] >= 2,
          str(q3.get("status")) if q3 else "无路径查询")


def main():
    test_example_end_to_end()
    test_negative_alias_only()
    test_negative_numeric_conflict()
    test_negative_insufficient()
    test_negative_fabricated_quote()
    test_doi_not_blocker()
    test_page_claim_forbidden()
    test_generic_term_cap()
    print("")
    if _FAILURES:
        print("自检失败 %d 项: %s" % (len(_FAILURES), ", ".join(_FAILURES)))
        return 1
    print("自检全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
