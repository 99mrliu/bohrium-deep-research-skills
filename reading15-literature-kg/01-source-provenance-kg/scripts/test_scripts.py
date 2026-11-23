#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_scripts.py — 负例为主的自检测试（unittest，仅标准库）。

运行（bundle 根目录或任意目录）：
    python3 scripts/test_scripts.py

覆盖的关键负例：
  - 引文不匹配（quote mismatch）
  - 错误来源（wrong source / 段落张冠李戴）
  - 重复 paragraph id（地址歧义）
  - 同名节点对缺少显式 nonmerge（no-merge 违规）
  - 数值不同的 merge（拒绝合并）
  - 边引用 merge member（合并未生效）
  - conflict 消解（resolution != preserved）
  - 根元数据归属错误（DOI/title 张冠李戴）
正例：
  - 自带最小示例零 error 通过、覆盖度 100%
  - 查询执行器确定性（两次运行逐字节一致）与查询语义
  - 装配器动态镜像合同键、未知键置 null 不省略
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import kgcommon as k  # noqa: E402
import normalize_input  # noqa: E402
import verify_evidence  # noqa: E402
import build_graph  # noqa: E402
import query_graph  # noqa: E402
import assemble_result  # noqa: E402

BUNDLE_ROOT = SCRIPTS_DIR.parent
EXAMPLE = BUNDLE_ROOT / "examples" / "minimal"


def make_corpus(sources):
    """构造内存中的 normalized corpus。"""
    return {
        "format": k.FORMAT_NORMALIZED_CORPUS,
        "input_dir": "<memory>",
        "sources": sources,
        "duplicate_paragraph_ids": {},
        "skipped": [],
        "warnings": [],
    }


def base_source(sid="P1", role="primary"):
    return {
        "source_id": sid,
        "role": role,
        "doi": f"10.0000/{sid.lower()}",
        "title": f"SYNTHETIC {sid} title",
        "authors": ["X. Test"],
        "path": f"{sid.lower()}-material.json",
        "paragraph_count": 2,
        "paragraphs": [
            {"id": f"{sid}.p1", "section": "Intro",
             "text": f"This is synthetic paragraph one of {sid}. It mentions alpha widget."},
            {"id": f"{sid}.p2", "section": "Data",
             "text": f"The alpha widget of {sid} has mass 10 g."},
        ],
    }


def base_extraction():
    return {
        "case_id": "TEST",
        "primary_paper": "n_paper",
        "nodes": [
            {"node_id": "n_paper", "kind": "paper", "label": "paper P1",
             "canonical_key": "paper:10.0000/p1",
             "attributes": {"doi": "10.0000/p1", "title": "SYNTHETIC P1 title",
                            "authors": ["X. Test"]},
             "evidence": [{"source_id": "P1", "paragraph_id": "P1.p1",
                           "quote": "synthetic paragraph one"}]},
            {"node_id": "n_widget", "kind": "sample", "label": "alpha widget",
             "canonical_key": "sample:alpha-widget",
             "evidence": [{"source_id": "P1", "paragraph_id": "P1.p2",
                           "quote": "mass 10 g"}]},
        ],
        "edges": [
            {"edge_id": "e1", "type": "describes",
             "subject": "n_paper", "object": "n_widget",
             "evidence": [{"source_id": "P1", "paragraph_id": "P1.p2",
                           "quote": "alpha widget of P1 has mass 10 g"}]},
        ],
        "merges": [], "nonmerges": [], "conflicts": [], "unreported": [],
    }


class VerifierNegativeTests(unittest.TestCase):
    def setUp(self):
        self.corpus = make_corpus([base_source()])
        self.ext = base_extraction()

    def errors(self, extraction, corpus=None):
        rep = verify_evidence.verify(extraction, corpus or self.corpus)
        return rep

    def test_positive_baseline(self):
        rep = self.errors(self.ext)
        self.assertTrue(rep["ok"], rep["errors"])

    def test_quote_mismatch(self):
        ext = copy.deepcopy(self.ext)
        ext["nodes"][1]["evidence"][0]["quote"] = "mass 999 g"
        rep = self.errors(ext)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("精确子串" in e for e in rep["errors"]), rep["errors"])

    def test_wrong_source(self):
        ext = copy.deepcopy(self.ext)
        ext["nodes"][1]["evidence"][0]["source_id"] = "NOPE"
        rep = self.errors(ext)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("不在语料中" in e for e in rep["errors"]), rep["errors"])

    def test_paragraph_from_wrong_source(self):
        """段落地址真实存在但属于另一来源：张冠李戴必须报错。"""
        corpus = make_corpus([base_source("P1", "primary"), base_source("S1", "secondary")])
        ext = copy.deepcopy(self.ext)
        ext["nodes"][1]["evidence"][0] = {"source_id": "P1", "paragraph_id": "S1.p2",
                                          "quote": "mass 10 g"}
        rep = self.errors(ext, corpus)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("不存在" in e for e in rep["errors"]), rep["errors"])

    def test_duplicate_paragraph_id_ambiguous(self):
        corpus = make_corpus([base_source()])
        corpus["duplicate_paragraph_ids"] = {"P1": ["P1.p2"]}
        rep = self.errors(self.ext, corpus)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("歧义" in e for e in rep["errors"]), rep["errors"])

    def test_missing_edge_evidence(self):
        ext = copy.deepcopy(self.ext)
        ext["edges"][0]["evidence"] = []
        rep = self.errors(ext)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("缺少证据" in e for e in rep["errors"]), rep["errors"])

    def test_same_label_without_nonmerge(self):
        ext = copy.deepcopy(self.ext)
        ext["nodes"].append({"node_id": "n_widget2", "kind": "sample",
                             "label": "Alpha  Widget",
                             "canonical_key": "sample:alpha-widget-other",
                             "evidence": [{"source_id": "P1", "paragraph_id": "P1.p2",
                                           "quote": "mass 10 g"}]})
        rep = self.errors(ext)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("同名节点对" in e for e in rep["errors"]), rep["errors"])
        # 加入显式 nonmerge 后应通过
        ext["nonmerges"].append({"nonmerge_id": "nmX",
                                 "members": ["n_widget", "n_widget2"],
                                 "reason": "同名通用术语但物理样品不同",
                                 "evidence": [{"source_id": "P1", "paragraph_id": "P1.p2",
                                               "quote": "mass 10 g"}]})
        rep2 = self.errors(ext)
        self.assertTrue(rep2["ok"], rep2["errors"])

    def test_metric_merge_value_mismatch_rejected(self):
        corpus = make_corpus([base_source("P1", "primary"), base_source("S1", "secondary")])
        ext = base_extraction()
        ext["nodes"] += [
            {"node_id": "n_m_p1", "kind": "metric", "label": "porosity 42",
             "canonical_key": "metric:porosity",
             "attributes": {"value": "42"},
             "evidence": [{"source_id": "P1", "paragraph_id": "P1.p2", "quote": "mass 10 g"}]},
            {"node_id": "n_m_s1", "kind": "metric", "label": "porosity 38",
             "canonical_key": "metric:porosity",
             "attributes": {"value": "38"},
             "evidence": [{"source_id": "S1", "paragraph_id": "S1.p2", "quote": "mass 10 g"}]},
            {"node_id": "n_m", "kind": "metric", "label": "porosity merged",
             "canonical_key": "metric:porosity",
             "evidence": [{"source_id": "P1", "paragraph_id": "P1.p2", "quote": "mass 10 g"},
                          {"source_id": "S1", "paragraph_id": "S1.p2", "quote": "mass 10 g"}]},
        ]
        ext["merges"] = [{"merge_id": "mX", "node": "n_m",
                          "members": ["n_m_p1", "n_m_s1"],
                          "justification": "test",
                          "evidence": [{"source_id": "P1", "paragraph_id": "P1.p2",
                                        "quote": "mass 10 g"}]}]
        rep = self.errors(ext, corpus)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("数值不一致" in e for e in rep["errors"]), rep["errors"])

    def test_edge_referencing_merge_member(self):
        corpus = make_corpus([base_source("P1", "primary"), base_source("S1", "secondary")])
        ext = base_extraction()
        ext["nodes"] += [
            {"node_id": "n_mt_p1", "kind": "method", "label": "freeze-casting P1",
             "canonical_key": "method:fc",
             "evidence": [{"source_id": "P1", "paragraph_id": "P1.p1", "quote": "alpha widget"}]},
            {"node_id": "n_mt_s1", "kind": "method", "label": "freeze-casting S1",
             "canonical_key": "method:fc",
             "evidence": [{"source_id": "S1", "paragraph_id": "S1.p1", "quote": "alpha widget"}]},
            {"node_id": "n_mt", "kind": "method", "label": "freeze-casting",
             "canonical_key": "method:fc",
             "evidence": [{"source_id": "P1", "paragraph_id": "P1.p1", "quote": "alpha widget"},
                          {"source_id": "S1", "paragraph_id": "S1.p1", "quote": "alpha widget"}]},
        ]
        ext["merges"] = [{"merge_id": "mX", "node": "n_mt",
                          "members": ["n_mt_p1", "n_mt_s1"],
                          "justification": "同一通用方法概念",
                          "evidence": [{"source_id": "P1", "paragraph_id": "P1.p1",
                                        "quote": "alpha widget"}]}]
        # 错误：边引用了 member 而非合并节点
        ext["edges"].append({"edge_id": "e_bad", "type": "produced_by",
                             "subject": "n_widget", "object": "n_mt_p1",
                             "evidence": [{"source_id": "P1", "paragraph_id": "P1.p1",
                                           "quote": "alpha widget"}]})
        rep = self.errors(ext, corpus)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("merge member" in e for e in rep["errors"]), rep["errors"])

    def test_conflict_resolution_must_be_preserved(self):
        ext = copy.deepcopy(self.ext)
        ext["conflicts"] = [{"conflict_id": "cX", "topic": "t",
                             "claims": [{"node": "n_widget"}],
                             "resolution": "averaged"}]
        rep = self.errors(ext)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("preserved" in e for e in rep["errors"]), rep["errors"])

    def test_root_metadata_misattribution(self):
        corpus = make_corpus([base_source("P1", "primary"), base_source("S1", "secondary")])
        ext = copy.deepcopy(self.ext)
        # 把 P1 的 DOI 安到 S1 来源的 paper 节点上
        ext["nodes"][0]["evidence"][0] = {"source_id": "S1", "paragraph_id": "S1.p1",
                                          "quote": "synthetic paragraph one"}
        rep = self.errors(ext, corpus)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("归属错误" in e for e in rep["errors"]), rep["errors"])
        self.assertTrue(any("primary" in e for e in rep["errors"]), rep["errors"])


class NormalizerTests(unittest.TestCase):
    def _write(self, d, name, obj):
        p = Path(d) / name
        if isinstance(obj, str):
            p.write_text(obj, encoding="utf-8")
        else:
            p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def test_map_form_material_json(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, "material.json",
                        {"P1": {"role": "primary", "path": "primary-material.json"}})
            self._write(d, "primary-material.json", {
                "jats": {"article-meta": {"doi": "10.0/x", "title": "T", "authors": []},
                         "body": {"paragraphs": [{"id": "P1.p1", "text": "hello world"}]}}})
            corpus = normalize_input.normalize(d)
            self.assertEqual(len(corpus["sources"]), 1)
            self.assertEqual(corpus["sources"][0]["source_id"], "P1")

    def test_missing_and_duplicate_paragraph_ids(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, "material.json",
                        [{"source_id": "P1", "role": "primary",
                          "path": "primary-material.json"}])
            self._write(d, "primary-material.json", {
                "jats": {"article-meta": {"doi": "10.0/x", "title": "T", "authors": []},
                         "body": {"paragraphs": [
                             {"text": "no id paragraph"},
                             {"id": "P1.p2", "text": "first copy"},
                             {"id": "P1.p2", "text": "second copy dropped"}]}}})
            corpus = normalize_input.normalize(d)
            paras = corpus["sources"][0]["paragraphs"]
            self.assertEqual([p["id"] for p in paras], ["P1.auto1", "P1.p2"])
            self.assertEqual(corpus["duplicate_paragraph_ids"], {"P1": ["P1.p2"]})
            self.assertEqual(paras[1]["text"], "first copy")
            self.assertTrue(any("自动编址" in w for w in corpus["warnings"]))

    def test_sidecar_xml_registered_not_parsed(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, "material.json",
                        [{"source_id": "P1", "role": "primary",
                          "path": "primary-material.json"}])
            self._write(d, "primary-material.json", {
                "jats": {"article-meta": {"doi": "10.0/x", "title": "T", "authors": []},
                         "body": {"paragraphs": [{"id": "P1.p1", "text": "x"}]}}})
            self._write(d, "secondary-publisher.xml", "<x/>")
            corpus = normalize_input.normalize(d)
            self.assertEqual(len(corpus["skipped"]), 1)
            self.assertEqual(corpus["skipped"][0]["path"], "secondary-publisher.xml")
            self.assertIn("sha256", corpus["skipped"][0])


class MinimalExampleEndToEndTests(unittest.TestCase):
    """直接对仓库内最小示例跑 verify/build/query，不依赖 run 脚本产物。"""

    @classmethod
    def setUpClass(cls):
        cls.corpus = normalize_input.normalize(str(EXAMPLE))
        cls.extraction = k.read_json(EXAMPLE / "candidate_extraction.json")
        cls.report = verify_evidence.verify(cls.extraction, cls.corpus)
        cls.graph = build_graph.build(cls.corpus, cls.extraction)

    def test_example_verifies_clean(self):
        self.assertTrue(self.report["ok"], self.report["errors"])
        cov = self.report["coverage"]
        self.assertEqual(cov["coverage_ratio"], 1.0, cov)

    def test_example_graph_size(self):
        s = self.graph["stats"]
        self.assertGreaterEqual(s["node_count"], 8)
        self.assertGreaterEqual(s["edge_count"], 8)
        self.assertEqual(s["merge_count"], 1)
        self.assertGreaterEqual(s["nonmerge_count"], 1)

    def test_queries_execute_and_are_deterministic(self):
        specs = query_graph._extract_batch(k.read_json(EXAMPLE / "case.json"))
        r1 = query_graph.run_batch(self.graph, specs)
        r2 = query_graph.run_batch(self.graph, copy.deepcopy(specs))
        self.assertEqual(json.dumps(r1, sort_keys=True, ensure_ascii=False),
                         json.dumps(r2, sort_keys=True, ensure_ascii=False),
                         "查询执行必须逐字节确定")
        self.assertGreaterEqual(len(r1["queries"]), 3)
        for q in r1["queries"]:
            self.assertTrue(q["ok"], q)
            self.assertIsNotNone(q["result"])

    def test_query_semantics(self):
        g = self.graph
        r = query_graph.run_query(g, {"type": "neighborhood", "node": "n_method_fc", "hops": 1})
        ids = {n["node_id"] for n in r["result"]["nodes"]}
        self.assertEqual(ids, {"n_method_fc", "n_sample_al_p1", "n_sample_al_s1"})
        # 邻域结果必须携带证据
        for n in r["result"]["nodes"]:
            self.assertTrue(n.get("evidence"))
        r = query_graph.run_query(g, {"type": "by-type", "kind": "sample", "source_id": "S1"})
        ids = {n["node_id"] for n in r["result"]["nodes"]}
        self.assertEqual(ids, {"n_sample_al_s1"})
        r = query_graph.run_query(g, {"type": "path", "from": "n_paper_p1", "to": "n_paper_s1"})
        ids = {n["node_id"] for n in r["result"]["nodes"]}
        self.assertEqual(ids, {"n_paper_p1", "n_sample_al_p1", "n_method_fc",
                               "n_sample_al_s1", "n_paper_s1"})
        self.assertEqual(r["result"]["path_length_edges"], 4)

    def test_assembler_mirrors_contract(self):
        with tempfile.TemporaryDirectory() as d:
            case = k.read_json(EXAMPLE / "case.json")
            queries = query_graph.run_batch(
                self.graph, query_graph._extract_batch(case))
            result, ledger, outputs = assemble_result.assemble(
                case, self.corpus, self.graph, self.report, queries, d,
                {"case": str(EXAMPLE / "case.json")})
            self.assertEqual(set(result.keys()), set(case["output_contract"].keys()),
                             "result.json 必须精确镜像合同键集合")
            self.assertEqual(result["case_id"], "SYNTHETIC-MINIMAL-001")
            self.assertIsNone(result["external_enrichment"],
                              "流程不产生的键必须置 null 而非省略")
            self.assertTrue(any("external_enrichment" in n for n in ledger["contract_notes"]))
            self.assertEqual(result["primary_paper"]["doi"], "10.0000/synthetic.p1.0001")
            self.assertEqual(len(result["queries"]), 4)
            svg = (Path(d) / "preview.svg").read_text(encoding="utf-8")
            self.assertIn("<svg", svg)
            self.assertIn("</svg>", svg)
            self.assertIn("n_method_fc", svg)
            self.assertIn("<line", svg)  # 边真实绘制
            dot = (Path(d) / "preview.dot").read_text(encoding="utf-8")
            self.assertIn("digraph", dot)


if __name__ == "__main__":
    unittest.main(verbosity=2)
